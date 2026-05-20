<div align="center">

# 🚨 RoadSoS

### AI-Powered Offline Emergency Response System

*National Road Safety Hackathon 2026 | CoERS, RBG Labs, IIT Madras*

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Offline-First](https://img.shields.io/badge/Offline-First-green.svg)](https://github.com)
[![Edge AI](https://img.shields.io/badge/Edge-AI-orange.svg)](https://github.com)

**When every second counts, RoadSoS delivers — even without internet.**

[Features](#-features) • [Quick Start](#-quick-start) • [Architecture](#-architecture) • [API](#-api-reference) • [Contributing](#-contributing)

</div>

---

## 🎯 Problem Statement

Road accidents claim **1.3 million lives annually** worldwide. In remote areas and during network outages, emergency response is critically delayed due to:

- ❌ Dependence on cloud-based mapping services
- ❌ Inability to locate nearest emergency services offline
- ❌ Lack of AI-powered triage for severity assessment
- ❌ No SMS fallback for zero-connectivity scenarios

**RoadSoS solves this with a fully offline, edge-AI powered emergency response system.**

---

## ✨ Features

### 🔌 **100% Offline Operation**
- **No internet required** — all data and AI models run locally
- SQLite spatial database with R*Tree indexing for instant proximity search
- Bundled OpenStreetMap (OSM) emergency services data
- Works in remote areas, tunnels, and during network outages

### 🤖 **AI-Powered Triage**
- **Dual-mode intelligence:**
  - Primary: Local Small Language Model (SLM) via Ollama (Qwen 2.5 0.5B / Llama 3.2 1B)
  - Fallback: Deterministic keyword classifier (zero dependencies)
- Automatic severity classification: `critical` | `high` | `moderate` | `low`
- Intelligent service routing based on incident analysis
- Trauma center prioritization for critical cases

### 📍 **Geospatial Intelligence**
- **Haversine-based proximity search** with sub-millisecond response times
- Reverse geocoding using offline GeoJSON administrative boundaries
- Compass bearing and cardinal direction guidance
- Multi-tier service prioritization (hospitals, police, ambulance, towing, mechanics)

### 📱 **SMS Fallback Engine**
- Auto-generates concise SOS messages for low-bandwidth scenarios
- GPS coordinate embedding with Google Maps links
- Queues messages for auto-send when network is restored
- Emergency contact auto-detection from nearest services

### 🗺️ **CoERS Sanjaya Integration**
- GeoJSON export of incident logs for blackspot heatmap analytics
- Real-time incident logging with severity metadata
- Compatible with CoERS national road safety platform

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- (Optional) [Ollama](https://ollama.ai) for AI triage (runs separately)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/roadsos.git
cd roadsos

# Install dependencies
pip install -r requirements.txt

# (Optional) Install Ollama for AI triage
# Visit: https://ollama.ai/download
# Then pull a lightweight model:
ollama pull qwen2.5:0.5b
```

### Running RoadSoS

#### 1️⃣ **Interactive CLI Mode** (Default)

```bash
python main.py
```

**Example interaction:**
```
You: I'm at 21.1458, 79.0882. Severe accident, person unconscious
RoadSoS: 🚨 CRITICAL EMERGENCY — Calling for immediate trauma care!

📋 Assessment: CRITICAL road accident: Severe accident, person unconscious

🔎 Nearest Emergency Services:

1. 🚨 Trauma Centre [EMERGENCY FACILITY]
   Government Medical College & Hospital
   📍 2.3 km NE | ☎ +91-712-2234567
   Civil Lines, Nagpur, Maharashtra

2. 🚑 Ambulance Service
   108 Emergency Ambulance
   📍 3.1 km E | ☎ 108
   Sitabuldi, Nagpur
```

#### 2️⃣ **API Server Mode**

```bash
python main.py --mode api --port 5000
```

**Endpoints:**
- `POST /api/chat` — Conversational interface
- `POST /api/emergency` — Direct emergency lookup
- `GET /api/sanjaya_export` — GeoJSON incident export
- `GET /api/health` — System health check

#### 3️⃣ **Database Seed Only**

```bash
python main.py --mode seed
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      RoadSoS System                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐      ┌──────────────┐                   │
│  │   CLI / API  │◄────►│   Chatbot    │                   │
│  │   Interface  │      │   Orchestrator│                   │
│  └──────────────┘      └───────┬──────┘                   │
│                                 │                           │
│         ┌───────────────────────┼───────────────────┐      │
│         │                       │                   │      │
│         ▼                       ▼                   ▼      │
│  ┌─────────────┐       ┌──────────────┐    ┌─────────────┐│
│  │ AI Triage   │       │  Geospatial  │    │ SMS Fallback││
│  │   Engine    │       │    Engine    │    │   Engine    ││
│  │             │       │              │    │             ││
│  │ • Ollama SLM│       │ • R*Tree     │    │ • SOS Draft ││
│  │ • Keyword   │       │ • Haversine  │    │ • Queue Mgmt││
│  │   Fallback  │       │ • GeoJSON    │    │             ││
│  └─────────────┘       └──────┬───────┘    └─────────────┘│
│                                │                            │
│                                ▼                            │
│                    ┌────────────────────┐                  │
│                    │  SQLite Database   │                  │
│                    │                    │                  │
│                    │ • emergency_services│                 │
│                    │ • services_rtree   │                  │
│                    │ • incident_log     │                  │
│                    │ • admin_boundaries │                  │
│                    └────────────────────┘                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Key Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Database** | SQLite + R*Tree | Offline spatial indexing |
| **AI Triage** | Ollama (Qwen/Llama) | Local severity classification |
| **Geospatial** | GeoPandas + Shapely | Polygon containment & distance calc |
| **Vector Search** | sqlite-vec | Semantic similarity (optional) |
| **API Server** | Flask | REST API for integrations |
| **Data Source** | OpenStreetMap | Emergency services POI data |

---

## 📡 API Reference

### `POST /api/chat`

Conversational interface for emergency assistance.

**Request:**
```json
{
  "message": "Accident on highway, person bleeding",
  "latitude": 21.1458,
  "longitude": 79.0882
}
```

**Response:**
```json
{
  "response": "⚠️ SERIOUS INCIDENT — Emergency services needed urgently...",
  "status": "ok"
}
```

### `POST /api/emergency`

Direct emergency service lookup without conversation.

**Request:**
```json
{
  "latitude": 21.1458,
  "longitude": 79.0882,
  "incident_description": "severe accident"
}
```

**Response:**
```json
{
  "services": [
    {
      "name": "Government Medical College",
      "service_type": "hospital",
      "distance_km": 2.3,
      "phone": "+91-712-2234567",
      "has_emergency": true
    }
  ],
  "severity": "high",
  "status": "ok"
}
```

### `GET /api/sanjaya_export`

Export incident logs as GeoJSON for CoERS Sanjaya integration.

**Response:**
```json
{
  "type": "FeatureCollection",
  "metadata": {
    "source": "RoadSoS v1.0",
    "coers_target": "Sanjaya Blackspot Analytics"
  },
  "features": [...]
}
```

---

## 🗂️ Project Structure

```
roadsos/
├── main.py                    # Entry point (CLI/API modes)
├── requirements.txt           # Python dependencies
├── modules/
│   ├── chatbot.py            # Conversational orchestrator
│   ├── ai_triage.py          # AI severity classification
│   ├── geospatial.py         # Offline proximity search
│   ├── database.py           # SQLite + R*Tree manager
│   ├── sms_fallback.py       # SMS/SOS message generator
│   └── data_seeder.py        # OSM data importer
├── data/
│   ├── roadsos.db            # SQLite spatial database (auto-generated)
│   └── admin_boundaries.geojson  # Offline jurisdiction data
└── tests/
    └── test_roadsos.py       # Unit & integration tests
```

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/

# Run with coverage
python -m pytest --cov=modules tests/

# Test specific module
python -m pytest tests/test_roadsos.py::test_triage_engine
```

---

## 🌍 Global Applicability

RoadSoS is designed for **worldwide deployment**:

- ✅ **Any country** — OSM data covers 200+ countries
- ✅ **Any language** — SLM models support multilingual input
- ✅ **Any device** — Runs on laptops, edge servers, Raspberry Pi
- ✅ **Any network** — Fully functional offline

### Deployment Scenarios

| Scenario | Configuration |
|----------|--------------|
| **Rural India** | CLI mode on Android (Termux) |
| **Highway Patrol** | API mode on vehicle-mounted tablet |
| **Emergency Call Center** | API integration with existing systems |
| **Disaster Response** | Offline mesh network deployment |

---

## 🤝 Contributing

We welcome contributions! Here's how you can help:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Commit your changes** (`git commit -m 'Add amazing feature'`)
4. **Push to the branch** (`git push origin feature/amazing-feature`)
5. **Open a Pull Request**

### Development Setup

```bash
# Install dev dependencies
pip install -r requirements.txt
pip install pytest pytest-cov black flake8

# Run linter
flake8 modules/ tests/

# Format code
black modules/ tests/

# Run tests
pytest
```

---

## 📊 Performance Benchmarks

| Operation | Time | Notes |
|-----------|------|-------|
| Proximity search (5 results) | **< 5ms** | R*Tree + Haversine |
| AI triage (Ollama) | **200-500ms** | Qwen 2.5 0.5B on CPU |
| AI triage (keyword fallback) | **< 1ms** | Deterministic classifier |
| Database initialization | **2-5 seconds** | One-time on first run |
| GeoJSON export (100 incidents) | **< 50ms** | Sanjaya integration |

*Tested on: Intel i5-8250U, 8GB RAM, SSD*

---

## 🛡️ Privacy & Security

- ✅ **Zero data transmission** — all processing happens locally
- ✅ **No API keys required** — no third-party dependencies
- ✅ **No user tracking** — incident logs stored locally only
- ✅ **GDPR compliant** — no personal data leaves the device

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **CoERS (Centre of Excellence for Road Safety)** — Problem statement & guidance
- **RBG Labs, IIT Madras** — Hackathon organization
- **OpenStreetMap Contributors** — Emergency services data
- **Ollama Team** — Local SLM inference framework
- **SQLite R*Tree Module** — Spatial indexing engine

---

## 📞 Contact & Support

- **Team Lead:** [Your Name](mailto:your.email@example.com)
- **Project Repository:** [github.com/your-org/roadsos](https://github.com/your-org/roadsos)
- **Issues & Bug Reports:** [GitHub Issues](https://github.com/your-org/roadsos/issues)
- **CoERS Hackathon:** [coers.iitm.ac.in](https://coers.iitm.ac.in)

---

<div align="center">

### 🚨 Built with ❤️ for Road Safety

**RoadSoS** — *Because every life matters, online or offline.*

[⬆ Back to Top](#-roadsos)

</div>
