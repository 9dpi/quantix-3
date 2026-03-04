"""
Quantix AI Core - Multi-Agent Web API
=======================================
FastAPI server cho dashboard và monitoring.
"""

import uvicorn
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
import os

from backend.quantix_core.config.settings import settings
from backend.quantix_core.database.connection import db


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Multi-Agent Forex Signal Intelligence System",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static Files (Assets) ────────────────────────────────────────

# Mount static files to serve style.css, simulator.js etc.
# We mount last to avoid shadowing API routes.
app.mount("/static", StaticFiles(directory="."), name="static")


# ── Dashboard UI ─────────────────────────────────────────────────

@app.get("/")
def root():
    """Serve the Dashboard HTML UI."""
    index_path = os.path.join(os.getcwd(), "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "message": "Dashboard UI (index.html) not found in root.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/health")
def health_check():
    db_healthy = db.health_check()
    return {
        "status": "healthy" if db_healthy else "degraded",
        "database": "connected" if db_healthy else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Signals ──────────────────────────────────────────────────────

@app.get("/api/v1/signals")
def get_signals(limit: int = 50, state: str = None):
    """Get recent signals."""
    try:
        query = db.client.table(settings.TABLE_SIGNALS).select("*").order(
            "generated_at", desc=True
        ).limit(limit)
        
        if state:
            query = query.eq("state", state)
        
        res = query.execute()
        return {"signals": res.data or [], "count": len(res.data or []), "success": True}
    except Exception as e:
        logger.error(f"Error fetching signals: {e}")
        return {"error": str(e), "signals": [], "success": False}


@app.get("/api/v1/signals/active")
def get_active_signals():
    """Get currently active signals."""
    try:
        active_states = ["PUBLISHED", "WAITING_FOR_ENTRY", "ENTRY_HIT", "ACTIVE"]
        res = db.client.table(settings.TABLE_SIGNALS).select("*").in_(
            "state", active_states
        ).order("generated_at", desc=True).execute()
        return {"signals": res.data or [], "count": len(res.data or [])}
    except Exception as e:
        return {"error": str(e), "signals": []}


# ── Agent Status ─────────────────────────────────────────────────

@app.get("/api/v1/agents/status")
def get_agent_status():
    """Get heartbeat status of all agents."""
    try:
        res = db.client.table(settings.TABLE_HEARTBEAT).select("*").order(
            "last_seen", desc=True
        ).execute()
        
        agents = res.data or []
        now = datetime.now(timezone.utc)
        
        for agent in agents:
            last_seen_str = agent.get("last_seen")
            if last_seen_str:
                try:
                    last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                    seconds_ago = (now - last_seen).total_seconds()
                    agent["seconds_since_heartbeat"] = int(seconds_ago)
                    agent["is_alive"] = seconds_ago < settings.AGENT_HEARTBEAT_TIMEOUT
                except Exception:
                    agent["is_alive"] = False
        
        return {"agents": agents, "count": len(agents)}
    except Exception as e:
        return {"error": str(e), "agents": []}


# ── Stats ────────────────────────────────────────────────────────

@app.get("/api/v1/stats")
def get_stats():
    """Get system performance stats."""
    try:
        res = db.client.table(settings.TABLE_SIGNALS).select("*").execute()
        signals = res.data or []
        
        total = len(signals)
        wins = len([s for s in signals if s.get("state") == "TP_HIT"])
        losses = len([s for s in signals if s.get("state") == "SL_HIT"])
        active = len([s for s in signals if s.get("state") in ["PUBLISHED", "ACTIVE", "ENTRY_HIT"]])
        
        win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0
        
        return {
            "total_signals": total,
            "wins": wins,
            "losses": losses,
            "active": active,
            "win_rate": round(win_rate, 4),
        }
    except Exception as e:
        return {"error": str(e)}

# ── Logs & Validation ──────────────────────────────────────────

@app.get("/api/v1/validation-logs")
def get_validation_logs(limit: int = 50):
    """Get signal validation logs."""
    try:
        res = db.client.table(settings.TABLE_VALIDATION).select("*").order(
            "created_at", desc=True
        ).limit(limit).execute()
        return {"data": res.data or [], "count": len(res.data or []), "success": True}
    except Exception as e:
        logger.warning(f"Validation logs table issue: {e}")
        return {"data": [], "count": 0, "success": True}


@app.get("/api/v1/analysis-logs")
def get_analysis_logs(limit: int = 20):
    """Get AI analysis logs."""
    try:
        res = db.client.table(settings.TABLE_ANALYSIS_LOG).select("*").order(
            "timestamp", desc=True
        ).limit(limit).execute()
        return {"data": res.data or [], "count": len(res.data or []), "success": True}
    except Exception as e:
        logger.warning(f"Analysis logs table issue: {e}")
        return {"data": [], "count": 0, "success": True}


# ── Entrypoint ───────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(f"🌐 Starting {settings.APP_NAME} API on {settings.API_HOST}:{settings.API_PORT}")
    uvicorn.run(
        "backend.quantix_core.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )
