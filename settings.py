"""
Settings manager for Viral Sandbox.
Handles loading and saving game settings to settings.json.
"""
import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


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


def save_settings(settings: dict) -> None:
    """Save settings to settings.json."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)
