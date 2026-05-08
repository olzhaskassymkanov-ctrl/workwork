"""
Скрипт обновления данных о посетителях из Jira Cloud.

Подключается к Jira REST API, забирает задачи из указанного проекта
и сохраняет их в visitors.js, который читает HTML-страница.

Запуск:
    python update_visitors.py

Для автообновления каждые N минут — настройте через cron / Task Scheduler
или используйте режим демона (см. ниже).
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# ============================================================
# Конфигурация — все значения берутся из .env файла
# ============================================================
load_dotenv()

JIRA_URL = os.getenv("JIRA_URL", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "")
JIRA_JQL = os.getenv("JIRA_JQL", f"project = {JIRA_PROJECT_KEY} ORDER BY created DESC")

# ID custom-полей в Jira (вида customfield_10XXX)
FIELD_GUEST_NAME = os.getenv("FIELD_GUEST_NAME", "")     # имя гостя
FIELD_VISIT_DATE = os.getenv("FIELD_VISIT_DATE", "")     # дата прихода
FIELD_VISIT_TIME = os.getenv("FIELD_VISIT_TIME", "")     # время прихода
FIELD_HOST       = os.getenv("FIELD_HOST", "")           # кто встречает
FIELD_PURPOSE    = os.getenv("FIELD_PURPOSE", "")        # цель визита
FIELD_OFFICE     = os.getenv("FIELD_OFFICE", "")         # офис

OUTPUT_FILE = Path(__file__).parent / "visitors.js"

# Маппинг текстовых значений цели визита из Jira -> ключи для HTML
PURPOSE_MAP = {
    "встреча": "meeting",
    "meeting": "meeting",
    "собеседование": "interview",
    "interview": "interview",
    "доставка": "delivery",
    "delivery": "delivery",
}

# === Справочник офисов ===
# Каждый офис: id (используется в коде), name (отображается), address.
# Чтобы добавить новый офис, добавьте запись в OFFICES и алиасы в OFFICE_ALIASES.
OFFICES = [
    {"id": "satpayev_almaty", "name": "Сатпаева, Алматы", "address": "ул. Сатпаева, Алматы"},
    {"id": "gagarin_almaty",  "name": "Гагарина, Алматы", "address": "ул. Гагарина, Алматы"},
]

# Какие значения из Jira соответствуют какому офису.
# Сравнение регистронезависимое и без учёта пробелов по краям.
OFFICE_ALIASES = {
    "satpayev_almaty": [
        "сатпаева, алматы", "сатпаева алматы", "satpayev almaty", "satpayev, almaty",
        "сатпаева", "satpayev",
    ],
    "gagarin_almaty": [
        "гагарина, алматы", "гагарина алматы", "gagarin almaty", "gagarin, almaty",
        "гагарина", "gagarin",
    ],
}

# Интервал автообновления (минуты). 0 = выйти после одного запуска.
REFRESH_INTERVAL_MIN = int(os.getenv("REFRESH_INTERVAL_MIN", "0"))


# ============================================================
# Логика
# ============================================================
def check_config():
    missing = []
    for key in ("JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"):
        if not globals()[key]:
            missing.append(key)
    if missing:
        print(f"[!] Не заполнены обязательные переменные: {', '.join(missing)}")
        print("    Скопируйте .env.example в .env и заполните значения.")
        sys.exit(1)


def fetch_issues():
    """Тянет задачи из Jira через REST API."""
    url = f"{JIRA_URL}/rest/api/3/search"
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}

    fields_to_fetch = [
        "summary", "created", "assignee", "issuetype", "status",
        FIELD_GUEST_NAME, FIELD_VISIT_DATE, FIELD_VISIT_TIME,
        FIELD_HOST, FIELD_PURPOSE, FIELD_OFFICE,
    ]
    fields_to_fetch = [f for f in fields_to_fetch if f]

    all_issues = []
    start_at = 0
    page_size = 100

    while True:
        params = {
            "jql": JIRA_JQL,
            "fields": ",".join(fields_to_fetch),
            "startAt": start_at,
            "maxResults": page_size,
        }
        r = requests.get(url, headers=headers, auth=auth, params=params, timeout=30)
        if r.status_code != 200:
            print(f"[!] Ошибка Jira API ({r.status_code}): {r.text}")
            sys.exit(1)
        data = r.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        if start_at + len(issues) >= data.get("total", 0) or not issues:
            break
        start_at += page_size

    return all_issues


def get_field(fields: dict, field_id: str, default=""):
    """Безопасное чтение значения поля Jira (учитывает разные форматы)."""
    if not field_id:
        return default
    val = fields.get(field_id)
    if val is None:
        return default
    if isinstance(val, dict):
        # для select-полей формат {"value": "...", ...}
        return val.get("value") or val.get("name") or default
    if isinstance(val, list) and val:
        first = val[0]
        if isinstance(first, dict):
            return first.get("value") or first.get("name") or default
        return str(first)
    return str(val)


def normalize_purpose(raw: str) -> str:
    if not raw:
        return "other"
    key = raw.strip().lower()
    return PURPOSE_MAP.get(key, "other")


def normalize_office(raw: str) -> str:
    """Сопоставляет значение из Jira с id офиса из справочника."""
    if not raw:
        return ""
    key = raw.strip().lower()
    for office_id, aliases in OFFICE_ALIASES.items():
        if key in aliases:
            return office_id
    # точное совпадение по id (на случай, если в Jira хранится id напрямую)
    if any(o["id"] == key for o in OFFICES):
        return key
    return ""


def parse_date(raw: str, fallback_iso: str = "") -> str:
    """Возвращает дату YYYY-MM-DD."""
    if not raw and fallback_iso:
        raw = fallback_iso
    if not raw:
        return ""
    raw = raw.strip()
    # Уже в формате YYYY-MM-DD
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    # ISO с T (например 2026-05-09T12:30:00.000+0300)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return raw


def parse_time(raw: str, fallback_iso: str = "") -> str:
    """Возвращает время HH:MM."""
    if not raw and fallback_iso:
        try:
            return datetime.fromisoformat(fallback_iso.replace("Z", "+00:00")).strftime("%H:%M")
        except Exception:
            pass
    if not raw:
        return ""
    raw = raw.strip()
    if "T" in raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%H:%M")
        except Exception:
            pass
    if len(raw) >= 5 and raw[2] == ":":
        return raw[:5]
    return raw


def transform(issues: list) -> list:
    visitors = []
    for issue in issues:
        f = issue.get("fields", {})
        created = f.get("created", "")

        guest_name = get_field(f, FIELD_GUEST_NAME) or f.get("summary", "")
        visit_date = parse_date(get_field(f, FIELD_VISIT_DATE), fallback_iso=created)
        visit_time = parse_time(get_field(f, FIELD_VISIT_TIME), fallback_iso=created)

        host_raw = get_field(f, FIELD_HOST)
        if not host_raw:
            assignee = f.get("assignee") or {}
            host_raw = assignee.get("displayName", "") if isinstance(assignee, dict) else ""

        purpose_raw = get_field(f, FIELD_PURPOSE)
        if not purpose_raw:
            issuetype = f.get("issuetype") or {}
            purpose_raw = issuetype.get("name", "") if isinstance(issuetype, dict) else ""

        office_raw = get_field(f, FIELD_OFFICE)

        visitors.append({
            "key": issue.get("key", ""),
            "office": normalize_office(office_raw),
            "office_raw": office_raw,
            "name": guest_name,
            "date": visit_date,
            "time": visit_time,
            "host": host_raw,
            "purpose": normalize_purpose(purpose_raw),
            "purpose_raw": purpose_raw,
        })
    return visitors


def write_output(visitors: list):
    payload = {
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "offices": OFFICES,
        "visitors": visitors,
    }
    js = "// Auto-generated by update_visitors.py — do not edit manually.\n"
    js += "window.VISITORS_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    OUTPUT_FILE.write_text(js, encoding="utf-8")
    by_office = {}
    for v in visitors:
        by_office[v["office"] or "(не определён)"] = by_office.get(v["office"] or "(не определён)", 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in by_office.items())
    print(f"[OK] Записано {len(visitors)} посетителей в {OUTPUT_FILE.name}")
    if summary:
        print(f"     По офисам: {summary}")


def run_once():
    check_config()
    issues = fetch_issues()
    print(f"[+] Получено {len(issues)} задач из Jira")
    visitors = transform(issues)
    write_output(visitors)


def main():
    if REFRESH_INTERVAL_MIN > 0:
        print(f"[i] Режим автообновления: каждые {REFRESH_INTERVAL_MIN} мин (Ctrl+C — выход)")
        while True:
            try:
                run_once()
            except Exception as e:
                print(f"[!] Ошибка: {e}")
            time.sleep(REFRESH_INTERVAL_MIN * 60)
    else:
        run_once()


if __name__ == "__main__":
    main()
