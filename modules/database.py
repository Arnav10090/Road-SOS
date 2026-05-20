"""
modules/database.py
RoadSoS - SQLite Database Manager with R-Tree Spatial Indexing

Architecture:
  - SQLite + R*Tree module for sub-millisecond offline spatial queries
  - sqlite-vec extension for semantic vector search on emergency data
  - Entire database is bundled offline; no network required

Key Tables:
  - emergency_services      : Core POI data (hospitals, police, etc.)
  - services_rtree          : R-Tree spatial index for fast proximity lookup
  - incident_log            : Local incident/distress log for Sanjaya export
  - vector_embeddings       : sqlite-vec table for semantic similarity search
"""

import sqlite3
import json
import struct
import math
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime


def serialize_vector(v: List[float]) -> bytes:
    """Serialize a float list to bytes for sqlite-vec storage."""
    return struct.pack(f"{len(v)}f", *v)


def deserialize_vector(b: bytes) -> List[float]:
    """Deserialize bytes back to float list."""
    n = len(b) // 4
    return list(struct.unpack(f"{n}f", b))


class DatabaseManager:
    """
    Manages the offline SQLite spatial database for RoadSoS.
    Uses R*Tree for geospatial queries and sqlite-vec for semantic search.
    """

    def __init__(self, db_path: str = "data/roadsos.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._vec_available = False

    def get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._load_extensions()
        return self._conn

    def _load_extensions(self):
        """Attempt to load sqlite-vec extension for vector search."""
        conn = self._conn
        conn.enable_load_extension(True)
        # Try loading sqlite-vec (sqlite-vector extension)
        for ext_name in ["sqlite_vec", "vec0", "vector"]:
            try:
                conn.load_extension(ext_name)
                self._vec_available = True
                print(f"[DB] sqlite-vec extension loaded: {ext_name}")
                break
            except sqlite3.OperationalError:
                continue
        if not self._vec_available:
            print("[DB] sqlite-vec not available; falling back to keyword search.")
        conn.enable_load_extension(False)

    def initialize_schema(self):
        """Create all tables, indexes, and virtual tables."""
        conn = self.get_connection()
        with conn:
            # ── Core emergency services table ──────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emergency_services (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    osm_id          TEXT UNIQUE,
                    name            TEXT NOT NULL,
                    service_type    TEXT NOT NULL,   -- hospital|police|ambulance|towing|puncture|trauma_center
                    sub_type        TEXT,            -- e.g., trauma_center, primary_care
                    latitude        REAL NOT NULL,
                    longitude       REAL NOT NULL,
                    phone           TEXT,
                    address         TEXT,
                    country_code    TEXT DEFAULT 'IN',
                    state_code      TEXT,
                    is_24h          INTEGER DEFAULT 0,
                    has_emergency   INTEGER DEFAULT 0,  -- emergency=yes tag
                    has_trauma      INTEGER DEFAULT 0,  -- trauma_center=yes tag
                    extra_tags      TEXT,            -- JSON blob of additional OSM tags
                    last_updated    TEXT DEFAULT (datetime('now'))
                )
            """)

            # ── R*Tree spatial index (core offline geo-query engine) ───────
            # minLat, maxLat, minLon, maxLon define the bounding box per service
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS services_rtree
                USING rtree(
                    id,
                    min_lat, max_lat,
                    min_lon, max_lon
                )
            """)

            # ── Trigger: auto-populate R-Tree on insert ────────────────────
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS after_service_insert
                AFTER INSERT ON emergency_services
                BEGIN
                    INSERT OR REPLACE INTO services_rtree(id, min_lat, max_lat, min_lon, max_lon)
                    VALUES (NEW.id, NEW.latitude, NEW.latitude, NEW.longitude, NEW.longitude);
                END
            """)

            # ── Trigger: update R-Tree on update ──────────────────────────
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS after_service_update
                AFTER UPDATE ON emergency_services
                BEGIN
                    UPDATE services_rtree
                    SET min_lat = NEW.latitude, max_lat = NEW.latitude,
                        min_lon = NEW.longitude, max_lon = NEW.longitude
                    WHERE id = NEW.id;
                END
            """)

            # ── Vector embeddings table (sqlite-vec format) ───────────────
            if self._vec_available:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS service_embeddings (
                        service_id  INTEGER PRIMARY KEY,
                        embedding   BLOB NOT NULL,
                        text_repr   TEXT NOT NULL
                    )
                """)
            else:
                # Fallback: full-text search table
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS services_fts
                    USING fts5(service_id UNINDEXED, text_repr)
                """)

            # ── Incident log (for CoERS Sanjaya GeoJSON export) ───────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incident_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT DEFAULT (datetime('now')),
                    latitude        REAL,
                    longitude       REAL,
                    incident_type   TEXT,
                    severity        TEXT,  -- critical|high|moderate|low
                    description     TEXT,
                    dispatched_to   TEXT,  -- JSON list of service IDs contacted
                    sms_sent        INTEGER DEFAULT 0,
                    resolved        INTEGER DEFAULT 0
                )
            """)

            # ── Administrative boundaries for jurisdiction lookup ──────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_boundaries (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT NOT NULL,
                    admin_level     INTEGER,  -- 2=country, 4=state, 6=district
                    country_code    TEXT,
                    state_code      TEXT,
                    geojson_polygon TEXT,      -- Serialized GeoJSON polygon
                    centroid_lat    REAL,
                    centroid_lon    REAL
                )
            """)

            # ── Standard indexes ──────────────────────────────────────────
            conn.execute("CREATE INDEX IF NOT EXISTS idx_service_type ON emergency_services(service_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_country ON emergency_services(country_code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_state ON emergency_services(state_code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_has_emergency ON emergency_services(has_emergency)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_has_trauma ON emergency_services(has_trauma)")

        print("[DB] Schema initialized successfully.")

    def insert_service(self, service: Dict) -> int:
        """Insert a single emergency service; returns new row ID."""
        conn = self.get_connection()
        cursor = conn.execute("""
            INSERT OR REPLACE INTO emergency_services
            (osm_id, name, service_type, sub_type, latitude, longitude,
             phone, address, country_code, state_code, is_24h, has_emergency,
             has_trauma, extra_tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            service.get("osm_id"),
            service.get("name", "Unknown"),
            service.get("service_type"),
            service.get("sub_type"),
            service["latitude"],
            service["longitude"],
            service.get("phone"),
            service.get("address"),
            service.get("country_code", "IN"),
            service.get("state_code"),
            int(service.get("is_24h", False)),
            int(service.get("has_emergency", False)),
            int(service.get("has_trauma", False)),
            json.dumps(service.get("extra_tags", {})),
        ))
        conn.commit()
        return cursor.lastrowid

    def bulk_insert_services(self, services: List[Dict]):
        """Efficiently bulk-insert services."""
        conn = self.get_connection()
        rows = [(
            s.get("osm_id"), s.get("name", "Unknown"), s.get("service_type"),
            s.get("sub_type"), s["latitude"], s["longitude"],
            s.get("phone"), s.get("address"), s.get("country_code", "IN"),
            s.get("state_code"), int(s.get("is_24h", False)),
            int(s.get("has_emergency", False)), int(s.get("has_trauma", False)),
            json.dumps(s.get("extra_tags", {})),
        ) for s in services]
        conn.executemany("""
            INSERT OR IGNORE INTO emergency_services
            (osm_id, name, service_type, sub_type, latitude, longitude,
             phone, address, country_code, state_code, is_24h, has_emergency,
             has_trauma, extra_tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

    def query_rtree_bbox(
        self,
        lat: float,
        lon: float,
        radius_km: float = 20.0,
        service_types: Optional[List[str]] = None,
        trauma_only: bool = False,
        limit: int = 20
    ) -> List[Dict]:
        """
        Core offline spatial query using R*Tree bounding box intersection.
        Converts radius_km to lat/lon deltas for bounding-box pre-filter,
        then computes Haversine distance for precise ranking.
        """
        # Approx degree deltas for bounding box
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))

        min_lat = lat - lat_delta
        max_lat = lat + lat_delta
        min_lon = lon - lon_delta
        max_lon = lon + lon_delta

        conn = self.get_connection()

        # Build dynamic filter
        filters = ""
        params = [min_lat, max_lat, min_lon, max_lon]
        if service_types:
            placeholders = ",".join("?" * len(service_types))
            filters += f" AND es.service_type IN ({placeholders})"
            params.extend(service_types)
        if trauma_only:
            filters += " AND (es.has_trauma = 1 OR es.has_emergency = 1)"

        params.append(limit * 3)  # Fetch extra for Haversine re-ranking

        rows = conn.execute(f"""
            SELECT es.*
            FROM emergency_services es
            JOIN services_rtree rt ON es.id = rt.id
            WHERE rt.min_lat >= ? AND rt.max_lat <= ?
              AND rt.min_lon >= ? AND rt.max_lon <= ?
              {filters}
            LIMIT ?
        """, params).fetchall()

        # Haversine precise ranking
        results = []
        for row in rows:
            d = haversine_km(lat, lon, row["latitude"], row["longitude"])
            item = dict(row)
            item["distance_km"] = round(d, 3)
            item["extra_tags"] = json.loads(item.get("extra_tags") or "{}")
            results.append(item)

        results.sort(key=lambda x: x["distance_km"])
        return results[:limit]

    def log_incident(self, lat: float, lon: float, incident_type: str,
                     severity: str, description: str) -> int:
        """Log an incident for later Sanjaya GeoJSON export."""
        conn = self.get_connection()
        cursor = conn.execute("""
            INSERT INTO incident_log (latitude, longitude, incident_type, severity, description)
            VALUES (?, ?, ?, ?, ?)
        """, (lat, lon, incident_type, severity, description))
        conn.commit()
        return cursor.lastrowid

    def get_recent_incidents(self, limit: int = 100) -> List[Dict]:
        conn = self.get_connection()
        rows = conn.execute("""
            SELECT * FROM incident_log ORDER BY timestamp DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_service_count(self) -> int:
        conn = self.get_connection()
        result = conn.execute("SELECT COUNT(*) FROM emergency_services").fetchone()
        return result[0]

    def is_seeded(self) -> bool:
        return self.get_service_count() > 0

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Haversine formula: shortest great-circle distance between two points.
    Returns distance in kilometers.
    """
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
