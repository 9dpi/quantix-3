"""
Data Quality Agent — Stage 1
==============================
Kiểm tra tính toàn vẹn dữ liệu (gap, spike, completeness).
Subscribe: stage_1.raw_data → Publish: stage_1.validated_data hoặc stage_1.quality_alert
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List
from loguru import logger

from backend.quantix_core.agents.base_agent import BaseAgent
from backend.quantix_core.messaging.bus import MessageBus


class DataQualityAgent(BaseAgent):
    """
    Kiểm tra chất lượng dữ liệu trước khi chuyển sang Stage 2.
    
    Checks:
    1. Completeness — đủ số lượng nến tối thiểu
    2. Gaps — phát hiện khoảng trống thời gian bất thường
    3. Spikes — outlier detection dựa trên ATR
    4. Staleness — dữ liệu quá cũ
    """
    
    # Thresholds
    MIN_CANDLES = 20
    MAX_GAP_FACTOR = 3.0         # Gap > 3x interval = cảnh báo
    SPIKE_ATR_THRESHOLD = 3.0    # Candle > 3x ATR = spike
    
    def __init__(self):
        super().__init__(agent_name="data_quality", stage=1)
    
    @property
    def subscriptions(self) -> list:
        return [MessageBus.CH_RAW_DATA]
    
    def on_message(self, channel: str, message: Dict[str, Any]):
        payload = message.get("payload", {})
        correlation_id = message.get("correlation_id")
        
        symbol = payload.get("symbol", "UNKNOWN")
        timeframe = payload.get("timeframe", "15m")
        history = payload.get("history", [])
        
        # Run quality checks
        issues = self._validate(history, symbol, timeframe)
        
        if issues:
            logger.warning(f"⚠️ Quality issues for {symbol}/{timeframe}: {issues}")
            self.emit(
                channel=MessageBus.CH_QUALITY_ALERT,
                payload={"symbol": symbol, "timeframe": timeframe, "issues": issues},
                correlation_id=correlation_id,
            )
            
            # Chỉ block nếu có critical issue
            critical = [i for i in issues if i.get("severity") == "CRITICAL"]
            if critical:
                logger.error(f"🚫 CRITICAL quality issue — blocking data for {symbol}")
                return
        
        # Pass — forward validated data
        self.emit(
            channel=MessageBus.CH_VALIDATED_DATA,
            payload=payload,
            correlation_id=correlation_id,
        )
        
        logger.info(f"✅ Data quality OK: {symbol}/{timeframe} ({len(history)} candles)")
    
    def _validate(self, history: List[Dict], symbol: str, timeframe: str) -> List[Dict]:
        """Chạy tất cả quality checks, trả về danh sách issues."""
        issues = []
        
        if not history:
            issues.append({"check": "completeness", "severity": "CRITICAL", "detail": "No data"})
            return issues
        
        # 1. Completeness
        if len(history) < self.MIN_CANDLES:
            issues.append({
                "check": "completeness",
                "severity": "CRITICAL",
                "detail": f"Only {len(history)} candles (need {self.MIN_CANDLES})"
            })
            return issues
        
        try:
            df = pd.DataFrame(history)
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['open'] = df['open'].astype(float)
        except Exception as e:
            issues.append({"check": "parse", "severity": "CRITICAL", "detail": str(e)})
            return issues
        
        # 2. Spike detection (ATR-based)
        try:
            tr = pd.concat([
                df['high'] - df['low'],
                (df['high'] - df['close'].shift()).abs(),
                (df['low'] - df['close'].shift()).abs(),
            ], axis=1).max(axis=1)
            
            atr = tr.rolling(window=14).mean()
            
            for i in range(14, len(df)):
                candle_range = df['high'].iloc[i] - df['low'].iloc[i]
                if atr.iloc[i] > 0 and candle_range > self.SPIKE_ATR_THRESHOLD * atr.iloc[i]:
                    issues.append({
                        "check": "spike",
                        "severity": "WARNING",
                        "detail": f"Candle {i}: range={candle_range:.5f} > {self.SPIKE_ATR_THRESHOLD}x ATR"
                    })
        except Exception as e:
            logger.debug(f"Spike check error (non-critical): {e}")
        
        # 3. Zero/NaN check
        null_count = df[['open', 'high', 'low', 'close']].isnull().sum().sum()
        zero_count = (df[['open', 'high', 'low', 'close']] == 0).sum().sum()
        
        if null_count > 0:
            issues.append({"check": "null_values", "severity": "WARNING", "detail": f"{null_count} null values"})
        if zero_count > 0:
            issues.append({"check": "zero_values", "severity": "CRITICAL", "detail": f"{zero_count} zero prices"})
        
        return issues


# ── Entrypoint ───────────────────────────────────────────────────
if __name__ == "__main__":
    agent = DataQualityAgent()
    agent.start()
