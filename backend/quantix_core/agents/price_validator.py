"""
Price Validator Agent — Stage 3
==================================
Kiểm tra chéo giá với nguồn thứ hai để đảm bảo tính chính xác.
Subscribe: stage_3.filtered_signal → Publish: stage_3.validated_signal
"""

from typing import Dict, Any
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.feeds.binance_feed import BinanceFeed
from backend.quantix_core.database.connection import db
from backend.quantix_core.config.settings import settings


class PriceValidatorAgent(BaseAgent):
    """
    Cross-validate giá hiện tại với nguồn thứ hai.
    
    Ghi kết quả validation vào fx_signal_validation table.
    Cảnh báo nếu slippage vượt ngưỡng (> 5 pips).
    """
    
    MAX_SLIPPAGE_PIPS = 5.0
    
    def __init__(self):
        super().__init__(agent_name="price_validator", stage=3)
        self.validation_feed = BinanceFeed(timeout=8)
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_FILTERED_SIGNAL]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        payload = message.get("payload", {})
        correlation_id = message.get("correlation_id")
        
        symbol = payload.get("symbol", "EURUSD")
        current_price = payload.get("current_price", {})
        primary_close = current_price.get("close", 0)
        
        if not primary_close:
            # No price to validate — pass through
            self.emit(
                channel=MessageBus.CH_VALIDATED_SIGNAL,
                payload={**payload, "price_validated": False, "validation_note": "No primary price"},
                correlation_id=correlation_id,
            )
            return
        
        try:
            # Fetch from validation source
            validation_price = self.validation_feed.get_price(symbol)
            
            if not validation_price:
                logger.warning(f"⚠️ Validation feed unavailable for {symbol}")
                # Still pass through with warning
                self.emit(
                    channel=MessageBus.CH_VALIDATED_SIGNAL,
                    payload={**payload, "price_validated": False, "validation_note": "Validation feed down"},
                    correlation_id=correlation_id,
                )
                return
            
            validation_close = validation_price.get("close", 0)
            slippage_pips = abs(primary_close - validation_close) / 0.0001
            
            # Log validation result
            self._log_validation(symbol, primary_close, validation_close, slippage_pips)
            
            if slippage_pips > self.MAX_SLIPPAGE_PIPS:
                logger.warning(
                    f"⚠️ High slippage for {symbol}: {slippage_pips:.1f} pips "
                    f"(primary={primary_close:.5f}, validation={validation_close:.5f})"
                )
                # Still pass but flag it
                payload["high_slippage"] = True
                payload["slippage_pips"] = round(slippage_pips, 1)
            
            self.emit(
                channel=MessageBus.CH_VALIDATED_SIGNAL,
                payload={
                    **payload,
                    "price_validated": True,
                    "validation_price": validation_close,
                    "slippage_pips": round(slippage_pips, 1),
                },
                correlation_id=correlation_id,
            )
            
            logger.info(f"✅ Price validated: {symbol} slippage={slippage_pips:.1f} pips")
            
        except Exception as e:
            logger.error(f"❌ Price validation failed for {symbol}: {e}")
            # Fail-open: pass through
            self.emit(
                channel=MessageBus.CH_VALIDATED_SIGNAL,
                payload={**payload, "price_validated": False, "validation_note": str(e)},
                correlation_id=correlation_id,
            )
    
    def _log_validation(self, symbol: str, primary: float, validation: float, slippage: float):
        """Ghi kết quả validation vào DB."""
        try:
            db.client.table(settings.TABLE_VALIDATION).insert({
                "symbol": symbol,
                "primary_price": primary,
                "validation_price": validation,
                "slippage_pips": round(slippage, 2),
                "source": "binance_cross_check",
            }).execute()
        except Exception as e:
            logger.debug(f"Validation log DB error (non-critical): {e}")


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = PriceValidatorAgent()
    agent.start()
