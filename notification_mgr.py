"""
notification_mgr.py - Smart notification manager for the RJ Airplane Tracker.
Tracks which aircraft have already been alerted, respects user-configurable
filters (all / specific callsigns / low altitude), seeds the first poll to
prevent startup spam, filters ground vehicles, and batches multiple
simultaneous arrivals into grouped toast notifications.
"""

import logging
import time
import threading

from config import MAX_TOASTS_PER_POLL, MIN_AIRBORNE_ALTITUDE_M

logger = logging.getLogger(__name__)

# Attempt to import win11toast; fall back gracefully if unavailable
try:
    from win11toast import notify as _win_notify
    _HAS_WIN11TOAST = True
except ImportError:
    _HAS_WIN11TOAST = False
    logger.warning("win11toast not installed – notifications disabled.")


class NotificationManager:
    """
    Manages aircraft notification deduplication and user filter preferences.

    Key behaviours:
    - First poll is silently seeded (no notifications fired on startup).
    - Ground vehicles (on_ground=True, altitude < threshold) are ignored.
    - At most MAX_TOASTS_PER_POLL individual toasts per cycle; extras grouped.
    - Aircraft that leave the zone for >expiry_seconds can re-trigger.

    Attributes:
        enabled:           Master toggle.
        mode:              "ALL" | "SPECIFIC" | "LOW_ALTITUDE"
        target_callsigns:  List of callsign patterns to watch (SPECIFIC mode).
        max_altitude:      Max altitude in metres for LOW_ALTITUDE mode.
    """

    def __init__(
        self,
        enabled: bool = True,
        mode: str = "ALL",
        target_callsigns: list[str] | None = None,
        max_altitude: float = 1500.0,
        expiry_seconds: int = 600,
    ):
        self.enabled = enabled
        self.mode = mode
        self.target_callsigns = [cs.upper() for cs in (target_callsigns or [])]
        self.max_altitude = max_altitude
        self._expiry = expiry_seconds

        # {icao24: last_seen_timestamp}
        self._notified: dict[str, float] = {}
        self._lock = threading.Lock()

        # First-poll flag: True until the first batch of flights is processed
        self._first_poll = True

    # ── Public interface ────────────────────────────────────────────────────

    def process_flights(self, flights: list[dict]) -> None:
        """
        Evaluate a batch of flights against the current notification rules.
        On the first poll, all aircraft are silently seeded (no toasts).
        On subsequent polls, only new arrivals trigger notifications.
        """
        now = time.time()
        self._prune_expired(now)

        # ── First-poll seeding: mark all current aircraft as seen ───────────
        if self._first_poll:
            with self._lock:
                for flight in flights:
                    icao24 = flight.get("icao24")
                    if icao24:
                        self._notified[icao24] = now
            self._first_poll = False
            logger.info("First poll seeded: %d aircraft silently registered.", len(flights))
            return

        # ── Notifications disabled: still track for deduplication ───────────
        if not self.enabled:
            with self._lock:
                for flight in flights:
                    icao24 = flight.get("icao24")
                    if icao24:
                        self._notified[icao24] = now
            return

        # ── Process new arrivals ────────────────────────────────────────────
        new_qualifying = []
        for flight in flights:
            icao24 = flight.get("icao24")
            if not icao24:
                continue

            with self._lock:
                if icao24 in self._notified:
                    # Already alerted; just refresh timestamp
                    self._notified[icao24] = now
                    continue

            # Check if this is actually an overhead flight (not ground)
            if not self._is_overhead(flight):
                with self._lock:
                    self._notified[icao24] = now  # Track it but don't notify
                continue

            if self._matches_filter(flight):
                new_qualifying.append(flight)
                with self._lock:
                    self._notified[icao24] = now
            else:
                with self._lock:
                    self._notified[icao24] = now  # Track non-matching too

        # ── Fire notifications with throttling ──────────────────────────────
        if new_qualifying:
            self._fire_batch(new_qualifying)

    def update_preferences(
        self,
        enabled: bool | None = None,
        mode: str | None = None,
        target_callsigns: list[str] | None = None,
        max_altitude: float | None = None,
    ) -> None:
        """Live-update notification preferences from the settings UI."""
        if enabled is not None:
            self.enabled = enabled
        if mode is not None:
            self.mode = mode
        if target_callsigns is not None:
            self.target_callsigns = [cs.upper() for cs in target_callsigns]
        if max_altitude is not None:
            self.max_altitude = max_altitude

    # ── Internal helpers ────────────────────────────────────────────────────

    def _is_overhead(self, flight: dict) -> bool:
        """Return True only if the aircraft is airborne overhead."""
        if flight.get("on_ground"):
            return False
        altitude = flight.get("altitude")
        if altitude is None:
            return False
        return altitude >= MIN_AIRBORNE_ALTITUDE_M

    def _matches_filter(self, flight: dict) -> bool:
        """Check whether a flight should trigger a notification per current mode."""
        if self.mode == "ALL":
            return True

        callsign = (flight.get("callsign") or "").upper()
        altitude = flight.get("altitude")

        if self.mode == "SPECIFIC":
            if not self.target_callsigns:
                return False  # No targets configured
            return any(
                callsign == target or callsign.startswith(target)
                for target in self.target_callsigns
            )

        if self.mode == "LOW_ALTITUDE":
            if altitude is None:
                return False
            return altitude <= self.max_altitude

        return False

    def _fire_batch(self, flights: list[dict]) -> None:
        """
        Fire toast notifications for a batch of new flights.
        If there are more than MAX_TOASTS_PER_POLL, send individual toasts
        for the first few and a grouped summary for the rest.
        """
        individual = flights[:MAX_TOASTS_PER_POLL]
        grouped = flights[MAX_TOASTS_PER_POLL:]

        for flight in individual:
            self._fire_single_notification(flight)

        if grouped:
            callsigns = [f.get("callsign", "N/A") for f in grouped]
            title = f"✈️ +{len(grouped)} more aircraft in zone"
            body = ", ".join(callsigns)
            logger.info("Grouped notification → %s: %s", title, body)
            if _HAS_WIN11TOAST:
                try:
                    threading.Thread(
                        target=_win_notify,
                        kwargs={"title": title, "body": body, "app_id": "RJ Airplane Tracker"},
                        daemon=True,
                    ).start()
                except Exception as e:
                    logger.error("Grouped toast failed: %s", e)

    def _fire_single_notification(self, flight: dict) -> None:
        """Send a native Windows 11 toast notification for a single flight."""
        callsign = flight.get("callsign", "N/A")
        alt = flight.get("altitude")
        speed = flight.get("velocity")
        origin = flight.get("origin_country", "")

        alt_str = f"{alt:.0f}m" if alt is not None else "N/A"
        speed_str = f"{speed:.0f} km/h" if speed is not None else "N/A"

        title = "✈️ Aircraft Overhead Mumbai"
        body = f"{callsign}  |  Alt: {alt_str}  |  Speed: {speed_str}"
        if origin:
            body += f"  |  {origin}"

        logger.info("Notification → %s: %s", title, body)

        if _HAS_WIN11TOAST:
            try:
                # Run in separate thread to avoid blocking the GUI loop
                threading.Thread(
                    target=_win_notify,
                    kwargs={"title": title, "body": body, "app_id": "RJ Airplane Tracker"},
                    daemon=True,
                ).start()
            except Exception as e:
                logger.error("Toast notification failed: %s", e)

    def _prune_expired(self, now: float) -> None:
        """Remove aircraft that left the zone long enough ago to re-trigger."""
        with self._lock:
            expired_keys = [
                k for k, ts in self._notified.items()
                if (now - ts) > self._expiry
            ]
            for k in expired_keys:
                del self._notified[k]
