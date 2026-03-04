-- ============================================
-- Quantix AI Core - Multi-Agent v4.0
-- Database Migration Script
-- Run on Supabase SQL Editor
-- ============================================

-- 1. Agent Heartbeat Table
-- Healing Agent dùng để monitor trạng thái các agent
CREATE TABLE IF NOT EXISTS agent_heartbeat (
    id BIGSERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    stage INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    messages_processed INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    uptime_seconds FLOAT DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for quick lookups by agent
CREATE INDEX IF NOT EXISTS idx_heartbeat_agent_id ON agent_heartbeat(agent_id);
CREATE INDEX IF NOT EXISTS idx_heartbeat_last_seen ON agent_heartbeat(last_seen);

-- Unique constraint: only one row per agent (upsert pattern)
CREATE UNIQUE INDEX IF NOT EXISTS idx_heartbeat_agent_unique ON agent_heartbeat(agent_id);


-- 2. Market Data Cache Table
-- Giảm tải API, cache dữ liệu OHLCV
CREATE TABLE IF NOT EXISTS market_data_cache (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'binance',
    data JSONB NOT NULL,
    candle_count INTEGER DEFAULT 0,
    fetched_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cache_symbol_tf ON market_data_cache(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_cache_fetched ON market_data_cache(fetched_at);


-- 3. Add agent_decision_log column to fx_signals (if not exists)
-- Ghi lại ý kiến từ tất cả agent trong pipeline cho mỗi tín hiệu
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'fx_signals' AND column_name = 'agent_decision_log'
    ) THEN
        ALTER TABLE fx_signals ADD COLUMN agent_decision_log JSONB DEFAULT '{}';
    END IF;
END
$$;


-- 4. Signal Validation Table (Trader Proof)
CREATE TABLE IF NOT EXISTS fx_signal_validation (
    id BIGSERIAL PRIMARY KEY,
    signal_id UUID,
    check_type TEXT,
    validator_price FLOAT,
    validator_candle JSONB,
    is_discrepancy BOOLEAN DEFAULT FALSE,
    meta_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. AI Analysis Heartbeat Table
CREATE TABLE IF NOT EXISTS fx_analysis_log (
    id BIGSERIAL PRIMARY KEY,
    asset TEXT,
    status TEXT,
    confidence FLOAT,
    strength FLOAT,
    refinement TEXT,
    meta_data JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Shadow Comparison Log (Phase 5)
-- So sánh kết quả giữa hệ thống cũ và mới
CREATE TABLE IF NOT EXISTS shadow_comparison_log (
    id BIGSERIAL PRIMARY KEY,
    correlation_id TEXT,
    old_system_signal JSONB,
    new_system_signal JSONB,
    match BOOLEAN DEFAULT FALSE,
    discrepancy_details TEXT,
    compared_at TIMESTAMPTZ DEFAULT NOW()
);


-- 5. Enable RLS on new tables
ALTER TABLE agent_heartbeat ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_data_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_comparison_log ENABLE ROW LEVEL SECURITY;

-- Service role policy (backend access)
CREATE POLICY IF NOT EXISTS "service_role_heartbeat" ON agent_heartbeat
    FOR ALL USING (TRUE) WITH CHECK (TRUE);
    
CREATE POLICY IF NOT EXISTS "service_role_cache" ON market_data_cache
    FOR ALL USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY IF NOT EXISTS "service_role_shadow" ON shadow_comparison_log
    FOR ALL USING (TRUE) WITH CHECK (TRUE);
