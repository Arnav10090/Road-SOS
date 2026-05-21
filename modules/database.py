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
    ) -> Dict:
        """
        Core offline spatial query using R*Tree bounding box intersection.
        Converts radius_km to lat/lon deltas for bounding-box pre-filter,
        then computes Haversine distance for precise ranking.

        Returns:
            dict with keys:
                - total_found (int): total services matching bbox + filters
                - services (List[Dict]): top-N results sorted by Haversine distance
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
        base_params = [min_lat, max_lat, min_lon, max_lon]
        filter_params = []
        if service_types:
            placeholders = ",".join("?" * len(service_types))
            filters += f" AND es.service_type IN ({placeholders})"
            filter_params.extend(service_types)
        if trauma_only:
            filters += " AND (es.has_trauma = 1 OR es.has_emergency = 1)"

        # ── Count total matching contacts in geofenced radius ──────────
        count_params = base_params + filter_params
        total_found = conn.execute(f"""
            SELECT COUNT(*)
            FROM emergency_services es
            JOIN services_rtree rt ON es.id = rt.id
            WHERE rt.min_lat >= ? AND rt.max_lat <= ?
              AND rt.min_lon >= ? AND rt.max_lon <= ?
              {filters}
        """, count_params).fetchone()[0]

        # ── Fetch rows for Haversine re-ranking (over-fetch for precision) ─
        fetch_params = base_params + filter_params + [limit * 3]
        rows = conn.execute(f"""
            SELECT es.*
            FROM emergency_services es
            JOIN services_rtree rt ON es.id = rt.id
            WHERE rt.min_lat >= ? AND rt.max_lat <= ?
              AND rt.min_lon >= ? AND rt.max_lon <= ?
              {filters}
            LIMIT ?
        """, fetch_params).fetchall()

        # Haversine precise ranking
        results = []
        for row in rows:
            d = haversine_km(lat, lon, row["latitude"], row["longitude"])
            item = dict(row)
            item["distance_km"] = round(d, 3)
            item["extra_tags"] = json.loads(item.get("extra_tags") or "{}")
            results.append(item)

        results.sort(key=lambda x: x["distance_km"])
        return {"total_found": total_found, "services": results[:limit]}

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

    # ── Offline Semantic / RAG Search ──────────────────────────────────

    def query_semantic_services(
        self,
        query_text: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        radius_km: float = 50.0,
        limit: int = 10,
    ) -> Dict:
        """
        Offline semantic (RAG) search over emergency services using sqlite-vec
        vector embeddings or FTS5 full-text fallback.

        Returns:
            dict with keys:
                - total_found (int): total semantically indexed services
                - services (List[Dict]): results ranked by semantic relevance
        """
        conn = self.get_connection()
        if self._vec_available:
            return self._query_vec_services(conn, query_text, lat, lon, radius_km, limit)
        return self._query_fts_services(conn, query_text, lat, lon, radius_km, limit)

    def _query_vec_services(
        self, conn: sqlite3.Connection, query_text: str,
        lat: Optional[float], lon: Optional[float],
        radius_km: float, limit: int,
    ) -> Dict:
        """Vector similarity search using sqlite-vec cosine distance."""
        query_embedding = self._text_to_embedding(query_text)
        query_blob = serialize_vector(query_embedding)

        total = conn.execute("SELECT COUNT(*) FROM service_embeddings").fetchone()[0]
        try:
            rows = conn.execute("""
                SELECT se.service_id, se.text_repr,
                       vec_distance_cosine(se.embedding, ?) AS vec_distance,
                       es.*
                FROM service_embeddings se
                JOIN emergency_services es ON se.service_id = es.id
                ORDER BY vec_distance ASC
                LIMIT ?
            """, (query_blob, limit * 3)).fetchall()
        except Exception as e:
            print(f"[DB] sqlite-vec vector query failed: {e}; falling back to FTS5.")
            return self._query_fts_services(conn, query_text, lat, lon, radius_km, limit)

        results = []
        for row in rows:
            item = dict(row)
            item["semantic_score"] = round(
                1.0 - min(float(item.get("vec_distance", 1.0)), 1.0), 4
            )
            item["extra_tags"] = json.loads(item.get("extra_tags") or "{}")
            if lat is not None and lon is not None:
                item["distance_km"] = round(
                    haversine_km(lat, lon, item["latitude"], item["longitude"]), 3
                )
            results.append(item)

        # If location provided, re-rank by combined score (70% semantic, 30% proximity)
        if lat is not None and lon is not None and results:
            max_dist = max(r.get("distance_km", 1) for r in results) or 1
            for r in results:
                proximity = 1.0 - min(r.get("distance_km", max_dist) / max_dist, 1.0)
                r["combined_score"] = round(
                    0.7 * r["semantic_score"] + 0.3 * proximity, 4
                )
            results.sort(key=lambda x: x["combined_score"], reverse=True)

        return {"total_found": total, "services": results[:limit]}

    def _query_fts_services(
        self, conn: sqlite3.Connection, query_text: str,
        lat: Optional[float], lon: Optional[float],
        radius_km: float, limit: int,
    ) -> Dict:
        """Full-text search fallback when sqlite-vec is not available."""
        fts_terms = [w for w in query_text.lower().split() if len(w) > 2]
        fts_query = " OR ".join(fts_terms) if fts_terms else query_text.lower()

        try:
            total = conn.execute("SELECT COUNT(*) FROM services_fts").fetchone()[0]
            rows = conn.execute("""
                SELECT sf.service_id, sf.text_repr, rank,
                       es.*
                FROM services_fts sf
                JOIN emergency_services es ON CAST(sf.service_id AS INTEGER) = es.id
                WHERE services_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit * 3)).fetchall()
        except Exception:
            return {"total_found": 0, "services": []}

        results = []
        for row in rows:
            item = dict(row)
            item["semantic_score"] = round(
                1.0 / (1.0 + abs(float(item.get("rank", 0)))), 4
            )
            item["extra_tags"] = json.loads(item.get("extra_tags") or "{}")
            if lat is not None and lon is not None:
                item["distance_km"] = round(
                    haversine_km(lat, lon, item["latitude"], item["longitude"]), 3
                )
            results.append(item)

        return {"total_found": total, "services": results[:limit]}

    def build_service_embeddings(self) -> int:
        """
        Generate and store text embeddings for all emergency services.
        Populates sqlite-vec embeddings or FTS5 index for the offline RAG pipeline.
        Returns the number of services indexed.
        """
        conn = self.get_connection()
        services = conn.execute("SELECT * FROM emergency_services").fetchall()
        count = 0

        for svc in services:
            text_repr = (
                f"{svc['name']} | {svc['service_type']} | "
                f"{svc.get('sub_type') or ''} | "
                f"{svc.get('address') or ''} | "
                f"{svc.get('phone') or ''} | "
                f"emergency={'yes' if svc.get('has_emergency') else 'no'} "
                f"trauma={'yes' if svc.get('has_trauma') else 'no'}"
            )

            if self._vec_available:
                embedding = self._text_to_embedding(text_repr)
                conn.execute("""
                    INSERT OR REPLACE INTO service_embeddings
                    (service_id, embedding, text_repr) VALUES (?, ?, ?)
                """, (svc["id"], serialize_vector(embedding), text_repr))
            else:
                conn.execute("""
                    INSERT OR REPLACE INTO services_fts (service_id, text_repr)
                    VALUES (?, ?)
                """, (str(svc["id"]), text_repr))
            count += 1

        conn.commit()
        print(f"[DB] Built search index for {count} services "
              f"({'sqlite-vec vectors' if self._vec_available else 'FTS5 full-text'}).")
        return count

    def _text_to_embedding(self, text: str, dim: int = 384) -> List[float]:
        """
        Generate a text embedding vector for semantic search.
        Primary: Ollama embedding API (on-device, offline-ready).
        Fallback: Deterministic character n-gram hash embedding (zero dependencies).
        """
        try:
            import urllib.request
            payload = json.dumps({
                "model": "qwen3.5:0.8b",
                "prompt": text,
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                emb = data.get("embedding", [])
                if emb:
                    return emb[:dim] + [0.0] * max(0, dim - len(emb))
        except Exception:
            pass
        return self._hash_embedding(text, dim)

    @staticmethod
    def _hash_embedding(text: str, dim: int = 384) -> List[float]:
        """
        Deterministic hash-based embedding for offline vector search.
        Uses character trigram hashing to produce a fixed-dimension vector.
        Always available — zero external dependencies.
        """
        import hashlib
        embedding = [0.0] * dim
        text_lower = text.lower().strip()
        for i in range(max(len(text_lower) - 2, 1)):
            trigram = text_lower[i:i + 3]
            h = int(hashlib.md5(trigram.encode()).hexdigest(), 16)
            idx = h % dim
            embedding[idx] += 1.0
        magnitude = math.sqrt(sum(x * x for x in embedding)) or 1.0
        return [x / magnitude for x in embedding]


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
