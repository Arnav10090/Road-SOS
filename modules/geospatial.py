"""
modules/geospatial.py
RoadSoS - Offline Geospatial Engine

Architecture:
  - Pure offline geofencing using GeoJSON administrative boundaries
  - No Google Maps API, no network dependency
  - GPS latitude/longitude read directly from device GNSS hardware
  - GeoPandas + Shapely for polygon containment checks
  - R-Tree backed SQLite queries for instant proximity search

Global applicability: GeoJSON admin boundaries cover all countries.
"""

import json
import math
import os
from typing import Dict, List, Optional, Tuple

# Graceful import of geospatial stack
try:
    import geopandas as gpd
    from shapely.geometry import Point, shape
    GEOPANDAS_AVAILABLE = True
except ImportError:
    GEOPANDAS_AVAILABLE = False
    print("[Geo] GeoPandas not available; using fallback bounding-box geofencing.")

from .database import DatabaseManager, haversine_km


# Priority ordering for triage-based service type display
SEVERITY_SERVICE_MAP = {
    "critical": ["hospital", "trauma_center", "ambulance", "police"],
    "high":     ["hospital", "ambulance", "police", "towing"],
    "moderate": ["hospital", "police", "towing", "puncture"],
    "low":      ["police", "hospital", "towing", "puncture"],
}

# Friendly display names for service types
SERVICE_LABELS = {
    "hospital":     "🏥 Hospital / Trauma Centre",
    "trauma_center":"🚨 Trauma Centre",
    "ambulance":    "🚑 Ambulance Service",
    "police":       "🚔 Police Station",
    "towing":       "🔧 Towing / Vehicle Rescue",
    "puncture":     "🔩 Puncture Shop / Mechanic",
    "fire":         "🚒 Fire Station",
}


class GeospatialEngine:
    """
    Handles all offline location operations:
      1. Reverse geocoding (jurisdiction from GPS coords)
      2. Proximity search via SQLite R*Tree
      3. OSM GeoJSON boundary loading
    """

    def __init__(self, db: DatabaseManager, boundaries_path: str = "data/admin_boundaries.geojson"):
        self.db = db
        self.boundaries_path = boundaries_path
        self._gdf = None  # GeoDataFrame, loaded lazily
        self._loaded = False

    def _load_boundaries(self):
        """Lazily load GeoJSON administrative boundaries into a GeoDataFrame."""
        if self._loaded:
            return
        self._loaded = True

        if not GEOPANDAS_AVAILABLE:
            return

        if not os.path.exists(self.boundaries_path):
            print(f"[Geo] Boundaries file not found: {self.boundaries_path}")
            print("[Geo] Jurisdiction detection disabled; all queries will use global dataset.")
            return

        try:
            self._gdf = gpd.read_file(self.boundaries_path)
            print(f"[Geo] Loaded {len(self._gdf)} administrative boundaries.")
        except Exception as e:
            print(f"[Geo] Could not load boundaries: {e}")

    def get_jurisdiction(self, lat: float, lon: float) -> Dict:
        """
        Determine the administrative jurisdiction for given GPS coordinates.
        Fully offline - uses Shapely Point-in-Polygon via GeoPandas spatial join.

        Returns: dict with country_code, state_code, district, name
        """
        self._load_boundaries()

        if not GEOPANDAS_AVAILABLE or self._gdf is None:
            return self._fallback_jurisdiction(lat, lon)

        try:
            point = Point(lon, lat)  # GeoJSON = (lon, lat)
            point_gdf = gpd.GeoDataFrame([{"geometry": point}], crs="EPSG:4326")
            joined = gpd.sjoin(point_gdf, self._gdf, how="left", predicate="within")
            if not joined.empty and not joined.iloc[0].isnull().all():
                row = joined.iloc[0]
                return {
                    "country_code": str(row.get("ISO_A2", "IN")),
                    "state_code":   str(row.get("STATE_CODE", "")),
                    "district":     str(row.get("DISTRICT", "")),
                    "name":         str(row.get("NAME", "Unknown Area")),
                    "admin_level":  int(row.get("ADMIN_LVL", 4)),
                }
        except Exception as e:
            print(f"[Geo] Spatial join error: {e}")

        return self._fallback_jurisdiction(lat, lon)

    def _fallback_jurisdiction(self, lat: float, lon: float) -> Dict:
        """
        Fallback jurisdiction using rough bounding boxes for major regions.
        Used when GeoPandas is unavailable or boundary file is missing.
        """
        # India bounding box
        if 8.0 <= lat <= 37.6 and 68.0 <= lon <= 97.4:
            return {"country_code": "IN", "state_code": "XX", "name": "India", "admin_level": 2}
        # UK
        if 49.8 <= lat <= 60.9 and -8.6 <= lon <= 1.8:
            return {"country_code": "GB", "state_code": "ENG", "name": "United Kingdom", "admin_level": 2}
        # USA
        if 24.4 <= lat <= 49.4 and -125.0 <= lon <= -66.9:
            return {"country_code": "US", "state_code": "XX", "name": "United States", "admin_level": 2}
        return {"country_code": "XX", "state_code": "XX", "name": "Unknown Region", "admin_level": 0}

    def get_nearest_services(
        self,
        lat: float,
        lon: float,
        severity: str = "moderate",
        radius_km: float = 25.0,
        limit: int = 5,
        trauma_only: bool = False,
    ) -> List[Dict]:
        """
        Main proximity query - returns ranked list of nearest emergency services.

        Workflow:
          1. R-Tree bounding box pre-filter (instant, offline)
          2. Haversine precise distance calculation
          3. Severity-based service type prioritization
          4. Returns top-N sorted by distance within priority tiers
        """
        # Get priority service types for this severity level
        priority_types = SEVERITY_SERVICE_MAP.get(severity, SEVERITY_SERVICE_MAP["moderate"])

        # For critical incidents, prefer trauma centers / hospitals with emergency=yes
        force_trauma = severity == "critical"

        results = self.db.query_rtree_bbox(
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            service_types=priority_types,
            trauma_only=force_trauma,
            limit=limit * 4,  # Over-fetch for filtering
        )

        if not results and force_trauma:
            # Widen search if no trauma centers found
            results = self.db.query_rtree_bbox(
                lat=lat, lon=lon, radius_km=radius_km * 2,
                service_types=priority_types, trauma_only=False, limit=limit * 4
            )

        # Priority-rank: first by severity tier, then by distance
        def sort_key(item):
            stype = item.get("service_type", "")
            tier = priority_types.index(stype) if stype in priority_types else 99
            return (tier, item["distance_km"])

        results.sort(key=sort_key)

        # Add display metadata
        for r in results:
            r["label"] = SERVICE_LABELS.get(r.get("service_type", ""), r.get("service_type", ""))
            r["directions_hint"] = bearing_to_direction(
                bearing(lat, lon, r["latitude"], r["longitude"])
            )

        return results[:limit]

    def format_services_for_display(self, services: List[Dict], user_lat: float, user_lon: float) -> str:
        """Format service list into human-readable emergency response output."""
        if not services:
            return "No emergency services found in your area within the search radius."

        lines = []
        for i, svc in enumerate(services, 1):
            phone_str = f" | ☎ {svc['phone']}" if svc.get("phone") else ""
            emergency_tag = " [EMERGENCY FACILITY]" if svc.get("has_emergency") or svc.get("has_trauma") else ""
            lines.append(
                f"{i}. {svc.get('label', svc['service_type'])}{emergency_tag}\n"
                f"   {svc['name']}\n"
                f"   📍 {svc.get('distance_km', '?')} km {svc.get('directions_hint', '')}{phone_str}\n"
                f"   {svc.get('address', 'Address not available')}"
            )
        return "\n\n".join(lines)


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate compass bearing from point 1 to point 2."""
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2r)
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def bearing_to_direction(deg: float) -> str:
    """Convert bearing degrees to cardinal direction string."""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[round(deg / 45) % 8]
