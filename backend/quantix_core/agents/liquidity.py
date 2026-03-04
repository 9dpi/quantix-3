"""
Liquidity Sweep Agent — Stage 2
=================================
Phát hiện các cú quét thanh khoản tại vùng đỉnh/đáy phiên.
Subscribe: stage_1.validated_data → Publish: stage_2.liquidity_result
"""

import pandas as pd
from typing import Dict, Any, List
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.engine.primitives.liquidity_filter import LiquidityFilter
from backend.quantix_core.engine.primitives.swing_detector import SwingDetector


class LiquiditySweepAgent(BaseAgent):
    """
    Phát hiện các cú quét thanh khoản — dấu hiệu institutional activity.
    
    Quét thanh khoản xảy ra khi giá vượt qua đỉnh/đáy phiên trước đó
    và đảo chiều, bẫy các trader retail.
    """
    
    def __init__(self):
        super().__init__(agent_name="liquidity_sweep", stage=2)
        self.filter = LiquidityFilter()
        self.swing_detector = SwingDetector()
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_VALIDATED_DATA]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        payload = message.get("payload", {})
        correlation_id = message.get("correlation_id")
        
        symbol = payload.get("symbol", "EURUSD")
        timeframe = payload.get("timeframe", "M15")
        history = payload.get("history", [])
        
        if not history or len(history) < 10:
            return
        
        try:
            df = pd.DataFrame(history)
            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype(float)
            
            # 1. First detect swings needed for liquidity filter
            swings = self.swing_detector.detect_swings(df)
            
            # 2. Detect liquidity sweeps using those swings
            sweeps = self.filter.detect_sweeps(df, swings)
            
            # 3. Serialize
            sweep_list = []
            for sweep in sweeps:
                sweep_list.append({
                    "type": getattr(sweep, 'type', 'UNKNOWN'),
                    "level": getattr(sweep, 'swept_level', 0),
                    "index": getattr(sweep, 'index', -1),
                    "strength": getattr(sweep, 'rejection_strength', 0),
                })
            
            liquidity_result = {
                "symbol": symbol,
                "timeframe": timeframe,
                "sweep_count": len(sweep_list),
                "sweeps": sweep_list,
                "current_price": payload.get("current_price", {}),
            }
            
            self.emit(
                channel=MessageBus.CH_LIQUIDITY_RESULT,
                payload=liquidity_result,
                correlation_id=correlation_id,
            )
            
            logger.info(f"💧 Liquidity Analysis: {symbol} found {len(sweep_list)} sweeps")
            
        except Exception as e:
            logger.error(f"❌ Liquidity detection failed for {symbol}: {e}")


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = LiquiditySweepAgent()
    agent.start()
