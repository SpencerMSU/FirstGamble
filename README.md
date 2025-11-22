# FirstGamble Telegram Mini App (Python backend)

Мини-приложение для Telegram WebApp с играми «Кости», «Блэкджек», «Слотики», рейтингом и магазином. Бэкенд написан на **Python + FastAPI + PostgreSQL** с проверкой `initData` от Telegram и серверными кулдаунами 5 минут для каждой игры. Бот стартует с инлайн-кнопками «Подтвердить/Отклонить» и открывает мини-приложение только после подтверждения.

## Что реализовано
- Эндпоинты FastAPI для всех игр, профиля, кулдаунов, магазина и рейтинга с серверной проверкой Telegram `initData`.
- Отдельный кулдаун 5 минут на каждую игру; первый запуск без задержки.
- Начисление очков за победы и сохранение результатов в БД, привязка к Telegram ID.
- Telegram-бот на `aiogram` со стартовым сообщением и инлайн-кнопками для запуска мини-приложения.
- Dockerfile и docker-compose для быстрого запуска Postgres + бэкенда.
- Документация с пошаговыми командами для VDS (Ubuntu 24, TimewebCloud) и схемой БД.
- **Фронтенд мини-приложения (React + Vite)**: главные кнопки, раздел «Лудка» с Костями, Блэкджеком, Слотами и рейтингом, адаптив под мобилку/ПК, авто тёмная/светлая тема, отображение кулдаунов и очков.

## Стек
- **Бэкенд**: FastAPI + SQLAlchemy (async) + aiogram.
- **База данных**: PostgreSQL 15 (по умолчанию можно запустить в Docker).
- **Деплой**: Docker Compose или systemd+venv. Фронтенд разворачивается на Vercel (нужно подключить отдельно).

## Быстрый старт (локально)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env  # пропишите реальные токены и строку подключения к БД

# Запустить Postgres (если нет) через docker-compose
docker compose up -d postgres

# Запустить API
uvicorn app.main:app --app-dir backend --reload

# Запустить бота (отдельный терминал)
python -m backend.bot
```

### Фронтенд (Vite + React)
```bash
cd frontend
npm install
VITE_API_BASE=http://localhost:8080 npm run dev   # или npm run build для prod
```
Переменная `VITE_API_BASE` обязательна (URL API). Сборка для деплоя лежит в `frontend/dist`.

## Основные маршруты API
- `POST /auth/telegram` — верификация `initData`, создание/обновление пользователя.
- `GET /profile` — профиль и очки (требует заголовок `X-Telegram-Init-Data`).
- `GET /cooldowns` — остаток КД по играм.
- `POST /game/dice` — сыграть в кости (до 5 кубиков).
- `POST /game/blackjack` — сыграть в блэкджек (одна колода, дилер тянет до 17, ничья в пользу дилера).
- `POST /game/slots` — слоты (выигрыш только 3 одинаковых символа).
- `GET /shop` — баланс и тестовые товары.
- `GET /leaderboard` — топ и позиция игрока.

Подробная инструкция по развёртыванию — в `docs/DEPLOYMENT.md`, схема таблиц — в `docs/SCHEMA.md`.
