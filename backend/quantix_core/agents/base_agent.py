"""
Base Agent Framework for Quantix Multi-Agent System

Lớp cơ sở cho tất cả agent trong hệ thống. Mỗi agent kế thừa class này
và chỉ cần override:
    - agent_name: Tên định danh
    - subscriptions: Danh sách channels cần lắng nghe
    - on_message(): Xử lý message nhận được
    - run_cycle(): (optional) Logic chạy theo timer thay vì event-driven

Lifecycle:
    1. __init__() → setup agent identity
    2. start() → connect Redis, subscribe, start heartbeat, enter main loop
    3. on_message() → xử lý từng message
    4. stop() → graceful shutdown
"""

import signal
import sys
import time
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from loguru import logger

from backend.quantix_core.config.settings import settings
from backend.quantix_core.messaging.bus import MessageBus


class BaseAgent(ABC):
    """
    Abstract base class cho tất cả Quantix agents.
    
    Features:
    - Auto Redis connection & reconnection
    - Heartbeat mechanism (configurable interval)
    - Graceful shutdown on SIGINT/SIGTERM
    - Structured logging with agent context
    - Error recovery with configurable retry
    """
    
    def __init__(self, agent_name: str, stage: int = 0):
        """
        Args:
            agent_name: Unique name cho agent (e.g. "bos_detector")
            stage: Stage number trong pipeline (1-5, 0=system)
        """
        self.agent_name = agent_name
        self.agent_id = f"{agent_name}_{settings.INSTANCE_NAME}"
        self.stage = stage
        self.bus = MessageBus(agent_id=self.agent_id)
        
        # State
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._started_at: Optional[datetime] = None
        self._message_count = 0
        self._error_count = 0
        
        # Configure logging
        self._setup_logging()
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    # ── Abstract Methods (override in subclass) ──────────────────
    
    @property
    @abstractmethod
    def subscriptions(self) -> List[str]:
        """Channels that this agent subscribes to. Override in subclass."""
        return []
    
    @abstractmethod
    def on_message(self, channel: str, message: Dict[str, Any]):
        """
        Handle incoming message. Override in subclass.
        
        Args:
            channel: Channel the message came from
            message: Parsed message dict with keys:
                     agent_id, stage, event, correlation_id, timestamp, payload
        """
        pass
    
    def run_cycle(self) -> Optional[float]:
        """
        Optional: Timer-based execution cycle.
        Override this for agents that run on a schedule (e.g. Data Fetcher).
        
        Returns:
            Sleep duration in seconds before next cycle, or None to use event-driven mode.
        """
        return None
    
    def on_start(self):
        """Optional hook called after agent starts successfully."""
        pass
    
    def on_stop(self):
        """Optional hook called before agent shuts down."""
        pass
    
    # ── Main Lifecycle ───────────────────────────────────────────
    
    def start(self):
        """Start the agent: connect, subscribe, enter main loop."""
        logger.info(f"🚀 Agent [{self.agent_name}] starting...")
        
        # Connect to Redis
        if not self.bus.connect():
            logger.critical(f"💀 Agent [{self.agent_name}] cannot connect to Redis. Exiting.")
            sys.exit(1)
        
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        
        # Start heartbeat thread
        self._start_heartbeat()
        
        # Call startup hook
        self.on_start()
        
        logger.success(f"✅ Agent [{self.agent_name}] is now running (stage={self.stage})")
        
        # Determine execution mode
        cycle_interval = self.run_cycle()
        
        if cycle_interval is not None:
            # Timer-based mode (e.g. Data Fetcher: every 5 minutes)
            self._run_timer_loop(cycle_interval)
        elif self.subscriptions:
            # Event-driven mode (subscribe and listen)
            self._run_event_loop()
        else:
            logger.warning(f"⚠️ Agent [{self.agent_name}] has no subscriptions and no timer cycle. Idling.")
            self._run_idle_loop()
    
    def stop(self):
        """Graceful shutdown."""
        logger.info(f"🛑 Agent [{self.agent_name}] shutting down...")
        self._running = False
        
        # Call shutdown hook
        self.on_stop()
        
        # Send final heartbeat with stopping status
        try:
            self.bus.send_heartbeat(status="stopping")
        except Exception:
            pass
        
        # Disconnect
        self.bus.disconnect()
        
        uptime = ""
        if self._started_at:
            uptime = f" (uptime: {datetime.now(timezone.utc) - self._started_at})"
        
        logger.info(
            f"👋 Agent [{self.agent_name}] stopped.{uptime} "
            f"Messages: {self._message_count}, Errors: {self._error_count}"
        )
    
    # ── Execution Loops ──────────────────────────────────────────
    
    def _run_event_loop(self):
        """Event-driven loop: subscribe to channels and process messages."""
        logger.info(f"📡 [{self.agent_name}] Entering event-driven mode. Subscribing to: {self.subscriptions}")
        
        self.bus.subscribe(self.subscriptions, self._handle_message)
        
        try:
            self.bus.listen()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.error(f"❌ [{self.agent_name}] Event loop error: {e}")
            self._error_count += 1
        finally:
            self.stop()
    
    def _run_timer_loop(self, interval: float):
        """Timer-based loop: also subscribe to channels if any, and run cycles."""
        logger.info(f"⏱️ [{self.agent_name}] Entering timer mode (interval={interval}s)")
        
        # Subscribe in background if there are subscriptions
        if self.subscriptions:
            sub_thread = threading.Thread(
                target=self._background_subscriber,
                daemon=True,
                name=f"{self.agent_name}-subscriber",
            )
            sub_thread.start()
        
        try:
            while self._running:
                try:
                    new_interval = self.run_cycle()
                    if new_interval is not None:
                        interval = new_interval
                except Exception as e:
                    logger.error(f"❌ [{self.agent_name}] Cycle error: {e}")
                    self._error_count += 1
                
                # Sleep with interruption check
                self._interruptible_sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
    
    def _run_idle_loop(self):
        """Idle loop for agents that only send heartbeats."""
        try:
            while self._running:
                self._interruptible_sleep(60)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
    
    def _background_subscriber(self):
        """Background thread for listening to subscriptions in timer mode."""
        self.bus.subscribe(self.subscriptions, self._handle_message)
        try:
            self.bus.listen()
        except Exception as e:
            logger.error(f"❌ [{self.agent_name}] Background subscriber error: {e}")
    
    # ── Message Handling ─────────────────────────────────────────
    
    def _handle_message(self, message: Dict[str, Any]):
        """Internal message handler with error catching and metrics."""
        self._message_count += 1
        channel = message.get("event", "unknown")
        corr_id = message.get("correlation_id", "n/a")[:8]
        
        logger.debug(f"📨 [{self.agent_name}] Received: {channel} (corr={corr_id})")
        
        try:
            self.on_message(channel, message)
        except Exception as e:
            self._error_count += 1
            logger.error(
                f"❌ [{self.agent_name}] Error processing message "
                f"(channel={channel}, corr={corr_id}): {e}"
            )
    
    # ── Heartbeat ────────────────────────────────────────────────
    
    def _start_heartbeat(self):
        """Start background heartbeat thread."""
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name=f"{self.agent_name}-heartbeat",
        )
        self._heartbeat_thread.start()
    
    def _heartbeat_loop(self):
        """Send periodic heartbeat signals."""
        while self._running:
            try:
                self.bus.send_heartbeat(
                    status="running",
                    metadata={
                        "stage": self.stage,
                        "messages_processed": self._message_count,
                        "errors": self._error_count,
                        "uptime_seconds": (
                            (datetime.now(timezone.utc) - self._started_at).total_seconds()
                            if self._started_at else 0
                        ),
                    },
                )
            except Exception as e:
                logger.warning(f"⚠️ [{self.agent_name}] Heartbeat send failed: {e}")
            
            self._interruptible_sleep(settings.AGENT_HEARTBEAT_INTERVAL)
    
    # ── Utilities ────────────────────────────────────────────────
    
    def _setup_logging(self):
        """Configure structured logging for this agent."""
        logger.remove()
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            f"<cyan>{self.agent_name}</cyan> | "
            "<level>{message}</level>"
        )
        logger.add(sys.stderr, format=log_format, level="DEBUG" if settings.DEBUG else "INFO")
    
    def _signal_handler(self, signum, frame):
        """Handle OS signals for graceful shutdown."""
        logger.info(f"🔔 [{self.agent_name}] Received signal {signum}. Initiating shutdown...")
        self._running = False
    
    def _interruptible_sleep(self, seconds: float):
        """Sleep that can be interrupted by stop()."""
        end_time = time.time() + seconds
        while self._running and time.time() < end_time:
            time.sleep(min(1.0, end_time - time.time()))
    
    # ── Publish Helpers ──────────────────────────────────────────
    
    def emit(
        self,
        channel: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Convenience method to publish a message.
        Automatically sets stage from agent config.
        """
        return self.bus.publish(
            channel=channel,
            payload=payload,
            correlation_id=correlation_id,
            stage=self.stage,
        )
