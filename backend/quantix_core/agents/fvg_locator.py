"""
FVG Locator Agent — Stage 2
=============================
Xác định các Fair Value Gaps (FVG) trên khung M15.
Subscribe: stage_1.validated_data → Publish: stage_2.fvg_result
"""

import pandas as pd
from typing import Dict, Any, List
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.engine.primitives.fvg_detector import FVGDetector


class FVGLocatorAgent(BaseAgent):
    """
    Phát hiện Fair Value Gaps — vùng mất cân bằng giá tiềm năng.
    
    FVG xuất hiện khi có khoảng trống giữa nến 1 và nến 3,
    cho thấy vùng giá chưa được test lại.
    """
    
    def __init__(self):
        super().__init__(agent_name="fvg_locator", stage=2)
        self.detector = FVGDetector()
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_VALIDATED_DATA]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        payload = message.get("payload", {})
        correlation_id = message.get("correlation_id")
        
        symbol = payload.get("symbol", "EURUSD")
        timeframe = payload.get("timeframe", "M15")
        history = payload.get("history", [])
        
        if not history or len(history) < 5:
            return
        
        try:
            df = pd.DataFrame(history)
            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype(float)
            
            # 1. Detect FVGs (Corrected method name)
            fvgs = self.detector.detect_fvgs(df)
            
            # 2. Serialize FVGs (Corrected attribute names)
            fvg_list = []
            for fvg in fvgs:
                fvg_list.append({
                    "type": getattr(fvg, 'type', 'UNKNOWN'),
                    "top": getattr(fvg, 'top', 0),
                    "bottom": getattr(fvg, 'bottom', 0),
                    "midpoint": getattr(fvg, 'midpoint', 0),
                    "size_pips": getattr(fvg, 'size_pips', 0),
                    "quality": getattr(fvg, 'quality', 0),
                    "index": getattr(fvg, 'index', -1),
                })
            
            fvg_result = {
                "symbol": symbol,
                "timeframe": timeframe,
                "fvg_count": len(fvg_list),
                "fvgs": fvg_list,
                "current_price": payload.get("current_price", {}),
            }
            
            self.emit(
                channel=MessageBus.CH_FVG_RESULT,
                payload=fvg_result,
                correlation_id=correlation_id,
            )
            
            logger.info(f"🔲 FVG Analysis: {symbol} found {len(fvg_list)} FVGs")
            
        except Exception as e:
            logger.error(f"❌ FVG detection failed for {symbol}: {e}")


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = FVGLocatorAgent()
    agent.start()
