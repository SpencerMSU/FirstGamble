from typing import Dict, List

# Achievement Configuration
# id: unique string key
# name: display name
# description: description
# reward: points to award
# condition: logic identifier or thresholds

ACHIEVEMENTS: Dict[str, Dict] = {
    "first_win": {
        "id": "first_win",
        "name": "Первая победа",
        "description": "Выиграй в любой игре",
        "reward": 50,
        "type": "stat_threshold",
        "stat_key": "wins",
        "threshold": 1
    },
    "games_10": {
        "id": "games_10",
        "name": "Любитель",
        "description": "Сыграй 10 игр",
        "reward": 50,
        "type": "stat_threshold",
        "stat_key": "games_total",
        "threshold": 10
    },
    "games_100": {
        "id": "games_100",
        "name": "Профи",
        "description": "Сыграй 100 игр",
        "reward": 200,
        "type": "stat_threshold",
        "stat_key": "games_total",
        "threshold": 100
    },
    "wins_50": {
        "id": "wins_50",
        "name": "Чемпион",
        "description": "Выиграй 50 раз",
        "reward": 500,
        "type": "stat_threshold",
        "stat_key": "wins",
        "threshold": 50
    },
    "rich_1000": {
        "id": "rich_1000",
        "name": "Богач",
        "description": "Накопи 1000 монет на балансе",
        "reward": 100,
        "type": "balance_threshold",
        "threshold": 1000
    }
}
