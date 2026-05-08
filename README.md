# Журнал посетителей — интеграция с Jira Cloud

Веб-страница для отображения данных о посетителях. Данные берутся из Jira: один тикет = один визит.

## Архитектура

```
Jira Cloud  →  update_visitors.py  →  visitors.js  →  visitors.html
              (Python, по cron)        (JSON-данные)    (UI)
```

Браузер не может напрямую обращаться к Jira API из-за CORS, поэтому есть Python-скрипт-прослойка, который тянет данные и сохраняет их в файл `visitors.js`. HTML-страница загружает этот файл и отображает таблицу.

## Файлы

- `visitors.html` — веб-интерфейс с таблицей, поиском и фильтрами. Сам себя перезагружает раз в 5 минут.
- `update_visitors.py` — скрипт, тянущий данные из Jira REST API.
- `visitors.js` — сгенерированные данные (перезаписывается скриптом).
- `.env.example` — шаблон конфигурации.
- `requirements.txt` — Python-зависимости.
- `.gitignore` — исключает `.env` и служебные файлы из git.

## Настройка

### 1. Установка

```bash
pip install -r requirements.txt
```

### 2. Получение API-токена Jira

Зайдите на https://id.atlassian.com/manage-profile/security/api-tokens и создайте токен.

### 3. Конфигурация

Скопируйте `.env.example` в `.env` и заполните:

```
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=ваш-токен
JIRA_PROJECT_KEY=VISIT
FIELD_GUEST_NAME=customfield_10100
FIELD_VISIT_DATE=customfield_10101
FIELD_VISIT_TIME=customfield_10102
FIELD_HOST=customfield_10103
FIELD_PURPOSE=customfield_10104
FIELD_OFFICE=customfield_10105
REFRESH_INTERVAL_MIN=5
```

### Справочник офисов

Список офисов и распознаваемые названия настраиваются прямо в `update_visitors.py`:

```python
OFFICES = [
    {"id": "satpayev_almaty", "name": "Сатпаева, Алматы", "address": "ул. Сатпаева, Алматы"},
    {"id": "gagarin_almaty",  "name": "Гагарина, Алматы", "address": "ул. Гагарина, Алматы"},
]

OFFICE_ALIASES = {
    "satpayev_almaty": ["сатпаева, алматы", "satpayev almaty", "сатпаева", ...],
    "gagarin_almaty":  ["гагарина, алматы", "gagarin almaty", "гагарина", ...],
}
```

Чтобы добавить новый офис: дописать запись в `OFFICES` и набор алиасов в `OFFICE_ALIASES`. Скрипт автоматически сопоставит значение из Jira (регистронезависимо) с нужным офисом. Если значение из Jira не распознано — посетитель попадёт в категорию «не определён» и будет виден только во вкладке «Все офисы». В UI вкладки переключаются между офисами, плюс работают фильтр по цели визита и поиск.

### 4. Узнать ID custom-полей

Открыть в браузере (зайти под своим аккаунтом):

```
https://yourcompany.atlassian.net/rest/api/3/field
```

Найти нужные поля по имени и взять их `id` (например, `customfield_10101`).

## Запуск

### Однократно

```bash
python update_visitors.py
```

Скрипт сделает запрос к Jira, обновит `visitors.js` и завершится.

### В режиме автообновления

Установите в `.env` `REFRESH_INTERVAL_MIN=5` и запустите:

```bash
python update_visitors.py
```

Скрипт будет работать в фоне и обновлять данные каждые 5 минут. HTML-страница тоже сама перезагружается каждые 5 минут.

### Через cron (Linux/Mac)

```bash
crontab -e
```

Добавить строку (обновлять каждые 5 минут):

```
*/5 * * * * cd /path/to/project && /usr/bin/python3 update_visitors.py
```

В `.env` оставьте `REFRESH_INTERVAL_MIN=0`.

## Открытие интерфейса

Чтобы браузер мог загрузить `visitors.js`, проще всего запустить локальный HTTP-сервер в папке проекта:

```bash
python -m http.server 8000
```

Затем открыть http://localhost:8000/visitors.html

(Прямое открытие `visitors.html` двойным кликом тоже обычно работает — данные подгружаются как `<script src="visitors.js">`, а не через fetch.)

## Маппинг полей Jira → таблица

| Поле в таблице  | Источник в Jira                        |
|-----------------|----------------------------------------|
| Имя гостя       | `FIELD_GUEST_NAME` (или `summary`)     |
| Дата прихода    | `FIELD_VISIT_DATE` (или `created`)     |
| Время прихода   | `FIELD_VISIT_TIME` (или `created`)     |
| Кто встречает   | `FIELD_HOST` (или `assignee`)          |
| Цель визита     | `FIELD_PURPOSE` (или `issuetype`)      |
| Офис            | `FIELD_OFFICE` (нормализуется по справочнику) |

## Публикация в GitHub

### 1. Перенести файлы в постоянную папку

Скопируйте все файлы проекта в любую папку у себя на компьютере, например `~/projects/visitors-board`.

### 2. Создать репозиторий на github.com

1. Откройте https://github.com/new
2. Repository name: `visitors-board` (или своё название)
3. Public
4. **НЕ** ставьте галочки на «Add a README», «Add .gitignore», «Choose a license» — у нас уже всё есть
5. Нажмите **Create repository**

GitHub покажет страницу с командами — нужны те, что в разделе «…or push an existing repository from the command line».

### 3. Инициализировать git и запушить

В терминале (macOS / Linux):

```bash
cd ~/projects/visitors-board

git init -b main
git add .
git commit -m "Initial commit: журнал посетителей с интеграцией Jira"

# Замените URL на ссылку из шага 2 (вкладка HTTPS)
git remote add origin https://github.com/<ваш-username>/visitors-board.git

git push -u origin main
```

При первом push GitHub попросит авторизоваться:

- **macOS**: открывается окно «Sign in with browser» → войдите через GitHub в браузере, дальше git запомнит токен в Keychain.
- **Linux/Windows**: вместо пароля используйте Personal Access Token (Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token, scope `repo`). Сохраните токен — он показывается один раз.

### 4. Проверка

Откройте `https://github.com/<ваш-username>/visitors-board` — должны быть видны все файлы. Файла `.env` там быть не должно (он в `.gitignore`).

### 5. Дальнейшие изменения

```bash
git add .
git commit -m "что изменили"
git push
```

### Важно про секреты

Файл `.env` с реальным `JIRA_API_TOKEN` **никогда** не должен попадать в git — он в `.gitignore`. Если случайно закоммитили токен — отзовите его в https://id.atlassian.com/manage-profile/security/api-tokens и создайте новый.

Цель визита нормализуется: значения `Встреча/Meeting` → `meeting`, `Собеседование/Interview` → `interview`, `Доставка/Delivery` → `delivery`, остальное → `other`. Маппинг настраивается в `PURPOSE_MAP` внутри `update_visitors.py`.
