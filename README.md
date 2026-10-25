# 🔥 OBOR — Autonomous Peatland & Wildfire Intelligence System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![DuckDB](https://img.shields.io/badge/DuckDB-OLAP_Warehouse-FFF000.svg?logo=duckdb)](https://duckdb.org)
[![SQLite](https://img.shields.io/badge/SQLite-Operational_Store-003B57.svg?logo=sqlite)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **OBOR** (*Torch* in Indonesian) is an autonomous, mission-critical multi-agent system designed for real-time peatland and forest wildfire detection, predictive risk modeling, dual runtime safety governance, and tactical emergency dispatch across Kalimantan (Borneo), Indonesia.

---

## 🌟 Key Highlights

- 🛰️ **Real-Time Satellite & Telemetry Ingestion:** Continuous live data streams from NASA FIRMS VIIRS NRT (375m thermal anomalies), Himawari-8/9 geostationary observations, and Open-Meteo / BMKG weather reanalysis.
- 🏛️ **Dual Runtime Governance & Trust Supervisors:**
  - **AVF (Agent Viability Framework):** Mathematical runtime viability monitoring tracking Viability Index $VI(t)$, Lyapunov-like drift stability $V_T(t)$, monotonic alert escalation (Normal → Advisory → Watch → Warning), and predicted time to safety violation $t^*$.
  - **Jev AI Trust Supervisor:** Low-token / zero-token structured validation ensuring agent actions strictly adhere to safety boundaries, verifiable environmental facts, and emergency operational limits.
- ⚡ **Dual Database Storage Tier:**
  - **Operational SQLite (`data/operational/wildfire.db`):** High-throughput transactional store for active incidents, agent decision audit trails, and dispatch logs.
  - **Geospatial DuckDB Warehouse (`data/warehouse/wildfire.duckdb`):** High-performance analytical columnar store with peatland thickness models, historical fire frequency, and strategic water/resource buffers.
  - **Automated Hourly ETL Synchronization:** Background synchronization bridge (`src/storage/sync.py`) streaming operational records into the analytical warehouse with zero downtime.
- 🤖 **Autonomous Multi-Agent Swarm:**
  - **Orchestrator Agent (`OborAgent`):** Coordinates lifecycle, sensor evaluation, and safety compliance.
  - **Impact Assessment Agent:** Computes population, ecological, and economic vulnerability scores.
  - **Water Resource Agent:** Calculates proximity and capacity of strategic rivers, retention basins, and canals.
  - **Tactical Resource Agent:** Matches fire severity with Manggala Agni Daops and BPBD personnel equipment.
  - **Emergency Dispatcher:** Generates simulated, auditable tactical dispatch manifests with verified coordinates.
- 📊 **Real-Time Glassmorphic Command Dashboard:**
  - Dark-mode responsive UI with interactive Leaflet GIS mapping.
  - Dynamic SVG Viability Index gauge, incident metrics, and real-time Server-Sent Events (SSE).

---

## 🏗️ System Architecture

```text
       ┌────────────────────────────────────────────────────────┐
       │   Satellite & Meteorological Telemetry Ingestion       │
       │   [NASA FIRMS VIIRS]  [Himawari-8/9]  [Open-Meteo]      │
       └───────────────────────────┬────────────────────────────┘
                                   │
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │         OBOR Multi-Agent Orchestration Swarm           │
       │  ┌───────────────────┐       ┌──────────────────────┐  │
       │  │ Prediction Model  │ ──▶   │  Impact Agent        │  │
       │  └───────────────────┘       └──────────┬───────────┘  │
       │           │                             │              │
       │           ▼                             ▼              │
       │  ┌───────────────────┐       ┌──────────────────────┐  │
       │  │ Water Agent       │       │  Resource Agent      │  │
       │  └────────┬──────────┘       └──────────┬───────────┘  │
       │           └──────────────┬──────────────┘              │
       │                          ▼                             │
       │              Tactical Dispatcher (Manggala Agni)       │
       └──────────────────────────┬─────────────────────────────┘
                                  │
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │             Dual Runtime Safety Governance             │
       │  ┌──────────────────────────────────────────────────┐  │
       │  │ AVF Engine: VI(t), Stability V_T(t), TTV (t*)    │  │
       │  └──────────────────────────────────────────────────┘  │
       │  ┌──────────────────────────────────────────────────┐  │
       │  │ Jev AI Supervisor: Trust, Health & Boundaries    │  │
       │  └──────────────────────────────────────────────────┘  │
       └──────────────────────────┬─────────────────────────────┘
                                  │
                     ┌────────────┴────────────┐
                     ▼                         ▼
         ┌───────────────────────┐ ┌───────────────────────┐
         │  Operational SQLite   │ │  DuckDB Data Warehouse│
         │  (Transactional Store)│ │  (Geospatial OLAP)    │
         └───────────┬───────────┘ └───────────▲───────────┘
                     │     Hourly ETL Bridge   │
                     └─────────────────────────┘
                                  │
                                  ▼
         ┌─────────────────────────────────────────────────┐
         │   FastAPI Engine & Real-time Web Dashboard SSE  │
         └─────────────────────────────────────────────────┘
```

---

## 📂 Repository Structure

```text
.
├── data/                                # Unified data storage
│   ├── operational/wildfire.db          # SQLite operational transactional database
│   └── warehouse/wildfire.duckdb        # DuckDB analytical geospatial data warehouse
├── docs/                                # Architecture & warehouse documentation
│   ├── architecture/                    # System design, multi-agent specs & diagrams
│   └── warehouse/                       # Data dictionary, feasibility & benchmark reports
├── scripts/                             # Utility & data generation tools
│   ├── data_mining/                     # Scripts for GEE, weather, fuel, and peatland extraction
│   └── train_wildfire_models.py         # Multi-model training & ML benchmark harness
├── src/                                 # Canonical production source package
│   ├── agents/                          # Multi-agent swarm implementation
│   │   ├── orchestrator.py              # OborAgent lifecycle orchestrator
│   │   ├── dispatcher.py                # Emergency dispatch & Manggala Agni Daops
│   │   ├── impact_agent.py              # Vulnerability & exposure scoring
│   │   ├── water_agent.py               # Water body proximity & capacity routing
│   │   ├── resource_agent.py            # Equipment & crew allocation
│   │   ├── jev_supervisor.py            # Jev AI trust supervisor
│   │   └── trust_agent.py               # Multi-agent safety observer
│   ├── api/                             # FastAPI application & SSE streaming
│   │   └── app.py                       # HTTP endpoints & real-time events
│   ├── config/                          # Centralized settings & environment variables
│   │   └── settings.py                  # Pydantic-based configuration
│   ├── data/                            # Real-time satellite & weather ingestion
│   │   ├── fetcher.py                   # NASA FIRMS & BMKG client
│   │   └── spatial.py                   # Geospatial grid indexing (Kalimantan bounds)
│   ├── etl/                             # Data pipeline transformations
│   │   └── transform_environmental.py   # Environmental & satellite transformations
│   ├── governance/                      # Agent Viability Framework (AVF)
│   │   ├── engine.py                    # VI calculation & Lyapunov stability tracking
│   │   └── alerts.py                    # Monotonic alert level state machine
│   ├── ml/                              # Machine learning risk predictors
│   │   └── predictor.py                 # Multi-model inference (LightGBM, XGBoost, etc.)
│   └── storage/                         # Data persistence layer
│       ├── sqlite_db.py                 # SQLite client & schema initialization
│       ├── duckdb_client.py             # DuckDB connection & query utilities
│       ├── sync.py                      # SQLite-to-DuckDB hourly warehouse sync bridge
│       └── schema/                      # DDL definitions
├── static/                              # Front-end dashboard assets
│   ├── index.html                       # Responsive glassmorphism web console
│   ├── index.css                        # Modern CSS styling & animations
│   └── app.js                           # Leaflet GIS, SSE client & UI updates
├── tests/                               # Verification test suite
│   ├── unit/                            # 21 modular unit tests
│   └── integration/                     # End-to-end integration & low-token verification
├── main.py                              # Unified application entry point
└── requirements.txt                     # Production Python dependencies
```

---

## 🚀 Quick Start

### Option A: 🐳 Docker (Recommended for Team & Cross-Platform)

Running with Docker guarantees consistent runtime environments across Linux, macOS (Apple Silicon / Intel), and Windows without local C++/OpenMP (`libgomp`/`libomp`) dependency issues:

```bash
# 1. Clone the repository
git clone https://github.com/ProsperousJoy/obor.git
cd obor

# 2. Configure environment
cp .env.example .env

# 3. Start the system via Docker Compose
docker compose up --build
```
Open your browser at **http://localhost:8000**.

---

### Option B: 🐍 Local Python Setup

#### 1. Prerequisites
- Python 3.10 or higher
- Git

#### 2. Clone and Setup Environment
```bash
git clone https://github.com/ProsperousJoy/obor.git
cd obor

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the project root:
```env
# Operational Mode
DEMO_MODE=true               # Set to 'false' to ingest live NASA FIRMS feeds
AGENT_POLL_INTERVAL=30      # Sensor check interval in seconds

# OpenAI API Key (Optional for basic monitoring, required for full LLM analysis)
OPENAI_API_KEY=your_key_here

# Jev AI Supervisor
JEV_API_URL=https://api.jev.ai/v1
JEV_API_KEY=your_jev_key_here
```

### 4. Run the System
```bash
python main.py
```
Open your browser and navigate to:
```
http://localhost:8000
```

---

## 🧪 Testing & Verification

OBOR comes with a comprehensive test suite guaranteeing governance reliability, data integrity, and low-token verification:

```bash
# Run all unit tests (21 tests)
python3 -m unittest discover -s tests -v

# Run low-token integration test suite
python3 tests/integration/test_low_token.py

# Run end-to-end Kalimantan Borneo integration test
python3 tests/integration/test_borneo_low_token.py

# Run API endpoint integration test
python3 tests/integration/test_api_endpoints.py
```

---

## 📜 Theoretical Foundations

OBOR's governance layer implements runtime viability algorithms adapted from:
> **"Governing What You Cannot Observe: Adaptive Runtime Governance for Autonomous AI Agents"**  
> *Marín & Chaudhary (2026)*

Key formulations implemented:
- **Viability Index ($VI$):** Quantifies distance from safety violation manifolds in multi-dimensional agent decision space.
- **Lyapunov Stability Tracking ($V_T$):** Ensures that perturbation responses remain bounded over time.
- **Time to Violation ($t^*$):** Predictive early warning estimating minutes remaining before critical containment capacity is exceeded.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
