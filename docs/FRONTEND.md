# Фронтенд мини-приложения (React + Vite)

Ниже — пошаговая инструкция: локальный запуск, сборка и выкладка на Vercel. Все команды можно копировать как есть.

## 1) Требования
- Node.js 18+ (Vercel использует 18/20).
- Настроенный бэкенд, доступный по HTTPS (например, `https://firstgamble.ru`).

## 2) Клонирование и установка зависимостей
```bash
cd ~/apps/FirstGamble/frontend
npm install
```
Создастся `node_modules` и `package-lock.json`. Они не коммитятся (уже в `.gitignore`).

## 3) Локальный запуск с реальным API
```bash
cd ~/apps/FirstGamble/frontend
VITE_API_BASE=http://localhost:8080 npm run dev
```
- Откройте `http://localhost:5173` в браузере.
- В Telegram-песочнице скопируйте `initData` и вставьте в поле на экране (если не заходите через Telegram).

## 4) Продакшн-сборка
```bash
cd ~/apps/FirstGamble/frontend
VITE_API_BASE=https://firstgamble.ru npm run build
```
Результат появится в `frontend/dist` — это статические файлы (HTML/CSS/JS), которые можно отдавать через Vercel или Nginx.

## 5) Вёрстка и UI
- Главные кнопки: «Лудка», «Цены», «RPG», «Магазин», «Розыгрыши».
- Внутри «Лудки» — вкладки «Кости», «Блэкджек», «Слотики», «Рейтинг».
- Адаптация под мобильные/ПК, авто-тема (Telegram theme / `prefers-color-scheme`).
- Показываем кулдауны по каждому режиму, баланс очков, победы/проигрыши.

## 6) Деплой на Vercel (root = `frontend`)
1. Установите Vercel CLI (один раз на сервер/локально):
   ```bash
   npm install -g vercel
   ```
2. Авторизуйтесь (пройдите браузерную ссылку):
   ```bash
   vercel login
   ```
3. Создайте проект, указав корень `frontend/` и сборку `npm run build`:
   ```bash
   cd ~/apps/FirstGamble/frontend
   vercel init   # если проект ещё не создан
   vercel link   # выбрать аккаунт/проект
   ```
4. Добавьте переменную окружения для API (обязательно HTTPS):
   ```bash
   vercel env add VITE_API_BASE
   # вставьте https://firstgamble.ru
   ```
5. Задеплойте:
   ```bash
   vercel --prod
   ```
6. Сохраните выданный URL (например, `https://firstgamble.vercel.app`) и пропишите его в `FRONTEND_URL` бэкенда/бота.

## 7) Обновление после `git pull`
```bash
cd ~/apps/FirstGamble/frontend
npm install                 # если package.json изменился
VITE_API_BASE=https://firstgamble.ru npm run build
vercel --prod               # пересборка и выкладка
```

## 8) Частые вопросы
- **Почему нужен VITE_API_BASE?** Telegram mini app работает в домене Vercel; браузер должен знать адрес API.
- **Где initData?** Реальное значение приходит из Telegram WebApp. Для тестов можно передать строку через `?initData=` в URL или вставить вручную в поле на стартовом экране.
- **Темы/адаптив?** Цвета и фон переключаются автоматически при изменении темы Telegram; блоки тянутся под ширину экрана.
