"""
Settings manager for Viral Sandbox.
Handles loading and saving game settings to settings.json.
"""
import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

WINDOW_MODES = ("maximized", "windowed")
HAND_SIZE_MIN = 1
HAND_SIZE_MAX = 20


def get_default_settings() -> dict:
    """Return default settings."""
    return {
        "display": {
            "window_mode": "maximized"
        },
        "game": {
            "starting_hand_size": 7,
            "default_database": "default_database.json"
        }
    }


def load_settings() -> dict:
    """Load settings from settings.json. Returns defaults if file doesn't exist."""
    defaults = get_default_settings()
    try:
        with open(SETTINGS_FILE, "r") as f:
            saved = json.load(f)
        # Merge saved values into defaults (so new settings get their defaults)
        for section in defaults:
            if section in saved and isinstance(saved[section], dict):
                for key in defaults[section]:
                    if key in saved[section]:
                        defaults[section][key] = saved[section][key]
        return defaults
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults


def validate_settings(settings: dict) -> tuple[bool, str]:
    """Check settings before saving. Returns (valid, message)."""
    try:
        window_mode = settings["display"]["window_mode"]
        hand_size = settings["game"]["starting_hand_size"]
        default_database = settings["game"]["default_database"]
    except (KeyError, TypeError):
        return False, "Settings are missing required entries."

    if window_mode not in WINDOW_MODES:
        return False, f"Window mode must be one of: {', '.join(WINDOW_MODES)}."
    if (not isinstance(hand_size, int) or isinstance(hand_size, bool)
            or not HAND_SIZE_MIN <= hand_size <= HAND_SIZE_MAX):
        return False, (f"Starting Hand Size must be a number between "
                       f"{HAND_SIZE_MIN} and {HAND_SIZE_MAX}.")
    if not isinstance(default_database, str):
        return False, "Database must be a file name."
    return True, "OK"


def save_settings(settings: dict) -> None:
    """Save settings to settings.json."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)
