# 🌌 Quantix Multi-Agent Architecture v4.0

![Quantix Banner](https://img.shields.io/badge/Architecture-Multi--Agent_v4.0-blue?style=for-the-badge&logo=ai) 
![Stack](https://img.shields.io/badge/Stack-Python_%7C_Redis_%7C_Supabase-green?style=for-the-badge)

**Quantix Multi-Agent** is a state-of-the-art distributed forex signal intelligence system. It evolves the original Quantix AI Core from a monolithic architecture into a highly resilient, event-driven multi-agent ecosystem.

---

## 🏗 Architecture Overview

The system follows a strict 5-stage processing pipeline connected via **Redis Pub/Sub** and **Redis Streams**.

| Stage | Name | Role | Channels |
| :--- | :--- | :--- | :--- |
| **1** | **Data** | Data fetching & quality assurance | `stage_1.raw_data` → `stage_1.validated_data` |
| **2** | **Analysis** | Technical analysis (SMC, FVG, Liquidity) | `stage_2.bos_result`, `stage_2.fvg_result`, etc. |
| **3** | **Validation** | Confidence aggregation & session filtering | `stage_3.confidence_result` → `stage_3.validated_signal` |
| **4** | **Risk** | R:R optimization, circuit breaking, sizing | `stage_4.rr_result`, `stage_4.circuit_result`, etc. |
| **5** | **Decision** | Final issuance & lifecycle management | `stage_5.signal_issued` → Telegram & Dashboard |

---

## 🤖 Meet the Agents

The system currently deploys 15+ specialized agents:

- **Stage 1:** `DataFetcherAgent`, `DataQualityAgent`
- **Stage 2:** `BOSDetectorAgent`, `FVGLocatorAgent`, `LiquiditySweepAgent`
- **Stage 3:** `ConfidenceScorerAgent`, `SessionFilterAgent`, `PriceValidatorAgent`
- **Stage 4:** `RROptimizerAgent`, `CircuitBreakerAgent`, `PositionSizingAgent`
- **Stage 5:** `SignalDispatcherAgent`, `WatcherAgent`
- **System:** `HealingAgent` (Self-healing & Health Monitor), `WebAPIService`

---

## 🛠 Tech Stack

- **Core Framework:** [Python 3.11](https://www.python.org/)
- **Message Bus:** [Redis](https://redis.io/) (Pub/Sub + Streams)
- **Database:** [Supabase](https://supabase.com/) (PostgreSQL)
- **API Engine:** [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- **Strategy Engine:** Deterministic SMC-Lite logic (Price Action based)
- **Logging/Ops:** [Loguru](https://github.com/Delgan/loguru) + [Health Heartbeats](https://github.com/9dpi/quantix-3/blob/main/backend/quantix_core/agents/healing.py)

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11+
- Redis Server (Local or Managed)
- Supabase Project

### 2. Installation
```powershell
# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your keys
```

### 3. Run Agents (One Command)
You can start all 15 agents and the Web API in one go for local operation:
```powershell
# In the root project directory
$env:PYTHONPATH = "."
python start_quantix.py
```

### 4. Running Individual Agents (Manual Control)
If you prefer manual control:
```powershell
# Set PYTHONPATH for Windows/Linux
$env:PYTHONPATH = "."
python -m backend.quantix_core.agents.data_fetcher
```
Or run the Web API Dashboard alone:
```powershell
python -m backend.quantix_core.api.main
```

### 5. Running Tests
The system includes comprehensive mock pipeline tests that do not require a real Redis or DB:
```powershell
python -m tests.test_full_pipeline
```

---

## 🔧 Self-Healing & Monitoring

The architecture includes a dedicated **Healing Agent** that:
- Monitors heartbeats from all active agents.
- Automatically cleans up stuck signals (Janitor mode).
- Issues `system.admin_alert` if any agent goes offline or produces excessive errors.

---

## 🔐 Deployment

Optimized for **Railway** or **Render** deployments using the provided `Dockerfile` and `Procfile`.

> [!IMPORTANT]
> **Shadow Mode:** Ensure `ENABLE_SHADOW_MODE=true` in `.env` for the first 1-2 weeks of production to observe signal accuracy without live execution.

---

## 📜 License

© 2026 9dpi Quantix Project. Distributed under the MIT License.
