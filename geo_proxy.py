"""
POSIFY Business Network — Geography / Routing Proxy
===================================================
Replaces the previous proprietary map-geo proxy. Uses free, OpenStreetMap-compatible
public services so NO API token is required:

* Geocoding / reverse geocoding -> Nominatim
  (https://nominatim.openstreetmap.org)
* Distance matrix & routing (distance + ETA) -> OSRM public instance
  (https://router.project-osrm.org)

All calls are made server-side (never from the browser) so the backend can
add caching, rate-limiting headers and a User-Agent as required by the
Nominatim usage policy. The browser only ever receives the plain JSON.
"""

from __future__ import annotations

import os
import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional

import requests as _requests

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OSRM_URL = "https://router.project-osrm.org"
DEFAULT_USER_AGENT = "POSIFY-Business-Network/1.0"
DEFAULT_TIMEOUT = 8


def server_configured() -> bool:
    """The public Nominatim/OSRM services need no secret token."""
    return True


@lru_cache(maxsize=1)
def config() -> Dict[str, Any]:
    return {
        "public_token_available": False,
        "server_token_available": False,
        "serverAvailable": True,
        "source": "openstreetmap-nominatim-osrm",
        "mapStyle": "https://tiles.openfreemap.org/styles/liberty",
    }


def _headers() -> Dict[str, str]:
    return {"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "en"}


def geocode_forward(query: str, limit: int = 5) -> Optional[List[Dict[str, Any]]]:
    if not query:
        return None
    try:
        resp = _requests.get(
            f"{NOMINATIM_URL}/search",
            params={"format": "json", "q": query, "limit": limit},
            headers=_headers(), timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return [
            {
                "label": item.get("display_name"),
                "lat": float(item.get("lat")),
                "lng": float(item.get("lon")),
                "type": item.get("class"),
            }
            for item in data
        ] if data else None
    except Exception as exc:
        logger.warning("Nominatim geocode_forward failed: %s", exc)
        return None


def reverse_geocode(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    try:
        resp = _requests.get(
            f"{NOMINATIM_URL}/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lng},
            headers=_headers(), timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("lat") is None:
            return None
        return {
            "label": data.get("display_name"),
            "lat": float(data.get("lat")),
            "lng": float(data.get("lon")),
            "type": data.get("class"),
            "address": data.get("address"),
        }
    except Exception as exc:
        logger.warning("Nominatim reverse_geocode failed: %s", exc)
        return None


def distance_matrix(points: List[Dict[str, float]]) -> Optional[List[List[float]]]:
    """OSRM `table` service -> duration matrix (seconds) for a list of {latitude,longitude}."""
    if not points or len(points) < 2:
        return None
    coords = ";".join(f"{p['longitude']},{p['latitude']}" for p in points)
    try:
        resp = _requests.get(
            f"{OSRM_URL}/table/v1/driving/{coords}",
            headers=_headers(), timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("durations")
    except Exception as exc:
        logger.warning("OSRM matrix failed: %s", exc)
        return None


def route_line(lat: float, lng: float, dest_lat: float, dest_lng: float) -> Optional[Dict[str, Any]]:
    """OSRM route -> distance (meters), duration (seconds) + geometry (geojson LineString)."""
    coords = f"{lng},{lat};{dest_lng},{dest_lat}"
    try:
        resp = _requests.get(
            f"{OSRM_URL}/route/v1/driving/{coords}",
            params={"overview": "simplified", "geometries": "geojson", "alternatives": "false"},
            headers=_headers(), timeout=DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        route = data.get("routes", [{}])[0]
        if not route:
            return None
        return {
            "distance_m": route.get("distance"),
            "duration_s": route.get("duration"),
            "eta_minutes": round(route.get("duration", 0) / 60, 1),
            "geometry": route.get("geometry"),
            "source": "osrm",
        }
    except Exception as exc:
        logger.warning("OSRM route failed: %s", exc)
        return None


def register_geo_routes(app, auth_manager):
    """HTTP endpoints for geocoding / reverse-geocoding / routing (OSM-compatible)."""
    from flask import request as _req
    from auth.decorators import require_auth
    auth = require_auth(auth_manager, None)

    @app.get("/api/geocode")
    @auth
    def geocode():
        q = _req.args.get("q")
        if not q:
            return {"error": "q parameter is required"}, 400
        result = geocode_forward(q)
        return {"result": result, "success": bool(result)}, 200

    @app.get("/api/reverse-geocode")
    @auth
    def reverse_geocode_http():
        lat = _req.args.get("lat", type=float)
        lng = _req.args.get("lng", type=float)
        if lat is None or lng is None:
            return {"error": "lat and lng parameters are required"}, 400
        result = reverse_geocode(lat, lng)
        return {"result": result, "success": bool(result)}, 200

    @app.get("/api/route")
    @auth
    def route_http():
        lat = _req.args.get("from_lat", type=float)
        lng = _req.args.get("from_lng", type=float)
        tlat = _req.args.get("to_lat", type=float)
        tlng = _req.args.get("to_lng", type=float)
        if None in (lat, lng, tlat, tlng):
            return {"error": "from_lat,from_lng,to_lat,to_lng are required"}, 400
        from network_models import haversine_km, etamp_from_km
        route = route_line(lat, lng, tlat, tlng)
        if not route:
            dist = haversine_km(lat, lng, tlat, tlng)
            return {"distance_km": round(dist, 2), "duration_s": round(etamp_from_km(dist) * 60, 1),
                    "eta_minutes": etamp_from_km(dist), "geometry": None, "source": "haversine-fallback",
                    "success": True}, 200
        return route, 200

    @app.get("/api/matrix")
    @auth
    def matrix_http():
        raw = _req.args.get("points")
        if not raw:
            return {"error": "points query param required (lat,lng;lat,lng;...)"}, 400
        points = []
        for pair in raw.split(";"):
            a, b = pair.split(",")
            points.append({"latitude": float(a), "longitude": float(b)})
        if len(points) < 2:
            return {"error": "need at least 2 points"}, 400
        matrix = distance_matrix(points)
        return {"matrix": matrix, "success": bool(matrix)}, 200
