# Стек Loki + Promtail + Grafana

Ниже — последовательные шаги для Ubuntu 24 (Timeweb) для сбора логов `firstgamble-api.service`, `firstgamble-bot.service` и Nginx.

## 1. Подготовка окружения (Ubuntu 24)
```bash
sudo apt update && sudo apt install -y ca-certificates curl gnupg lsb-release
# Docker + Compose Plugin
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

## 2. Развёртывание стека
Скопируйте каталог `logging-stack/` на сервер, задайте пароль Grafana и запустите:
```bash
cd /path/to/logging-stack
export GRAFANA_ADMIN_USER=admin
export GRAFANA_ADMIN_PASSWORD='StrongPassHere'
sudo docker compose up -d
```

- Grafana: порт 3000 (проксируется Nginx на logs.firstgamble.ru)
- Loki: порт 3100 (внутренний, использует Promtail)
- Promtail: читает journal и `/var/log/nginx/*.log`

## 3. Конфигурации
- `docker-compose.yml` — сервисы Loki/Promtail/Grafana с томами для хранения.
- `loki-config.yaml` — локальное хранение, retention 7d, compactor включён.
- `promtail-config.yaml` — читает `firstgamble-api.service`, `firstgamble-bot.service` из journal и логи Nginx. Лейблы: `job=firstgamble`, `service=firstgamble-api|firstgamble-bot|nginx`, `env=prod`.
- Grafana provisioning:
  - `grafana/provisioning/datasources/loki.yml` — data source Loki.
  - `grafana/provisioning/dashboards/dashboard.yml` + `grafana/dashboards/firstgamble-logs.json` — базовый дашборд с панелью логов и таблицей начислений очков.

## 4. Nginx: `logs.firstgamble.ru`
Пример конфига (`/etc/nginx/sites-available/logs.firstgamble.ru`):
```nginx
server {
    listen 80;
    server_name logs.firstgamble.ru;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name logs.firstgamble.ru;

    ssl_certificate /etc/letsencrypt/live/logs.firstgamble.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/logs.firstgamble.ru/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Выпустить сертификат:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d logs.firstgamble.ru
```
Grafana использует собственную аутентификацию (`admin` / ваш пароль), поэтому дополнительный Basic Auth не требуется.

## 5. Полезные запросы в Grafana (Loki Query)
- Все начисления очков: `{job="firstgamble"} |= "Игрок с id"`
- Начисления за игру dice: `{job="firstgamble"} |= "Игрок с id" |= "игре dice"`
- Начисления конкретному пользователю: `{job="firstgamble"} |= "Игрок с id 123456789"`
- Фильтр по сервису API: `{job="firstgamble", service="firstgamble-api"}`

## 6. Жизненный цикл
```bash
# Логи контейнеров
sudo docker compose logs -f loki promtail grafana
# Обновить стек после правок конфигов
sudo docker compose pull
sudo docker compose up -d
# Резервное копирование
sudo tar czf logging-stack-backup.tgz loki-config.yaml promtail-config.yaml grafana/
```
