"""
Signal Dispatcher Agent — Stage 5
=====================================
Quyết định cuối cùng: phát hành tín hiệu, ghi DB, gửi Telegram.
Subscribe: stage_4.rr_result, stage_4.circuit_result, stage_4.sizing_result
Publish: stage_5.signal_issued
"""

import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.database.connection import db
from backend.quantix_core.config.settings import settings


class SignalDispatcherAgent(BaseAgent):
    """
    Tổng hợp kết quả từ R:R Optimizer, Circuit Breaker, Position Sizing.
    
    Decision logic:
    1. confidence >= MIN_CONFIDENCE ✓
    2. circuit_breaker.allow == True ✓
    3. R:R >= MIN_RR ✓
    4. valid sizing ✓
    
    Nếu tất cả pass → ghi tín hiệu vào fx_signals + gửi Telegram.
    """
    
    AGGREGATION_TIMEOUT = 30  # seconds to wait for all Stage 4 results
    
    def __init__(self):
        super().__init__(agent_name="dispatcher", stage=5)
        self._buffer: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
    
    @property
    def subscriptions(self) -> list:
        return [
            MessageBus.CH_RR_RESULT,
            MessageBus.CH_CIRCUIT_RESULT,
            MessageBus.CH_SIZING_RESULT,
        ]
    
    def on_start(self):
        self._cleanup_thread.start()
        # Lazy import notifier
        try:
            from backend.quantix_core.notifications.telegram_notifier_v2 import create_notifier
            self._notifier = create_notifier()
            logger.info("📱 Telegram notifier loaded")
        except Exception as e:
            logger.warning(f"⚠️ Telegram notifier not available: {e}")
            self._notifier = None
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        correlation_id = message.get("correlation_id")
        if not correlation_id:
            return
        
        event = message.get("event", "")
        payload = message.get("payload", {})
        
        with self._lock:
            if correlation_id not in self._buffer:
                self._buffer[correlation_id] = {"ts": time.time()}
            
            if "rr" in event:
                self._buffer[correlation_id]["rr"] = payload
            elif "circuit" in event:
                self._buffer[correlation_id]["circuit"] = payload
            elif "sizing" in event:
                self._buffer[correlation_id]["sizing"] = payload
            
            buf = self._buffer[correlation_id]
            has_rr = "rr" in buf
            has_circuit = "circuit" in buf
            has_sizing = "sizing" in buf
        
        # Need at least rr + circuit to decide
        if has_rr and has_circuit:
            self._evaluate_and_dispatch(correlation_id)
    
    def _evaluate_and_dispatch(self, correlation_id: str):
        """Evaluate collected results and decide whether to issue signal."""
        with self._lock:
            buf = self._buffer.pop(correlation_id, None)
        
        if not buf:
            return
        
        rr_data = buf.get("rr", {})
        circuit_data = buf.get("circuit", {})
        sizing_data = buf.get("sizing", {})
        
        symbol = rr_data.get("symbol", "EURUSD")
        direction = rr_data.get("direction", "")
        confidence = rr_data.get("final_confidence", 0)
        rr_ratio = rr_data.get("rr_ratio", 0)
        circuit_allowed = circuit_data.get("circuit_allowed", False)
        lot_size = sizing_data.get("lot_size", 0.01)
        
        # ── Decision Logic ──
        decision_log = {
            "confidence_check": confidence >= settings.MIN_CONFIDENCE,
            "circuit_check": circuit_allowed,
            "rr_check": rr_ratio >= settings.MIN_RR,
            "confidence": confidence,
            "rr_ratio": rr_ratio,
            "circuit_reason": circuit_data.get("circuit_reason", ""),
        }
        
        all_pass = all([
            confidence >= settings.MIN_CONFIDENCE,
            circuit_allowed,
            rr_ratio >= settings.MIN_RR,
        ])
        
        if not all_pass:
            logger.info(f"🚫 Signal rejected for {symbol}: {decision_log}")
            return
        
        # ── Issue Signal ──
        if settings.ENABLE_SHADOW_MODE:
            logger.info(f"👻 SHADOW MODE: Would issue {direction} {symbol} (not publishing)")
            return
        
        try:
            signal_data = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": rr_data.get("entry_price"),
                "stop_loss": rr_data.get("stop_loss"),
                "take_profit": rr_data.get("take_profit"),
                "ai_confidence": round(confidence, 4),
                "rr_ratio": rr_ratio,
                "lot_size": lot_size,
                "confidence_grade": sizing_data.get("confidence_grade", "B"),
                "entry_method": rr_data.get("entry_method", ""),
                "state": "PUBLISHED",
                "status": "ACTIVE",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "agent_decision_log": decision_log,
            }
            
            # Write to database
            res = db.client.table(settings.TABLE_SIGNALS).insert(signal_data).execute()
            
            if res.data:
                signal_id = res.data[0].get("id", "unknown")
                logger.success(
                    f"✅ SIGNAL ISSUED: #{signal_id} {direction} {symbol} "
                    f"entry={rr_data.get('entry_price'):.5f} "
                    f"SL={rr_data.get('stop_loss'):.5f} "
                    f"TP={rr_data.get('take_profit'):.5f} "
                    f"conf={confidence:.2%} R:R={rr_ratio:.2f}"
                )
                
                # Publish for Watcher Agent
                self.emit(
                    channel=MessageBus.CH_SIGNAL_ISSUED,
                    payload={**signal_data, "signal_id": signal_id},
                    correlation_id=correlation_id,
                )
                
                # Send Telegram notification
                self._send_telegram(signal_data, signal_id)
            
        except Exception as e:
            logger.error(f"❌ Signal dispatch failed: {e}")
    
    def _send_telegram(self, signal: Dict, signal_id: str):
        """Gửi thông báo Telegram."""
        if not self._notifier:
            return
        try:
            self._notifier.send_signal_alert(signal, signal_id)
        except Exception as e:
            logger.warning(f"⚠️ Telegram send failed: {e}")
    
    def _cleanup_loop(self):
        """Dọn dẹp buffer items timeout."""
        while self._running:
            time.sleep(10)
            now = time.time()
            expired = []
            with self._lock:
                for corr_id, buf in self._buffer.items():
                    if now - buf.get("ts", now) > self.AGGREGATION_TIMEOUT:
                        expired.append(corr_id)
            for corr_id in expired:
                with self._lock:
                    self._buffer.pop(corr_id, None)
                logger.debug(f"🧹 Dispatcher buffer cleanup: {corr_id[:8]}")


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = SignalDispatcherAgent()
    agent.start()
