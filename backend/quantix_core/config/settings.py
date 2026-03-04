"""
Configuration settings for Quantix AI Core - Multi-Agent Edition v4.0
Kế thừa từ Quantix_AI_Core settings.py, bổ sung Redis và Agent config.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # ── Application ──────────────────────────────────────────────
    APP_NAME: str = "Quantix AI Core - Multi-Agent Edition"
    APP_VERSION: str = "4.0.0"
    MODEL_VERSION: str = "quantix_fx_v4.0_multiagent"
    DEBUG: bool = False
    INSTANCE_NAME: str = "LOCAL-DEV"
    
    # ── API ──────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api/v1"
    TWELVE_DATA_API_KEY: Optional[str] = None
    
    # ── Redis Message Bus ────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # ── Agent Configuration ──────────────────────────────────────
    AGENT_HEARTBEAT_INTERVAL: int = 60      # Gửi heartbeat mỗi 60s
    AGENT_HEARTBEAT_TIMEOUT: int = 900      # Coi agent chết nếu mất heartbeat 15 phút
    DATA_FETCH_INTERVAL: int = 300          # Data Fetcher chạy mỗi 5 phút
    WATCHER_CHECK_INTERVAL: int = 60        # Watcher check mỗi 60s
    
    # ── Supabase Database ────────────────────────────────────────
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    
    # ── Telegram Notifications ───────────────────────────────────
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    TELEGRAM_ADMIN_CHAT_ID: Optional[str] = None
    
    # ── Database Tables ──────────────────────────────────────────
    TABLE_SIGNALS: str = "fx_signals"
    TABLE_VALIDATION: str = "fx_signal_validation"
    TABLE_LIFECYCLE: str = "fx_signal_lifecycle"
    TABLE_ANALYSIS_LOG: str = "fx_analysis_log"
    TABLE_HEARTBEAT: str = "agent_heartbeat"
    TABLE_DATA_CACHE: str = "market_data_cache"
    
    # ── Trading Rules ────────────────────────────────────────────
    MIN_RR: float = 1.0
    MIN_CONFIDENCE: float = 0.80
    MAX_SIGNALS_PER_ASSET: int = 3
    MAX_PENDING_DURATION_MINUTES: int = 35
    MAX_TRADE_DURATION_MINUTES: int = 180
    
    # ── Anti-Burst Rules ─────────────────────────────────────────
    MIN_RELEASE_INTERVAL_MINUTES: int = 20
    MAX_SIGNALS_PER_DAY: int = 9999
    
    # ── Session Times (UTC) ──────────────────────────────────────
    TOKYO_OPEN: str = "00:00"
    TOKYO_CLOSE: str = "09:00"
    LONDON_OPEN: str = "08:00"
    LONDON_CLOSE: str = "17:00"
    NY_OPEN: str = "13:00"
    NY_CLOSE: str = "22:00"
    
    # ── Confidence Grading Thresholds ────────────────────────────
    CONFIDENCE_A_PLUS: float = 0.95
    CONFIDENCE_A: float = 0.90
    CONFIDENCE_B_PLUS: float = 0.85
    CONFIDENCE_B: float = 0.80
    
    # ── Agent Weights (for probability calculation) ──────────────
    WEIGHT_STRUCTURE: float = 0.30
    WEIGHT_SESSION: float = 0.25
    WEIGHT_VOLATILITY: float = 0.20
    WEIGHT_HISTORICAL: float = 0.25
    
    # ── Invalidation Rules ───────────────────────────────────────
    VOLATILITY_SPIKE_THRESHOLD: float = 2.0
    NEWS_PROXIMITY_MINUTES: int = 30
    
    # ── Feature Flags ────────────────────────────────────────────
    QUANTIX_MODE: str = "INTERNAL"
    ENABLE_LIVE_SIGNAL: bool = True
    ENABLE_SHADOW_MODE: bool = False     # Shadow mode cho Phase 5
    WATCHER_OBSERVE_MODE: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"


# Global settings instance
settings = Settings()
