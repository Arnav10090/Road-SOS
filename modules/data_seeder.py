"""
modules/data_seeder.py
RoadSoS - OSM Data Seeder

Populates the local SQLite spatial database with emergency services.

Data Sources:
  1. OpenStreetMap Overpass API (internet required for initial seed only)
  2. Bundled seed data (fully offline fallback)

OSM tags used (per RoadSoS requirements):
  - amenity=hospital + emergency=yes       → Trauma centres
  - amenity=police                         → Police stations
  - amenity=ambulance_station             → Ambulance services
  - craft=towing + shop=car_repair         → Vehicle rescue
  - shop=tyres + shop=bicycle_repair       → Puncture shops
  - shop=car + shop=motorcycle             → Showrooms

Production workflow:
  1. On first install (with internet), fetch full country OSM dataset
  2. Store compressed in local SQLite
  3. All subsequent queries are 100% offline

For hackathon demo: bundled seed data covers major Indian cities + sample global data.
"""

import json
from typing import List, Dict, Optional
from .database import DatabaseManager


# ── Bundled seed data ─────────────────────────────────────────────────────
# Represents what would be fetched from OSM Overpass API
# Covers: Nagpur, Mumbai, Delhi, Chennai, Hyderabad + global samples

SEED_DATA = [
    # ── Nagpur, Maharashtra ─────────────────────────────────────────────
    {"osm_id": "IN_MH_NG_001", "name": "Government Medical College & Hospital", "service_type": "hospital",
     "sub_type": "trauma_center", "latitude": 21.1467, "longitude": 79.0888,
     "phone": "0712-2701000", "address": "Hanuman Nagar, Nagpur, MH 440003",
     "country_code": "IN", "state_code": "MH", "is_24h": True, "has_emergency": True, "has_trauma": True},
    {"osm_id": "IN_MH_NG_002", "name": "Mayo Hospital Nagpur", "service_type": "hospital",
     "sub_type": "general", "latitude": 21.1479, "longitude": 79.0848,
     "phone": "0712-2720100", "address": "Ambazari, Nagpur, MH 440010",
     "country_code": "IN", "state_code": "MH", "is_24h": True, "has_emergency": True},
    {"osm_id": "IN_MH_NG_003", "name": "Nagpur Police Control Room", "service_type": "police",
     "latitude": 21.1498, "longitude": 79.0827,
     "phone": "0712-2567901", "address": "Civil Lines, Nagpur, MH 440001",
     "country_code": "IN", "state_code": "MH", "is_24h": True},
    {"osm_id": "IN_MH_NG_004", "name": "Wardhaman Nagar Police Station", "service_type": "police",
     "latitude": 21.1591, "longitude": 79.0958,
     "phone": "0712-2523490", "address": "Wardhaman Nagar, Nagpur, MH",
     "country_code": "IN", "state_code": "MH", "is_24h": True},
    {"osm_id": "IN_MH_NG_005", "name": "Samarth Ambulance Service Nagpur", "service_type": "ambulance",
     "latitude": 21.1440, "longitude": 79.0812,
     "phone": "108", "address": "Dhantoli, Nagpur, MH 440012",
     "country_code": "IN", "state_code": "MH", "is_24h": True},
    {"osm_id": "IN_MH_NG_006", "name": "Swadeshi Vehicle Recovery Nagpur", "service_type": "towing",
     "latitude": 21.1330, "longitude": 79.0750,
     "phone": "+91-9876543210", "address": "Hingna Road, Nagpur, MH",
     "country_code": "IN", "state_code": "MH", "is_24h": True},
    {"osm_id": "IN_MH_NG_007", "name": "National Tyre Puncture Shop", "service_type": "puncture",
     "latitude": 21.1502, "longitude": 79.0921,
     "phone": "+91-9823456789", "address": "Sitabuldi, Nagpur, MH",
     "country_code": "IN", "state_code": "MH"},
    # ── Mumbai, Maharashtra ─────────────────────────────────────────────
    {"osm_id": "IN_MH_MB_001", "name": "KEM Hospital Mumbai", "service_type": "hospital",
     "sub_type": "trauma_center", "latitude": 19.0042, "longitude": 72.8367,
     "phone": "022-24107000", "address": "Acharya Donde Marg, Parel, Mumbai 400012",
     "country_code": "IN", "state_code": "MH", "is_24h": True, "has_emergency": True, "has_trauma": True},
    {"osm_id": "IN_MH_MB_002", "name": "Mumbai Police Emergency", "service_type": "police",
     "latitude": 18.9393, "longitude": 72.8348,
     "phone": "100", "address": "Crawford Market, Mumbai, MH 400001",
     "country_code": "IN", "state_code": "MH", "is_24h": True},
    # ── Delhi, NCR ─────────────────────────────────────────────────────
    {"osm_id": "IN_DL_001", "name": "AIIMS Trauma Centre", "service_type": "hospital",
     "sub_type": "trauma_center", "latitude": 28.5673, "longitude": 77.2100,
     "phone": "011-26588500", "address": "Ansari Nagar East, New Delhi 110029",
     "country_code": "IN", "state_code": "DL", "is_24h": True, "has_emergency": True, "has_trauma": True},
    {"osm_id": "IN_DL_002", "name": "Delhi Police PCR", "service_type": "police",
     "latitude": 28.6139, "longitude": 77.2090,
     "phone": "100", "address": "Connaught Place, New Delhi 110001",
     "country_code": "IN", "state_code": "DL", "is_24h": True},
    {"osm_id": "IN_DL_003", "name": "Delhi Ambulance Service (CATS)", "service_type": "ambulance",
     "latitude": 28.6100, "longitude": 77.2050,
     "phone": "102", "address": "Central Delhi, New Delhi",
     "country_code": "IN", "state_code": "DL", "is_24h": True},
    # ── Chennai, Tamil Nadu ─────────────────────────────────────────────
    {"osm_id": "IN_TN_001", "name": "Rajiv Gandhi Government General Hospital", "service_type": "hospital",
     "sub_type": "trauma_center", "latitude": 13.0844, "longitude": 80.2734,
     "phone": "044-25305000", "address": "Park Town, Chennai 600003",
     "country_code": "IN", "state_code": "TN", "is_24h": True, "has_emergency": True, "has_trauma": True},
    {"osm_id": "IN_TN_002", "name": "Chennai City Police Control", "service_type": "police",
     "latitude": 13.0827, "longitude": 80.2707,
     "phone": "100", "address": "Vepery, Chennai, TN 600007",
     "country_code": "IN", "state_code": "TN", "is_24h": True},
    # ── Hyderabad, Telangana ────────────────────────────────────────────
    {"osm_id": "IN_TS_001", "name": "Osmania General Hospital", "service_type": "hospital",
     "sub_type": "trauma_center", "latitude": 17.3792, "longitude": 78.4705,
     "phone": "040-24600455", "address": "Afzalganj, Hyderabad 500012",
     "country_code": "IN", "state_code": "TS", "is_24h": True, "has_emergency": True, "has_trauma": True},
    # ── Bangalore, Karnataka ────────────────────────────────────────────
    {"osm_id": "IN_KA_001", "name": "Victoria Hospital Bangalore", "service_type": "hospital",
     "sub_type": "trauma_center", "latitude": 12.9706, "longitude": 77.5729,
     "phone": "080-26706000", "address": "Fort Road, Bangalore 560002",
     "country_code": "IN", "state_code": "KA", "is_24h": True, "has_emergency": True, "has_trauma": True},
    # ── National Emergency Numbers ──────────────────────────────────────
    {"osm_id": "IN_NATIONAL_001", "name": "National Emergency (India)", "service_type": "ambulance",
     "latitude": 28.6139, "longitude": 77.2090,
     "phone": "112", "address": "National Emergency Number",
     "country_code": "IN", "state_code": "NA", "is_24h": True, "has_emergency": True},
    # ── Global Samples ─────────────────────────────────────────────────
    # UK - London
    {"osm_id": "GB_LDN_001", "name": "King's College Hospital London", "service_type": "hospital",
     "sub_type": "trauma_center", "latitude": 51.4695, "longitude": -0.0947,
     "phone": "+44-20-3299-9000", "address": "Denmark Hill, London SE5 9RS",
     "country_code": "GB", "state_code": "ENG", "is_24h": True, "has_emergency": True, "has_trauma": True},
    {"osm_id": "GB_LDN_002", "name": "Metropolitan Police London", "service_type": "police",
     "latitude": 51.5076, "longitude": -0.1277,
     "phone": "999", "address": "New Scotland Yard, London SW1H 0BG",
     "country_code": "GB", "state_code": "ENG", "is_24h": True},
    # USA - Los Angeles
    {"osm_id": "US_LA_001", "name": "LAC+USC Medical Center", "service_type": "hospital",
     "sub_type": "trauma_center", "latitude": 34.0583, "longitude": -118.2083,
     "phone": "+1-323-409-1000", "address": "1200 N State St, Los Angeles CA 90033",
     "country_code": "US", "state_code": "CA", "is_24h": True, "has_emergency": True, "has_trauma": True},
    {"osm_id": "US_LA_002", "name": "LAPD Emergency", "service_type": "police",
     "latitude": 34.0522, "longitude": -118.2437,
     "phone": "911", "address": "100 W 1st St, Los Angeles CA 90012",
     "country_code": "US", "state_code": "CA", "is_24h": True},
    # Singapore
    {"osm_id": "SG_001", "name": "Singapore General Hospital A&E", "service_type": "hospital",
     "sub_type": "trauma_center", "latitude": 1.2797, "longitude": 103.8364,
     "phone": "+65-6222-3322", "address": "Outram Road, Singapore 169608",
     "country_code": "SG", "state_code": "SG", "is_24h": True, "has_emergency": True, "has_trauma": True},
    {"osm_id": "SG_002", "name": "Singapore Police Force", "service_type": "police",
     "latitude": 1.3521, "longitude": 103.8198,
     "phone": "999", "address": "28 Irrawaddy Road, Singapore 329560",
     "country_code": "SG", "state_code": "SG", "is_24h": True},
]


class DataSeeder:
    """Seeds the offline database with emergency services from OSM-sourced data."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def is_seeded(self) -> bool:
        return self.db.is_seeded()

    def seed_all(self):
        """Seed all bundled emergency service data."""
        print(f"[Seeder] Inserting {len(SEED_DATA)} emergency service records...")
        self.db.bulk_insert_services(SEED_DATA)
        print(f"[Seeder] Total services in DB: {self.db.get_service_count()}")

    def fetch_from_overpass(self, country_code: str = "IN", state_bbox: tuple = None):
        """
        Fetch live OSM data from Overpass API (requires internet — one-time seeding).
        Converts OSM nodes to our schema and inserts into local SQLite.

        Overpass QL query example:
            [out:json][timeout:60];
            (
              node["amenity"="hospital"]["emergency"="yes"](bbox);
              node["amenity"="police"](bbox);
              node["craft"="towing"](bbox);
              node["shop"="tyres"](bbox);
            );
            out body;
        """
        try:
            import urllib.request
            import json

            if not state_bbox:
                # Default: India bounding box
                state_bbox = (8.0, 68.0, 37.6, 97.4)

            bbox_str = f"{state_bbox[0]},{state_bbox[1]},{state_bbox[2]},{state_bbox[3]}"
            overpass_query = f"""
            [out:json][timeout:60];
            (
              node["amenity"="hospital"]{bbox_str};
              node["amenity"="police"]{bbox_str};
              node["amenity"="ambulance_station"]{bbox_str};
              node["craft"="towing"]{bbox_str};
              node["shop"="tyres"]{bbox_str};
              node["shop"="car_repair"]{bbox_str};
            );
            out body;
            """
            url = "https://overpass-api.de/api/interpreter"
            encoded_query = urllib.parse.urlencode({"data": overpass_query}).encode()
            req = urllib.request.Request(url, data=encoded_query)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            services = []
            for element in data.get("elements", []):
                if element.get("type") != "node":
                    continue
                tags = element.get("tags", {})
                service = self._map_osm_to_service(element["id"], element["lat"], element["lon"], tags, country_code)
                if service:
                    services.append(service)

            if services:
                self.db.bulk_insert_services(services)
                print(f"[Seeder] Fetched and stored {len(services)} services from OSM Overpass API.")
            return len(services)

        except Exception as e:
            print(f"[Seeder] Overpass fetch failed: {e}. Using bundled seed data.")
            self.seed_all()
            return 0

    def _map_osm_to_service(self, osm_id, lat, lon, tags, country_code) -> Optional[Dict]:
        """Map an OSM node's tags to our emergency service schema."""
        amenity = tags.get("amenity", "")
        craft = tags.get("craft", "")
        shop = tags.get("shop", "")

        if amenity == "hospital":
            stype = "hospital"
            sub = "trauma_center" if tags.get("emergency") == "yes" else "general"
        elif amenity == "police":
            stype = "police"
            sub = None
        elif amenity == "ambulance_station":
            stype = "ambulance"
            sub = None
        elif craft == "towing" or shop == "car_repair":
            stype = "towing"
            sub = None
        elif shop in ("tyres", "bicycle_repair"):
            stype = "puncture"
            sub = None
        else:
            return None

        return {
            "osm_id": f"OSM_{osm_id}",
            "name": tags.get("name", tags.get("operator", "Unknown")),
            "service_type": stype,
            "sub_type": sub,
            "latitude": lat,
            "longitude": lon,
            "phone": tags.get("phone", tags.get("contact:phone")),
            "address": tags.get("addr:full", tags.get("addr:street")),
            "country_code": country_code,
            "is_24h": tags.get("opening_hours", "").strip() == "24/7",
            "has_emergency": tags.get("emergency") == "yes",
            "has_trauma": tags.get("trauma_center") == "yes" or (stype == "hospital" and tags.get("emergency") == "yes"),
            "extra_tags": {k: v for k, v in tags.items() if k not in ("name", "phone", "amenity")},
        }
