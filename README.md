# FirstGamble

FirstGamble is a Telegram-based gaming platform that allows users to play various minigames, earn points, and participate in raffles. The platform consists of a Telegram bot, a web application with the games, and a backend API.

## Project Structure

The repository is organized into the following main components:

- **`firstgamble_api`**: A Python FastAPI application that serves as the backend API for the platform. It handles user authentication, game logic, leaderboards, and more.
- **`firstgamble_bot`**: A Python application that implements the Telegram bot. The bot is the main entry point for users to access the platform.
- **`ludka` and `minigames`**: These directories contain the C++ and JavaScript source code for the various minigames available on the platform.
- **`logging-stack`**: A Docker-based logging stack using Loki, Promtail, and Grafana to collect and visualize logs from the different services.
- **Static files**: The root directory contains various HTML, JavaScript, and other static files for the web application.

## Setup and Installation

### Backend API

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Create `tokens.txt`**: Create a `tokens.txt` file in the root directory with the following content:
   ```
   BOT_TOKEN=<your_telegram_bot_token>
   CONSERVE_AUTH_TOKEN=<a_secret_token>
   REDIS_HOST=<your_redis_host>
   REDIS_PORT=<your_redis_port>
   REDIS_DB=<your_redis_db>
   WEBAPP_URL=<your_webapp_url>
   ADMIN_USER=<your_admin_username>
   ADMIN_PASS=<your_admin_password>
   ADMIN_TG_ID=<your_telegram_id>
   ```
3. **Run the API**:
   ```bash
   uvicorn api_app:app --host 0.0.0.0 --port 8000
   ```

### Telegram Bot

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Run the bot**:
   ```bash
   python bot.py
   ```

### Logging Stack

1. **Install Docker and Docker Compose**.
2. **Navigate to the `logging-stack` directory**:
   ```bash
   cd logging-stack
   ```
3. **Set the Grafana admin password**:
   ```bash
   export GRAFANA_ADMIN_PASSWORD='<your_strong_password>'
   ```
4. **Start the logging stack**:
   ```bash
   sudo docker compose up -d
   ```

## Usage

Once all the components are up and running, you can interact with the platform through the Telegram bot. The bot will provide you with a link to the web application where you can play the games.

The API documentation is available at `/docs` when the API is running.
