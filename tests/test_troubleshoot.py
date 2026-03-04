"""
Troubleshoot Mock Pipeline flow
===================================
Debug receivers count and pubsub mechanism in fakeredis.
"""

import json
import time
import threading
import sys
from loguru import logger
from fakeredis import FakeRedis

from backend.quantix_core.messaging.bus import MessageBus
from backend.quantix_core.agents.data_fetcher import DataFetcherAgent
from backend.quantix_core.agents.data_quality import DataQualityAgent
from backend.quantix_core.agents.bos_detector import BOSDetectorAgent
from backend.quantix_core.config.settings import settings

# Force Settings for Debug
settings.DEBUG = True

class MockMessageBus(MessageBus):
    """MessageBus using a shared FakeRedis instance."""
    def __init__(self, redis_instance: FakeRedis, agent_id: str = "test"):
        super().__init__(agent_id=agent_id)
        self._redis = redis_instance
        
    def connect(self) -> bool:
        return True

def test_debug_flow():
    shared_redis = FakeRedis(decode_responses=True)
    results = {}
    
    def monitor_handler(msg):
        event = msg.get('event')
        print(f"DEBUG: MONITOR_HANDLER got event: {event}")
        results[event] = msg
    
    # Setup monitor
    monitor_bus = MockMessageBus(shared_redis, "monitor")
    monitor_bus.subscribe([
        MessageBus.CH_RAW_DATA,
        MessageBus.CH_VALIDATED_DATA,
        MessageBus.CH_BOS_RESULT
    ], monitor_handler)
    
    # Print subscription count
    # Fakeredis internal check (not public API but helps)
    # shared_redis.pubsub_channels() return [b'stage_1.raw_data', ...]
    print(f"DEBUG: Subscribed channels: {shared_redis.pubsub_channels()}")
    
    t_monitor = threading.Thread(target=monitor_bus.listen, daemon=True)
    t_monitor.start()
    
    # Setup agents
    fetcher = DataFetcherAgent()
    fetcher.bus = MockMessageBus(shared_redis, fetcher.agent_id)
    
    quality = DataQualityAgent()
    quality.bus = MockMessageBus(shared_redis, quality.agent_id)
    t_quality = threading.Thread(target=quality.start, daemon=True)
    t_quality.start()
    
    bos = BOSDetectorAgent()
    bos.bus = MockMessageBus(shared_redis, bos.agent_id)
    t_bos = threading.Thread(target=bos.start, daemon=True)
    t_bos.start()
    
    time.sleep(2)
    print(f"DEBUG: Active PubSub channels: {shared_redis.pubsub_channels()}")
    # numsub returns {channel_name: count}
    print(f"DEBUG: Channel subscribers: {shared_redis.pubsub_numsub(MessageBus.CH_RAW_DATA, MessageBus.CH_VALIDATED_DATA, MessageBus.CH_BOS_RESULT)}")
    
    # Trigger publish
    # Instead of fetcher._fetch_and_publish, let's do a direct publish manual test first
    print("DEBUG: Manually publishing test message...")
    fetcher.bus.publish(MessageBus.CH_RAW_DATA, {"test": "data"})
    
    time.sleep(2)
    print(f"DEBUG: Intermediate results keys: {list(results.keys())}")
    
    # Trigger full fetcher logic
    print("DEBUG: Triggering full DataFetcher manual cycle")
    fetcher._fetch_and_publish("EURUSD", "15m")
    
    time.sleep(5)
    print(f"Final results keys: {list(results.keys())}")
    
    # Shutdown
    shared_redis.close()

if __name__ == "__main__":
    test_debug_flow()
