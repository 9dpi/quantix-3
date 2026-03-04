"""
Confidence Scorer Agent — Stage 3
====================================
Tổng hợp kết quả từ BOS, FVG, Liquidity (Stage 2) và tính confidence score.
Subscribe: stage_2.bos_result, stage_2.fvg_result, stage_2.liquidity_result
Publish: stage_3.confidence_result

QUAN TRỌNG: Agent này phải đợi đủ 3 kết quả từ Stage 2 
(matching correlation_id) trước khi tính score.
"""

import time
import threading
from typing import Dict, Any, Optional
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.engine.confidence_refiner import ConfidenceRefiner


class ConfidenceScorerAgent(BaseAgent):
    """
    Tổng hợp tất cả kết quả phân tích cấu trúc và tính confidence score.
    
    Sử dụng correlation_id để match kết quả từ cùng một data cycle.
    Timeout: nếu sau 60s chưa đủ 3 kết quả → tính với dữ liệu có sẵn.
    """
    
    AGGREGATION_TIMEOUT = 60  # seconds
    
    def __init__(self):
        super().__init__(agent_name="confidence_scorer", stage=3)
        self.refiner = ConfidenceRefiner()
        # Buffer: {correlation_id: {"bos": ..., "fvg": ..., "liquidity": ..., "ts": ...}}
        self._buffer: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        
        # Start cleanup thread for expired buffers
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
    
    @property
    def subscriptions(self) -> list:
        return [
            MessageBus.CH_BOS_RESULT,
            MessageBus.CH_FVG_RESULT,
            MessageBus.CH_LIQUIDITY_RESULT,
        ]
    
    def on_start(self):
        self._cleanup_thread.start()
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        correlation_id = message.get("correlation_id")
        if not correlation_id:
            return
        
        event = message.get("event", "")
        payload = message.get("payload", {})
        
        with self._lock:
            if correlation_id not in self._buffer:
                self._buffer[correlation_id] = {"ts": time.time()}
            
            # Store result by type
            if "bos" in event:
                self._buffer[correlation_id]["bos"] = payload
            elif "fvg" in event:
                self._buffer[correlation_id]["fvg"] = payload
            elif "liquidity" in event:
                self._buffer[correlation_id]["liquidity"] = payload
            
            # Check if all 3 results arrived
            buf = self._buffer[correlation_id]
            has_all = all(k in buf for k in ["bos", "fvg", "liquidity"])
        
        if has_all:
            self._compute_and_emit(correlation_id)
    
    def _compute_and_emit(self, correlation_id: str):
        """Tính confidence score từ dữ liệu đã tổng hợp."""
        with self._lock:
            buf = self._buffer.pop(correlation_id, None)
        
        if not buf:
            return
        
        bos_data = buf.get("bos", {})
        fvg_data = buf.get("fvg", {})
        liquidity_data = buf.get("liquidity", {})
        
        symbol = bos_data.get("symbol", fvg_data.get("symbol", "EURUSD"))
        timeframe = bos_data.get("timeframe", "M15")
        
        try:
            # Calculate base confidence from structure analysis
            structure_confidence = bos_data.get("confidence", 0)
            
            # Apply refinements (session weight, volatility, spread)
            release_score, reason = self.refiner.calculate_release_score(
                raw_confidence=structure_confidence
            )
            
            # Combine additional factors
            fvg_bonus = min(0.05, fvg_data.get("fvg_count", 0) * 0.02)
            liquidity_bonus = min(0.05, liquidity_data.get("sweep_count", 0) * 0.03)
            
            final_score = min(1.0, release_score + fvg_bonus + liquidity_bonus)
            
            result = {
                "symbol": symbol,
                "timeframe": timeframe,
                "raw_confidence": structure_confidence,
                "release_score": release_score,
                "final_confidence": round(final_score, 4),
                "refinement_reason": reason,
                "bias": bos_data.get("bias", "NEUTRAL"),
                "fvg_count": fvg_data.get("fvg_count", 0),
                "fvgs": fvg_data.get("fvgs", []),
                "sweep_count": liquidity_data.get("sweep_count", 0),
                "sweeps": liquidity_data.get("sweeps", []),
                "structure_events": bos_data.get("structure_events", []),
                "current_price": fvg_data.get("current_price", {}),
            }
            
            self.emit(
                channel=MessageBus.CH_CONFIDENCE_RESULT,
                payload=result,
                correlation_id=correlation_id,
            )
            
            logger.info(
                f"🎯 Confidence: {symbol} score={final_score:.2%} "
                f"(raw={structure_confidence:.2f}, refined={release_score:.4f}, "
                f"fvg+={fvg_bonus:.2f}, liq+={liquidity_bonus:.2f})"
            )
            
        except Exception as e:
            logger.error(f"❌ Confidence calculation failed: {e}")
    
    def _cleanup_loop(self):
        """Dọn dẹp buffer items quá timeout và tính với dữ liệu partial."""
        while self._running:
            time.sleep(15)
            now = time.time()
            expired = []
            
            with self._lock:
                for corr_id, buf in self._buffer.items():
                    if now - buf.get("ts", now) > self.AGGREGATION_TIMEOUT:
                        expired.append(corr_id)
            
            for corr_id in expired:
                logger.warning(f"⏱️ Aggregation timeout for {corr_id[:8]}. Computing with partial data.")
                self._compute_and_emit(corr_id)


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = ConfidenceScorerAgent()
    agent.start()
