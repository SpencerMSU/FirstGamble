# Структура базы данных (PostgreSQL)

Актуальные таблицы под реализованный Python-бэкенд.

## `users`
- `id` (serial, PK)
- `tg_id` (bigint, unique, not null) — Telegram ID игрока.
- `username` (varchar(64), nullable)
- `first_name` (varchar(64), nullable)
- `last_name` (varchar(64), nullable)
- `points` (integer, not null, default 0) — текущий баланс очков.
- `created_at` (timestamptz, default now())

## `cooldowns`
- `id` (serial, PK)
- `user_id` (int, FK -> users.id, on delete cascade)
- `game_type` (enum: `dice | blackjack | slots`)
- `last_played_at` (timestamptz, not null) — время последней игры для вычисления КД.
- Уникальный индекс `(user_id, game_type)`

## `game_results`
- `id` (serial, PK)
- `user_id` (int, FK -> users.id, on delete cascade)
- `game_type` (enum: `dice | blackjack | slots`)
- `outcome` (enum: `win | lose | draw`)
- `payload` (jsonb) — детали игры (броски, карты, барабаны слотов).
- `created_at` (timestamptz, default now())

## `shop_items`
- `id` (serial, PK)
- `title` (varchar(128), unique)
- `description` (varchar(256))
- `price_points` (integer, not null)

## Логика кулдаунов и очков
- Кулдаун 5 минут на каждую игру считается на сервере: `remaining = max(0, 5*60 - (now() - last_played_at))`.
- Первый запуск игры у пользователя создаёт запись в `cooldowns` и не блокирует (0 секунд ожидания).
- Очки добавляются только за победу (`outcome = win`):
  - Кости — +1 очко
  - Блэкджек — +1 очко
  - Слоты — +1 очко
- Каждая игра сохраняет подробный `payload` для проверки антиабуза и отображения истории на клиенте.
