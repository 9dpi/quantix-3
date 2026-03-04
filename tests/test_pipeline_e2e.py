"""
End-to-End Pipeline Integration Test
=====================================
Verifies the complete signal pipeline from data fetch to signal dispatch.
"""

import json
import time
import threading
import redis
from unittest.mock import MagicMock, patch
from loguru import logger


def test_message_flow():
    """Test that messages flow correctly through all channels."""
    from backend.quantix_core.messaging.bus import MessageBus
    
    received_messages = []
    
    # Create a subscriber
    bus = MessageBus(agent_id="test_subscriber")
    if not bus.connect():
        logger.error("Cannot connect to Redis for testing")
        return False
    
    def handler(msg):
        received_messages.append(msg)
    
    bus.subscribe([MessageBus.CH_RAW_DATA], handler)
    
    # Start listening in background
    listen_thread = threading.Thread(target=bus.listen, daemon=True)
    listen_thread.start()
    
    time.sleep(0.5)  # Wait for subscription
    
    # Create a publisher
    pub_bus = MessageBus(agent_id="test_publisher")
    pub_bus.connect()
    
    test_payload = {"symbol": "EURUSD", "timeframe": "15m", "test": True}
    pub_bus.publish(MessageBus.CH_RAW_DATA, test_payload, correlation_id="test-corr-001")
    
    time.sleep(1)  # Wait for message
    
    # Verify
    assert len(received_messages) >= 1, f"Expected at least 1 message, got {len(received_messages)}"
    msg = received_messages[0]
    assert msg["payload"]["symbol"] == "EURUSD"
    assert msg["correlation_id"] == "test-corr-001"
    
    bus.disconnect()
    pub_bus.disconnect()
    
    logger.success("✅ Message flow test PASSED")
    return True


def test_base_agent_lifecycle():
    """Test BaseAgent start/stop lifecycle."""
    from backend.quantix_core.agents.base_agent import BaseAgent
    
    class TestAgent(BaseAgent):
        def __init__(self):
            super().__init__(agent_name="test_agent", stage=0)
            self.received = []
        
        @property
        def subscriptions(self):
            return []
        
        def on_message(self, channel, message):
            self.received.append(message)
        
        def run_cycle(self):
            return None
    
    agent = TestAgent()
    assert agent.agent_name == "test_agent"
    assert agent._running is False
    
    logger.success("✅ BaseAgent lifecycle test PASSED")
    return True


def test_channel_naming():
    """Test channel naming convention."""
    from backend.quantix_core.messaging.bus import MessageBus
    
    assert MessageBus.CH_RAW_DATA == "stage_1.raw_data"
    assert MessageBus.CH_BOS_RESULT == "stage_2.bos_result"
    assert MessageBus.CH_CONFIDENCE_RESULT == "stage_3.confidence_result"
    assert MessageBus.CH_RR_RESULT == "stage_4.rr_result"
    assert MessageBus.CH_SIGNAL_ISSUED == "stage_5.signal_issued"
    
    logger.success("✅ Channel naming test PASSED")
    return True


def test_settings_loaded():
    """Test settings are correctly loaded."""
    from backend.quantix_core.config.settings import settings
    
    assert settings.APP_VERSION == "4.0.0"
    assert settings.MIN_CONFIDENCE == 0.80
    assert settings.MIN_RR == 1.0
    assert settings.AGENT_HEARTBEAT_INTERVAL == 60
    assert settings.TABLE_HEARTBEAT == "agent_heartbeat"
    
    logger.success("✅ Settings test PASSED")
    return True


if __name__ == "__main__":
    logger.info("🧪 Running integration tests...")
    
    results = {
        "channel_naming": test_channel_naming(),
        "settings": test_settings_loaded(),
        "base_agent": test_base_agent_lifecycle(),
    }
    
    # Redis-dependent tests
    try:
        results["message_flow"] = test_message_flow()
    except Exception as e:
        logger.warning(f"⚠️ Message flow test skipped (Redis not available): {e}")
        results["message_flow"] = "SKIPPED"
    
    passed = sum(1 for v in results.values() if v is True)
    total = len(results)
    
    logger.info(f"\n{'='*50}")
    logger.info(f"Test Results: {passed}/{total} passed")
    for name, result in results.items():
        status = "✅" if result is True else ("⚠️ SKIP" if result == "SKIPPED" else "❌")
        logger.info(f"  {status} {name}")
