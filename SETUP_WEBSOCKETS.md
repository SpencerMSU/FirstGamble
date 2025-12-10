# WebSocket Configuration Guide

To enable real-time features (Chat, Durak Online), your server must support WebSocket connections (`wss://` since you use HTTPS).

## 1. Nginx Configuration
If you use Nginx as a reverse proxy for Uvicorn (FastAPI), you must add the `Upgrade` headers to the location block where your API is served.

Example config block:
```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

## 2. Uvicorn Command
Ensure Uvicorn is running with a command that allows connection upgrades (default behavior is usually fine).
`uvicorn firstgamble_api.routes:app --host 0.0.0.0 --port 8000`

## 3. Firewall
Ensure the port (e.g., 443 for HTTPS) allows long-lived connections and doesn't have aggressive timeouts (Durak games can last minutes).

## 4. HTTPS Certificates
You mentioned you have certificates. Ensure they are valid and Nginx is configured to terminate SSL before passing to Uvicorn (or Uvicorn is configured with SSL, though Nginx proxy is recommended).

## 5. Persistence
Currently, game state is stored **in-memory** for the specific worker process.
* **Important:** You must run Uvicorn with **1 worker** (`--workers 1`) to ensure all players in a room connect to the same process.
* If you scale to multiple workers, players might connect to different processes and not see each other.
* For multi-worker support, a Redis backend for Game State would be required (future improvement).
