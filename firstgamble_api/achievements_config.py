from typing import Dict

# Achievement Configuration
# id: unique string key
# name: display name
# description: description
# reward: points to award
# condition: logic identifier or thresholds
# game: category for the UI (general, dice, slot, etc.)
# type: stat_threshold | gamestat_threshold | balance_threshold
# stat_key: for stat_threshold (wins, games_total, etc.)
# threshold: value to reach

ACHIEVEMENTS: Dict[str, Dict] = {
    # --- GENERAL ---
    "first_win": {
        "id": "first_win",
        "name": "Первая победа",
        "description": "Выиграй в любой игре",
        "reward": 10,
        "type": "stat_threshold",
        "stat_key": "wins",
        "threshold": 1,
        "game": "general"
    },
    "games_10": {
        "id": "games_10",
        "name": "Начинающий",
        "description": "Сыграй 10 игр суммарно",
        "reward": 15,
        "type": "stat_threshold",
        "stat_key": "games_total",
        "threshold": 10,
        "game": "general"
    },
    "games_50": {
        "id": "games_50",
        "name": "Любитель",
        "description": "Сыграй 50 игр суммарно",
        "reward": 25,
        "type": "stat_threshold",
        "stat_key": "games_total",
        "threshold": 50,
        "game": "general"
    },
    "games_100": {
        "id": "games_100",
        "name": "Профи",
        "description": "Сыграй 100 игр суммарно",
        "reward": 50,
        "type": "stat_threshold",
        "stat_key": "games_total",
        "threshold": 100,
        "game": "general"
    },
    "wins_10": {
        "id": "wins_10",
        "name": "Победитель I",
        "description": "Выиграй 10 раз",
        "reward": 20,
        "type": "stat_threshold",
        "stat_key": "wins",
        "threshold": 10,
        "game": "general"
    },
    "wins_50": {
        "id": "wins_50",
        "name": "Победитель II",
        "description": "Выиграй 50 раз",
        "reward": 50,
        "type": "stat_threshold",
        "stat_key": "wins",
        "threshold": 50,
        "game": "general"
    },
    "rich_100": {
        "id": "rich_100",
        "name": "Копилка",
        "description": "Накопи 100 монет",
        "reward": 10,
        "type": "balance_threshold",
        "threshold": 100,
        "game": "general"
    },
    "rich_500": {
        "id": "rich_500",
        "name": "Кошелек",
        "description": "Накопи 500 монет",
        "reward": 25,
        "type": "balance_threshold",
        "threshold": 500,
        "game": "general"
    },
    "rich_1000": {
        "id": "rich_1000",
        "name": "Богач",
        "description": "Накопи 1000 монет",
        "reward": 50,
        "type": "balance_threshold",
        "threshold": 1000,
        "game": "general"
    },

    # --- DICE ---
    "dice_novice": {
        "id": "dice_novice",
        "name": "Новичок в Dice",
        "description": "Сыграй 5 раз в Dice",
        "reward": 10,
        "type": "gamestat_threshold",
        "game_id": "dice",
        "stat_key": "games_total",
        "threshold": 5,
        "game": "dice"
    },
    "dice_player": {
        "id": "dice_player",
        "name": "Игрок в Dice",
        "description": "Сыграй 20 раз в Dice",
        "reward": 20,
        "type": "gamestat_threshold",
        "game_id": "dice",
        "stat_key": "games_total",
        "threshold": 20,
        "game": "dice"
    },
    "dice_winner": {
        "id": "dice_winner",
        "name": "Везунчик в Dice",
        "description": "Выиграй 10 раз в Dice",
        "reward": 25,
        "type": "gamestat_threshold",
        "game_id": "dice",
        "stat_key": "wins",
        "threshold": 10,
        "game": "dice"
    },
    "dice_master": {
        "id": "dice_master",
        "name": "Мастер Dice",
        "description": "Выиграй 50 раз в Dice",
        "reward": 50,
        "type": "gamestat_threshold",
        "game_id": "dice",
        "stat_key": "wins",
        "threshold": 50,
        "game": "dice"
    },

    # --- SLOTS ---
    "slot_spinner": {
        "id": "slot_spinner",
        "name": "Спиннер",
        "description": "Сыграй 10 раз в Слоты",
        "reward": 10,
        "type": "gamestat_threshold",
        "game_id": "slot",
        "stat_key": "games_total",
        "threshold": 10,
        "game": "slot"
    },
    "slot_fan": {
        "id": "slot_fan",
        "name": "Фанатик Слотов",
        "description": "Сыграй 50 раз в Слоты",
        "reward": 30,
        "type": "gamestat_threshold",
        "game_id": "slot",
        "stat_key": "games_total",
        "threshold": 50,
        "game": "slot"
    },
    "slot_lucky": {
        "id": "slot_lucky",
        "name": "Удача 777",
        "description": "Выиграй 5 раз в Слоты",
        "reward": 20,
        "type": "gamestat_threshold",
        "game_id": "slot",
        "stat_key": "wins",
        "threshold": 5,
        "game": "slot"
    },

    # --- BLACKJACK (BJ) ---
    "bj_deal": {
        "id": "bj_deal",
        "name": "Раздача",
        "description": "Сыграй 5 раз в Blackjack",
        "reward": 10,
        "type": "gamestat_threshold",
        "game_id": "bj",
        "stat_key": "games_total",
        "threshold": 5,
        "game": "bj"
    },
    "bj_shark": {
        "id": "bj_shark",
        "name": "Акула стола",
        "description": "Выиграй 10 раз в Blackjack",
        "reward": 30,
        "type": "gamestat_threshold",
        "game_id": "bj",
        "stat_key": "wins",
        "threshold": 10,
        "game": "bj"
    },

    # --- STACK ---
    "stack_builder": {
        "id": "stack_builder",
        "name": "Строитель",
        "description": "Сыграй 10 раз в Stack",
        "reward": 10,
        "type": "gamestat_threshold",
        "game_id": "stack",
        "stat_key": "games_total",
        "threshold": 10,
        "game": "stack"
    },
    "stack_high": {
        "id": "stack_high",
        "name": "Высотка",
        "description": "Выиграй 5 раз в Stack",
        "reward": 20,
        "type": "gamestat_threshold",
        "game_id": "stack",
        "stat_key": "wins",
        "threshold": 5,
        "game": "stack"
    },

    # --- RUNNER ---
    "runner_run": {
        "id": "runner_run",
        "name": "Бегун",
        "description": "Сыграй 10 раз в Runner",
        "reward": 10,
        "type": "gamestat_threshold",
        "game_id": "runner",
        "stat_key": "games_total",
        "threshold": 10,
        "game": "runner"
    },
    "runner_fast": {
        "id": "runner_fast",
        "name": "Спринтер",
        "description": "Выиграй 5 раз в Runner",
        "reward": 20,
        "type": "gamestat_threshold",
        "game_id": "runner",
        "stat_key": "wins",
        "threshold": 5,
        "game": "runner"
    },

    # --- PULSE ---
    "pulse_try": {
        "id": "pulse_try",
        "name": "Пульс",
        "description": "Сыграй 10 раз в Pulse",
        "reward": 10,
        "type": "gamestat_threshold",
        "game_id": "pulse",
        "stat_key": "games_total",
        "threshold": 10,
        "game": "pulse"
    },
    "pulse_survivor": {
        "id": "pulse_survivor",
        "name": "Выживший",
        "description": "Выиграй 5 раз в Pulse",
        "reward": 20,
        "type": "gamestat_threshold",
        "game_id": "pulse",
        "stat_key": "wins",
        "threshold": 5,
        "game": "pulse"
    },

    # --- DOODLE ---
    "doodle_jump": {
        "id": "doodle_jump",
        "name": "Прыгун",
        "description": "Сыграй 10 раз в Doodle",
        "reward": 10,
        "type": "gamestat_threshold",
        "game_id": "doodle",
        "stat_key": "games_total",
        "threshold": 10,
        "game": "doodle"
    },
    "doodle_space": {
        "id": "doodle_space",
        "name": "Космос",
        "description": "Выиграй 5 раз в Doodle",
        "reward": 20,
        "type": "gamestat_threshold",
        "game_id": "doodle",
        "stat_key": "wins",
        "threshold": 5,
        "game": "doodle"
    }
}
