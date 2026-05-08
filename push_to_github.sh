#!/bin/bash
# Скрипт для первичной публикации проекта в GitHub репозиторий
# https://github.com/olzhaskassymkanov-ctrl/workwork
#
# Запуск из папки с файлами проекта:
#   bash push_to_github.sh

set -e

REMOTE_URL="https://github.com/olzhaskassymkanov-ctrl/workwork.git"

echo "==> Проверяем git"
git --version

echo "==> Инициализируем репозиторий (если ещё не было)"
if [ ! -d ".git" ]; then
  git init -b main
fi

echo "==> Добавляем файлы"
git add .

echo "==> Делаем коммит"
git commit -m "Initial commit: журнал посетителей с интеграцией Jira" || echo "(нечего коммитить)"

echo "==> Привязываем remote $REMOTE_URL"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

echo "==> Пушим в main"
git push -u origin main

echo ""
echo "✅ Готово! Открой: https://github.com/olzhaskassymkanov-ctrl/workwork"
