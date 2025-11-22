# API шпаргалка (FastAPI)

## Авторизация через Telegram WebApp
1. На клиенте получите `initData` из `Telegram.WebApp.initData`.
2. Передавайте его в заголовке `X-Telegram-Init-Data` для всех защищённых запросов.
3. На сервере подпись проверяется через HMAC согласно документации Telegram (секрет = SHA256 от `BOT_TOKEN`).

## Базовые проверки
```bash
# Проверка здоровья
curl http://localhost:8080/health

# Профиль (нужно подставить initData)
curl -H "X-Telegram-Init-Data: <initData>" http://localhost:8080/profile
```

## Игры и кулдауны
```bash
# Кулдауны по всем играм
curl -H "X-Telegram-Init-Data: <initData>" http://localhost:8080/cooldowns

# Кости (dice_count 1..5)
curl -X POST -H "Content-Type: application/json" \
  -H "X-Telegram-Init-Data: <initData>" \
  -d '{"dice_count":3}' \
  http://localhost:8080/game/dice

# Блэкджек (один запрос — вся партия)
curl -X POST -H "X-Telegram-Init-Data: <initData>" http://localhost:8080/game/blackjack

# Слоты
curl -X POST -H "X-Telegram-Init-Data: <initData>" http://localhost:8080/game/slots
```
Если кулдаун ещё идёт, сервер вернёт `429` и JSON вида `{"message":"Кулдаун ещё не закончился","remaining_seconds":123}`.

## Магазин и рейтинг
```bash
# Магазин (баланс + тестовые товары)
curl -H "X-Telegram-Init-Data: <initData>" http://localhost:8080/shop

# Рейтинг (топ-20 + ваша позиция)
curl -H "X-Telegram-Init-Data: <initData>" http://localhost:8080/leaderboard
```

## Бот (aiogram)
Запуск локально:
```bash
BOT_TOKEN=... FRONTEND_URL=https://firstgamble.ru \
python -m backend.bot
```
Бот отправляет стартовое сообщение с двумя инлайн-кнопками: «✅ Подтвердить» открывает WebApp по `FRONTEND_URL`, «❌ Отклонить» показывает алерт и не запускает мини-приложение.
