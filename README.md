<div align="center">

# 🚨 RoadSoS

### AI-Powered Offline Emergency Response Chatbot for Road Accidents

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/SQLite-R*Tree-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Ollama](https://img.shields.io/badge/Ollama-SLM-black?style=for-the-badge&logo=ollama&logoColor=white)](https://ollama.ai/)
[![OpenStreetMap](https://img.shields.io/badge/OpenStreetMap-Data-7EBC6F?style=for-the-badge&logo=openstreetmap&logoColor=white)](https://www.openstreetmap.org/)
[![Tests](https://img.shields.io/badge/Tests-28%2F28%20Passing-52B043?style=for-the-badge&logo=pytest&logoColor=white)](./tests/)
[![Offline](https://img.shields.io/badge/Network-100%25%20Offline-red?style=for-the-badge&logo=wifi&logoColor=white)]()
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](./LICENSE)

<br/>

**Submitted to the National Road Safety Hackathon 2026**  
*CoERS · RBG Labs · IIT Madras · JSPM's Rajarshi Shahu College of Engineering*

<br/>

> *"Because every second in the golden hour counts — and no accident should wait for a mobile signal."*

<br/>

[**Quick Start**](#-quick-start) · [**Architecture**](#-architecture) · [**Features**](#-features) · [**API Reference**](#-api-reference) · [**Tests**](#-testing) · [**CoERS Integration**](#-coers-governance-integration)

</div>

---

## 📖 Table of Contents

- [Overview](#-overview)
- [The Problem](#-the-problem)
- [Features](#-features)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Detailed Setup](#-detailed-setup)
  - [1. Clone & Install](#1-clone--install-dependencies)
  - [2. Set Up Ollama (AI Engine)](#2-set-up-ollama-optional-but-recommended)
  - [3. Seed the Database](#3-seed-the-offline-database)
  - [4. Run CLI Mode](#4-run-in-cli-mode)
  - [5. Run API Server](#5-run-as-api-server)
- [Usage Guide](#-usage-guide)
- [API Reference](#-api-reference)
- [Testing](#-testing)
- [Configuration](#-configuration)
- [CoERS Governance Integration](#-coers-governance-integration)
- [Tech Stack](#-tech-stack)
- [Performance](#-performance)
- [Troubleshooting](#-troubleshooting)

---

## 🌟 Overview

RoadSoS is a **fully offline, AI-powered emergency response chatbot** that provides instant access to nearby trauma centres, hospitals, police stations, ambulance services, towing, and puncture shops during road accidents — **with zero internet connection required**.

The application uses three core technologies working entirely on-device:

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **AI Triage** | Qwen3.5-0.8B via Ollama + keyword fallback | Classifies incident severity, determines service needs |
| **Spatial DB** | SQLite R\*Tree + Haversine ranking | Sub-2ms offline proximity queries for emergency services |
| **Geofencing** | OpenStreetMap + GeoPandas | Offline jurisdiction detection and global data coverage |

> **Every component runs on the edge device. No API keys. No cloud. No signal needed.**

---

## 🔴 The Problem

India records **over 1.7 lakh road fatalities annually**. A large proportion are attributable to delays in emergency response — caused by:

- 📵 **Dead zones on highways** — where accident blackspots and no-signal zones coincide
- 🗂️ **Fragmented information** — emergency contacts spread across government portals, none offline-capable
- 🏥 **Poor triage** — bystanders cannot distinguish a trauma centre from a basic clinic
- 🌍 **No global standard** — India, UK, US, and Singapore all use different emergency schemas

RoadSoS solves all four — for any country, on any network condition.

---

## ✨ Features

### Core Emergency Features
- 🏥 **Intelligent Hospital Triage** — filters trauma-capable facilities vs. basic care based on AI severity classification
- 🚔 **Nearest Police Station** — with direct phone numbers, distance, and compass bearing
- 🚑 **Ambulance Services** — including national numbers (108 India, 999 UK, 911 USA)
- 🔧 **Towing & Puncture Shops** — for breakdowns and minor incidents
- 📍 **Haversine-ranked results** — sorted by real great-circle distance, not just bounding box

### AI & Intelligence
- 🧠 **On-device SLM Triage** — Qwen3.5-0.8B or Llama 3.2 1B via Ollama; zero cloud calls
- 🔑 **Keyword Fallback Classifier** — 4-tier severity system (Critical / High / Moderate / Low); always available
- 💬 **Natural Language Interface** — describe your emergency in plain text; AI handles the rest
- 📦 **sqlite-vec Semantic Search** — vector embeddings stored as BLOBs for semantic RAG queries

### Offline & Reliability
- 📴 **100% Offline Runtime** — GPS → R-Tree → Response pipeline requires no internet
- 📱 **SMS SOS Fallback** — compresses distress signal into SMS format for GSM dispatch (no data needed)
- 🗺️ **OSM-sourced Data** — OpenStreetMap via Overpass QL; one-time seeding, all subsequent queries offline
- 🌍 **Global Coverage** — India, United Kingdom, United States, Singapore bundled; extensible to any OSM country

### Integration
- 📊 **Sanjaya GeoJSON Export** — incident data formatted for CoERS Sanjaya blackspot analytics
- 🔌 **Flask REST API** — for mobile app frontends and CoERS platform integration
- 📝 **Incident Logging** — every emergency logged locally for DDHI/RATH data pipeline

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INPUT                              │
│              GPS Coordinates + Incident Description             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AI TRIAGE ENGINE                             │
│  ┌─────────────────────┐    ┌──────────────────────────────┐   │
│  │  Ollama SLM         │    │  Keyword Classifier          │   │
│  │  (Qwen3.5-0.8B)     │ OR │  (Zero dependencies,         │   │
│  │  JSON schema output │    │   always available)          │   │
│  └─────────────────────┘    └──────────────────────────────┘   │
│           │                                                      │
│           ▼                                                      │
│  severity: critical | high | moderate | low                     │
│  needs_ambulance | needs_trauma_center | needs_police           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  GEOSPATIAL ENGINE                              │
│                                                                  │
│  1. Hardware GPS → lat/lon (no network)                         │
│  2. GeoPandas sjoin → jurisdiction detection                    │
│  3. R-Tree bounding box pre-filter (< 1ms)                      │
│  4. Haversine re-ranking (precise great-circle distance)        │
│  5. Severity filter (trauma_only for critical incidents)        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              SQLITE SPATIAL DATABASE                            │
│  ┌──────────────────┐  ┌─────────────────┐  ┌───────────────┐ │
│  │ emergency_       │  │ services_rtree  │  │ sqlite-vec    │ │
│  │ services         │  │ (virtual table) │  │ embeddings    │ │
│  │ 23+ POIs         │  │ R*Tree index    │  │ BLOB vectors  │ │
│  └──────────────────┘  └─────────────────┘  └───────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RESPONSE                                   │
│  Ranked emergency list + compass bearing + phone numbers        │
│  + Incident logged + GeoJSON queued for Sanjaya export          │
│  + SMS SOS queued if no data signal                             │
└─────────────────────────────────────────────────────────────────┘
```

### Offline Guarantee

| Component | Internet Required? |
|-----------|-------------------|
| GPS coordinate reading | ❌ Never (hardware GNSS) |
| SQLite R-Tree spatial query | ❌ Never |
| Keyword triage classifier | ❌ Never |
| SLM inference (Ollama) | ❌ Never (model pre-downloaded) |
| Incident logging | ❌ Never |
| SMS SOS dispatch | ❌ Never (GSM only) |
| Initial OSM data seeding | ✅ Once only |
| Ollama model download | ✅ Once only |
| Sanjaya GeoJSON push | ✅ When available |

---

## 📁 Project Structure

```
roadsos/
│
├── main.py                        # Entry point (CLI / API / seed modes)
├── requirements.txt               # Python dependencies
│
├── modules/
│   ├── __init__.py
│   ├── database.py                # SQLite R*Tree manager + sqlite-vec integration
│   │                              #   → DatabaseManager, haversine_km()
│   │
│   ├── geospatial.py              # Offline GPS, geofencing, proximity search
│   │                              #   → GeospatialEngine, bearing(), bearing_to_direction()
│   │
│   ├── ai_triage.py               # Dual-mode AI triage engine
│   │                              #   → AITriageEngine (Ollama SLM + keyword fallback)
│   │
│   ├── chatbot.py                 # Conversation manager + Sanjaya export
│   │                              #   → RoadSoSChatbot, export_geojson()
│   │
│   ├── sms_fallback.py            # Low-network SMS queue engine
│   │                              #   → SMSFallbackEngine, queue_sms(), flush_queue()
│   │
│   └── data_seeder.py             # OSM Overpass data pipeline + bundled seed data
│                                  #   → DataSeeder, 23 pre-seeded POIs across 4 countries
│
├── tests/
│   └── test_roadsos.py            # 28-test offline unit test suite
│
└── data/                          # Auto-created at runtime
    ├── roadsos.db                 # SQLite spatial database (R-Tree indexed)
    ├── sms_queue.db               # SMS fallback queue
    └── admin_boundaries.geojson   # Optional: offline geofencing polygons
```

---

## ⚙️ Prerequisites

### Required
| Requirement | Version | Notes |
|------------|---------|-------|
| Python | 3.10+ | `python --version` to check |
| pip | 23+ | Bundled with Python |

### Recommended (for full AI features)
| Requirement | Notes |
|------------|-------|
| [Ollama](https://ollama.ai) | Enables on-device SLM triage. Without it, the keyword classifier handles triage automatically. |
| 4 GB RAM | Minimum for Qwen3.5-0.8B (1.6 GB). 8 GB recommended for Llama 3.2 1B (2.5 GB). |
| GNSS/GPS hardware | Required for real location; simulation via manual coordinate input works without it. |

### Optional (for enhanced features)
| Package | Purpose |
|---------|---------|
| `geopandas` + `shapely` | Precise offline geofencing with GeoJSON admin boundaries |
| `flask` | REST API server for mobile app and CoERS Sanjaya integration |
| `sqlite-vec` | Semantic vector search (RAG pipeline) |

> **Minimum viable setup:** Python 3.10+ only. No Ollama, no geopandas required. The app will run fully offline using the keyword classifier and bounding-box geofencing fallbacks.

---

## 🚀 Quick Start

Get RoadSoS running in under 2 minutes:

```bash
# 1. Clone the repository
git clone https://github.com/<your-team>/roadsos.git
cd roadsos

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch (seeds DB automatically on first run)
python main.py --mode cli
```

That's it. The database seeds itself and you're in the interactive emergency chatbot.

---

## 🔧 Detailed Setup

### 1. Clone & Install Dependencies

```bash
# Clone
git clone https://github.com/<your-team>/roadsos.git
cd roadsos

# Create a virtual environment (recommended)
python -m venv venv

# Activate it
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install core + optional dependencies
pip install -r requirements.txt

# For systems using externally-managed Python (e.g. Ubuntu 24.04):
pip install -r requirements.txt --break-system-packages
```

**Verify installation:**
```bash
python -c "import sqlite3; print('SQLite:', sqlite3.sqlite_version)"
python -c "import geopandas; print('GeoPandas:', geopandas.__version__)"
```

---

### 2. Set Up Ollama (Optional but Recommended)

Ollama enables full on-device AI triage with the Small Language Model. Skip this section to use the keyword classifier fallback instead.

**Install Ollama:**

```bash
# Linux / macOS
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: Download from https://ollama.ai/download
```

**Pull a model** (choose based on your available RAM):

```bash
# Ultra-lightweight: ~800 MB download, ~1.6 GB RAM (recommended for most devices)
ollama pull qwen3.5:0.8b

# More capable: ~1.2 GB download, ~2.0 GB RAM
ollama pull qwen3.5:1.5b

# Best quality: ~2.0 GB download, ~2.5 GB RAM
ollama pull llama3.2:1b
```

**Start Ollama service:**
```bash
ollama serve
# Runs at http://localhost:11434 — leave this terminal open
```

**Verify Ollama is running:**
```bash
curl http://localhost:11434/api/tags
# Should return JSON with your installed models
```

> **Note:** If Ollama is not running, RoadSoS automatically falls back to the deterministic keyword classifier. No configuration needed — it's seamless.

---

### 3. Seed the Offline Database

The database seeds automatically on first launch, but you can seed it manually:

```bash
# Seed only (no interactive session)
python main.py --mode seed

# Expected output:
# [RoadSoS] Initializing offline spatial database...
# [Seeder] Inserting 23 emergency service records...
# [Seeder] Total services in DB: 23
# [RoadSoS] Database initialization complete.
```

**To seed from live OpenStreetMap data** (requires internet, one time only):

```python
# Run this Python snippet once to fetch live OSM data for India:
from modules.database import DatabaseManager
from modules.data_seeder import DataSeeder

db = DatabaseManager("data/roadsos.db")
db.initialize_schema()
seeder = DataSeeder(db)

# Fetch from Overpass API for India bounding box
seeder.fetch_from_overpass(country_code="IN", state_bbox=(8.0, 68.0, 37.6, 97.4))
```

After seeding, all subsequent runs are **100% offline**.

---

### 4. Run in CLI Mode

The interactive command-line chatbot:

```bash
python main.py --mode cli
```

```
============================================================
  RoadSoS - Road Emergency Response Assistant
  Powered by Offline Edge AI | CoERS Hackathon 2026
============================================================
Type 'help' for commands, 'quit' to exit.

You: 
```

**Try these example inputs:**

```
# Set your location first (GPS coordinates):
You: 21.1458, 79.0882

# Describe an emergency:
You: severe accident on the highway, person unconscious, head trauma

# Find specific services:
You: find nearest police station
You: nearest hospital

# Trigger SMS SOS mode (for no-signal scenarios):
You: send SOS

# Check system status:
You: status

# Get help:
You: help
```

**Example session output:**
```
You: 21.1458, 79.0882
RoadSoS: 📍 Location set: 21.1458, 79.0882
         Describe your situation or search for services.

You: severe accident, person bleeding from head, unconscious

RoadSoS: 🚨 CRITICAL EMERGENCY — Calling for immediate trauma care!

         📋 Assessment: CRITICAL road accident: severe accident, person bleeding...

         🔎 Nearest Emergency Services:

         1. 🏥 Hospital / Trauma Centre [EMERGENCY FACILITY]
            Government Medical College & Hospital
            📍 0.98 km N | ☎ 0712-2701000
            Hanuman Nagar, Nagpur, MH 440003

         2. 🚑 Ambulance Service
            Samarth Ambulance Service Nagpur
            📍 2.1 km SW | ☎ 108
            Dhantoli, Nagpur, MH 440012

         3. 🚔 Police Station
            Nagpur Police Control Room
            📍 2.4 km NW | ☎ 0712-2567901
            Civil Lines, Nagpur, MH 440001

         📵 No signal? Type 'send SOS' to send an offline SMS alert.

         📊 Incident #1 logged for CoERS Sanjaya analytics.
```

---

### 5. Run as API Server

Launch the Flask REST API for integration with mobile frontends or the CoERS Sanjaya platform:

```bash
# Default: http://0.0.0.0:5000
python main.py --mode api

# Custom host and port
python main.py --mode api --host 127.0.0.1 --port 8080

# Custom database path
python main.py --mode api --db /path/to/custom.db
```

**Verify the server is running:**
```bash
curl http://localhost:5000/api/health
# {"status": "offline-ready", "db_connected": true}
```

---

## 📡 API Reference

### `POST /api/chat`
Natural language emergency chatbot interface.

**Request:**
```json
{
  "message": "severe accident, person injured",
  "latitude": 21.1458,
  "longitude": 79.0882
}
```

**Response:**
```json
{
  "response": "🚨 CRITICAL EMERGENCY...\n1. Government Medical College...",
  "status": "ok"
}
```

---

### `POST /api/emergency`
Direct emergency lookup — returns structured JSON of nearest services.

**Request:**
```json
{
  "latitude": 21.1458,
  "longitude": 79.0882,
  "incident_description": "head trauma, unconscious"
}
```

**Response:**
```json
{
  "severity": "critical",
  "services": [
    {
      "name": "Government Medical College & Hospital",
      "service_type": "hospital",
      "distance_km": 0.98,
      "phone": "0712-2701000",
      "has_trauma": true,
      "has_emergency": true,
      "directions_hint": "N",
      "label": "🏥 Hospital / Trauma Centre"
    }
  ],
  "status": "ok"
}
```

---

### `GET /api/sanjaya_export`
Export all logged incidents as GeoJSON for CoERS Sanjaya platform ingestion.

**Response:**
```json
{
  "type": "FeatureCollection",
  "metadata": {
    "source": "RoadSoS v1.0",
    "coers_target": "Sanjaya Blackspot Analytics"
  },
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [79.0882, 21.1458] },
      "properties": {
        "severity": "critical",
        "incident_type": "road_accident",
        "sanjaya_layer": "road_accidents"
      }
    }
  ]
}
```

---

### `GET /api/health`
System health check.

```json
{ "status": "offline-ready", "db_connected": true }
```

---

## 🧪 Testing

Run the complete 28-test offline suite:

```bash
# Run all tests
python tests/test_roadsos.py

# Or with pytest (install with: pip install pytest)
pytest tests/ -v
```

**Expected output:**
```
Running RoadSoS Test Suite...

test_zero_distance (TestHaversine) ... ok
test_known_distance (TestHaversine) ... ok
test_symmetry (TestHaversine) ... ok
test_seeding (TestDatabase) ... ok
test_rtree_query_nagpur (TestDatabase) ... ok
test_rtree_query_filter_by_type (TestDatabase) ... ok
test_rtree_trauma_only (TestDatabase) ... ok
test_rtree_returns_sorted_by_distance (TestDatabase) ... ok
test_incident_logging (TestDatabase) ... ok
test_critical_classification (TestAITriage) ... ok
test_high_classification (TestAITriage) ... ok
test_moderate_classification (TestAITriage) ... ok
test_low_classification (TestAITriage) ... ok
test_full_triage_structure (TestAITriage) ... ok
test_sos_message_length (TestAITriage) ... ok
test_critical_needs_ambulance (TestAITriage) ... ok
test_fallback_jurisdiction_india (TestGeospatial) ... ok
test_fallback_jurisdiction_uk (TestGeospatial) ... ok
test_fallback_jurisdiction_usa (TestGeospatial) ... ok
test_nearest_services_returns_results (TestGeospatial) ... ok
test_bearing_direction (TestGeospatial) ... ok
test_format_display (TestGeospatial) ... ok
test_help_command (TestChatbot) ... ok
test_status_command (TestChatbot) ... ok
test_emergency_without_location_asks_for_location (TestChatbot) ... ok
test_emergency_with_location (TestChatbot) ... ok
test_coords_extraction (TestChatbot) ... ok
test_geojson_export (TestChatbot) ... ok

----------------------------------------------------------------------
Ran 28 tests in 0.262s

OK
```

> ✅ All 28 tests are designed to pass with **network completely disabled**. No mocking of network calls — the tests prove genuine offline operation.

**Test coverage by module:**

| Test Class | Tests | What's Verified |
|-----------|-------|----------------|
| `TestHaversine` | 3 | Distance formula accuracy and mathematical properties |
| `TestDatabase` | 7 | R-Tree queries, seed data integrity, incident logging |
| `TestAITriage` | 7 | All 4 severity tiers, SOS message format, service flags |
| `TestGeospatial` | 6 | Jurisdiction detection (IN/GB/US), proximity search, display formatting |
| `TestChatbot` | 5 | Intent routing, GPS extraction, GeoJSON Sanjaya export |

---

## ⚙️ Configuration

All configuration is handled via command-line arguments. No config file needed.

```bash
python main.py --help

# Options:
#   --mode {cli,api,seed}    Run mode (default: cli)
#   --db PATH                SQLite database path (default: data/roadsos.db)
#   --host HOST              API server host (default: 0.0.0.0)
#   --port PORT              API server port (default: 5000)
```

**Changing the AI model:**

Edit the `AITriageEngine` instantiation in `main.py`:

```python
# In main.py, change the model_name parameter:
triage_engine = AITriageEngine(model_name="qwen3.5:0.8b")   # ultralight
triage_engine = AITriageEngine(model_name="qwen3.5:1.5b")   # balanced
triage_engine = AITriageEngine(model_name="llama3.2:1b")    # most capable
```

**Changing search radius:**

```python
# In chatbot.py or via direct API call:
services = geo_engine.get_nearest_services(
    lat=21.1458,
    lon=79.0882,
    severity="critical",
    radius_km=50.0,    # default: 25 km
    limit=10,          # default: 5
)
```

---

## 🏛️ CoERS Governance Integration

RoadSoS is architecturally designed as a microservice feeding into the broader CoERS ecosystem:

```
RoadSoS (Edge)
      │
      ├──── GeoJSON export ──────► SANJAYA (IIT Madras)
      │                            Location intelligence & blackspot heatmaps
      │                            Deployed in Haryana, Delhi NCR
      │
      ├──── Incident feed ───────► RATH
      │                            Odisha Integrated Road Safety Dashboard
      │                            State-level incident visualization
      │
      ├──── Emergency data ──────► DDHI
      │                            100 high-risk districts, 17 states
      │                            Emergency Care pillar of the 5E framework
      │
      └──── Hazard reports ──────► ThinnAI
                                   Driver training platform
                                   Adaptive hazard-perception scenarios
```

**Triggering a Sanjaya export:**
```bash
# Via API
curl http://localhost:5000/api/sanjaya_export

# Via Python
from modules.chatbot import RoadSoSChatbot
incidents = db.get_recent_incidents(limit=500)
geojson = chatbot.export_geojson(incidents)
# POST geojson to Sanjaya API endpoint
```

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Language** | Python 3.10+ | Dominant in AI/geospatial; preferred by hackathon |
| **Database** | SQLite 3 + R\*Tree module | Embedded, zero-config, cross-platform, <2ms spatial queries |
| **Vector Search** | sqlite-vec extension | 384-dim vector BLOBs; replaces Pinecone/Weaviate with no cloud |
| **Geospatial** | GeoPandas + Shapely | Offline GeoJSON polygon containment; no Google Maps API |
| **AI Inference** | Ollama + Qwen3.5-0.8B | On-device SLM; 200+ language support; 262K context window |
| **Map Data** | OpenStreetMap (Overpass QL) | Free, global, crowdsourced; `amenity=hospital`, `craft=towing` etc. |
| **API Server** | Flask 3.0 | Lightweight; REST endpoints for mobile and CoERS integration |
| **SMS** | GSM / Android SmsManager | No data required; pure circuit-switched SMS |
| **Testing** | Python `unittest` | Zero external dependencies; runs fully offline |

---

## ⚡ Performance

Benchmarked on Intel Core i5 (CPU only, no GPU):

| Operation | Average Time |
|-----------|-------------|
| R-Tree bounding box query (23 services) | **< 2 ms** |
| Haversine re-ranking (50 results) | **< 1 ms** |
| Keyword triage classification | **< 0.1 ms** |
| SLM triage via Ollama (Qwen3.5-0.8B) | **~800 ms** |
| Full chatbot response (no SLM) | **< 5 ms** |
| GeoJSON export (100 incidents) | **< 10 ms** |
| Database initialization + seeding | **< 300 ms** |

---

## 🔍 Troubleshooting

### ❌ `ModuleNotFoundError: No module named 'geopandas'`
```bash
pip install geopandas shapely pyproj --break-system-packages
```
GeoPandas is optional. Without it, RoadSoS uses bounding-box geofencing fallback automatically.

---

### ❌ Ollama connection refused
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not, start it
ollama serve

# Pull a model if none installed
ollama pull qwen3.5:0.8b
```
Without Ollama, RoadSoS switches to keyword classifier automatically — no action needed.

---

### ❌ `sqlite3.OperationalError: no such module: rtree`
Your SQLite build doesn't include the R\*Tree module. This is very rare on modern systems. Fix:
```bash
# Ubuntu/Debian
sudo apt-get install libsqlite3-dev

# Then reinstall Python's sqlite3 module
pip install pysqlite3-binary
```

---

### ❌ Empty results from spatial query
The bundled seed data covers: **Nagpur, Mumbai, Delhi, Chennai, Hyderabad, Bangalore** (India) + **London** (UK) + **Los Angeles** (USA) + **Singapore**. If you're querying other coordinates, either seed live OSM data or add entries manually:

```python
from modules.database import DatabaseManager
db = DatabaseManager("data/roadsos.db")
db.initialize_schema()
db.insert_service({
    "osm_id": "CUSTOM_001",
    "name": "My Local Hospital",
    "service_type": "hospital",
    "latitude": YOUR_LAT,
    "longitude": YOUR_LON,
    "phone": "YOUR_PHONE",
    "country_code": "IN",
    "has_emergency": True,
    "has_trauma": True,
})
```

---

### ❌ Tests failing
```bash
# Make sure you're in the project root
cd roadsos

# Run with verbose output
python tests/test_roadsos.py -v

# Tests use temporary databases — no setup needed
# All 28 should pass offline without any external service
```

---

## 🗺️ Global Coverage

| Country | Emergency Number | Seeded Cities | OSM Extensible? |
|---------|-----------------|---------------|-----------------|
| 🇮🇳 India | 112 / 108 / 100 | Nagpur, Mumbai, Delhi, Chennai, Hyderabad, Bangalore | ✅ Yes |
| 🇬🇧 United Kingdom | 999 | London | ✅ Yes |
| 🇺🇸 United States | 911 | Los Angeles | ✅ Yes |
| 🇸🇬 Singapore | 995 | Singapore City | ✅ Yes |
| Any country | — | — | ✅ Via OSM Overpass |

---

## 📜 License

This project is submitted under the **MIT License** for the National Road Safety Hackathon 2026.

- **OSM data**: © OpenStreetMap contributors (ODbL License)
- **Ollama**: MIT License
- **SQLite**: Public Domain
- **GeoPandas / Shapely**: BSD License

---

## 🙏 Acknowledgements

Built for the **National Road Safety Hackathon 2026**, organized by:

- **Centre of Excellence for Road Safety (CoERS)**, RBG Labs, IIT Madras
- **JSPM's Rajarshi Shahu College of Engineering**, Pune
- In association with the **Ministry of Road Transport & Highways (MoRTH)**

Data sources: OpenStreetMap contributors · Ministry of Road Transport & Highways · National Health Mission India

---

<div align="center">

**Made with ❤️ for safer roads**

*National Road Safety Hackathon 2026 · Problem Statement: RoadSoS*

</div>