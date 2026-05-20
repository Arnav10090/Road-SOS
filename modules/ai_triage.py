"""
modules/ai_triage.py
RoadSoS - Offline AI Triage Engine

Architecture:
  - Primary: Local SLM via Ollama (Qwen3.5-0.8B or Llama 3.2 1B)
  - Fallback: Deterministic keyword classifier (zero dependencies)
  - All inference runs on-device; no API keys, no internet

Purpose:
  1. Classify incident severity from free-text descriptions
  2. Extract injury types and service needs
  3. Draft AI-generated emergency alert messages
  4. Context-aware hospital filtering (e.g., trauma vs. basic care)
"""

import re
from typing import Dict, Tuple, Optional

# ── Severity keyword taxonomy ──────────────────────────────────────────────
CRITICAL_KEYWORDS = [
    "unconscious", "not breathing", "no pulse", "severe bleeding",
    "head trauma", "head injury", "spine", "spinal", "crush", "trapped",
    "multiple victims", "fire", "explosion", "fatal", "cardiac", "stroke",
    "paralyzed", "not responding", "bleeding heavily", "severe burn",
]

HIGH_KEYWORDS = [
    "bleeding", "broken bone", "fracture", "deep cut", "chest pain",
    "difficulty breathing", "concussion", "hit by car", "motorcycle accident",
    "rollover", "truck", "semi-truck", "bus accident", "multiple injuries",
    "injured badly", "badly hurt", "serious", "severe",
]

MODERATE_KEYWORDS = [
    "accident", "collision", "crash", "fender bender", "hurt",
    "pain", "wound", "bruise", "injury", "hit", "bumped", "fell",
    "minor accident", "fainted", "dizzy",
]

LOW_KEYWORDS = [
    "flat tyre", "flat tire", "puncture", "breakdown", "stalled",
    "out of fuel", "locked out", "minor scratch", "small dent",
    "vehicle issue", "car trouble", "need towing",
]

# ── SLM system prompt for triage ──────────────────────────────────────────
TRIAGE_SYSTEM_PROMPT = """You are RoadSoS, an emergency medical triage assistant for road accidents.
Analyze the incident description and respond ONLY with a JSON object in this exact format:
{
  "severity": "<critical|high|moderate|low>",
  "injury_types": ["<list of injury keywords>"],
  "needs_ambulance": <true|false>,
  "needs_trauma_center": <true|false>,
  "needs_police": <true|false>,
  "needs_towing": <true|false>,
  "summary": "<one sentence summary of situation>"
}
Be conservative: when in doubt, escalate severity. Lives depend on accuracy."""


class AITriageEngine:
    """
    Dual-mode triage engine:
      1. SLM mode: uses local Ollama instance (if running)
      2. Deterministic fallback: keyword-based classifier
    """

    def __init__(self, model_name: str = "qwen2.5:0.5b", ollama_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.ollama_url = ollama_url
        self._ollama_available = self._check_ollama()

    def _check_ollama(self) -> bool:
        """Check if local Ollama instance is running (offline-first check)."""
        try:
            import urllib.request
            req = urllib.request.urlopen(f"{self.ollama_url}/api/tags", timeout=2)
            return req.status == 200
        except Exception:
            print("[Triage] Ollama not running; using deterministic keyword classifier.")
            return False

    def classify_severity(self, incident_text: str) -> str:
        """
        Classify incident severity from free-text description.
        Returns one of: 'critical', 'high', 'moderate', 'low'
        """
        if self._ollama_available:
            result = self._slm_triage(incident_text)
            if result:
                return result.get("severity", "moderate")
        return self._keyword_classify(incident_text)

    def full_triage(self, incident_text: str) -> Dict:
        """
        Full triage analysis: severity + service needs + summary.
        Used to drive intelligent service filtering.
        """
        if self._ollama_available:
            result = self._slm_triage(incident_text)
            if result:
                return result

        # Deterministic fallback with inferred service needs
        severity = self._keyword_classify(incident_text)
        text_lower = incident_text.lower()
        return {
            "severity": severity,
            "injury_types": self._extract_injury_keywords(incident_text),
            "needs_ambulance": severity in ("critical", "high"),
            "needs_trauma_center": severity == "critical",
            "needs_police": any(w in text_lower for w in ["accident", "collision", "crash", "hit"]),
            "needs_towing": any(w in text_lower for w in ["tow", "stuck", "breakdown", "flat", "puncture"]),
            "summary": self._generate_summary(incident_text, severity),
        }

    def _slm_triage(self, incident_text: str) -> Optional[Dict]:
        """Query local Ollama SLM for structured triage output."""
        try:
            import json
            import urllib.request
            import urllib.error

            payload = json.dumps({
                "model": self.model_name,
                "system": TRIAGE_SYSTEM_PROMPT,
                "prompt": f"Incident: {incident_text}",
                "stream": False,
                "format": "json",
            }).encode("utf-8")

            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data.get("response", "")
                # Strip any markdown code fences
                response_text = re.sub(r"```[a-z]*\n?", "", response_text).strip()
                return json.loads(response_text)
        except Exception as e:
            print(f"[Triage] SLM query failed: {e}. Falling back to keyword classifier.")
            return None

    def _keyword_classify(self, text: str) -> str:
        """Rule-based keyword classifier - zero dependencies, always available."""
        text_lower = text.lower()
        score = 0
        if any(kw in text_lower for kw in CRITICAL_KEYWORDS):
            return "critical"
        if any(kw in text_lower for kw in HIGH_KEYWORDS):
            return "high"
        if any(kw in text_lower for kw in MODERATE_KEYWORDS):
            return "moderate"
        if any(kw in text_lower for kw in LOW_KEYWORDS):
            return "low"
        # Default for road-related but unspecified situations
        return "moderate"

    def _extract_injury_keywords(self, text: str) -> list:
        """Extract relevant medical/incident keywords from text."""
        text_lower = text.lower()
        found = []
        for kw_list in [CRITICAL_KEYWORDS, HIGH_KEYWORDS, MODERATE_KEYWORDS]:
            found.extend(kw for kw in kw_list if kw in text_lower)
        return list(set(found))[:5]

    def _generate_summary(self, text: str, severity: str) -> str:
        """Generate a concise summary for the incident log."""
        severity_label = {
            "critical": "CRITICAL road accident",
            "high":     "Serious road incident",
            "moderate": "Road accident",
            "low":      "Minor road incident",
        }.get(severity, "Road incident")
        # Truncate input for summary
        excerpt = text[:100].strip()
        return f"{severity_label}: {excerpt}"

    def draft_sos_message(self, lat: float, lon: float, incident_text: str,
                          severity: str, nearest_service_name: str = "") -> str:
        """
        Draft a concise SMS/SOS alert message for low-network fallback.
        Formatted to fit within SMS character limits (~160 chars).
        """
        severity_code = {"critical": "CRITICAL", "high": "URGENT", "moderate": "ACCIDENT", "low": "BREAKDOWN"}
        code = severity_code.get(severity, "ACCIDENT")
        location = f"GPS:{lat:.5f},{lon:.5f}"
        maps_link = f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"
        service_str = f" Near:{nearest_service_name[:20]}" if nearest_service_name else ""
        return (
            f"[RoadSoS {code}] {location}{service_str} "
            f"Incident:{incident_text[:50]} "
            f"Location:{maps_link}"
        )
