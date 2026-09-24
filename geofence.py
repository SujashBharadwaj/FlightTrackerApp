"""
geofence.py - Geofencing utilities for the RJ Airplane Tracker Widget.
Provides bounding-box generation for the OpenSky API and precise Haversine
distance checking. All functions are null-safe to prevent crashes from
incomplete API data.
"""

import math

# Earth's mean radius in kilometres
_EARTH_RADIUS_KM = 6371.0


def compute_bounding_box(center_lat: float, center_lon: float, radius_km: float) -> dict:
    """
    Compute an axis-aligned bounding box around *center* that fully encloses
    a circle of *radius_km* kilometres.

    Returns a dict with keys: lamin, lamax, lomin, lomax
    suitable for direct use as OpenSky query parameters.
    """
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * math.cos(math.radians(center_lat)))

    return {
        "lamin": round(center_lat - delta_lat, 6),
        "lamax": round(center_lat + delta_lat, 6),
        "lomin": round(center_lon - delta_lon, 6),
        "lomax": round(center_lon + delta_lon, 6),
    }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance in kilometres between two
    latitude/longitude points using the Haversine formula.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (math.sin(d_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_inside_geofence(
    lat: object,
    lon: object,
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> bool:
    """
    Return True if the point (*lat*, *lon*) falls within *radius_km* of the
    centre.  Returns False (never raises) when coordinates are None, non-numeric,
    or otherwise invalid - guaranteeing the geofence check never crashes the app.
    """
    try:
        # Coerce to float; catches None, empty strings, and garbage values
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return False

    # Quick sanity: valid geographic range
    if not (-90 <= lat_f <= 90) or not (-180 <= lon_f <= 180):
        return False

    try:
        return haversine_km(lat_f, lon_f, center_lat, center_lon) <= radius_km
    except Exception:
        # Belt-and-braces: never crash on math edge cases
        return False


def geofence_circle_points(
    center_lat: float, center_lon: float, radius_km: float, segments: int = 64
) -> list[tuple[float, float]]:
    """
    Generate a list of (lat, lon) points tracing a circle on the map surface.
    Used to draw the visual geofence boundary on TkinterMapView.
    """
    points = []
    for i in range(segments + 1):
        angle = math.radians(360.0 * i / segments)
        d_lat = (radius_km / 111.0) * math.cos(angle)
        d_lon = (radius_km / (111.0 * math.cos(math.radians(center_lat)))) * math.sin(angle)
        points.append((center_lat + d_lat, center_lon + d_lon))
    return points
