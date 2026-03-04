"""
BOS Detector Agent — Stage 2
==============================
Phát hiện Break of Structure (BOS) theo cả hai chiều.
Subscribe: stage_1.validated_data → Publish: stage_2.bos_result
"""

import pandas as pd
from typing import Dict, Any, List
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.engine.structure_engine_v1 import StructureEngineV1


class BOSDetectorAgent(BaseAgent):
    """
    Phân tích cấu trúc thị trường: BOS, CHoCH, swing points.
    
    Gọi StructureEngineV1.analyze() và extract kết quả BOS.
    """
    
    def __init__(self):
        super().__init__(agent_name="bos_detector", stage=2)
        self.engine = StructureEngineV1(sensitivity=2)
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_VALIDATED_DATA]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        payload = message.get("payload", {})
        correlation_id = message.get("correlation_id")
        
        symbol = payload.get("symbol", "EURUSD")
        timeframe = payload.get("timeframe", "M15")
        history = payload.get("history", [])
        
        if not history:
            return
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(history)
            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype(float)
            
            # Chạy engine analysis
            state = self.engine.analyze(
                df=df,
                symbol=symbol,
                timeframe=timeframe,
                source="binance"
            )
            
            # Extract BOS results
            api_response = self.engine.to_api_response(state)
            
            bos_result = {
                "symbol": symbol,
                "timeframe": timeframe,
                "bias": api_response.get("bias", "NEUTRAL"),
                "confidence": api_response.get("confidence", 0),
                "structure_events": api_response.get("events", []),
                "swing_points": api_response.get("swings", []),
                "reasoning": api_response.get("reasoning", ""),
            }
            
            self.emit(
                channel=MessageBus.CH_BOS_RESULT,
                payload=bos_result,
                correlation_id=correlation_id,
            )
            
            logger.info(
                f"📐 BOS Analysis: {symbol} bias={bos_result['bias']} "
                f"confidence={bos_result['confidence']:.2f}"
            )
            
        except Exception as e:
            logger.error(f"❌ BOS analysis failed for {symbol}: {e}")


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = BOSDetectorAgent()
    agent.start()
