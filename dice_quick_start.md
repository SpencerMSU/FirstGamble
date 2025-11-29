# Быстрый запуск для начисления очков в игре «Кости» (Lua)

Минимальный набор библиотек и готовый фрагмент кода, который можно вставить в Lua-скрипт для обращения к публичному эндпоинту `/api/dice/award`.

## Что подключить
- Lua 5.1+ (подходит для LÖVE, OpenResty и стандартного Lua).
- Клиент HTTP из [`luasocket`](https://luarocks.org/modules/luarocks/luasocket) и модуль для JSON — например [`lua-cjson`](https://luarocks.org/modules/openresty/lua-cjson). Установить через LuaRocks:
  ```bash
  luarocks install luasocket
  luarocks install lua-cjson
  ```

## Готовый код
Вставьте блок в свой Lua-скрипт, заменив значения токена, `DICE_SUM` и при необходимости `NickName`.

```lua
local http = require("socket.http")
local ltn12 = require("ltn12")
local cjson = require("cjson")

local API_URL = "https://api.firstgamble.ru/api/dice/award" 
local SERVICE_TOKEN = "auth_conserve_82650245_XxX"

local DICE_SUM = 7
local NickName = "Player_123"

local payload_table = {
  dice_sum = DICE_SUM,
  Nick_Name = NickName
}

local payload = cjson.encode(payload_table)
local response_body = {}

local ok, status_code, headers, status_line = http.request({
  url = API_URL,
  method = "POST",
  headers = {
    ["Content-Type"] = "application/json",
    ["X-ConServe-Auth"] = SERVICE_TOKEN,
    ["Content-Length"] = tostring(#payload),
  },
  source = ltn12.source.string(payload),
  sink = ltn12.sink.table(response_body),
})
```

### Что важно помнить
- Токен обязателен: без `X-ConServe-Auth` сервер вернёт `401 invalid conserve token`.
- Для внешних вызовов проверяется диапазон `dice_sum` **1–12**; при выходе за пределы ответ будет `400 dice_sum out of range`.
- Если указан `Nick_Name` (в примере переменная `NickName`), он должен быть привязан в кабинете; иначе вернётся `404 Nick_Name is not linked`.
