"""
config.py - Central configuration for the RJ Airplane Tracker Widget.
Stores default coordinates (Mumbai Airport), geofence radius, polling
intervals, notification preferences, and persists user changes to JSON.
"""

import json
import os

# ─── Default Coordinates: Mumbai Airport (BOM / VABB) ───────────────────────
DEFAULT_LATITUDE = 19.09
DEFAULT_LONGITUDE = 72.87
DEFAULT_RADIUS_KM = 10.0

# ─── Available radius options (km) ─────────────────────────────────────────
RADIUS_OPTIONS = [5, 10, 15, 20, 30]

# ─── Polling Intervals (seconds) ────────────────────────────────────────────
SPEED_OPTIONS = {
    "Fast (30s)": 30,
    "Normal (60s)": 60,
    "Eco (120s)": 120,
}
DEFAULT_SPEED = "Normal (60s)"

# ─── Notification Modes ─────────────────────────────────────────────────────
# "ALL"           – notify for every aircraft entering the zone
# "SPECIFIC"      – notify only for callsigns matching target prefixes
# "LOW_ALTITUDE"  – notify only for aircraft below altitude threshold
NOTIFICATION_MODES = ["ALL", "SPECIFIC", "LOW_ALTITUDE"]
DEFAULT_NOTIFICATION_MODE = "ALL"
DEFAULT_NOTIFICATIONS_ENABLED = True

# Default callsign targets – enter specific callsigns (e.g. "IGO5175", "AIC101")
# or prefixes (e.g. "IGO", "AIC") to watch in SPECIFIC mode
DEFAULT_TARGET_CALLSIGNS = []

# ─── Ground Filtering ───────────────────────────────────────────────────────
# When False, aircraft on the ground (taxiing, parked) are excluded from
# the map and notifications. Can be toggled live via the UI.
IGNORE_GROUND_VEHICLES = True
DEFAULT_SHOW_GROUNDED = False
MIN_AIRBORNE_ALTITUDE_M = 150  # Minimum altitude to be considered "overhead"

# Altitude threshold for LOW_ALTITUDE mode (meters)
DEFAULT_MAX_ALTITUDE_METERS = 1500  # ~5000 ft

# ─── Map Settings ───────────────────────────────────────────────────────────
DEFAULT_ZOOM = 12

# ─── Notification Batch / Throttle ──────────────────────────────────────────
# Max individual toast notifications per poll cycle (extras are grouped)
MAX_TOASTS_PER_POLL = 2

# ─── Widget Dimensions ─────────────────────────────────────────────────────
WIDGET_WIDTH = 700
WIDGET_HEIGHT = 550
WIDGET_MIN_WIDTH = 400
WIDGET_MIN_HEIGHT = 350

# ─── Cleanup ────────────────────────────────────────────────────────────────
# Seconds before a departed aircraft can re-trigger a notification
AIRCRAFT_EXPIRY_SECONDS = 600  # 10 minutes

# ─── Settings Persistence ──────────────────────────────────────────────────
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_settings.json")


def _default_settings() -> dict:
    """Return a fresh dictionary of default user settings."""
    return {
        "latitude": DEFAULT_LATITUDE,
        "longitude": DEFAULT_LONGITUDE,
        "radius_km": DEFAULT_RADIUS_KM,
        "speed": DEFAULT_SPEED,
        "notifications_enabled": DEFAULT_NOTIFICATIONS_ENABLED,
        "notification_mode": DEFAULT_NOTIFICATION_MODE,
        "target_callsigns": DEFAULT_TARGET_CALLSIGNS,
        "max_altitude_meters": DEFAULT_MAX_ALTITUDE_METERS,
        "show_grounded": DEFAULT_SHOW_GROUNDED,
        "window_width": WIDGET_WIDTH,
        "window_height": WIDGET_HEIGHT,
    }


def load_settings() -> dict:
    """
    Load persisted user settings from JSON.
    Falls back to defaults if file is missing or corrupt.
    """
    defaults = _default_settings()
    if not os.path.exists(SETTINGS_FILE):
        return defaults
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        # Merge saved values over defaults so new keys are always present
        for key in defaults:
            if key not in saved:
                saved[key] = defaults[key]
        return saved
    except (json.JSONDecodeError, IOError, OSError):
        return defaults


def save_settings(settings: dict) -> None:
    """Persist the current user settings dict to disk as JSON."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except (IOError, OSError):
        pass  # Non-critical; swallow silently
