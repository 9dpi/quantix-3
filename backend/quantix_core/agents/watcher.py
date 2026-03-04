"""
Watcher Agent — Stage 5
=========================
Theo dõi trạng thái các lệnh active: entry hit, SL, TP, timeout.
Subscribe: stage_5.signal_issued → Publish: stage_5.signal_updated

Kế thừa logic từ engine/signal_watcher.py.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.database.connection import db
from backend.quantix_core.config.settings import settings
from backend.quantix_core.feeds.binance_feed import BinanceFeed


class WatcherAgent(BaseAgent):
    """
    Theo dõi tín hiệu active và cập nhật trạng thái theo lifecycle:
    
    PUBLISHED → WAITING_FOR_ENTRY → ENTRY_HIT → ACTIVE
    ACTIVE → TP_HIT | SL_HIT | CANCELLED (timeout)
    
    Features:
    - Breakeven lock khi lợi nhuận đạt 50% TP
    - Timeout sau MAX_TRADE_DURATION_MINUTES
    - Atomic DB transitions (tránh duplicate Telegram)
    """
    
    def __init__(self):
        super().__init__(agent_name="watcher", stage=5)
        self.feed = BinanceFeed(timeout=5)
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_SIGNAL_ISSUED]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        """Nhận tín hiệu mới được phát hành — log để tracking."""
        payload = message.get("payload", {})
        signal_id = payload.get("signal_id")
        logger.info(f"📌 Watcher: tracking new signal #{signal_id}")
    
    def run_cycle(self) -> Optional[float]:
        """Check tất cả active signals mỗi WATCHER_CHECK_INTERVAL giây."""
        try:
            self._check_active_signals()
        except Exception as e:
            logger.error(f"❌ Watcher cycle error: {e}")
        
        return float(settings.WATCHER_CHECK_INTERVAL)
    
    def _check_active_signals(self):
        """Query và check tất cả signals đang active."""
        try:
            active_states = ["PUBLISHED", "WAITING_FOR_ENTRY", "ENTRY_HIT", "ACTIVE"]
            
            # Fetch all active signals
            res = db.client.table(settings.TABLE_SIGNALS).select("*").in_(
                "state", active_states
            ).execute()
            
            signals = res.data or []
            
            if not signals:
                return
            
            logger.debug(f"👁️ Watcher: checking {len(signals)} active signals")
            
            for signal in signals:
                try:
                    self._evaluate_signal(signal)
                except Exception as e:
                    logger.error(f"❌ Error evaluating signal {signal.get('id')}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Failed to fetch active signals: {e}")
    
    def _evaluate_signal(self, signal: Dict):
        """Đánh giá một signal dựa trên giá hiện tại."""
        signal_id = signal.get("id")
        state = signal.get("state")
        symbol = signal.get("symbol", "EURUSD")
        direction = signal.get("direction")
        entry_price = signal.get("entry_price", 0)
        stop_loss = signal.get("stop_loss", 0)
        take_profit = signal.get("take_profit", 0)
        
        if not all([entry_price, stop_loss, take_profit, direction]):
            return
        
        # Get current price
        price_data = self.feed.get_price(symbol)
        if not price_data:
            return
        
        current_price = price_data.get("close", 0)
        now = datetime.now(timezone.utc)
        
        # ── State Machine ──
        
        # PUBLISHED/WAITING → Check entry hit
        if state in ["PUBLISHED", "WAITING_FOR_ENTRY"]:
            # Check timeout
            gen_at = self._parse_time(signal.get("generated_at"))
            if gen_at:
                pending_minutes = (now - gen_at).total_seconds() / 60
                if pending_minutes >= settings.MAX_PENDING_DURATION_MINUTES:
                    self._update_signal(signal_id, "CANCELLED", "EXPIRED",
                                        f"Entry window expired ({int(pending_minutes)}m)")
                    return
            
            # Check entry hit
            if direction == "BUY" and current_price <= entry_price:
                self._update_signal(signal_id, "ENTRY_HIT", "ACTIVE",
                                    entry_hit_at=now.isoformat())
                logger.info(f"🎯 Entry HIT: #{signal_id} BUY at {current_price:.5f}")
            elif direction == "SELL" and current_price >= entry_price:
                self._update_signal(signal_id, "ENTRY_HIT", "ACTIVE",
                                    entry_hit_at=now.isoformat())
                logger.info(f"🎯 Entry HIT: #{signal_id} SELL at {current_price:.5f}")
        
        # ENTRY_HIT/ACTIVE → Check TP/SL/timeout
        elif state in ["ENTRY_HIT", "ACTIVE"]:
            # Check trade duration timeout
            hit_at = self._parse_time(signal.get("entry_hit_at") or signal.get("generated_at"))
            if hit_at:
                trade_minutes = (now - hit_at).total_seconds() / 60
                if trade_minutes >= settings.MAX_TRADE_DURATION_MINUTES:
                    self._update_signal(signal_id, "CANCELLED", "CLOSED_TIMEOUT",
                                        f"Trade duration expired ({int(trade_minutes)}m)")
                    return
            
            # Check TP hit
            if direction == "BUY" and current_price >= take_profit:
                self._update_signal(signal_id, "TP_HIT", "CLOSED", "Take Profit hit")
                logger.success(f"💰 TP HIT: #{signal_id} at {current_price:.5f}")
            elif direction == "SELL" and current_price <= take_profit:
                self._update_signal(signal_id, "TP_HIT", "CLOSED", "Take Profit hit")
                logger.success(f"💰 TP HIT: #{signal_id} at {current_price:.5f}")
            
            # Check SL hit
            elif direction == "BUY" and current_price <= stop_loss:
                self._update_signal(signal_id, "SL_HIT", "CLOSED", "Stop Loss hit")
                logger.warning(f"🔴 SL HIT: #{signal_id} at {current_price:.5f}")
            elif direction == "SELL" and current_price >= stop_loss:
                self._update_signal(signal_id, "SL_HIT", "CLOSED", "Stop Loss hit")
                logger.warning(f"🔴 SL HIT: #{signal_id} at {current_price:.5f}")
            
            # Check breakeven lock (50% of TP distance reached)
            else:
                self._check_breakeven(signal, current_price)
    
    def _check_breakeven(self, signal: Dict, current_price: float):
        """Di chuyển SL lên breakeven nếu lợi nhuận đạt 50% TP distance."""
        signal_id = signal.get("id")
        direction = signal.get("direction")
        entry_price = signal.get("entry_price", 0)
        take_profit = signal.get("take_profit", 0)
        stop_loss = signal.get("stop_loss", 0)
        
        tp_distance = abs(take_profit - entry_price)
        
        if direction == "BUY":
            current_profit = current_price - entry_price
        else:
            current_profit = entry_price - current_price
        
        # Breakeven at 50% TP
        if current_profit >= tp_distance * 0.5:
            # Move SL to entry (breakeven)
            if (direction == "BUY" and stop_loss < entry_price) or \
               (direction == "SELL" and stop_loss > entry_price):
                self._update_signal(
                    signal_id, None, None,
                    note="Breakeven lock activated",
                    new_sl=entry_price,
                )
                logger.info(f"🔒 Breakeven LOCK: #{signal_id} SL moved to {entry_price:.5f}")
    
    def _update_signal(self, signal_id: str, new_state: Optional[str], new_status: Optional[str],
                       note: str = "", entry_hit_at: str = None, new_sl: float = None):
        """Atomic update signal state in DB."""
        try:
            update_data = {}
            if new_state:
                update_data["state"] = new_state
            if new_status:
                update_data["status"] = new_status
            if entry_hit_at:
                update_data["entry_hit_at"] = entry_hit_at
            if new_sl is not None:
                update_data["stop_loss"] = new_sl
            if new_state in ["TP_HIT", "SL_HIT", "CANCELLED"]:
                update_data["closed_at"] = datetime.now(timezone.utc).isoformat()
                update_data["result"] = new_state
            
            if update_data:
                db.client.table(settings.TABLE_SIGNALS).update(update_data).eq(
                    "id", signal_id
                ).execute()
                
                # Publish update
                self.emit(
                    channel=MessageBus.CH_SIGNAL_UPDATED,
                    payload={"signal_id": signal_id, **update_data, "note": note},
                )
                
        except Exception as e:
            logger.error(f"❌ Signal update failed for #{signal_id}: {e}")
    
    def _parse_time(self, time_str: Optional[str]) -> Optional[datetime]:
        if not time_str:
            return None
        try:
            return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except Exception:
            return None


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = WatcherAgent()
    agent.start()
