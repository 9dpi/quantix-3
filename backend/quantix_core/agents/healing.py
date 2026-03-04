"""
Healing Agent — Stage 5 (System)
====================================
Giám sát sức khỏe toàn bộ hệ thống multi-agent.
Thay thế Watchdog — có khả năng active healing.

Subscribe: system.heartbeat
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.database.connection import db
from backend.quantix_core.engine.janitor import Janitor
from backend.quantix_core.config.settings import settings


class HealingAgent(BaseAgent):
    """
    System health monitor + active healing capabilities.
    
    Responsibilities:
    1. Track agent heartbeats — detect agents that stopped responding
    2. Run Janitor cleanup — giải phóng stuck signals
    3. Alert admin — khi agent chết hoặc hệ thống bất thường
    4. Dead letter queue review — xem xét messages xử lý lỗi
    """
    
    JANITOR_INTERVAL = 300  # Run janitor every 5 minutes
    DLQ_CHECK_INTERVAL = 600  # Check DLQ every 10 minutes
    
    # Expected agents list
    EXPECTED_AGENTS = [
        "data_fetcher", "data_quality",
        "bos_detector", "fvg_locator", "liquidity_sweep",
        "confidence_scorer", "session_filter", "price_validator",
        "rr_optimizer", "circuit_breaker", "position_sizing",
        "dispatcher", "watcher",
    ]
    
    def __init__(self):
        super().__init__(agent_name="healing", stage=0)
        self._agent_status: Dict[str, Dict] = {}
        self._last_janitor_run = 0
        self._last_dlq_check = 0
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_AGENT_HEARTBEAT]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        """Process heartbeat from other agents."""
        agent_id = message.get("agent_id", "")
        payload = message.get("payload", {})
        
        self._agent_status[agent_id] = {
            "last_seen": datetime.now(timezone.utc),
            "status": payload.get("status", "unknown"),
            "stage": payload.get("metadata", {}).get("stage", 0),
            "messages": payload.get("metadata", {}).get("messages_processed", 0),
            "errors": payload.get("metadata", {}).get("errors", 0),
            "uptime": payload.get("metadata", {}).get("uptime_seconds", 0),
        }
        
        # Persist to DB
        self._persist_heartbeat(agent_id, payload)
    
    def run_cycle(self) -> Optional[float]:
        """Periodic health checks."""
        now = time.time()
        
        # 1. Check for dead agents
        self._check_agent_health()
        
        # 2. Run Janitor cleanup
        if now - self._last_janitor_run >= self.JANITOR_INTERVAL:
            self._run_janitor()
            self._last_janitor_run = now
        
        # 3. Check Dead Letter Queue
        if now - self._last_dlq_check >= self.DLQ_CHECK_INTERVAL:
            self._check_dlq()
            self._last_dlq_check = now
        
        return 60.0  # Check every 60 seconds
    
    def _check_agent_health(self):
        """Phát hiện agents không gửi heartbeat."""
        now = datetime.now(timezone.utc)
        timeout = settings.AGENT_HEARTBEAT_TIMEOUT
        
        dead_agents = []
        
        for agent_id, status in self._agent_status.items():
            last_seen = status.get("last_seen")
            if last_seen:
                seconds_ago = (now - last_seen).total_seconds()
                if seconds_ago > timeout:
                    dead_agents.append({
                        "agent_id": agent_id,
                        "last_seen_seconds_ago": int(seconds_ago),
                        "last_status": status.get("status"),
                    })
        
        if dead_agents:
            logger.critical(f"💀 DEAD AGENTS DETECTED: {len(dead_agents)}")
            for da in dead_agents:
                logger.critical(
                    f"  - {da['agent_id']}: last seen {da['last_seen_seconds_ago']}s ago "
                    f"(timeout={timeout}s)"
                )
            
            # Send admin alert
            self.emit(
                channel=MessageBus.CH_ADMIN_ALERT,
                payload={
                    "alert_type": "DEAD_AGENTS",
                    "dead_agents": dead_agents,
                    "timestamp": now.isoformat(),
                },
            )
    
    def _run_janitor(self):
        """Run Janitor cleanup to fix stuck signals."""
        logger.info("🧹 Healing: running Janitor cleanup...")
        try:
            Janitor.run_sync()
        except Exception as e:
            logger.error(f"❌ Janitor run failed: {e}")
    
    def _check_dlq(self):
        """Check Dead Letter Queue for failed messages."""
        try:
            dlq_length = self.bus.redis.llen(MessageBus.CH_DEAD_LETTER)
            if dlq_length > 0:
                logger.warning(f"📬 Dead Letter Queue has {dlq_length} unprocessed messages")
                
                if dlq_length > 50:
                    self.emit(
                        channel=MessageBus.CH_ADMIN_ALERT,
                        payload={
                            "alert_type": "DLQ_OVERFLOW",
                            "dlq_length": dlq_length,
                        },
                    )
        except Exception as e:
            logger.debug(f"DLQ check error: {e}")
    
    def _persist_heartbeat(self, agent_id: str, payload: Dict):
        """Ghi heartbeat vào DB (upsert pattern)."""
        try:
            heartbeat_data = {
                "agent_id": agent_id,
                "agent_name": agent_id.rsplit("_", 1)[0] if "_" in agent_id else agent_id,
                "stage": payload.get("metadata", {}).get("stage", 0),
                "status": payload.get("status", "unknown"),
                "messages_processed": payload.get("metadata", {}).get("messages_processed", 0),
                "errors": payload.get("metadata", {}).get("errors", 0),
                "uptime_seconds": payload.get("metadata", {}).get("uptime_seconds", 0),
                "metadata": payload.get("metadata", {}),
                "last_seen": datetime.now(timezone.utc).isoformat(),
            }
            
            # Upsert: update if exists, insert if not
            db.client.table(settings.TABLE_HEARTBEAT).upsert(
                heartbeat_data,
                on_conflict="agent_id"
            ).execute()
            
        except Exception as e:
            logger.debug(f"Heartbeat persist error (non-critical): {e}")
    
    def on_start(self):
        logger.info(f"🏥 Healing Agent monitoring {len(self.EXPECTED_AGENTS)} expected agents")
        logger.info(f"🔧 Janitor interval: {self.JANITOR_INTERVAL}s, "
                     f"DLQ check interval: {self.DLQ_CHECK_INTERVAL}s, "
                     f"Heartbeat timeout: {settings.AGENT_HEARTBEAT_TIMEOUT}s")


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = HealingAgent()
    agent.start()
