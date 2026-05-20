"""
tests/test_roadsos.py
RoadSoS - Test Suite

Tests all core modules in offline mode (no network required).
Run: python -m pytest tests/ -v
Or:  python tests/test_roadsos.py
"""

import sys
import os
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.database import DatabaseManager, haversine_km
from modules.geospatial import GeospatialEngine, bearing, bearing_to_direction
from modules.ai_triage import AITriageEngine
from modules.sms_fallback import SMSFallbackEngine
from modules.data_seeder import DataSeeder
from modules.chatbot import RoadSoSChatbot


class TestHaversine(unittest.TestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(haversine_km(21.1, 79.0, 21.1, 79.0), 0.0, places=3)

    def test_known_distance(self):
        # Nagpur to Mumbai approx 880 km
        d = haversine_km(21.1458, 79.0882, 19.0760, 72.8777)
        self.assertGreater(d, 600)
        self.assertLess(d, 1000)

    def test_symmetry(self):
        d1 = haversine_km(21.0, 79.0, 28.6, 77.2)
        d2 = haversine_km(28.6, 77.2, 21.0, 79.0)
        self.assertAlmostEqual(d1, d2, places=3)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.db = DatabaseManager(self.tmp)
        self.db.initialize_schema()
        # Seed test data
        seeder = DataSeeder(self.db)
        seeder.seed_all()

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.tmp):
            os.remove(self.tmp)

    def test_seeding(self):
        count = self.db.get_service_count()
        self.assertGreater(count, 10, "Expected at least 10 seeded services")

    def test_rtree_query_nagpur(self):
        # Nagpur city center
        results = self.db.query_rtree_bbox(21.1458, 79.0882, radius_km=20)
        self.assertGreater(len(results), 0, "Should find services near Nagpur")

    def test_rtree_query_filter_by_type(self):
        results = self.db.query_rtree_bbox(21.1458, 79.0882, service_types=["police"])
        for r in results:
            self.assertEqual(r["service_type"], "police")

    def test_rtree_trauma_only(self):
        results = self.db.query_rtree_bbox(21.1458, 79.0882, trauma_only=True)
        for r in results:
            self.assertTrue(r["has_trauma"] or r["has_emergency"],
                            "Trauma-only query should only return trauma/emergency facilities")

    def test_rtree_returns_sorted_by_distance(self):
        results = self.db.query_rtree_bbox(21.1458, 79.0882, radius_km=50)
        if len(results) >= 2:
            for i in range(len(results) - 1):
                self.assertLessEqual(results[i]["distance_km"], results[i + 1]["distance_km"])

    def test_incident_logging(self):
        inc_id = self.db.log_incident(21.1458, 79.0882, "road_accident", "critical", "Test incident")
        self.assertIsNotNone(inc_id)
        incidents = self.db.get_recent_incidents(1)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["severity"], "critical")


class TestAITriage(unittest.TestCase):
    def setUp(self):
        self.engine = AITriageEngine()  # Ollama likely not running in test; uses keyword fallback

    def test_critical_classification(self):
        result = self.engine.classify_severity("severe head trauma, person unconscious, not breathing")
        self.assertEqual(result, "critical")

    def test_high_classification(self):
        result = self.engine.classify_severity("motorcycle accident, broken leg, bleeding")
        self.assertEqual(result, "high")

    def test_moderate_classification(self):
        result = self.engine.classify_severity("minor car accident on the highway")
        self.assertIn(result, ("moderate", "high"))

    def test_low_classification(self):
        result = self.engine.classify_severity("flat tyre, need towing")
        self.assertEqual(result, "low")

    def test_full_triage_structure(self):
        result = self.engine.full_triage("car crash, 2 people hurt, one unconscious")
        self.assertIn("severity", result)
        self.assertIn("needs_ambulance", result)
        self.assertIn("needs_police", result)
        self.assertIn("needs_towing", result)
        self.assertIn("summary", result)

    def test_sos_message_length(self):
        msg = self.engine.draft_sos_message(21.1458, 79.0882, "head trauma accident", "critical", "GMC Hospital")
        # SMS should be concise
        self.assertLess(len(msg), 350)

    def test_critical_needs_ambulance(self):
        result = self.engine.full_triage("severe bleeding, unconscious person")
        self.assertTrue(result["needs_ambulance"])
        self.assertTrue(result["needs_trauma_center"])


class TestGeospatial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".db")
        self.db = DatabaseManager(self.tmp)
        self.db.initialize_schema()
        seeder = DataSeeder(self.db)
        seeder.seed_all()
        self.geo = GeospatialEngine(self.db)

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.tmp):
            os.remove(self.tmp)

    def test_fallback_jurisdiction_india(self):
        j = self.geo._fallback_jurisdiction(21.1458, 79.0882)
        self.assertEqual(j["country_code"], "IN")

    def test_fallback_jurisdiction_uk(self):
        j = self.geo._fallback_jurisdiction(51.5074, -0.1278)
        self.assertEqual(j["country_code"], "GB")

    def test_fallback_jurisdiction_usa(self):
        j = self.geo._fallback_jurisdiction(34.0522, -118.2437)
        self.assertEqual(j["country_code"], "US")

    def test_nearest_services_returns_results(self):
        services = self.geo.get_nearest_services(21.1458, 79.0882, severity="critical")
        self.assertGreater(len(services), 0)

    def test_bearing_direction(self):
        # North should be ~N
        d = bearing_to_direction(0)
        self.assertEqual(d, "N")
        d = bearing_to_direction(90)
        self.assertEqual(d, "E")

    def test_format_display(self):
        services = self.geo.get_nearest_services(21.1458, 79.0882)
        formatted = self.geo.format_services_for_display(services, 21.1458, 79.0882)
        self.assertIn("km", formatted)


class TestChatbot(unittest.TestCase):
    def setUp(self):
        self.tmp_db = tempfile.mktemp(suffix=".db")
        self.tmp_sms = tempfile.mktemp(suffix=".db")
        self.db = DatabaseManager(self.tmp_db)
        self.db.initialize_schema()
        DataSeeder(self.db).seed_all()
        self.geo = GeospatialEngine(self.db)
        self.triage = AITriageEngine()
        self.sms = SMSFallbackEngine(self.tmp_sms)
        self.bot = RoadSoSChatbot(self.db, self.geo, self.triage, self.sms)

    def tearDown(self):
        self.db.close()
        for f in [self.tmp_db, self.tmp_sms]:
            if os.path.exists(f):
                os.remove(f)

    def test_help_command(self):
        resp = self.bot.process_message("help")
        self.assertIn("location", resp.lower())

    def test_status_command(self):
        resp = self.bot.process_message("status")
        self.assertIn("Offline Database", resp)

    def test_emergency_without_location_asks_for_location(self):
        resp = self.bot.process_message("there's been a crash, someone is hurt")
        self.assertIn("location", resp.lower())

    def test_emergency_with_location(self):
        self.bot.set_location(21.1458, 79.0882)
        resp = self.bot.process_message("bad accident, person bleeding")
        self.assertIn("Services", resp)

    def test_coords_extraction(self):
        resp = self.bot.process_message("21.1458, 79.0882")
        self.assertIn("Location set", resp)

    def test_geojson_export(self):
        self.db.log_incident(21.1458, 79.0882, "road_accident", "high", "Test")
        incidents = self.db.get_recent_incidents()
        geojson = self.bot.export_geojson(incidents)
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertGreater(len(geojson["features"]), 0)
        self.assertEqual(geojson["features"][0]["properties"]["sanjaya_layer"], "road_accidents")


if __name__ == "__main__":
    print("Running RoadSoS Test Suite...\n")
    unittest.main(verbosity=2)
