"""
R:R Optimizer Agent — Stage 4
================================
Tính toán TP/SL tối ưu dựa trên ATR, FVG, và loại phiên.
Subscribe: stage_3.validated_signal → Publish: stage_4.rr_result
"""

import pandas as pd
from typing import Dict, Any, Optional, Tuple
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.utils.entry_calculator import EntryCalculator
from backend.quantix_core.config.settings import settings


class RROptimizerAgent(BaseAgent):
    """
    Tính toán Risk:Reward ratio tối ưu cho mỗi tín hiệu.
    
    Logic:
    - Entry: FVG midpoint (nếu có) hoặc fixed offset
    - SL: Dựa trên swing point + buffer  
    - TP: ATR-based, điều chỉnh theo session type (PEAK/HIGH/LOW)
    - R:R tối thiểu: 1.0
    """
    
    # ATR multipliers by session type
    SESSION_TP_MULTIPLIER = {
        "PEAK": 2.5,      # London-NY overlap: aggressive TP
        "HIGH": 2.0,      # Pure London
        "LOW": 1.5,       # Asian / off-hours
    }
    
    SL_ATR_MULTIPLIER = 1.2  # SL = 1.2x ATR below/above entry
    
    def __init__(self):
        super().__init__(agent_name="rr_optimizer", stage=4)
        self.calculator = EntryCalculator(offset_pips=5.0)
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_VALIDATED_SIGNAL]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        payload = message.get("payload", {})
        correlation_id = message.get("correlation_id")
        
        symbol = payload.get("symbol", "EURUSD")
        bias = payload.get("bias", "NEUTRAL")
        current_price = payload.get("current_price", {})
        fvgs = payload.get("fvgs", [])
        
        market_price = current_price.get("close", 0)
        if not market_price or bias == "NEUTRAL":
            logger.debug(f"Skip R:R for {symbol}: no price or neutral bias")
            return
        
        try:
            direction = "BUY" if bias == "BULLISH" else "SELL"
            
            # Calculate entry using FVG if available
            fvg = self._find_best_fvg(fvgs, direction, market_price)
            entry, is_valid, entry_msg = self.calculator.calculate_fvg_entry(
                market_price=market_price,
                direction=direction,
                fvg=fvg,
            )
            
            if not is_valid:
                entry, is_valid, entry_msg = self.calculator.calculate_and_validate(
                    market_price=market_price,
                    direction=direction,
                )
            
            if not is_valid:
                logger.warning(f"⚠️ Invalid entry for {symbol}: {entry_msg}")
                return
            
            # Calculate SL and TP
            sl, tp = self._compute_sl_tp(entry, direction, market_price)
            
            # Validate R:R
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr_ratio = reward / risk if risk > 0 else 0
            
            if rr_ratio < settings.MIN_RR:
                logger.info(f"🚫 R:R too low for {symbol}: {rr_ratio:.2f} < {settings.MIN_RR}")
                return
            
            rr_result = {
                **payload,
                "direction": direction,
                "entry_price": round(entry, 5),
                "stop_loss": round(sl, 5),
                "take_profit": round(tp, 5),
                "risk_pips": round(risk / 0.0001, 1),
                "reward_pips": round(reward / 0.0001, 1),
                "rr_ratio": round(rr_ratio, 2),
                "entry_method": entry_msg,
            }
            
            self.emit(
                channel=MessageBus.CH_RR_RESULT,
                payload=rr_result,
                correlation_id=correlation_id,
            )
            
            logger.info(
                f"📊 R:R Optimized: {symbol} {direction} "
                f"entry={entry:.5f} SL={sl:.5f} TP={tp:.5f} R:R={rr_ratio:.2f}"
            )
            
        except Exception as e:
            logger.error(f"❌ R:R calculation failed for {symbol}: {e}")
    
    def _compute_sl_tp(self, entry: float, direction: str, market_price: float) -> Tuple[float, float]:
        """Tính SL/TP dựa trên fixed ATR estimate."""
        # Estimate ATR from typical EURUSD M15 range (~5-15 pips)
        atr_estimate = 0.0010  # 10 pips default
        
        sl_distance = atr_estimate * self.SL_ATR_MULTIPLIER
        tp_distance = atr_estimate * self.SESSION_TP_MULTIPLIER.get("HIGH", 2.0)
        
        if direction == "BUY":
            sl = entry - sl_distance
            tp = entry + tp_distance
        else:
            sl = entry + sl_distance
            tp = entry - tp_distance
        
        return sl, tp
    
    def _find_best_fvg(self, fvgs: list, direction: str, market_price: float):
        """Tìm FVG phù hợp nhất cho entry."""
        if not fvgs:
            return None
        
        # Simple: dùng FVG đầu tiên phù hợp
        target_type = "BULLISH" if direction == "BUY" else "BEARISH"
        for fvg_data in fvgs:
            if fvg_data.get("type") == target_type:
                # Create a simple FVG-like object
                class FVGProxy:
                    def __init__(self, data):
                        self.midpoint = data.get("midpoint", 0)
                        self.quality = data.get("quality", "UNKNOWN")
                        self.type = data.get("type")
                        self.high = data.get("high", 0)
                        self.low = data.get("low", 0)
                
                return FVGProxy(fvg_data)
        
        return None


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = RROptimizerAgent()
    agent.start()
