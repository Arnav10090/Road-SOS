"""
RoadSoS - AI-Powered Emergency Response Chatbot
National Road Safety Hackathon 2026 | CoERS, RBG Labs, IIT Madras

Team Submission | Problem Statement: RoadSoS
Architecture: Offline-First Edge AI with SLM + SQLite-vec + OSM Spatial Indexing

Entry point for the RoadSoS application.
"""

import argparse
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.database import DatabaseManager
from modules.geospatial import GeospatialEngine
from modules.ai_triage import AITriageEngine
from modules.chatbot import RoadSoSChatbot
from modules.sms_fallback import SMSFallbackEngine
from modules.data_seeder import DataSeeder


def setup_database(db_path: str = "data/roadsos.db"):
    """Initialize and seed the SQLite spatial database."""
    print("[RoadSoS] Initializing offline spatial database...")
    db = DatabaseManager(db_path)
    db.initialize_schema()

    # Check if data needs seeding
    seeder = DataSeeder(db)
    if not seeder.is_seeded():
        print("[RoadSoS] Seeding emergency services data from OSM extracts...")
        seeder.seed_all()
        print("[RoadSoS] Building offline search index (RAG pipeline)...")
        db.build_service_embeddings()
        print("[RoadSoS] Database seeding complete.")
    else:
        print("[RoadSoS] Existing database loaded.")
    return db


def run_interactive_cli(db_path: str = "data/roadsos.db"):
    """Run the RoadSoS chatbot in interactive CLI mode."""
    print("=" * 60)
    print("  RoadSoS - Road Emergency Response Assistant")
    print("  Powered by Offline Edge AI | CoERS Hackathon 2026")
    print("=" * 60)
    print("Type 'help' for commands, 'quit' to exit.\n")

    db = setup_database(db_path)
    geo_engine = GeospatialEngine(db)
    triage_engine = AITriageEngine()
    sms_engine = SMSFallbackEngine()
    chatbot = RoadSoSChatbot(db, geo_engine, triage_engine, sms_engine)

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("RoadSoS: Stay safe on the roads. Goodbye.")
                break
            response = chatbot.process_message(user_input)
            print(f"\nRoadSoS: {response}\n")
        except KeyboardInterrupt:
            print("\nRoadSoS: Emergency session ended. Stay safe.")
            break
        except Exception as e:
            print(f"RoadSoS: System error: {e}")


def run_api_server(host: str = "0.0.0.0", port: int = 5000, db_path: str = "data/roadsos.db"):
    """Run the RoadSoS Flask API server (for integration with CoERS Sanjaya)."""
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        print("Flask not installed. Run: pip install flask")
        sys.exit(1)

    db = setup_database(db_path)
    geo_engine = GeospatialEngine(db)
    triage_engine = AITriageEngine()
    sms_engine = SMSFallbackEngine()
    chatbot = RoadSoSChatbot(db, geo_engine, triage_engine, sms_engine)

    app = Flask(__name__)

    @app.route("/api/chat", methods=["POST"])
    def chat():
        data = request.get_json()
        message = data.get("message", "")
        lat = data.get("latitude")
        lon = data.get("longitude")
        if lat and lon:
            chatbot.set_location(float(lat), float(lon))
        response = chatbot.process_message(message)
        return jsonify({"response": response, "status": "ok"})

    @app.route("/api/emergency", methods=["POST"])
    def emergency():
        """Direct emergency lookup - returns nearby services as JSON."""
        data = request.get_json()
        lat = float(data.get("latitude", 21.1458))
        lon = float(data.get("longitude", 79.0882))
        incident = data.get("incident_description", "road accident")
        severity = triage_engine.classify_severity(incident)
        services = geo_engine.get_nearest_services(lat, lon, severity=severity, limit=5)
        return jsonify({"services": services, "severity": severity, "status": "ok"})

    @app.route("/api/sanjaya_export", methods=["GET"])
    def sanjaya_export():
        """Export incident data as GeoJSON for CoERS Sanjaya integration."""
        incidents = db.get_recent_incidents(limit=100)
        geojson = chatbot.export_geojson(incidents)
        return jsonify(geojson)

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "offline-ready", "db_connected": True})

    print(f"[RoadSoS] API server starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RoadSoS - AI Emergency Response Chatbot")
    parser.add_argument("--mode", choices=["cli", "api", "seed"], default="cli",
                        help="Run mode: cli (interactive), api (Flask server), seed (data only)")
    parser.add_argument("--db", default="data/roadsos.db", help="SQLite database path")
    parser.add_argument("--host", default="0.0.0.0", help="API server host")
    parser.add_argument("--port", type=int, default=5000, help="API server port")
    args = parser.parse_args()

    os.makedirs("data", exist_ok=True)

    if args.mode == "cli":
        run_interactive_cli(args.db)
    elif args.mode == "api":
        run_api_server(args.host, args.port, args.db)
    elif args.mode == "seed":
        db = setup_database(args.db)
        print("[RoadSoS] Database initialization complete.")