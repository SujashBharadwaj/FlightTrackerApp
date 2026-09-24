"""
tracker_widget.py - Main entry-point for the RJ Airplane Tracker Widget.
Uses pywebview (WebView2 on Windows) to render a modern Leaflet-based map
with hardware-accelerated GPU rendering, smooth zoom, native edge resizing,
aircraft click popups, interactive callsign picker, and radius switching.

Phase 3: Full WebView2 migration from Tkinter.
"""

import ctypes
import json
import logging
import os
import queue
import sys
import threading
import time

import webview

from config import (
    DEFAULT_ZOOM,
    RADIUS_OPTIONS,
    SPEED_OPTIONS,
    WIDGET_HEIGHT,
    WIDGET_WIDTH,
    WIDGET_MIN_WIDTH,
    WIDGET_MIN_HEIGHT,
    load_settings,
    save_settings,
)
from notification_mgr import NotificationManager
from opensky_service import OpenSkyWorker

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Single-instance mutex name ─────────────────────────────────────────────
MUTEX_NAME = "Global\\RJAirplaneTrackerWidgetMutex"


def _acquire_single_instance_mutex():
    """
    Attempt to create a named Windows mutex to enforce single instance.
    If another instance already holds the mutex, print a message and exit.
    """
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    last_error = kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183

    if last_error == ERROR_ALREADY_EXISTS:
        print("RJ Airplane Tracker is already running. Exiting duplicate instance.")
        kernel32.CloseHandle(mutex)
        sys.exit(0)

    # Return handle so it stays alive for the process lifetime
    return mutex


class TrackerAPI:
    """
    Python ↔ JavaScript bridge exposed to the WebView frontend.
    All public methods here are callable from JS via `window.pywebview.api.*`.
    """

    def __init__(self, window_ref, settings, worker, notif_mgr):
        self._window = window_ref
        self._settings = settings
        self._worker = worker
        self._notif_mgr = notif_mgr

    def get_initial_config(self):
        """Return initial configuration for the frontend to bootstrap."""
        return {
            "latitude": self._settings["latitude"],
            "longitude": self._settings["longitude"],
            "radius_km": self._settings["radius_km"],
            "zoom": DEFAULT_ZOOM,
            "speed": self._settings["speed"],
            "notifications_enabled": self._settings["notifications_enabled"],
            "notification_mode": self._settings["notification_mode"],
            "target_callsigns": self._settings["target_callsigns"],
            "max_altitude_meters": self._settings["max_altitude_meters"],
            "radius_options": RADIUS_OPTIONS,
        }

    def set_radius(self, km):
        """Switch the geofence radius. Called from the JS radius buttons."""
        km = float(km)
        self._settings["radius_km"] = km
        self._worker.update_geofence(
            self._settings["latitude"],
            self._settings["longitude"],
            km,
        )
        save_settings(self._settings)
        logger.info("Radius changed to %.1f km", km)

    def set_speed(self, seconds):
        """Update polling interval. Called from the JS speed selector."""
        seconds = int(seconds)
        self._worker.set_interval(seconds)
        # Reverse-map to label for persistence
        for label, val in SPEED_OPTIONS.items():
            if val == seconds:
                self._settings["speed"] = label
                break
        save_settings(self._settings)
        logger.info("Speed changed to %ds", seconds)

    def get_detected_callsigns(self):
        """Return list of recently detected callsigns for the picker UI."""
        return self._worker.get_detected_callsigns()

    def save_notification_settings(self, enabled, mode, callsigns, max_alt):
        """Persist notification preferences from the settings panel."""
        self._notif_mgr.update_preferences(
            enabled=bool(enabled),
            mode=str(mode),
            target_callsigns=list(callsigns) if callsigns else [],
            max_altitude=float(max_alt),
        )
        self._settings["notifications_enabled"] = bool(enabled)
        self._settings["notification_mode"] = str(mode)
        self._settings["target_callsigns"] = list(callsigns) if callsigns else []
        self._settings["max_altitude_meters"] = float(max_alt)
        save_settings(self._settings)
        logger.info("Notification settings saved: enabled=%s mode=%s callsigns=%s", enabled, mode, callsigns)

    def minimize_window(self):
        """Minimize the window."""
        try:
            self._window.minimize()
        except Exception as e:
            logger.warning("Minimize failed: %s", e)

    def close_app(self):
        """Gracefully shut down the application."""
        try:
            self._worker.request_stop()
            save_settings(self._settings)
        except Exception:
            pass
        try:
            self._window.destroy()
        except Exception:
            pass
        os._exit(0)


def _gui_update_loop(window, flight_queue, status_queue, notif_mgr):
    """
    Background thread that drains the queues and pushes data to the
    WebView frontend via evaluate_js. Runs every 1 second.
    """
    # Wait for DOM to be ready
    time.sleep(2)

    while True:
        try:
            # ── Status updates ──────────────────────────────────────────────
            try:
                while True:
                    status = status_queue.get_nowait()
                    try:
                        window.evaluate_js(f'updateStatus("{status}")')
                    except Exception:
                        pass
            except queue.Empty:
                pass

            # ── Flight data updates ─────────────────────────────────────────
            try:
                while True:
                    flights = flight_queue.get_nowait()
                    notif_mgr.process_flights(flights)
                    try:
                        flights_json = json.dumps(flights)
                        window.evaluate_js(f'updateFlights({flights_json})')
                    except Exception:
                        pass
            except queue.Empty:
                pass

        except Exception as e:
            logger.debug("GUI update error: %s", e)

        time.sleep(1)


def on_loaded(window, settings, worker, notif_mgr, flight_queue, status_queue):
    """Called when the webview DOM is fully loaded. Initializes the map and starts the update loop."""
    # Send initial config to JS
    config = {
        "latitude": settings["latitude"],
        "longitude": settings["longitude"],
        "radius_km": settings["radius_km"],
        "zoom": DEFAULT_ZOOM,
        "speed": settings["speed"],
        "notifications_enabled": settings["notifications_enabled"],
        "notification_mode": settings["notification_mode"],
        "target_callsigns": settings["target_callsigns"],
        "max_altitude_meters": settings["max_altitude_meters"],
        "radius_options": RADIUS_OPTIONS,
    }
    config_json = json.dumps(config)
    window.evaluate_js(f'initMap({config_json})')

    # Start the GUI update loop in a separate thread
    updater = threading.Thread(
        target=_gui_update_loop,
        args=(window, flight_queue, status_queue, notif_mgr),
        daemon=True,
    )
    updater.start()


# ════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Enforce single instance
    _mutex_handle = _acquire_single_instance_mutex()

    # Load settings
    settings = load_settings()

    # Queues for thread-safe communication
    flight_queue = queue.Queue()
    status_queue = queue.Queue()

    # Notification manager
    notif_mgr = NotificationManager(
        enabled=settings["notifications_enabled"],
        mode=settings["notification_mode"],
        target_callsigns=settings["target_callsigns"],
        max_altitude=settings["max_altitude_meters"],
    )

    # Start background OpenSky worker
    interval = SPEED_OPTIONS.get(settings["speed"], 60)
    worker = OpenSkyWorker(
        center_lat=settings["latitude"],
        center_lon=settings["longitude"],
        radius_km=settings["radius_km"],
        interval_seconds=interval,
        result_queue=flight_queue,
        status_queue=status_queue,
    )
    worker.start()

    # Resolve the HTML file path
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

    # Create a placeholder window reference for the API
    # (will be set once the window is created)
    window_holder = {"window": None}

    class APIBridge(TrackerAPI):
        """Thin wrapper to allow late-binding the window reference."""
        def __init__(self, settings, worker, notif_mgr):
            self._settings = settings
            self._worker = worker
            self._notif_mgr = notif_mgr
            self._window = None

        def _set_window(self, w):
            self._window = w

    api = APIBridge(settings, worker, notif_mgr)

    # Create the webview window
    window = webview.create_window(
        title="RJ Airplane Tracker",
        url=html_path,
        width=settings.get("window_width", WIDGET_WIDTH),
        height=settings.get("window_height", WIDGET_HEIGHT),
        min_size=(WIDGET_MIN_WIDTH, WIDGET_MIN_HEIGHT),
        resizable=True,
        frameless=True,
        easy_drag=False,
        js_api=api,
        background_color="#0d1117",
    )
    api._set_window(window)

    def _on_loaded():
        on_loaded(window, settings, worker, notif_mgr, flight_queue, status_queue)

    window.events.loaded += _on_loaded

    # Start the webview event loop (blocks until window closes)
    webview.start(debug=False)

    # Cleanup after window closes
    try:
        worker.request_stop()
        save_settings(settings)
    except Exception:
        pass
    os._exit(0)
