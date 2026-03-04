"""
Position Sizing Agent — Stage 4
===================================
Đề xuất khối lượng vào lệnh dựa trên confidence và risk.
Subscribe: stage_4.rr_result → Publish: stage_4.sizing_result
"""

from typing import Dict, Any
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.config.settings import settings


class PositionSizingAgent(BaseAgent):
    """
    Tính toán khối lượng vào lệnh sử dụng Modified Kelly Criterion.
    
    Formula:
        kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
        position_size = kelly_fraction * confidence * base_lot
        
    Safety constraints:
        - Max lot size capped
        - Minimum lot size enforced
        - Scale by confidence grade
    """
    
    # Default parameters (sẽ được điều chỉnh bởi historical performance)
    BASE_LOT = 0.01           # Lot cơ sở
    MAX_LOT = 0.10            # Max lot
    MIN_LOT = 0.01            # Min lot
    ASSUMED_WIN_RATE = 0.55   # Baseline assumption
    ASSUMED_AVG_WIN = 1.5     # Avg win in R
    ASSUMED_AVG_LOSS = 1.0    # Avg loss in R
    
    # Confidence → lot multiplier
    CONFIDENCE_SCALE = {
        "A+": 1.0,   # >= 95%
        "A":  0.8,   # >= 90%
        "B+": 0.6,   # >= 85%
        "B":  0.4,   # >= 80%
    }
    
    def __init__(self):
        super().__init__(agent_name="position_sizing", stage=4)
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_RR_RESULT]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        payload = message.get("payload", {})
        correlation_id = message.get("correlation_id")
        
        confidence = payload.get("final_confidence", 0)
        rr_ratio = payload.get("rr_ratio", 0)
        symbol = payload.get("symbol", "EURUSD")
        
        try:
            lot_size = self._calculate_lot(confidence, rr_ratio)
            grade = self._get_grade(confidence)
            
            sizing_result = {
                **payload,
                "lot_size": lot_size,
                "confidence_grade": grade,
                "sizing_method": "modified_kelly",
            }
            
            self.emit(
                channel=MessageBus.CH_SIZING_RESULT,
                payload=sizing_result,
                correlation_id=correlation_id,
            )
            
            logger.info(
                f"📏 Position sizing: {symbol} lot={lot_size} "
                f"grade={grade} confidence={confidence:.2%}"
            )
            
        except Exception as e:
            logger.error(f"❌ Position sizing failed: {e}")
    
    def _calculate_lot(self, confidence: float, rr_ratio: float) -> float:
        """Modified Kelly Criterion with confidence scaling."""
        # Kelly fraction
        kelly = (
            self.ASSUMED_WIN_RATE * self.ASSUMED_AVG_WIN
            - (1 - self.ASSUMED_WIN_RATE) * self.ASSUMED_AVG_LOSS
        ) / self.ASSUMED_AVG_WIN
        
        kelly = max(0, kelly)  # Never negative
        
        # Scale by confidence grade
        grade = self._get_grade(confidence)
        scale = self.CONFIDENCE_SCALE.get(grade, 0.4)
        
        # Calculate position size
        lot = self.BASE_LOT * kelly * scale * (1 + rr_ratio * 0.1)
        
        # Clamp to bounds
        lot = max(self.MIN_LOT, min(self.MAX_LOT, round(lot, 2)))
        
        return lot
    
    def _get_grade(self, confidence: float) -> str:
        """Map confidence to grade."""
        if confidence >= settings.CONFIDENCE_A_PLUS:
            return "A+"
        elif confidence >= settings.CONFIDENCE_A:
            return "A"
        elif confidence >= settings.CONFIDENCE_B_PLUS:
            return "B+"
        elif confidence >= settings.CONFIDENCE_B:
            return "B"
        return "C"


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = PositionSizingAgent()
    agent.start()
