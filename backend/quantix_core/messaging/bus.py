"""
Redis Message Bus for Quantix Multi-Agent System

Cung cấp abstraction layer cho Redis Pub/Sub và Redis Streams,
cho phép các agent giao tiếp với nhau theo message-driven architecture.

Channel Naming Convention:
    stage_{n}.{event_type}
    
Message Format (JSON):
    {
        "agent_id": "bos_detector_001",
        "stage": 2,
        "event": "bos_result",
        "correlation_id": "uuid-v4",
        "timestamp": "ISO-8601",
        "payload": { ... }
    }
"""

import json
import uuid
import redis
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Any
from loguru import logger
from backend.quantix_core.config.settings import settings


class MessageBus:
    """
    Redis-based message bus for inter-agent communication.
    
    Supports:
    - Pub/Sub for real-time event broadcasting
    - Streams + Consumer Groups for reliable, ordered processing
    - Dead Letter Queue for failed message handling
    """
    
    # ── Channel Names ────────────────────────────────────────────
    # Stage 1: Data
    CH_RAW_DATA = "stage_1.raw_data"
    CH_VALIDATED_DATA = "stage_1.validated_data"
    CH_QUALITY_ALERT = "stage_1.quality_alert"
    
    # Stage 2: Analysis
    CH_BOS_RESULT = "stage_2.bos_result"
    CH_FVG_RESULT = "stage_2.fvg_result"
    CH_LIQUIDITY_RESULT = "stage_2.liquidity_result"
    
    # Stage 3: Validation
    CH_CONFIDENCE_RESULT = "stage_3.confidence_result"
    CH_FILTERED_SIGNAL = "stage_3.filtered_signal"
    CH_SIGNAL_BLOCKED = "stage_3.signal_blocked"
    CH_VALIDATED_SIGNAL = "stage_3.validated_signal"
    
    # Stage 4: Risk
    CH_RR_RESULT = "stage_4.rr_result"
    CH_CIRCUIT_RESULT = "stage_4.circuit_result"
    CH_SIZING_RESULT = "stage_4.sizing_result"
    
    # Stage 5: Execution
    CH_SIGNAL_ISSUED = "stage_5.signal_issued"
    CH_SIGNAL_UPDATED = "stage_5.signal_updated"
    
    # System
    CH_AGENT_HEARTBEAT = "system.heartbeat"
    CH_DEAD_LETTER = "system.dead_letter"
    CH_ADMIN_ALERT = "system.admin_alert"
    
    def __init__(self, agent_id: str = "unknown"):
        self.agent_id = agent_id
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._handlers: Dict[str, Callable] = {}
    
    def connect(self) -> bool:
        """Kết nối tới Redis server."""
        try:
            self._redis = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=10,
                socket_connect_timeout=10,
                retry_on_timeout=True,
            )
            # Test connection
            self._redis.ping()
            logger.info(f"✅ [{self.agent_id}] Connected to Redis: {settings.REDIS_URL}")
            return True
        except redis.ConnectionError as e:
            logger.error(f"❌ [{self.agent_id}] Redis connection failed: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ [{self.agent_id}] Redis unexpected error: {e}")
            return False
    
    def disconnect(self):
        """Ngắt kết nối Redis."""
        if self._pubsub:
            try:
                self._pubsub.unsubscribe()
                self._pubsub.close()
            except Exception:
                pass
        if self._redis:
            try:
                self._redis.close()
            except Exception:
                pass
        logger.info(f"🔌 [{self.agent_id}] Disconnected from Redis")
    
    @property
    def redis(self) -> redis.Redis:
        """Lấy Redis client, tự kết nối lại nếu cần."""
        if self._redis is None:
            self.connect()
        return self._redis
    
    # ── Publishing ───────────────────────────────────────────────
    
    def publish(
        self,
        channel: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
        stage: Optional[int] = None,
    ) -> bool:
        """
        Publish message lên channel.
        
        Args:
            channel: Tên channel (dùng hằng số CH_*)
            payload: Dữ liệu cần gửi
            correlation_id: ID để tracking xuyên suốt pipeline
            stage: Stage number (1-5)
        """
        try:
            message = {
                "agent_id": self.agent_id,
                "stage": stage or self._extract_stage(channel),
                "event": channel.split(".")[-1] if "." in channel else channel,
                "correlation_id": correlation_id or str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": payload,
            }
            
            serialized = json.dumps(message, default=str)
            receivers = self.redis.publish(channel, serialized)
            
            logger.debug(
                f"📤 [{self.agent_id}] Published to {channel} "
                f"(receivers={receivers}, corr={message['correlation_id'][:8]})"
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ [{self.agent_id}] Publish failed on {channel}: {e}")
            return False
    
    # ── Subscribing ──────────────────────────────────────────────
    
    def subscribe(self, channels: List[str], handler: Callable[[Dict], None]):
        """
        Subscribe vào một hoặc nhiều channels.
        
        Args:
            channels: Danh sách channels cần lắng nghe
            handler: Callback function nhận message dict
        """
        if self._pubsub is None:
            self._pubsub = self.redis.pubsub()
        
        for ch in channels:
            self._handlers[ch] = handler
        
        self._pubsub.subscribe(*channels)
        logger.info(f"📥 [{self.agent_id}] Subscribed to: {channels}")
    
    def listen(self):
        """
        Blocking listen loop. Chạy trong thread riêng hoặc main loop.
        Yields parsed messages.
        """
        if self._pubsub is None:
            raise RuntimeError("Must subscribe before listening")
        
        for raw_message in self._pubsub.listen():
            if raw_message["type"] != "message":
                continue
            
            try:
                channel = raw_message["channel"]
                data = json.loads(raw_message["data"])
                
                handler = self._handlers.get(channel)
                if handler:
                    handler(data)
                    
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ [{self.agent_id}] Invalid JSON on {raw_message.get('channel')}: {e}")
            except Exception as e:
                logger.error(f"❌ [{self.agent_id}] Handler error: {e}")
                # Send to dead letter queue
                self._send_to_dlq(raw_message, str(e))
    
    # ── Redis Streams (for Stage synchronization) ────────────────
    
    def stream_add(self, stream: str, data: Dict[str, Any], correlation_id: Optional[str] = None) -> str:
        """
        Thêm message vào Redis Stream (dùng cho Stage 2→3 sync).
        
        Returns:
            Stream entry ID
        """
        message = {
            "agent_id": self.agent_id,
            "correlation_id": correlation_id or str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": json.dumps(data, default=str),
        }
        
        entry_id = self.redis.xadd(stream, message)
        logger.debug(f"📝 [{self.agent_id}] Stream add to {stream}: {entry_id}")
        return entry_id
    
    def stream_read_group(
        self,
        stream: str,
        group: str,
        consumer: str,
        count: int = 10,
        block: int = 5000,
    ) -> List[Dict]:
        """
        Đọc messages từ Stream sử dụng consumer group.
        Đảm bảo mỗi message chỉ được xử lý bởi 1 consumer.
        
        Args:
            stream: Stream name
            group: Consumer group name
            consumer: Consumer name (typically agent_id)
            count: Max messages per read
            block: Block timeout in ms (0 = non-blocking)
        """
        try:
            # Ensure group exists
            try:
                self.redis.xgroup_create(stream, group, id="0", mkstream=True)
            except redis.ResponseError:
                pass  # Group already exists
            
            results = self.redis.xreadgroup(
                group, consumer, {stream: ">"}, count=count, block=block
            )
            
            messages = []
            for stream_name, entries in results:
                for entry_id, fields in entries:
                    msg = {
                        "entry_id": entry_id,
                        "agent_id": fields.get("agent_id", ""),
                        "correlation_id": fields.get("correlation_id", ""),
                        "timestamp": fields.get("timestamp", ""),
                        "data": json.loads(fields.get("data", "{}")),
                    }
                    messages.append(msg)
                    # Acknowledge processing
                    self.redis.xack(stream, group, entry_id)
            
            return messages
            
        except Exception as e:
            logger.error(f"❌ [{self.agent_id}] Stream read failed ({stream}): {e}")
            return []
    
    # ── Heartbeat ────────────────────────────────────────────────
    
    def send_heartbeat(self, status: str = "running", metadata: Optional[Dict] = None):
        """Gửi heartbeat signal cho Healing Agent monitor."""
        self.publish(
            self.CH_AGENT_HEARTBEAT,
            payload={
                "status": status,
                "metadata": metadata or {},
            },
            stage=0,
        )
    
    # ── Utilities ────────────────────────────────────────────────
    
    def _message_wrapper(self, raw_message):
        """Internal wrapper for pubsub callback pattern."""
        # Redis pubsub callback mode handles this automatically
        pass
    
    def _extract_stage(self, channel: str) -> int:
        """Extract stage number from channel name."""
        try:
            if channel.startswith("stage_"):
                return int(channel.split(".")[0].replace("stage_", ""))
        except (ValueError, IndexError):
            pass
        return 0
    
    def _send_to_dlq(self, raw_message: Dict, error: str):
        """Send failed message to Dead Letter Queue."""
        try:
            dlq_entry = {
                "original_channel": raw_message.get("channel", "unknown"),
                "original_data": raw_message.get("data", ""),
                "error": error,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "agent_id": self.agent_id,
            }
            self.redis.rpush(
                self.CH_DEAD_LETTER,
                json.dumps(dlq_entry, default=str),
            )
        except Exception as e:
            logger.error(f"❌ [{self.agent_id}] Failed to send to DLQ: {e}")
