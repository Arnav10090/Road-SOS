"""
modules/chatbot.py
RoadSoS - Conversational Emergency Chatbot

The primary user-facing interface.
Integrates all subsystems: triage, geospatial, SLM, SMS fallback.
Manages conversation state and routes user intents.
"""

import json
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .database import DatabaseManager
from .geospatial import GeospatialEngine
from .ai_triage import AITriageEngine
from .sms_fallback import SMSFallbackEngine


# ── Intent detection patterns ──────────────────────────────────────────────
INTENT_PATTERNS = {
    "emergency":  r"\b(help|emergency|accident|crash|injured|hurt|bleeding|unconscious|fire|trapped)\b",
    "find_service": r"\b(find|nearest|nearby|close|where|hospital|police|ambulance|tow|mechanic|puncture)\b",
    "set_location": r"\b(location|gps|coordinates|i.?am.?at|i.?m at|lat|lon)\b",
    "status":     r"\b(status|ready|working|offline)\b",
    "sms":        r"\b(sms|text|send|no.?network|no.?signal|offline.?mode)\b",
}

HELP_TEXT = """
Available commands:
  📍 Set location:  "I am at [city/address]" or type GPS coords
  🚨 Emergency:     Describe the accident (e.g., "severe accident on highway")
  🔍 Find services: "find nearest hospital" / "nearest police station"
  📱 SMS mode:      "send SOS" or "no signal mode"
  ℹ️  Status:       "status" to check system readiness
  ❌ Quit:          "quit" or "exit"
"""

WELCOME_MESSAGE = """
👋 Welcome to RoadSoS — Your Offline Road Emergency Assistant.
I can help you find nearby hospitals, police stations, ambulances,
towing services, and more — even without internet access.

Type your emergency situation or 'help' for more options.
"""


class RoadSoSChatbot:
    """
    Manages multi-turn conversation for emergency response.
    All responses are generated from local data — fully offline capable.
    """

    def __init__(
        self,
        db: DatabaseManager,
        geo_engine: GeospatialEngine,
        triage_engine: AITriageEngine,
        sms_engine: "SMSFallbackEngine",
    ):
        self.db = db
        self.geo = geo_engine
        self.triage = triage_engine
        self.sms = sms_engine

        # Conversation state
        self._lat: Optional[float] = None
        self._lon: Optional[float] = None
        self._last_incident: Optional[str] = None
        self._last_triage: Optional[Dict] = None
        self._awaiting_location = False
        self._incident_id: Optional[int] = None

    def set_location(self, lat: float, lon: float):
        """Set current GPS location (called from API or CLI)."""
        self._lat = lat
        self._lon = lon

    def process_message(self, user_input: str) -> str:
        """Route user message to the appropriate handler."""
        text = user_input.strip()

        # Handle help command
        if text.lower() == "help":
            return HELP_TEXT

        # Handle status command
        if re.search(INTENT_PATTERNS["status"], text, re.IGNORECASE):
            return self._get_status()

        # Handle location setting
        if self._awaiting_location or re.search(INTENT_PATTERNS["set_location"], text, re.IGNORECASE):
            loc_result = self._parse_location(text)
            if loc_result:
                return loc_result

        # Try to parse GPS coords directly
        coords = self._extract_coords(text)
        if coords:
            self._lat, self._lon = coords
            return f"📍 Location set: {self._lat:.4f}, {self._lon:.4f}\nNow describe your emergency or what service you need."

        # Handle SMS/SOS trigger
        if re.search(INTENT_PATTERNS["sms"], text, re.IGNORECASE):
            return self._handle_sms_request()

        # Handle emergency or service search
        if re.search(INTENT_PATTERNS["emergency"], text, re.IGNORECASE):
            return self._handle_emergency(text)

        if re.search(INTENT_PATTERNS["find_service"], text, re.IGNORECASE):
            return self._handle_service_search(text)

        # Default: treat any input as a potential emergency description
        return self._handle_emergency(text)

    def _handle_emergency(self, description: str) -> str:
        """Process emergency incident description."""
        if not self._lat or not self._lon:
            self._last_incident = description
            self._awaiting_location = True
            return (
                "⚠️  Emergency received. I need your location first.\n"
                "Please type your GPS coordinates (e.g., '21.1458, 79.0882')\n"
                "or your city/landmark name."
            )

        # Run full AI triage
        triage = self.triage.full_triage(description)
        self._last_triage = triage
        self._last_incident = description
        severity = triage["severity"]

        # Log the incident
        self._incident_id = self.db.log_incident(
            lat=self._lat,
            lon=self._lon,
            incident_type="road_accident",
            severity=severity,
            description=description,
        )

        # Determine needed services
        needed_types = []
        if triage["needs_ambulance"] or triage["needs_trauma_center"]:
            needed_types.extend(["hospital", "ambulance"])
        if triage["needs_police"]:
            needed_types.append("police")
        if triage["needs_towing"]:
            needed_types.extend(["towing", "puncture"])
        if not needed_types:
            needed_types = ["hospital", "police", "ambulance"]

        # Fetch nearest services
        services = self.geo.get_nearest_services(
            lat=self._lat,
            lon=self._lon,
            severity=severity,
            trauma_only=(severity == "critical"),
            limit=5,
        )

        # Build response
        severity_banners = {
            "critical": "🚨 CRITICAL EMERGENCY — Calling for immediate trauma care!",
            "high":     "⚠️  SERIOUS INCIDENT — Emergency services needed urgently.",
            "moderate": "🔶 ROAD ACCIDENT — Locating nearest emergency services.",
            "low":      "🔷 MINOR INCIDENT — Finding nearby assistance.",
        }
        banner = severity_banners.get(severity, "🔶 INCIDENT DETECTED")

        response_parts = [
            banner,
            f"\n📋 Assessment: {triage.get('summary', description[:80])}",
            "\n🔎 Nearest Emergency Services:\n",
            self.geo.format_services_for_display(services, self._lat, self._lon),
        ]

        if severity in ("critical", "high"):
            sms_hint = "\n\n📵 No signal? Type 'send SOS' to send an offline SMS alert."
            response_parts.append(sms_hint)

        # Sanjaya export note
        response_parts.append(
            f"\n\n📊 Incident #{self._incident_id} logged for CoERS Sanjaya analytics."
        )

        return "\n".join(response_parts)

    def _handle_service_search(self, query: str) -> str:
        """Handle requests to find specific service types."""
        if not self._lat or not self._lon:
            self._awaiting_location = True
            return "Please share your location first (GPS coordinates or city name)."

        # Detect requested service type from query
        query_lower = query.lower()
        if any(w in query_lower for w in ["hospital", "doctor", "medical", "health"]):
            types = ["hospital", "trauma_center"]
            label = "hospitals"
        elif any(w in query_lower for w in ["police", "cop", "station"]):
            types = ["police"]
            label = "police stations"
        elif any(w in query_lower for w in ["ambulance"]):
            types = ["ambulance"]
            label = "ambulance services"
        elif any(w in query_lower for w in ["tow", "rescue", "vehicle", "breakdown"]):
            types = ["towing"]
            label = "towing services"
        elif any(w in query_lower for w in ["puncture", "tyre", "tire", "mechanic"]):
            types = ["puncture"]
            label = "puncture shops"
        else:
            types = None
            label = "emergency services"

        services = self.geo.db.query_rtree_bbox(
            lat=self._lat, lon=self._lon,
            service_types=types, limit=5,
        )

        if not services:
            return f"No {label} found within 25 km of your location in the offline database."

        header = f"📍 Nearest {label.title()} near you:\n"
        return header + self.geo.format_services_for_display(services, self._lat, self._lon)

    def _handle_sms_request(self) -> str:
        """Generate and queue an SMS fallback alert."""
        if not self._lat or not self._lon:
            return "Location required before sending SOS. Please share your GPS coordinates."

        nearest = self.geo.db.query_rtree_bbox(
            lat=self._lat, lon=self._lon,
            service_types=["police"],
            limit=1,
        )
        nearest_name = nearest[0]["name"] if nearest else ""

        severity = self._last_triage.get("severity", "moderate") if self._last_triage else "moderate"
        incident_text = self._last_incident or "Road accident"

        sms_text = self.triage.draft_sos_message(
            lat=self._lat, lon=self._lon,
            incident_text=incident_text,
            severity=severity,
            nearest_service_name=nearest_name,
        )

        police_phone = nearest[0]["phone"] if nearest and nearest[0].get("phone") else "100"
        self.sms.queue_sms(phone=police_phone, message=sms_text)

        return (
            f"📵 SOS SMS prepared and queued:\n\n"
            f"TO: {police_phone}\n"
            f"MESSAGE:\n{sms_text}\n\n"
            f"✅ Will auto-send when network is restored.\n"
            f"If network is not restored, please call {police_phone} directly."
        )

    def _parse_location(self, text: str) -> Optional[str]:
        """Try to extract GPS coordinates or resolve city name."""
        coords = self._extract_coords(text)
        if coords:
            self._lat, self._lon = coords
            self._awaiting_location = False
            # Now process any pending incident
            if self._last_incident:
                incident = self._last_incident
                self._last_incident = None
                return (
                    f"📍 Location set: {self._lat:.4f}, {self._lon:.4f}\n\n"
                    + self._handle_emergency(incident)
                )
            return f"📍 Location set: {self._lat:.4f}, {self._lon:.4f}\n\nDescribe your situation or search for services."
        # Could not parse location
        return None

    def _extract_coords(self, text: str) -> Optional[Tuple[float, float]]:
        """Extract GPS coordinates from text using regex patterns."""
        patterns = [
            r"(-?\d{1,2}\.\d{2,6})\s*[,\s]\s*(-?\d{1,3}\.\d{2,6})",  # decimal: 21.1458, 79.0882
            r"lat[itude]*\s*[=:]\s*(-?\d+\.?\d*).+?lon[gitude]*\s*[=:]\s*(-?\d+\.?\d*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                lat, lon = float(match.group(1)), float(match.group(2))
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return lat, lon
        return None

    def _get_status(self) -> str:
        """Return system status summary."""
        db_count = self.db.get_service_count()
        loc_str = f"{self._lat:.4f}, {self._lon:.4f}" if self._lat else "Not set"
        ollama_status = "✅ Running" if self.triage._ollama_available else "⚠️  Not running (keyword fallback active)"
        return (
            f"🟢 RoadSoS Status\n"
            f"  Offline Database: ✅ {db_count:,} emergency services loaded\n"
            f"  AI Engine (Ollama): {ollama_status}\n"
            f"  Current Location: {loc_str}\n"
            f"  Network Required: ❌ None\n"
            f"  CoERS Integration: Sanjaya GeoJSON export ready"
        )

    def export_geojson(self, incidents: List[Dict]) -> Dict:
        """
        Export logged incidents as GeoJSON for CoERS Sanjaya integration.
        Sanjaya ingests this format for blackspot heatmap generation.
        """
        features = []
        for inc in incidents:
            if inc.get("latitude") and inc.get("longitude"):
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [inc["longitude"], inc["latitude"]],
                    },
                    "properties": {
                        "incident_id":   inc["id"],
                        "timestamp":     inc["timestamp"],
                        "severity":      inc["severity"],
                        "incident_type": inc["incident_type"],
                        "description":   inc["description"],
                        "source":        "RoadSoS",
                        "sanjaya_layer": "road_accidents",
                    },
                })
        return {
            "type": "FeatureCollection",
            "metadata": {
                "source": "RoadSoS v1.0",
                "generated": datetime.now().isoformat(),
                "coers_target": "Sanjaya Blackspot Analytics",
            },
            "features": features,
        }
