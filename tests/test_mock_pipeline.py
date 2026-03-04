"""
Mock Pipeline Test using Fakeredis (Simplest)
=============================================
Uses a single shared FakeRedis instance and DEBUG logging.
"""

import json
import time
import threading
import pandas as pd
from loguru import logger
from fakeredis import FakeRedis

# Force DEBUG level for testing
import sys
logger.remove()
logger.add(sys.stderr, level="DEBUG")

from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.agents.data_fetcher import DataFetcherAgent
from backend.quantix_core.agents.data_quality import DataQualityAgent
from backend.quantix_core.agents.bos_detector import BOSDetectorAgent
from backend.quantix_core.config.settings import settings

class MockMessageBus(MessageBus):
    """MessageBus using a shared FakeRedis instance."""
    def __init__(self, redis_instance: FakeRedis, agent_id: str = "test"):
        super().__init__(agent_id=agent_id)
        self._redis = redis_instance
        
    def connect(self) -> bool:
        # Already connected via shared instance
        return True

def test_mock_pipeline_flow():
    """Run a micro-pipeline: DataFetcher -> DataQuality -> BOSDetector."""
    
    # Single shared instance, decode_responses=True
    shared_redis = FakeRedis(decode_responses=True)
    
    results = {}
    
    def monitor_handler(msg):
        event = msg.get('event')
        logger.info(f"🔍 MONITOR INTERCEPTED: {event}")
        results[event] = msg
    
    # 1. Start monitor
    monitor_bus = MockMessageBus(shared_redis, "monitor")
    monitor_bus.subscribe([
        MessageBus.CH_RAW_DATA,
        MessageBus.CH_VALIDATED_DATA,
        MessageBus.CH_BOS_RESULT
    ], monitor_handler)
    
    t_monitor = threading.Thread(target=monitor_bus.listen, daemon=True)
    t_monitor.name = "MonitorThread"
    t_monitor.start()
    
    # 2. Setup and Start agents
    fetcher = DataFetcherAgent()
    fetcher.bus = MockMessageBus(shared_redis, fetcher.agent_id)
    # Note: Fetcher doesn't need start() for individual fetcher logic
    
    quality = DataQualityAgent()
    quality.bus = MockMessageBus(shared_redis, quality.agent_id)
    t_quality = threading.Thread(target=quality.start, daemon=True)
    t_quality.start()
    
    bos = BOSDetectorAgent()
    bos.bus = MockMessageBus(shared_redis, bos.agent_id)
    t_bos = threading.Thread(target=bos.start, daemon=True)
    t_bos.start()
    
    time.sleep(2) # Wait for subscriptions
    
    # 3. Simulate Data Fetching
    logger.info("🚀 Triggering DataFetcher manual cycle")
    fetcher._fetch_and_publish("EURUSD", "15m")
    
    logger.info("⏳ Waiting for agents to process messages...")
    
    # Wait loop
    timeout = 15
    start_time = time.time()
    while time.time() - start_time < timeout:
        if "bos_result" in results:
            break
        time.sleep(0.5)
        
    # Verify results
    logger.info(f"Final results keys: {list(results.keys())}")
    
    assert "raw_data" in results, "DataFetcher failed to produce stage_1.raw_data"
    assert "validated_data" in results, "DataQuality failed to produce stage_1.validated_data"
    assert "bos_result" in results, "BOSDetector failed to produce stage_2.bos_result"
    
    logger.success(f"✨ ALL CORE AGENTS LOGIC VERIFIED ✨")
    return True

if __name__ == "__main__":
    logger.info("🧪 Starting SIMPLE Mock Pipeline Test...")
    try:
        test_mock_pipeline_flow()
    except Exception as e:
        logger.error(f"❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
