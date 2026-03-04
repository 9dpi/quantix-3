"""
Session Filter Agent — Stage 3
=================================
Lọc tín hiệu theo phiên giao dịch và dead zones.
Subscribe: stage_3.confidence_result → Publish: stage_3.filtered_signal | stage_3.signal_blocked
"""

from typing import Dict, Any
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.utils.market_hours import MarketHours
from backend.quantix_core.config.settings import settings


class SessionFilterAgent(BaseAgent):
    """
    Loại bỏ tín hiệu trong các dead zones:
    - Saturday/Sunday (market closed)
    - Friday after 17:00 UTC (pre-weekend thin liquidity)
    - Rollover hours 21:00-23:00 UTC (high spread)
    - Monday before 01:00 UTC (thin opening)
    """
    
    def __init__(self):
        super().__init__(agent_name="session_filter", stage=3)
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_CONFIDENCE_RESULT]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        payload = message.get("payload", {})
        correlation_id = message.get("correlation_id")
        
        symbol = payload.get("symbol", "EURUSD")
        confidence = payload.get("final_confidence", 0)
        
        # Check market hours
        if not MarketHours.is_market_open():
            logger.info(f"🚫 Market closed — blocking signal for {symbol}")
            self.emit(
                channel=MessageBus.CH_SIGNAL_BLOCKED,
                payload={**payload, "block_reason": "MARKET_CLOSED"},
                correlation_id=correlation_id,
            )
            return
        
        # Check dead zones
        if not MarketHours.should_generate_signals():
            logger.info(f"🚫 Dead zone active — blocking signal for {symbol}")
            self.emit(
                channel=MessageBus.CH_SIGNAL_BLOCKED,
                payload={**payload, "block_reason": "DEAD_ZONE"},
                correlation_id=correlation_id,
            )
            return
        
        # Check minimum confidence threshold
        if confidence < settings.MIN_CONFIDENCE:
            logger.info(
                f"🚫 Confidence too low: {confidence:.2%} < {settings.MIN_CONFIDENCE:.2%} "
                f"— blocking {symbol}"
            )
            self.emit(
                channel=MessageBus.CH_SIGNAL_BLOCKED,
                payload={**payload, "block_reason": f"LOW_CONFIDENCE ({confidence:.2%})"},
                correlation_id=correlation_id,
            )
            return
        
        # Pass — signal is valid
        self.emit(
            channel=MessageBus.CH_FILTERED_SIGNAL,
            payload=payload,
            correlation_id=correlation_id,
        )
        
        logger.info(f"✅ Session filter passed: {symbol} confidence={confidence:.2%}")


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = SessionFilterAgent()
    agent.start()
