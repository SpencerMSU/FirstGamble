-- LudkaExe.lua — скрипт для реакции на /bj и проведения мини-игры в семейном чате

local encoding = require 'encoding'
encoding.default = 'CP1251'
local u8 = encoding.UTF8

local https = require 'ssl.https'
local ltn12 = require 'ltn12'

local json = {}

do
    local escape_char_map = {
        ["\b"] = "\\b",
        ["\f"] = "\\f",
        ["\n"] = "\\n",
        ["\r"] = "\\r",
        ["\t"] = "\\t",
        ["\""] = '\\"',
        ["\\"] = "\\\\"
    }

    local escape_char_map_inv = { ["\\/"] = "/" }
    for k, v in pairs(escape_char_map) do
        escape_char_map_inv[v] = k
    end

    local function escape_char(c)
        return escape_char_map[c] or string.format("\\u%04x", c:byte())
    end

    local function encode_nil()
        return "null"
    end

    local function encode_table(val, stack)
        local res = {}
        stack = stack or {}

        if stack[val] then
            error("circular reference")
        end
        stack[val] = true

        local is_array = (#val > 0)
        if is_array then
            for i = 1, #val do
                table.insert(res, json.encode(val[i], stack))
            end
            stack[val] = nil
            return "[" .. table.concat(res, ",") .. "]"
        else
            for k, v in pairs(val) do
                if type(k) ~= "string" then
                    error("json object keys must be strings")
                end
                table.insert(res, json.encode(k, stack) .. ":" .. json.encode(v, stack))
            end
            stack[val] = nil
            return "{" .. table.concat(res, ",") .. "}"
        end
    end

    local function decode_error(str, idx)
        error("invalid json at position " .. idx)
    end

    local function parse_unicode_escape(str)
        local hex = str:sub(3, 6)
        return string.char(tonumber(hex, 16))
    end

    local function parse_string(str, i)
        local res = {}
        local j = i + 1
        local k = j
        while j <= #str do
            local c = str:sub(j, j)
            if c == '"' then
                table.insert(res, str:sub(k, j - 1))
                return table.concat(res), j + 1
            end
            if c == '\\' then
                table.insert(res, str:sub(k, j - 1))
                local esc = str:sub(j, j + 1)
                if esc == "\\u" then
                    local escaped = str:sub(j, j + 5)
                    if not escaped:match("^\\u%x%x%x%x") then
                        decode_error(str, j)
                    end
                    table.insert(res, parse_unicode_escape(escaped))
                    j = j + 6
                else
                    local repl = escape_char_map_inv[esc]
                    if not repl then
                        decode_error(str, j)
                    end
                    table.insert(res, repl)
                    j = j + 2
                end
                k = j
            else
                j = j + 1
            end
        end
        decode_error(str, i)
    end

    local function parse_number(str, i)
        local x = i
        local s = str:sub(i, i)
        if s == "-" then
            x = x + 1
        end
        while str:sub(x, x):match("%d") do
            x = x + 1
        end
        if str:sub(x, x) == "." then
            x = x + 1
            while str:sub(x, x):match("%d") do
                x = x + 1
            end
        end
        local exp = str:sub(x, x)
        if exp == "e" or exp == "E" then
            x = x + 1
            local sign = str:sub(x, x)
            if sign == "+" or sign == "-" then
                x = x + 1
            end
            while str:sub(x, x):match("%d") do
                x = x + 1
            end
        end
        local number = tonumber(str:sub(i, x - 1))
        if not number then
            decode_error(str, i)
        end
        return number, x
    end

    local function skip_whitespace(str, i)
        while true do
            local c = str:sub(i, i)
            if c == "" then
                return i
            elseif c == " " or c == "\t" or c == "\r" or c == "\n" then
                i = i + 1
            else
                return i
            end
        end
    end

    local parse_value

    local function parse_array(str, i)
        local res = {}
        i = skip_whitespace(str, i)
        if str:sub(i, i) == "]" then
            return res, i + 1
        end
        local val
        while true do
            val, i = parse_value(str, i)
            table.insert(res, val)
            i = skip_whitespace(str, i)
            local c = str:sub(i, i)
            if c == "]" then
                return res, i + 1
            end
            if c ~= "," then
                decode_error(str, i)
            end
            i = skip_whitespace(str, i + 1)
        end
    end

    local function parse_object(str, i)
        local res = {}
        i = skip_whitespace(str, i)
        if str:sub(i, i) == "}" then
            return res, i + 1
        end
        while true do
            if str:sub(i, i) ~= '"' then
                decode_error(str, i)
            end
            local key
            key, i = parse_string(str, i)
            i = skip_whitespace(str, i)
            if str:sub(i, i) ~= ":" then
                decode_error(str, i)
            end
            i = skip_whitespace(str, i + 1)
            local val
            val, i = parse_value(str, i)
            res[key] = val
            i = skip_whitespace(str, i)
            local c = str:sub(i, i)
            if c == "}" then
                return res, i + 1
            end
            if c ~= "," then
                decode_error(str, i)
            end
            i = skip_whitespace(str, i + 1)
        end
    end

    function parse_value(str, i)
        i = skip_whitespace(str, i)
        local c = str:sub(i, i)
        if c == '"' then
            local val
            val, i = parse_string(str, i)
            return val, i
        elseif c == "{" then
            return parse_object(str, i + 1)
        elseif c == "[" then
            return parse_array(str, i + 1)
        elseif c == "-" or c:match("%d") then
            return parse_number(str, i)
        elseif str:sub(i, i + 3) == "null" then
            return nil, i + 4
        elseif str:sub(i, i + 3) == "true" then
            return true, i + 4
        elseif str:sub(i, i + 4) == "false" then
            return false, i + 5
        end
        decode_error(str, i)
    end

    function json.encode(val, stack)
        local t = type(val)
        if t == "nil" then
            return encode_nil()
        elseif t == "number" then
            if val ~= val or val >= math.huge or val <= -math.huge then
                error("number out of range")
            end
            return tostring(val)
        elseif t == "boolean" then
            return tostring(val)
        elseif t == "string" then
            return '"' .. val:gsub('[%z\1-\31\\"]', escape_char) .. '"'
        elseif t == "table" then
            return encode_table(val, stack)
        else
            error("unsupported type: " .. t)
        end
    end

    function json.decode(str)
        if type(str) ~= "string" then
            error("expected string for json.decode")
        end
        local res, idx = parse_value(str, 1)
        idx = skip_whitespace(str, idx or 1)
        if idx <= #str then
            decode_error(str, idx)
        end
        return res
    end
end

local MODE_DEBUG = "debugdev"
local MODE_MAIN = "main"
local blackjackMode = MODE_MAIN

local RESPONSE_DELAY = 2000 -- delay
local GAME_TIMEOUT = 30 -- единый таймер на игру (секунды)
local PERSONAL_COOLDOWN = 300 -- 5 минут
local GLOBAL_COOLDOWN = 60 -- 1 минута между играми
local BJ_TRIGGER = "/bj"
local TEST_TRIGGER = "/test"
local TEST_RESPONSE = "/fam :robot: тест"
local TEST_COOLDOWN = 2
local RATE_WIN_TRIGGER = "/ratewin"
local RATE_LOSE_TRIGGER = "/ratelose"
local RULES_TRIGGER = "/rules"
local ITOGI_TRIGGER = "/itogi"
local ITOGI_OWNER_NAME = "Spartak_First"

local RES_TRIGGER = "/res"
local INV_TRIGGER = "/inv"
local CONVERT_TRIGGER = "/conv"
local DONATE_TRIGGER = "/doncount"
local GRULES_TRIGGER = "/grules"
local PROMO_TRIGGER = "/promo"
local DICE_TEST_TRIGGER = "/testdice"

local DICE_API_URL = "https://api.firstgamble.ru/api/dice/award"
local DICE_MIN_SUM = 1
local DICE_MAX_SUM = 12

local PROMO_REWARD_POINTS = 5
local AVAILABLE_PROMO_CODES = {
    "Nyanyashyyy",
    "firstpromo2",
    "firstpromo3",
    "firstpromo4",
    "firstpromo5",
    "firstpromo6",
    "firstpromo7",
    "firstpromo8",
    "firstpromo9",
    "firstpromo10"
}

local MAX_RESOURCE_COUNT = 99
local RESOURCE_GLOBAL_COOLDOWN = 600 -- 10 минут единый кд для добычи

local RESOURCE_TYPES = {
    wood = {icon = ":u1f333:", label = "wood"},
    food = {icon = ":u1f9c0:", label = "food"},
    water = {icon = ":u1f4a6:", label = "water"}
}

local RESOURCE_KEYS = {"wood", "water", "food"}

local RESOURCE_LIST = {
    {key = "wood", icon = ":u1f333:"},
    {key = "food", icon = ":u1f9c0:"},
    {key = "water", icon = ":u1f4a6:"}
}

local CONFIG_FILE_NAME = "FirstConfig.json"
local DEFAULT_CONSERVE_AUTH_TOKEN = "auth_conserve_82650245_XxX"

local config = {
    blacklist = {},
    stats = {},
    pointFund = 0,
    cooldownFreePlayers = {},
    conserveAuthToken = DEFAULT_CONSERVE_AUTH_TOKEN
}

local blacklistSet = {}
local cooldownFreeSet = {}
local lastResourceGatherTimestamp = 0
local conserveAuthToken = nil
local trim

local CHEESE_LOVER = "alexand_morenzo"

local function ensureResourceContainer(entry)
    if not entry.resources or type(entry.resources) ~= "table" then
        entry.resources = {}
    end
    for _, key in ipairs(RESOURCE_KEYS) do
        local value = tonumber(entry.resources[key] or 0) or 0
        if value < 0 then value = 0 end
        entry.resources[key] = value
    end
end

local function ensurePromoContainer(entry)
    if not entry.redeemedPromos or type(entry.redeemedPromos) ~= "table" then
        entry.redeemedPromos = {}
    end
end

local function ensurePoints(entry)
    entry.points = tonumber(entry.points or 0) or 0
    if entry.points < 0 then entry.points = 0 end
    ensurePromoContainer(entry)
end

local scheduleMessage

local function pathSeparator()
    return package.config:sub(1, 1)
end

local function getScriptDirectory()
    local path = thisScript().path or ""
    local dir = path:match("^(.*[\\/])")
    if not dir then
        return ""
    end
    local sep = pathSeparator()
    if dir:sub(-1) == "/" or dir:sub(-1) == "\\" then
        dir = dir:sub(1, -2)
    end
    dir = dir:gsub("/", sep):gsub("\\", sep)
    return dir
end

local function joinPath(dir, file)
    if dir == "" then return file end
    local sep = pathSeparator()
    if dir:sub(-1) == sep then
        return dir .. file
    end
    return dir .. sep .. file
end

local function parseTokenLine(line)
    local key, value = line:match("^%s*([%w_]+)%s*=%s*(.+)%s*$")
    if not key or not value then
        return nil, nil
    end
    return key, value
end

local function debugLog(text)
    local prefix = "[LUDKA DEBUG] "
    local message = prefix .. tostring(text)
    sampAddChatMessage(u8:decode(message), -1)
end

local function loadConserveToken()
    if conserveAuthToken ~= nil then
        return conserveAuthToken ~= false and conserveAuthToken or nil
    end

    if type(config.conserveAuthToken) == "string" then
        local trimmed = trim(config.conserveAuthToken)
        if trimmed ~= "" then
            conserveAuthToken = trimmed
            return conserveAuthToken
        end
    end

    local path = joinPath(getScriptDirectory(), "tokens.txt")
    local file = io.open(path, "r")
    if file then
        for line in file:lines() do
            local key, value = parseTokenLine(line)
            if key and key:lower() == "conserveauthtoken" then
                conserveAuthToken = trim(value)
                break
            end
        end
        file:close()
    end

    if not conserveAuthToken or conserveAuthToken == "" then
        conserveAuthToken = DEFAULT_CONSERVE_AUTH_TOKEN
        debugLog(string.format(
            "Токен ConServeAuth не найден в FirstConfig.json или tokens.txt, использую тестовый %s",
            conserveAuthToken
        ))
    end

    return conserveAuthToken
end

local function performDiceAwardRequest(playerName, diceSum)
    debugLog("Начало отправки запроса на начисление за кости")

    local token = loadConserveToken()
    if not token then
        debugLog("Токен ConServeAuth не найден. Укажите его в FirstConfig.json или tokens.txt")
        return false, "missing_token"
    end

    local payloadTable = { dice_sum = diceSum }
    if playerName and playerName ~= "" then
        payloadTable.Nick_Name = playerName
    end

    debugLog(string.format(
        "Готовлю payload для %s: сумма=%s",
        tostring(payloadTable.Nick_Name or "без ника"),
        tostring(diceSum)
    ))

    local payload = json.encode(payloadTable)
    local responseChunks = {}
    local res, statusCode, headers, statusLine = https.request({
        url = DICE_API_URL,
        method = "POST",
        headers = {
            ["Content-Type"] = "application/json",
            ["Content-Length"] = tostring(#payload),
            ["X-ConServe-Auth"] = token
        },
        source = ltn12.source.string(payload),
        sink = ltn12.sink.table(responseChunks)
    })

    local responseText = table.concat(responseChunks)
    if not res then
        debugLog(string.format("Запрос не выполнен: %s", tostring(statusLine or "request_failed")))
        return false, tostring(statusLine or "request_failed")
    end

    local code = tonumber(statusCode) or 0
    debugLog(string.format("Ответ сервера: код=%d тело=%s", code, responseText ~= "" and responseText or "<пусто>"))
    if code >= 200 and code < 300 then
        return true, responseText
    end

    return false, string.format("status_%d:%s", code, responseText)
end

local function rebuildBlacklistSet()
    blacklistSet = {}
    for _, name in ipairs(config.blacklist) do
        blacklistSet[name:lower()] = true
    end
end

local function rebuildCooldownFreeSet()
    cooldownFreeSet = {}
    if not config.cooldownFreePlayers then return end
    for _, name in ipairs(config.cooldownFreePlayers) do
        cooldownFreeSet[name:lower()] = true
    end
end

local function saveConfig()
    local path = joinPath(getScriptDirectory(), CONFIG_FILE_NAME)
    local ok, content = pcall(json.encode, config)
    if not ok then
        sampAddChatMessage(u8:decode("[BJ] Ошибка сохранения конфигурации: " .. tostring(content)), -1)
        return
    end
    local file = io.open(path, "w")
    if file then
        file:write(content)
        file:close()
    else
        sampAddChatMessage(u8:decode("[BJ] Не удалось открыть файл конфигурации для записи."), -1)
    end
end

local function loadConfig()
    local path = joinPath(getScriptDirectory(), CONFIG_FILE_NAME)
    local needSave = false
    local file = io.open(path, "r")
    if file then
        local content = file:read("*a")
        file:close()
        if content and content ~= "" then
            local ok, data = pcall(json.decode, content)
            if ok and type(data) == "table" then
                local hasTokenField = type(data.conserveAuthToken) == "string"
                local configuredToken = hasTokenField and trim(data.conserveAuthToken) or ""
                if configuredToken == "" then
                    configuredToken = DEFAULT_CONSERVE_AUTH_TOKEN
                    needSave = true
                end
                config = {
                    blacklist = type(data.blacklist) == "table" and data.blacklist or {},
                    stats = type(data.stats) == "table" and data.stats or {},
                    pointFund = tonumber(data.pointFund or 0) or 0,
                    cooldownFreePlayers = type(data.cooldownFreePlayers) == "table" and data.cooldownFreePlayers or {},
                    conserveAuthToken = configuredToken
                }
                needSave = needSave or not hasTokenField
            else
                needSave = true
            end
        else
            needSave = true
        end
    else
        needSave = true
    end
    rebuildBlacklistSet()
    rebuildCooldownFreeSet()
    if needSave then
        saveConfig()
    end
end

local function findStatsEntry(name)
    local lowerName = name:lower()
    for storedName, value in pairs(config.stats) do
        if storedName:lower() == lowerName then
            return value, storedName
        end
    end
    return nil, nil
end

local function ensurePlayerStats(name)
    local entry, storedName = findStatsEntry(name)
    if entry then
        if storedName ~= name then
            config.stats[name] = entry
            config.stats[storedName] = nil
            saveConfig()
        end
        ensureResourceContainer(entry)
        ensurePoints(entry)
        return entry
    end
    config.stats[name] = {wins = 0, losses = 0}
    ensureResourceContainer(config.stats[name])
    ensurePoints(config.stats[name])
    saveConfig()
    return config.stats[name]
end

local function recordOutcome(name, outcome)
    local entry = ensurePlayerStats(name)
    if outcome == "win" then
        entry.wins = (entry.wins or 0) + 1
    elseif outcome == "lose" then
        entry.losses = (entry.losses or 0) + 1
    end
    if outcome == "win" or outcome == "lose" then
        saveConfig()
    end
end

local function resolveResourceKey(alias)
    alias = alias and alias:lower() or ""
    if RESOURCE_TYPES[alias] then
        return alias
    end
    return nil
end

local function isCheeseLover(name)
    return name and name:lower() == CHEESE_LOVER
end

local function getResourceName(key, playerName)
    local names = {
        wood = "Дерево",
        food = isCheeseLover(playerName) and "Сыр" or "Еда",
        water = "Вода"
    }
    return names[key] or key
end

local function getTotalResourceCount(resources)
    local total = 0
    for _, key in ipairs(RESOURCE_KEYS) do
        total = total + (tonumber(resources[key] or 0) or 0)
    end
    return total
end

local function getTotalPoints(entry)
    local resourceTotal = getTotalResourceCount(entry.resources or {})
    local savedPoints = tonumber(entry.points or 0) or 0
    return resourceTotal + savedPoints
end

local function formatInventory(resources, playerName)
    local parts = {}
    for _, key in ipairs(RESOURCE_KEYS) do
        local count = tonumber(resources[key] or 0) or 0
        parts[#parts + 1] = string.format("%s:%d", getResourceName(key, playerName), count)
    end
    return table.concat(parts, " ")
end

local function resolveMentionId(name)
    if sampGetPlayerIdByNickname then
        local id = sampGetPlayerIdByNickname(name)
        if id and id ~= -1 then
            return tostring(id)
        end
    end
    return name
end

local function isPlayerBlacklisted(name)
    return blacklistSet[name:lower()] == true
end

local function isPlayerCooldownFree(name)
    return cooldownFreeSet[name:lower()] == true
end

local function sendBlacklistNotification(displayName, isAdded)
    local message
    if isAdded then
        message = string.format("/fam @%s теперь в черном списке!", displayName)
    else
        message = string.format("/fam @%s более не в черном списке!", displayName)
    end
    scheduleMessage(message)
end

local function addToBlacklist(name)
    local lowerName = name:lower()
    if blacklistSet[lowerName] then
        return false
    end
    table.insert(config.blacklist, name)
    blacklistSet[lowerName] = true
    saveConfig()
    sendBlacklistNotification(name, true)
    return true
end

local function removeFromBlacklist(name)
    local lowerName = name:lower()
    if not blacklistSet[lowerName] then
        return false
    end
    local removedName = name
    for index, value in ipairs(config.blacklist) do
        if value:lower() == lowerName then
            removedName = value
            table.remove(config.blacklist, index)
            break
        end
    end
    blacklistSet[lowerName] = nil
    saveConfig()
    sendBlacklistNotification(removedName, false)
    return true
end

local numberToEmoji

local function createLeaderboardList(key, minValue)
    local list = {}
    for name, data in pairs(config.stats) do
        local value = tonumber(data[key] or 0) or 0
        if value >= (minValue or 0) then
            table.insert(list, {name = name, value = value})
        end
    end
    table.sort(list, function(a, b)
        if a.value == b.value then
            return a.name:lower() < b.name:lower()
        end
        return a.value > b.value
    end)
    return list
end

local function getTopPlayer(key)
    local bestName, bestValue
    for name, data in pairs(config.stats) do
        local value = tonumber(data[key] or 0) or 0
        if not bestName or value > bestValue or (value == bestValue and name:lower() < bestName:lower()) then
            bestName = name
            bestValue = value
        end
    end
    return bestName, bestValue or 0
end

local function sendLeaderboard(key, label)
    local list = createLeaderboardList(key, 1)
    if #list == 0 then
        scheduleMessage(string.format("/fam :robot: Нет данных для рейтинга %s.", label))
        return
    end
    local parts = {}
    local limit = math.min(3, #list)
    for i = 1, limit do
        parts[i] = string.format("%d)%s(%s)", i, list[i].name, numberToEmoji(list[i].value))
    end
    scheduleMessage(string.format("/fam :robot: ТОП %s: %s", label, table.concat(parts, ", ")))
end

function trim(text)
    if not text then return "" end
    return text:match("^%s*(.-)%s*$")
end

local function normalizeMessage(text)
    local trimmed = trim(text)
    return trimmed:gsub("[%.%,%!%?]+$", "")
end

local function isInventoryFull(resources)
    for _, key in ipairs(RESOURCE_KEYS) do
        if tonumber(resources[key] or 0) >= MAX_RESOURCE_COUNT then
            return true
        end
    end
    return false
end

local formatTime
local sendChatByMode

local function ensureRobotPrefix(text)
    if blackjackMode ~= MODE_MAIN then
        return text
    end

    if text:find("^/fam%s*:robot:") or text:find("^:robot:") then
        return text
    end

    if text:find("^/fam") then
        return text:gsub("^/fam%s*", "/fam :robot: ", 1)
    end

    return ":robot: " .. text
end

local function handleResourceGather(player)
    local entry = ensurePlayerStats(player.name)
    local resources = entry.resources
    local now = os.time()

    if lastResourceGatherTimestamp > 0 then
        local elapsed = now - lastResourceGatherTimestamp
        if elapsed < RESOURCE_GLOBAL_COOLDOWN then
            local remaining = RESOURCE_GLOBAL_COOLDOWN - elapsed
            scheduleMessage(string.format("/fam :robot: Общий кд на добычу ещё %s.", formatTime(remaining)))
            return
        end
    end
    local chosen = RESOURCE_LIST[math.random(#RESOURCE_LIST)]
    local current = tonumber(resources[chosen.key] or 0) or 0
    if current >= MAX_RESOURCE_COUNT then
        scheduleMessage(string.format("/fam @%s Инвентарь переполнен,ждите обновления!", player.id))
        return
    end

    local gain = math.random(1, 5)
    local availableSpace = MAX_RESOURCE_COUNT - current
    gain = math.min(gain, availableSpace)
    resources[chosen.key] = current + gain
    saveConfig()

    lastResourceGatherTimestamp = now

    local resourceName = getResourceName(chosen.key, player.name)
    local message = string.format("/fam @%s Вы добыли %d ресурса %s", player.id, gain, resourceName)
    scheduleMessage(message)
end

local function handleInventoryCheck(player)
    local entry = ensurePlayerStats(player.name)
    local resources = entry.resources
    if isInventoryFull(resources) then
        scheduleMessage(string.format("/fam @%s Инвентарь переполнен,ждите обновления!", player.id))
        return
    end

    local totalPoints = getTotalPoints(entry)
    local message = string.format("/fam У вас %s Очки(%s)", formatInventory(resources, player.name), numberToEmoji(totalPoints))
    scheduleMessage(message)
end

local function sendGameRules()
    local firstMessage = "/fam ИгрыФирстов.Суть:отгадать загадку,она будет выдана за достижение всеми членами 1000 очков игр"
    local secondMessage = "/fam /res(добыча),/inv(инвентарь),/conv(конверт),/doncount"

    scheduleMessage(firstMessage)
    scheduleMessage(secondMessage)
end

local function formatDiceTestResponseText(success)
    local statusText = success and "тест успешен" or "тест неудачен"
    return string.format("/fam тест апи эндпоинты,%s", statusText)
end

local function handleDiceTestTrigger(player, diceSum)
    debugLog(string.format("Запрос /testdice от %s с суммой %s", player.name or "?", tostring(diceSum or "<нет>")))
    if not diceSum then
        debugLog("Не передано число для теста /testdice")
        scheduleMessage(string.format("/fam :robot: @%s Использование: /testdice <число %d-%d>.", player.id, DICE_MIN_SUM, DICE_MAX_SUM))
        return
    end

    if diceSum < DICE_MIN_SUM or diceSum > DICE_MAX_SUM then
        debugLog(string.format("Число вне диапазона: %s (нужно %d-%d)", tostring(diceSum), DICE_MIN_SUM, DICE_MAX_SUM))
        scheduleMessage(string.format("/fam :robot: @%s Укажите число в диапазоне %d-%d.", player.id, DICE_MIN_SUM, DICE_MAX_SUM))
        return
    end

    debugLog("Отправляю тестовый запрос на сервер FirstClub")
    local success, errorText = performDiceAwardRequest(player.name, diceSum)
    scheduleMessage(formatDiceTestResponseText(success))

    local resultText = success and "Успех" or ("Ошибка: " .. tostring(errorText or "<нет описания>"))
    debugLog("Результат теста дайсов: " .. resultText)
end

local function handleConvertResources(player)
    local entry = ensurePlayerStats(player.name)
    local resources = entry.resources
    local totalResources = getTotalResourceCount(resources)

    if totalResources <= 0 then
        scheduleMessage(string.format("/fam :robot: @%s Нет ресурсов для конвертации в очки.", player.id))
        return
    end

    entry.points = (entry.points or 0) + totalResources
    for _, key in ipairs(RESOURCE_KEYS) do
        entry.resources[key] = 0
    end
    saveConfig()

    local totalPoints = getTotalPoints(entry)
    local message = string.format("/fam @%s Конвертировано %d ресурсов в очки. Текущие очки:%d", player.id, totalResources, totalPoints)
    scheduleMessage(message)
end

local function handleDonatePoints(player)
    local entry = ensurePlayerStats(player.name)
    local resources = entry.resources
    local totalResources = getTotalResourceCount(resources)
    local totalPoints = (entry.points or 0) + totalResources

    if totalPoints <= 0 then
        scheduleMessage(string.format("/fam :robot: @%s Нечего переводить в общий фонд.", player.id))
        return
    end

    config.pointFund = (config.pointFund or 0) + totalPoints
    entry.points = 0
    for _, key in ipairs(RESOURCE_KEYS) do
        resources[key] = 0
    end
    saveConfig()

    local message = string.format("/fam @%s Отдал %d очков в общий фонд. Фонд:%d", player.id, totalPoints, config.pointFund)
    scheduleMessage(message)
end

local function handlePromo(player, code)
    local normalized = code and code:lower() or ""
    if normalized == "" then
        scheduleMessage(string.format("/fam :robot: @%s Укажите промокод после /promo.", player.id))
        return
    end

    local entry = ensurePlayerStats(player.name)
    ensurePromoContainer(entry)

    for _, stored in ipairs(AVAILABLE_PROMO_CODES) do
        if normalized == stored:lower() then
            if entry.redeemedPromos[normalized] then
                scheduleMessage(string.format("/fam :robot: @%s Этот промокод уже активирован.", player.id))
                return
            end

            entry.redeemedPromos[normalized] = true
            entry.points = (entry.points or 0) + PROMO_REWARD_POINTS
            saveConfig()
            local totalPoints = getTotalPoints(entry)
            local message = string.format("/fam @%s Промокод активирован! Начислено %d очков. Текущие очки:%d", player.id, PROMO_REWARD_POINTS, totalPoints)
            scheduleMessage(message)
            return
        end
    end

    scheduleMessage(string.format("/fam :robot: @%s Неверный промокод.", player.id))
end

local ranks = {
    {label = "2", value = 2},
    {label = "3", value = 3},
    {label = "4", value = 4},
    {label = "5", value = 5},
    {label = "6", value = 6},
    {label = "7", value = 7},
    {label = "8", value = 8},
    {label = "9", value = 9},
    {label = "10", value = 10},
    {label = "J", value = 10},
    {label = "Q", value = 10},
    {label = "K", value = 10},
    {label = "A", value = 11}
}

local currentGame = nil
local personalCooldowns = {}
local lastGameTimestamp = 0
local processedMessages = {}
local lastTestTriggerTime = 0

function formatTime(seconds)
    if seconds < 0 then seconds = 0 end
    local minutes = math.floor(seconds / 60)
    local secs = seconds % 60
    return string.format("%d:%02d", minutes, secs)
end

local function buildDeck()
    local deck = {}
    for _, rank in ipairs(ranks) do
        for _ = 1, 4 do
            table.insert(deck, {label = rank.label, value = rank.value})
        end
    end
    return deck
end

local function drawCard(deck)
    if #deck == 0 then return nil end
    local index = math.random(#deck)
    return table.remove(deck, index)
end

local function handTotal(cards)
    local total = 0
    for _, card in ipairs(cards) do
        total = total + card.value
    end
    return total
end

local digitEmojis = {
    ['0'] = ':na:',
    ['1'] = ':nb:',
    ['2'] = ':nc:',
    ['3'] = ':nd:',
    ['4'] = ':ne:',
    ['5'] = ':nf:',
    ['6'] = ':ng:',
    ['7'] = ':nh:',
    ['8'] = ':ni:',
    ['9'] = ':nj:'
}

local letterEmojis = {
    ['J'] = ':lj:',
    ['Q'] = ':lq:',
    ['K'] = ':lk:',
    ['A'] = ':la:'
}

local function labelToEmoji(label)
    if label == '10' then
        return digitEmojis['1'] .. digitEmojis['0']
    end
    if letterEmojis[label] then
        return letterEmojis[label]
    end
    local replaced = label:gsub('(%d)', function(digit)
        return digitEmojis[digit] or digit
    end)
    return replaced
end

function numberToEmoji(number)
    local value = tonumber(number) or 0
    local isNegative = value < 0
    if isNegative then
        value = -value
    end
    if value == 0 then
        return (isNegative and "-" or "") .. (digitEmojis['0'] or '0')
    end
    local digits = tostring(math.floor(value + 0.00001))
    local parts = {}
    for i = 1, #digits do
        local digit = digits:sub(i, i)
        parts[#parts + 1] = digitEmojis[digit] or digit
    end
    local result = table.concat(parts, "")
    if isNegative then
        result = "-" .. result
    end
    return result
end

local function formatCards(cards)
    local parts = {}
    for i, card in ipairs(cards) do
        parts[i] = labelToEmoji(card.label)
    end
    return table.concat(parts, ",")
end

local messageQueue = {}
local dispatcherActive = false

local function dispatchMessages()
    if dispatcherActive then return end
    dispatcherActive = true

    lua_thread.create(function()
        while #messageQueue > 0 do
            local text = table.remove(messageQueue, 1)
            wait(RESPONSE_DELAY)
            if blackjackMode == MODE_MAIN then
                local message = ensureRobotPrefix(text)
                sampSendChat(u8:decode(message))
            else
                sampAddChatMessage(u8:decode("[BJ DEBUG] " .. text), -1)
            end
        end
        dispatcherActive = false
    end)
end

function scheduleMessage(text)
    table.insert(messageQueue, text)
    dispatchMessages()
end

function sendChatByMode(text)
    if blackjackMode == MODE_MAIN then
        local message = ensureRobotPrefix(text)
        sampSendChat(u8:decode(message))
    else
        sampAddChatMessage(u8:decode("[BJ DEBUG] " .. text), -1)
    end
end

local function parseFamilyChat(text)
    if not text then return nil end
    local clean = text:gsub("%{[^}]*%}", "")

    local numbers = {}
    for num in clean:gmatch("%[(%d+)%]") do
        table.insert(numbers, tonumber(num))
    end
    if #numbers == 0 then return nil end

    local id = numbers[#numbers]
    local rank = numbers[#numbers - 1] or 0
    local before = clean:match("(.+)%[%d+%]:")
    if not before then return nil end

    local name = before:match("([%w_]+)%s*$") or before:match("([%S]+)%s*$")
    if not name then return nil end

    local message = clean:match("%[%d+%]:%s*(.+)") or ""

    return {
        name = name,
        id = tostring(id),
        rank = rank,
        message = message,
        key = string.format("%s[%s]", name, tostring(id))
    }
end

local function dealerTurn(game)
    if game.dealerSettled then
        return handTotal(game.dealerCards)
    end
    game.dealerSettled = true
    local total = handTotal(game.dealerCards)
    while total < 17 do
        local card = drawCard(game.deck)
        if not card then break end
        table.insert(game.dealerCards, card)
        total = handTotal(game.dealerCards)
    end
    return total
end

local function determineOutcome(playerTotal, dealerTotal)
    if playerTotal > 21 then
        return "lose"
    end
    if dealerTotal > 21 then
        return "win"
    end
    if playerTotal > dealerTotal then
        return "win"
    end
    if playerTotal < dealerTotal then
        return "lose"
    end
    return "tie"
end

local function finishGame(game, outcome, note, placeNoteFirst)
    if not game or game.finished then return end
    game.finished = true

    local playerTotal = handTotal(game.playerCards)
    local dealerTotal = handTotal(game.dealerCards)
    local playerCardsText = formatCards(game.playerCards)
    local dealerCardsText = formatCards(game.dealerCards)

    local baseMessage
    if outcome == "win" then
        baseMessage = string.format(
            ":robot: @%s Вы:%s(%d),дилер %s(%d) Вы победили!",
            game.player.id,
            playerCardsText,
            playerTotal,
            dealerCardsText,
            dealerTotal
        )
    elseif outcome == "lose" then
        baseMessage = string.format(
            ":robot: @%s Вы:%s(%d),дилер %s(%d) Вы проиграли!",
            game.player.id,
            playerCardsText,
            playerTotal,
            dealerCardsText,
            dealerTotal
        )
    else
        baseMessage = string.format(
            ":robot: @%s Вы:%s(%d),дилер %s(%d) Ничья.",
            game.player.id,
            playerCardsText,
            playerTotal,
            dealerCardsText,
            dealerTotal
        )
    end

    local parts = {"/fam"}
    if note and note ~= "" and placeNoteFirst then
        table.insert(parts, note)
    end
    table.insert(parts, baseMessage)
    if note and note ~= "" and not placeNoteFirst then
        table.insert(parts, note)
    end
    local message = table.concat(parts, " ")

    scheduleMessage(message)

    if outcome == "win" or outcome == "lose" then
        recordOutcome(game.player.name, outcome)
    end

    personalCooldowns[game.player.key] = os.time()
    lastGameTimestamp = os.time()
    if currentGame == game then
        currentGame = nil
    end
end

local function handleTimeout(game)
    if not game or game.finished then return end
    dealerTurn(game)
    local playerTotal = handTotal(game.playerCards)
    local dealerTotal = handTotal(game.dealerCards)
    local outcome = determineOutcome(playerTotal, dealerTotal)
    finishGame(game, outcome, "Время!", true)
end

local function startTimeoutWatcher(game)
    lua_thread.create(function()
        wait(GAME_TIMEOUT * 1000)
        if currentGame == game and not game.finished then
            handleTimeout(game)
        end
    end)
end

local function startGame(player)
    ensurePlayerStats(player.name)
    local deck = buildDeck()
    local playerCards = {drawCard(deck), drawCard(deck)}
    local dealerCards = {drawCard(deck), drawCard(deck)}

    local game = {
        player = player,
        deck = deck,
        playerCards = playerCards,
        dealerCards = dealerCards,
        startTime = os.time(),
        finished = false,
        dealerSettled = false
    }

    currentGame = game
    startTimeoutWatcher(game)

    local playerTotal = handTotal(playerCards)
    local initialMessage = string.format(
        "/fam :robot:@%s у тебя 2 карты: %s (%d) | /more или /vse ?",
        player.id,
        formatCards(playerCards),
        playerTotal
    )
    scheduleMessage(initialMessage)

    local dealerTotal = handTotal(dealerCards)
    if playerTotal >= 21 or dealerTotal >= 21 then
        dealerTurn(game)
        local updatedPlayerTotal = handTotal(game.playerCards)
        local updatedDealerTotal = handTotal(game.dealerCards)
        local outcome = determineOutcome(updatedPlayerTotal, updatedDealerTotal)
        local note
        if updatedPlayerTotal == 21 and updatedDealerTotal ~= 21 then
            note = "Блэкджек!"
        elseif updatedDealerTotal == 21 and updatedPlayerTotal ~= 21 then
            note = "У дилера блэкджек."
        elseif updatedDealerTotal == 21 and updatedPlayerTotal == 21 then
            note = "Двойной блэкджек."
        elseif updatedPlayerTotal > 21 then
            note = "Перебор!"
        end
        finishGame(game, outcome, note)
    end
end

local function handleMore()
    local game = currentGame
    if not game or game.finished then return end

    if os.time() - game.startTime >= GAME_TIMEOUT then
        handleTimeout(game)
        return
    end

    local card = drawCard(game.deck)
    if card then
        table.insert(game.playerCards, card)
    end
    local playerTotal = handTotal(game.playerCards)

    if playerTotal > 21 then
        dealerTurn(game)
        finishGame(game, "lose", "Перебор!")
        return
    end

    local message = string.format(
        "/fam :robot: @%s Теперь %s(%d) | /more или /vse ?",
        game.player.id,
        formatCards(game.playerCards),
        playerTotal
    )
    scheduleMessage(message)
end

local function handleStand()
    local game = currentGame
    if not game or game.finished then return end

    if os.time() - game.startTime >= GAME_TIMEOUT then
        handleTimeout(game)
        return
    end

    dealerTurn(game)
    local playerTotal = handTotal(game.playerCards)
    local dealerTotal = handTotal(game.dealerCards)
    local outcome = determineOutcome(playerTotal, dealerTotal)
    finishGame(game, outcome)
end

local function onBjTrigger(player)
    local now = os.time()

    if currentGame and not currentGame.finished then
        return
    end

    if isPlayerBlacklisted(player.name) then
        local message = string.format("/fam :robot: @%s Вы в черном списке!", player.id)
        scheduleMessage(message)
        return
    end

    local cdStart = personalCooldowns[player.key]
    if not isPlayerCooldownFree(player.name) then
        if cdStart and (now - cdStart) < PERSONAL_COOLDOWN then
            local remaining = PERSONAL_COOLDOWN - (now - cdStart)
            local message = string.format(
                "/fam :robot:@%s У тебя персональное кд, осталось ещё %s.",
                player.id,
                formatTime(remaining)
            )
            scheduleMessage(message)
            return
        end

        if now - lastGameTimestamp < GLOBAL_COOLDOWN then
            local remaining = GLOBAL_COOLDOWN - (now - lastGameTimestamp)
            local message = string.format(
                "/fam :robot: Сейчас идёт перерыв между играми, подожди ещё %s.",
                formatTime(remaining)
            )
            scheduleMessage(message)
            return
        end
    end

    startGame(player)
end

local function handleMessage(data)
    if not data or not data.message then return end

    local cleanMessage = data.message:lower()
    local normalizedMessage = normalizeMessage(cleanMessage)
    local key = data.name .. data.id .. normalizedMessage
    local now = os.time()
    if processedMessages[key] and (now - processedMessages[key]) < 2 then
        return
    end
    processedMessages[key] = now

    if normalizedMessage == TEST_TRIGGER then
        if now - lastTestTriggerTime >= TEST_COOLDOWN then
            lastTestTriggerTime = now
            scheduleMessage(TEST_RESPONSE)
        end
    end

    if normalizedMessage == RATE_WIN_TRIGGER then
        sendLeaderboard("wins", "побед")
        return
    end

    if normalizedMessage == RATE_LOSE_TRIGGER then
        sendLeaderboard("losses", "поражений")
        return
    end

    local diceSumStr = cleanMessage:match("^" .. DICE_TEST_TRIGGER .. "[%s]+(%d+)$")
    if diceSumStr then
        handleDiceTestTrigger(data, tonumber(diceSumStr))
        return
    end

    if normalizedMessage == DICE_TEST_TRIGGER then
        handleDiceTestTrigger(data, nil)
        return
    end

    if normalizedMessage == GRULES_TRIGGER then
        sendGameRules()
        return
    end

    if normalizedMessage == CONVERT_TRIGGER then
        handleConvertResources(data)
        return
    end

    if normalizedMessage == DONATE_TRIGGER then
        handleDonatePoints(data)
        return
    end

    local promoCode = cleanMessage:match("^/promo%s+(%S+)$")
    if normalizedMessage:find(PROMO_TRIGGER, 1, true) == 1 then
        handlePromo(data, promoCode)
        return
    end

    if normalizedMessage == RULES_TRIGGER then
        scheduleMessage("/fam Дилер неподкупен,ставок нету,по итогам недели(вс) дам приз самым-самым")
        return
    end

    if normalizedMessage == ITOGI_TRIGGER then
        if data.name:lower() == ITOGI_OWNER_NAME:lower() then
            local bestName, bestWins = getTopPlayer("wins")
            local worstName, worstLosses = getTopPlayer("losses")
            if not bestName or (bestWins or 0) <= 0 then
                bestName = "Н/Д"
            end
            if not worstName or (worstLosses or 0) <= 0 then
                worstName = "Н/Д"
            end
            scheduleMessage(string.format("/fam Самый удачный:%s,неудачник:%s", bestName, worstName))
        else
            scheduleMessage("/fam Вы недосточно круты")
        end
        return
    end

    if normalizedMessage == BJ_TRIGGER then
        onBjTrigger(data)
        return
    end

    if normalizedMessage == RES_TRIGGER then
        handleResourceGather(data)
        return
    end

    if normalizedMessage == INV_TRIGGER then
        handleInventoryCheck(data)
        return
    end

    if not currentGame or currentGame.finished then
        return
    end

    if currentGame.player.name ~= data.name or currentGame.player.id ~= data.id then
        return
    end

    if normalizedMessage == "/more" then
        handleMore()
    elseif normalizedMessage == "/vse" then
        handleStand()
    end
end

function main()
    math.randomseed(os.time())
    while not isSampAvailable() do wait(100) end

    loadConfig()

    sampRegisterChatCommand("ludikmode", function(arg)
        arg = arg and arg:lower() or ""
        if arg == MODE_DEBUG or arg == MODE_MAIN then
            blackjackMode = arg
        else
            blackjackMode = (blackjackMode == MODE_DEBUG) and MODE_MAIN or MODE_DEBUG
        end
        sampAddChatMessage(u8:decode("[BJ] Режим переключён: " .. blackjackMode), -1)
    end)

    sampRegisterChatCommand("kdremove", function(param)
        local name = trim(param or "")
        if name == "" then
            sampAddChatMessage(u8:decode("[BJ] Укажите ник для снятия КД."), -1)
            return
        end

        for _, stored in ipairs(config.cooldownFreePlayers) do
            if stored:lower() == name:lower() then
                sampAddChatMessage(u8:decode("[BJ] Для этого ника уже снято КД."), -1)
                return
            end
        end

        table.insert(config.cooldownFreePlayers, name)
        rebuildCooldownFreeSet()
        saveConfig()
        sampAddChatMessage(u8:decode("[BJ] КД для указанного ника отключено."), -1)
    end)

    sampRegisterChatCommand("bladd", function(param)
        local name = trim(param)
        if name == "" then
            sampAddChatMessage(u8:decode("[BJ] Укажите ник для добавления в черный список."), -1)
            return
        end
        if addToBlacklist(name) then
            sampAddChatMessage(u8:decode("[BJ] Ник добавлен в черный список."), -1)
        else
            sampAddChatMessage(u8:decode("[BJ] Этот ник уже находится в черном списке."), -1)
        end
    end)

    sampRegisterChatCommand("blremove", function(param)
        local name = trim(param)
        if name == "" then
            sampAddChatMessage(u8:decode("[BJ] Укажите ник для удаления из черного списка."), -1)
            return
        end
        if removeFromBlacklist(name) then
            sampAddChatMessage(u8:decode("[BJ] Ник удалён из черного списка."), -1)
        else
            sampAddChatMessage(u8:decode("[BJ] Указанного ника нет в черном списке."), -1)
        end
    end)

    sampRegisterChatCommand("resadd", function(param)
        param = trim(param or "")
        local name, resourceKey, amountStr = param:match("^(%S+)%s+(%S+)%s+(%S+)$")
        if not name or not resourceKey or not amountStr then
            sampAddChatMessage(u8:decode("[RES] Использование: /resadd Nick_Name [wood|food|water] <1-99>."), -1)
            return
        end

        local normalizedKey = resolveResourceKey(resourceKey)
        if not normalizedKey then
            sampAddChatMessage(u8:decode("[RES] Некорректный тип ресурса. Доступные: wood, food, water."), -1)
            return
        end

        local amount = tonumber(amountStr)
        if not amount or amount < 1 or amount > MAX_RESOURCE_COUNT then
            sampAddChatMessage(u8:decode("[RES] Количество должно быть числом от 1 до 99."), -1)
            return
        end

        local entry = ensurePlayerStats(name)
        local resources = entry.resources
        local current = tonumber(resources[normalizedKey] or 0) or 0

        if current >= MAX_RESOURCE_COUNT then
            sampAddChatMessage(u8:decode("[RES] Нельзя добавить ресурсы: лимит уже достигнут."), -1)
            return
        end

        if current + amount > MAX_RESOURCE_COUNT then
            sampAddChatMessage(u8:decode("[RES] Нельзя добавить столько ресурсов: лимит 99 на один тип."), -1)
            return
        end

        resources[normalizedKey] = current + amount
        saveConfig()

        local mentionId = resolveMentionId(name)
        local message = string.format("/fam @%s Вам было добавлено %d %s", mentionId, amount, getResourceName(normalizedKey, name))
        scheduleMessage(message)
    end)

    sampRegisterChatCommand("resetallresandcount", function()
        for _, entry in pairs(config.stats) do
            ensureResourceContainer(entry)
            ensurePoints(entry)
            for _, key in ipairs(RESOURCE_KEYS) do
                entry.resources[key] = 0
            end
            entry.points = 0
            entry.wins = 0
            entry.losses = 0
        end
        config.pointFund = 0
        lastResourceGatherTimestamp = 0
        personalCooldowns = {}
        saveConfig()
        sampAddChatMessage(u8:decode("[BJ] Ресурсы, очки и счёт игры обнулены для всех."), -1)
    end)

    sampAddChatMessage(u8:decode("[BJ] Скрипт активирован. Текущий режим: " .. blackjackMode), -1)
    wait(-1)
end

require "samp.events".onServerMessage = function(color, text)
    if not text then return end
    local data = parseFamilyChat(text)
    if not data then return end
    handleMessage(data)
end