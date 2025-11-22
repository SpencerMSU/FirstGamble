Ниже — детальный рецепт для VDS (Ubuntu 24, TimewebCloud) с доменом `firstgamble.ru`. Все команды можно копировать по шагам.

## 1) Подготовка сервера
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl ufw fail2ban python3.11 python3.11-venv docker.io docker-compose-plugin
```

Разрешаем SSH и HTTP/HTTPS в UFW:
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

## 2) Клонирование репозитория
```bash
mkdir -p ~/apps && cd ~/apps
git clone https://github.com/SpencerMSU/FirstGamble.git
cd FirstGamble
```

## 3) Настройка окружения бэкенда (Python + venv)
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
```
Заполните `backend/.env` реальными значениями (BOT_TOKEN, DATABASE_URL, FRONTEND_URL).

Если хотите использовать системный Postgres вместо Docker, установите его:
```bash
sudo apt install -y postgresql postgresql-contrib
sudo -u postgres psql -c "CREATE USER firstgamble WITH PASSWORD 'changeme';"
sudo -u postgres psql -c "CREATE DATABASE firstgamble OWNER firstgamble;"
```
И в `backend/.env` пропишите:
```
DATABASE_URL=postgresql+asyncpg://firstgamble:changeme@localhost:5432/firstgamble
```

## 4) Запуск через Docker Compose (Postgres + API)
Если удобнее всё поднять в контейнерах, используйте комплект из репозитория:
```bash
docker compose up -d postgres  # только база
# первый запуск API создаст таблицы и товары
BOT_TOKEN=... FRONTEND_URL=https://firstgamble.ru DATABASE_URL=postgresql+asyncpg://firstgamble:changeme@postgres:5432/firstgamble docker compose up -d backend
```
Проверка:
```bash
curl http://localhost:8080/health
```

## 5) Запуск без Docker (systemd + venv)
Создайте unit-файл `/etc/systemd/system/firstgamble.service`:
```
[Unit]
Description=FirstGamble FastAPI
After=network.target

[Service]
User=%i
WorkingDirectory=/home/%i/apps/FirstGamble
EnvironmentFile=/home/%i/apps/FirstGamble/backend/.env
ExecStart=/home/%i/apps/FirstGamble/.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
Замените `%i` на своего пользователя, затем:
```bash
sudo systemctl daemon-reload
sudo systemctl enable firstgamble.service
sudo systemctl start firstgamble.service
sudo systemctl status firstgamble.service
```

## 6) Запуск Telegram-бота (aiogram)
Создайте второй unit `/etc/systemd/system/firstgamble-bot.service`:
```
[Unit]
Description=FirstGamble Telegram Bot
After=network.target

[Service]
User=%i
WorkingDirectory=/home/%i/apps/FirstGamble
EnvironmentFile=/home/%i/apps/FirstGamble/backend/.env
ExecStart=/home/%i/apps/FirstGamble/.venv/bin/python -m backend.bot
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
И активируйте:
```bash
sudo systemctl daemon-reload
sudo systemctl enable firstgamble-bot.service
sudo systemctl start firstgamble-bot.service
sudo systemctl status firstgamble-bot.service
```

## 7) Nginx + HTTPS
```bash
sudo apt install -y nginx
sudo tee /etc/nginx/sites-available/firstgamble <<'NGINX'
server {
    server_name firstgamble.ru;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX
sudo ln -s /etc/nginx/sites-available/firstgamble /etc/nginx/sites-enabled/firstgamble
sudo nginx -t
sudo systemctl restart nginx
```
Сертификат Let's Encrypt:
```bash
sudo snap install core; sudo snap refresh core
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot
sudo certbot --nginx -d firstgamble.ru
```

## 8) Обновление кода
```bash
cd ~/apps/FirstGamble
git pull
source .venv/bin/activate
pip install -r backend/requirements.txt
sudo systemctl restart firstgamble.service firstgamble-bot.service
```
Если используете Docker:
```bash
docker compose pull
BOT_TOKEN=... FRONTEND_URL=https://firstgamble.ru DATABASE_URL=postgresql+asyncpg://firstgamble:changeme@postgres:5432/firstgamble docker compose up -d --build
```

## 9) Проверка и вспомогательные команды
```bash
curl http://localhost:8080/health                     # API живой
curl -H "X-Telegram-Init-Data: <initData>" http://localhost:8080/profile   # проверка авторизации
journalctl -u firstgamble.service -f                   # логи API
journalctl -u firstgamble-bot.service -f              # логи бота
```

## 10) Что ещё подготовить
- Подключите фронтенд к Vercel (корень `frontend/`, команда `npm run build`) и задайте `VITE_API_BASE=https://firstgamble.ru`. Подробный чек-лист в `docs/FRONTEND.md`.
- Настройте DNS A-запись домена на IP VDS.
- Держите `Tokens.txt` и `backend/.env` только локально/на сервере, не коммитьте секреты.
