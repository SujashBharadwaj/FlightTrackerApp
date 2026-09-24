"""
opensky_service.py - Background polling thread for the OpenSky Network API.
Fetches live flight data within the configured bounding box, filters through
the geofence, and delivers results to the GUI via a thread-safe queue.
Respects Wi-Fi-only policy and user-adjustable polling speed.
"""

import logging
import queue
import threading
import time

import requests

from geofence import compute_bounding_box, is_inside_geofence
from wifi_detector import is_wifi_connected
from config import IGNORE_GROUND_VEHICLES, MIN_AIRBORNE_ALTITUDE_M

logger = logging.getLogger(__name__)

OPENSKY_API_URL = "https://opensky-network.org/api/states/all"

# ─── OpenSky state-vector field indices ─────────────────────────────────────
_ICAO24 = 0
_CALLSIGN = 1
_ORIGIN_COUNTRY = 2
_LONGITUDE = 5
_LATITUDE = 6
_BARO_ALT = 7
_ON_GROUND = 8
_VELOCITY = 9
_TRUE_TRACK = 10
_VERTICAL_RATE = 11


def _parse_aircraft(
    state: list,
    center_lat: float,
    center_lon: float,
    radius_km: float,
    filter_ground: bool = True,
) -> dict | None:
    """
    Parse a single OpenSky state vector into a clean dictionary.
    Returns None if coordinates are missing, outside the geofence,
    or if the aircraft is on the ground (when filter_ground is True).
    """
    try:
        lat = state[_LATITUDE]
        lon = state[_LONGITUDE]

        # Skip aircraft with no position data
        if lat is None or lon is None:
            return None

        # Strict geofence check (Haversine)
        if not is_inside_geofence(lat, lon, center_lat, center_lon, radius_km):
            return None

        callsign = (state[_CALLSIGN] or "").strip() or "N/A"
        altitude = state[_BARO_ALT]  # May be None
        velocity = state[_VELOCITY]  # May be None (m/s)
        heading = state[_TRUE_TRACK]
        on_ground = state[_ON_GROUND]
        vertical_rate = state[_VERTICAL_RATE]

        # Filter out ground vehicles, taxiing aircraft, and parked planes
        if filter_ground and on_ground:
            return None
        if filter_ground and altitude is not None and float(altitude) < MIN_AIRBORNE_ALTITUDE_M:
            return None

        return {
            "icao24": state[_ICAO24],
            "callsign": callsign,
            "origin_country": state[_ORIGIN_COUNTRY] or "Unknown",
            "latitude": float(lat),
            "longitude": float(lon),
            "altitude": round(float(altitude), 1) if altitude is not None else None,
            "velocity": round(float(velocity) * 3.6, 1) if velocity is not None else None,  # m/s → km/h
            "velocity_knots": round(float(velocity) * 1.944, 1) if velocity is not None else None,
            "heading": float(heading) if heading is not None else 0.0,
            "on_ground": bool(on_ground),
            "vertical_rate": float(vertical_rate) if vertical_rate is not None else 0.0,
            "altitude_ft": round(float(altitude) * 3.281, 0) if altitude is not None else None,
        }
    except (IndexError, TypeError, ValueError) as e:
        logger.debug("Skipping malformed state vector: %s", e)
        return None


class OpenSkyWorker(threading.Thread):
    """
    Daemon thread that periodically fetches flight data from OpenSky,
    filters it through the geofence, and pushes results into a queue.

    Attributes:
        result_queue: Thread-safe queue consumed by the GUI to update markers.
        status_queue: Thread-safe queue for status messages (str) shown in the header.
    """

    def __init__(
        self,
        center_lat: float,
        center_lon: float,
        radius_km: float,
        interval_seconds: int,
        result_queue: queue.Queue,
        status_queue: queue.Queue,
    ):
        super().__init__(daemon=True)
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.radius_km = radius_km
        self._interval = interval_seconds
        self.result_queue = result_queue
        self.status_queue = status_queue
        self._stop_event = threading.Event()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "RJAirplaneTracker/1.0"})
        self._geofence_lock = threading.Lock()

        # Rolling registry of all detected callsigns (for the UI picker)
        # {callsign: {icao24, altitude, last_seen_timestamp}}
        self._detected_callsigns: dict[str, dict] = {}
        self._callsigns_lock = threading.Lock()

    # ── Public controls ─────────────────────────────────────────────────────

    def set_interval(self, seconds: int) -> None:
        """Update the polling interval (called from GUI thread)."""
        self._interval = max(10, seconds)  # Floor at 10s for safety

    def update_geofence(self, center_lat: float, center_lon: float, radius_km: float) -> None:
        """Thread-safe update of the geofence parameters. Takes effect on next poll."""
        with self._geofence_lock:
            self.center_lat = center_lat
            self.center_lon = center_lon
            self.radius_km = radius_km
        logger.info("Geofence updated: (%.4f, %.4f) radius=%.1fkm", center_lat, center_lon, radius_km)

    def get_detected_callsigns(self) -> list[dict]:
        """Return a snapshot of recently detected callsigns for the UI picker."""
        now = time.time()
        with self._callsigns_lock:
            # Prune entries older than 10 minutes
            stale_keys = [k for k, v in self._detected_callsigns.items() if now - v["last_seen"] > 600]
            for k in stale_keys:
                del self._detected_callsigns[k]
            return [
                {"callsign": cs, "icao24": info.get("icao24", ""), "altitude": info.get("altitude")}
                for cs, info in self._detected_callsigns.items()
            ]

    def request_stop(self) -> None:
        """Signal the thread to shut down gracefully."""
        self._stop_event.set()

    # ── Main loop ───────────────────────────────────────────────────────────

    def run(self) -> None:
        logger.info("OpenSky worker started (interval=%ds)", self._interval)
        while not self._stop_event.is_set():
            self._poll_once()
            # Sleep in small increments so we can respond to stop quickly
            for _ in range(self._interval * 2):
                if self._stop_event.is_set():
                    break
                time.sleep(0.5)
        logger.info("OpenSky worker stopped.")

    def _poll_once(self) -> None:
        """Execute a single fetch-parse-enqueue cycle."""

        # ── Wi-Fi gate ──────────────────────────────────────────────────────────
        wifi_ok, _wifi_info = is_wifi_connected()
        if not wifi_ok:
            self.status_queue.put("paused_wifi")
            logger.info("Wi-Fi not connected. Skipping poll.")
            return

        # ── Build bounding box (thread-safe read) ────────────────────────────
        with self._geofence_lock:
            c_lat = self.center_lat
            c_lon = self.center_lon
            r_km = self.radius_km
        bbox = compute_bounding_box(c_lat, c_lon, r_km)

        try:
            self.status_queue.put("fetching")
            resp = self._session.get(
                OPENSKY_API_URL,
                params=bbox,
                timeout=15,
            )

            if resp.status_code == 429:
                self.status_queue.put("rate_limited")
                logger.warning("OpenSky 429 – rate limited; backing off.")
                return

            if resp.status_code == 503:
                self.status_queue.put("api_unavailable")
                logger.warning("OpenSky 503 – service unavailable.")
                return

            resp.raise_for_status()
            data = resp.json()

        except requests.exceptions.Timeout:
            self.status_queue.put("timeout")
            logger.warning("OpenSky request timed out.")
            return
        except requests.exceptions.ConnectionError:
            self.status_queue.put("no_connection")
            logger.warning("Network connection error.")
            return
        except requests.exceptions.RequestException as e:
            self.status_queue.put("api_error")
            logger.error("OpenSky request failed: %s", e)
            return
        except ValueError:
            self.status_queue.put("bad_response")
            logger.error("Failed to decode OpenSky JSON.")
            return

        # ── Parse & geofence filter ─────────────────────────────────────────
        states = data.get("states") or []
        flights = []
        now = time.time()
        for state_vec in states:
            aircraft = _parse_aircraft(
                state_vec,
                c_lat,
                c_lon,
                r_km,
                filter_ground=IGNORE_GROUND_VEHICLES,
            )
            if aircraft is not None:
                flights.append(aircraft)
                # Register in rolling callsign list
                cs = aircraft.get("callsign", "N/A")
                if cs and cs != "N/A":
                    with self._callsigns_lock:
                        self._detected_callsigns[cs] = {
                            "icao24": aircraft.get("icao24", ""),
                            "altitude": aircraft.get("altitude"),
                            "last_seen": now,
                        }

        self.result_queue.put(flights)
        airborne_count = len([f for f in flights if not f.get("on_ground")])
        self.status_queue.put(f"live:{airborne_count}")
        logger.info("Fetched %d states, %d airborne within geofence.", len(states), len(flights))
