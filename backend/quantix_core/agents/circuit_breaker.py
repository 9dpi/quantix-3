"""
Circuit Breaker Agent — Stage 4
===================================
Ngăn chặn spam tín hiệu: cooldown, max active signals, global lock.
Subscribe: stage_3.validated_signal → Publish: stage_4.circuit_result
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.database.connection import db
from backend.quantix_core.config.settings import settings


class CircuitBreakerAgent(BaseAgent):
    """
    Anti-burst system — ngăn chặn quá nhiều tín hiệu trong thời gian ngắn.
    
    Rules:
    1. Cooldown: MIN_RELEASE_INTERVAL_MINUTES giữa 2 tín hiệu
    2. Max Active: MAX_SIGNALS_PER_ASSET signals active cùng lúc per asset
    3. Daily Limit: MAX_SIGNALS_PER_DAY signals per ngày
    """
    
    def __init__(self):
        super().__init__(agent_name="circuit_breaker", stage=4)
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_VALIDATED_SIGNAL]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        payload = message.get("payload", {})
        correlation_id = message.get("correlation_id")
        
        symbol = payload.get("symbol", "EURUSD")
        
        try:
            allowed, reason = self._check_circuit(symbol)
            
            result = {
                **payload,
                "circuit_allowed": allowed,
                "circuit_reason": reason,
            }
            
            self.emit(
                channel=MessageBus.CH_CIRCUIT_RESULT,
                payload=result,
                correlation_id=correlation_id,
            )
            
            if allowed:
                logger.info(f"✅ Circuit breaker: ALLOW {symbol}")
            else:
                logger.warning(f"🚫 Circuit breaker: DENY {symbol} — {reason}")
                
        except Exception as e:
            logger.error(f"❌ Circuit breaker check failed: {e}")
            # Fail-closed: deny on error
            self.emit(
                channel=MessageBus.CH_CIRCUIT_RESULT,
                payload={**payload, "circuit_allowed": False, "circuit_reason": f"Error: {e}"},
                correlation_id=correlation_id,
            )
    
    def _check_circuit(self, symbol: str) -> tuple:
        """Kiểm tra tất cả circuit breaker rules. Returns (allowed, reason)."""
        now = datetime.now(timezone.utc)
        
        try:
            # Query active + recent signals
            res = db.client.table(settings.TABLE_SIGNALS).select("*").eq(
                "symbol", symbol
            ).execute()
            
            signals = res.data or []
        except Exception as e:
            logger.warning(f"⚠️ DB query failed in circuit check: {e}")
            return False, f"DB error: {e}"
        
        # Rule 1: Cooldown — check last signal time
        cooldown_minutes = settings.MIN_RELEASE_INTERVAL_MINUTES
        for sig in signals:
            gen_at_str = sig.get("generated_at")
            if not gen_at_str:
                continue
            try:
                gen_at = datetime.fromisoformat(gen_at_str.replace("Z", "+00:00"))
                minutes_ago = (now - gen_at).total_seconds() / 60
                if minutes_ago < cooldown_minutes:
                    return False, f"Cooldown: last signal {int(minutes_ago)}m ago (need {cooldown_minutes}m)"
            except Exception:
                continue
        
        # Rule 2: Max Active Signals
        active_states = ["WAITING_FOR_ENTRY", "ENTRY_HIT", "ACTIVE", "PUBLISHED", "PENDING"]
        active_count = len([s for s in signals if s.get("state") in active_states])
        
        if active_count >= settings.MAX_SIGNALS_PER_ASSET:
            return False, f"Max active: {active_count}/{settings.MAX_SIGNALS_PER_ASSET}"
        
        # Rule 3: Daily Limit
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_signals = 0
        for sig in signals:
            gen_at_str = sig.get("generated_at")
            if gen_at_str:
                try:
                    gen_at = datetime.fromisoformat(gen_at_str.replace("Z", "+00:00"))
                    if gen_at >= today_start:
                        today_signals += 1
                except Exception:
                    continue
        
        if today_signals >= settings.MAX_SIGNALS_PER_DAY:
            return False, f"Daily limit: {today_signals}/{settings.MAX_SIGNALS_PER_DAY}"
        
        return True, "All checks passed"


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = CircuitBreakerAgent()
    agent.start()
