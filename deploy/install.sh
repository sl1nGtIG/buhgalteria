#!/usr/bin/env bash
# Установка «Бухгалтерии» на чистый сервер Ubuntu/Debian одной командой:
#   curl -fsSL https://raw.githubusercontent.com/sl1nGtIG/buhgalteria/main/deploy/install.sh | sudo bash
# Повторный запуск обновляет код и перезапускает сервер, настройки (.env) и данные сохраняются.
set -euo pipefail

REPO="${BUH_REPO:-https://github.com/sl1nGtIG/buhgalteria}"
BRANCH="${BUH_BRANCH:-main}"
DIR="${BUH_DIR:-/opt/buhgalteria}"

if [ "$(id -u)" != 0 ]; then
  echo "Запустите с sudo." >&2
  exit 1
fi

ask() { # ask "Вопрос" — читает ответ с терминала, даже если скрипт пришёл через curl | bash
  local answer=""
  if { : </dev/tty; } 2>/dev/null; then
    read -r -p "$1" answer </dev/tty || true
  fi
  printf '%s' "$answer"
}

echo "==> Устанавливаю Docker и git"
command -v git >/dev/null || { apt-get update -qq && apt-get install -y -qq git; }
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh

echo "==> Скачиваю код ($BRANCH)"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch --depth 1 origin "$BRANCH"
  git -C "$DIR" checkout -q -B "$BRANCH" FETCH_HEAD
else
  git clone --depth 1 --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

if [ ! -f .env ]; then
  echo
  echo "==> Настройка (Enter — пропустить)"
  domain=$(ask "Домен для сайта, например buh.example.ru (без домена — доступ по IP): ")
  claude_key=$(ask "Ключ Claude API для распознавания фото (sk-ant-...): ")
  tg_token=$(ask "Токен Telegram-бота от @BotFather: ")
  app_token=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 16 || true)
  if [ -n "$domain" ]; then bind="127.0.0.1:8000"; else bind="80"; fi
  umask 077
  cat > .env <<ENV
APP_TOKEN=$app_token
ANTHROPIC_API_KEY=$claude_key
TELEGRAM_BOT_TOKEN=$tg_token
TELEGRAM_ALLOWED_CHATS=
DOMAIN=$domain
APP_BIND=$bind
ENV
fi

domain=$(sed -n 's/^DOMAIN=//p' .env)
profile=()
[ -n "$domain" ] && profile=(--profile https)

echo "==> Собираю и запускаю (первый раз — несколько минут)"
docker compose "${profile[@]}" up -d --build

if [ -n "$domain" ]; then
  url="https://$domain"
else
  url="http://$(hostname -I | awk '{print $1}')"
fi
echo
echo "Готово! Сайт: $url"
echo "Код доступа: $(sed -n 's/^APP_TOKEN=//p' .env)"
echo "Тот же адрес и код введите в приложении на телефоне: Настройки."
echo "Настройки лежат в $DIR/.env — после правки: cd $DIR && docker compose ${profile[*]:+${profile[*]} }up -d"
