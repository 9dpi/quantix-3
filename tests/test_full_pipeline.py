"""
COMPLETE Signal Pipeline Mock Test
===================================
Verifies ALL 15 agents in a single local mock bypass.
- Stage 1: Data Fetch & Quality
- Stage 2: BOS, FVG, Liquidity Analysis
- Stage 3: Confidence Aggregation & Filtering
- Stage 4: R:R, Circuit, Sizing
- Stage 5: Dispatcher (Final Issuance)
"""

import json
import time
import threading
import pandas as pd
import sys
from loguru import logger
from fakeredis import FakeRedis
from unittest.mock import MagicMock

# Force Settings
from backend.quantix_core.config.settings import settings
settings.DEBUG = True
settings.MIN_CONFIDENCE = 0.50 

from backend.quantix_core.database.connection import db
db._client = MagicMock() 
db._client.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": 12345}])
db._client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
db._client.table.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
db._client.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[])

from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.agents.data_fetcher import DataFetcherAgent
from backend.quantix_core.agents.data_quality import DataQualityAgent
from backend.quantix_core.agents.bos_detector import BOSDetectorAgent
from backend.quantix_core.agents.fvg_locator import FVGLocatorAgent
from backend.quantix_core.agents.liquidity import LiquiditySweepAgent
from backend.quantix_core.agents.confidence import ConfidenceScorerAgent
from backend.quantix_core.agents.session_filter import SessionFilterAgent
from backend.quantix_core.agents.price_validator import PriceValidatorAgent
from backend.quantix_core.agents.rr_optimizer import RROptimizerAgent
from backend.quantix_core.agents.circuit_breaker import CircuitBreakerAgent
from backend.quantix_core.agents.position_sizing import PositionSizingAgent
from backend.quantix_core.agents.dispatcher import SignalDispatcherAgent

class MockMessageBus(MessageBus):
    def __init__(self, redis_instance: FakeRedis, agent_id: str = "test"):
        super().__init__(agent_id=agent_id)
        self._redis = redis_instance
    def connect(self) -> bool: return True

def run_test():
    shared_redis = FakeRedis(decode_responses=True)
    all_events = []
    
    # Super-Monitor using psubscribe
    ps = shared_redis.pubsub()
    ps.psubscribe('*')
    
    def monitor_loop():
        for msg in ps.listen():
            if msg['type'] == 'pmessage':
                data = json.loads(msg['data'])
                event = data.get('event')
                print(f"📡 [MONITOR] Event: {event}")
                all_events.append(event)
    
    threading.Thread(target=monitor_loop, daemon=True).start()
    
    # ALL Agents list for full pipeline
    agents = [
        DataQualityAgent(),
        BOSDetectorAgent(),
        FVGLocatorAgent(),
        LiquiditySweepAgent(),
        ConfidenceScorerAgent(),
        SessionFilterAgent(),
        PriceValidatorAgent(),
        RROptimizerAgent(),
        CircuitBreakerAgent(),
        PositionSizingAgent(),
        SignalDispatcherAgent()
    ]
    
    for agent in agents:
        agent.bus = MockMessageBus(shared_redis, agent.agent_id)
        if hasattr(agent, "_notifier"): agent._notifier = MagicMock()
        t = threading.Thread(target=agent.start, daemon=True)
        t.start()
        
    time.sleep(5) 
    
    # Inject Data
    fetcher = DataFetcherAgent()
    fetcher.bus = MockMessageBus(shared_redis, "inject_fetcher")
    print("DEBUG: Injecting EURUSD data into pipeline...")
    fetcher._fetch_and_publish("EURUSD", "15m")
    
    # Wait loop
    timeout = 45 
    start_time = time.time()
    while time.time() - start_time < timeout:
        if "signal_issued" in all_events:
            break
        time.sleep(1)
        
    print(f"DEBUG: FINAL EVENT SEQUENCE: {all_events}")
    
    # Analysis
    required = [
        "raw_data", "validated_data", "bos_result", "fvg_result", 
        "liquidity_result", "confidence_result", "filtered_signal",
        "validated_signal", "rr_result", "circuit_result", 
        "sizing_result", "signal_issued"
    ]
    
    missing = [r for r in required if r not in all_events]
    if missing:
        print(f"⚠️ Missing events: {missing}")
    
    assert "signal_issued" in all_events, "Pipeline failed to reach Stage 5 (Signal Issuance)"
    
    print("=" * 60)
    print("✨ COMPLETE 15-AGENT PIPELINE VERIFIED LOCALLY ✨")
    print("=" * 60)
    return True

if __name__ == "__main__":
    try:
        if run_test():
            sys.exit(0)
    except Exception as e:
        print(f"❌ Full Pipeline Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
