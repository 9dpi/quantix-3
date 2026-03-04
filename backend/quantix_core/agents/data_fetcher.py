"""
Data Fetcher Agent — Stage 1
=============================
Lấy dữ liệu OHLCV theo chu kỳ từ Binance (primary) và TwelveData (fallback).
Publish dữ liệu đã chuẩn hóa vào channel stage_1.raw_data.

Schedule: Mỗi DATA_FETCH_INTERVAL giây (mặc định 300s = 5 phút).
"""

import pandas as pd
from typing import Dict, Any, List, Optional
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.config.settings import settings
from backend.quantix_core.feeds.binance_feed import BinanceFeed


class DataFetcherAgent(BaseAgent):
    """
    Thu thập dữ liệu OHLCV từ nhiều nguồn với cơ chế failover tự động.
    
    Flow:
        Timer (5 min) → Fetch Binance → Normalize → Publish raw_data
    """
    
    def __init__(self):
        super().__init__(agent_name="data_fetcher", stage=1)
        self.feed = BinanceFeed(timeout=10)
        self.symbols = ["EURUSD"]
        self.timeframes = ["15m"]
        self.history_limit = 100  # Lấy 100 nến gần nhất
    
    @property
    def subscriptions(self) -> list:
        return []  # Timer-based, không subscribe channel nào
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        pass  # Không dùng
    
    def run_cycle(self) -> Optional[float]:
        """Fetch data cho tất cả symbols/timeframes mỗi cycle."""
        for symbol in self.symbols:
            for tf in self.timeframes:
                try:
                    self._fetch_and_publish(symbol, tf)
                except Exception as e:
                    logger.error(f"❌ Fetch failed for {symbol}/{tf}: {e}")
        
        return float(settings.DATA_FETCH_INTERVAL)
    
    def _fetch_and_publish(self, symbol: str, timeframe: str):
        """Lấy dữ liệu từ feed và publish lên message bus."""
        
        # 1. Lấy dữ liệu hiện tại
        current_price = self.feed.get_price(symbol)
        if not current_price:
            logger.warning(f"⚠️ No current price for {symbol}")
            return
        
        # 2. Lấy lịch sử OHLCV
        history = self.feed.get_history(
            symbol=symbol,
            interval=timeframe,
            limit=self.history_limit
        )
        
        if not history or len(history) < 20:
            logger.warning(f"⚠️ Insufficient history for {symbol}/{timeframe}: {len(history or [])} candles")
            return
        
        # 3. Chuẩn hóa và publish
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "current_price": current_price,
            "history": history,
            "candle_count": len(history),
            "source": current_price.get("source", "binance"),
        }
        
        self.emit(
            channel=MessageBus.CH_RAW_DATA,
            payload=payload,
        )
        
        logger.info(
            f"📊 Fetched {symbol}/{timeframe}: "
            f"{len(history)} candles, price={current_price['close']:.5f}"
        )
    
    def on_start(self):
        logger.info(f"🔧 Config: symbols={self.symbols}, timeframes={self.timeframes}, "
                     f"interval={settings.DATA_FETCH_INTERVAL}s")


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = DataFetcherAgent()
    agent.start()
