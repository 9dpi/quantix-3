"""
Quantix Watchdog Service
========================
Monitors the heartbeats of all distributed services (Analyzer, Watcher, Validator).
Sends Telegram alerts if any service exceeds the stale threshold.
"""

import time
import os
from datetime import datetime, timezone, timedelta
from loguru import logger
from backend.quantix_core.database.connection import db
from backend.quantix_core.config.settings import settings
from backend.quantix_core.engine.janitor import Janitor

class QuantixWatchdog:
    def __init__(self, check_interval_sec: int = 300, stale_threshold_min: int = 15):
        self.check_interval_sec = check_interval_sec
        self.stale_threshold_min = stale_threshold_min
        
        # Initialize Telegram Notifier
        from backend.quantix_core.notifications.telegram_notifier_v2 import create_notifier
        self.notifier = None
        if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ADMIN_CHAT_ID:
            self.notifier = create_notifier(
                settings.TELEGRAM_BOT_TOKEN,
                settings.TELEGRAM_ADMIN_CHAT_ID, # Alerts go to Admin
                settings.TELEGRAM_ADMIN_CHAT_ID
            )
            logger.info("Watchdog Notifier initialized (Admin Channel).")
        else:
            logger.warning("Telegram configuration missing for Watchdog alerts.")

    def run(self):
        logger.info(f"🚀 Watchdog Service STARTED [Interval: {self.check_interval_sec}s, Threshold: {self.stale_threshold_min}m]")
        
        while True:
            try:
                self.perform_health_check()
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            
            time.sleep(self.check_interval_sec)

    def perform_health_check(self):
        logger.info("🏥 Performing system health check...")
        
        services = {
            "ANALYZER": {"asset": "HEARTBEAT", "status_prefix": "ALIVE"},
            "WATCHER":  {"asset": "HEARTBEAT_WATCHER", "status_prefix": "WATCHER_ACTIVE"},
            "VALIDATOR": {"asset": "VALIDATOR", "status_prefix": "ONLINE"}
        }
        
        now = datetime.now(timezone.utc)
        report = []
        alerts_needed = []

        for name, config in services.items():
            try:
                # Fetch latest heartbeat
                res = db.client.table(settings.TABLE_ANALYSIS_LOG)\
                    .select("timestamp, status")\
                    .eq("asset", config["asset"])\
                    .order("timestamp", desc=True)\
                    .limit(1)\
                    .execute()
                
                if not res.data:
                    report.append(f"🔴 {name}: No heartbeat found in DB.")
                    alerts_needed.append(f"🚨 ALERT: {name} has NO heartbeat data!")
                    continue

                last_hb = res.data[0]
                hb_time = datetime.fromisoformat(last_hb["timestamp"].replace("Z", "+00:00"))
                delay_min = (now - hb_time).total_seconds() / 60
                
                status_icon = "🟢" if delay_min <= self.stale_threshold_min else "🔴"
                report.append(f"{status_icon} {name}: {delay_min:.1f}m ago ({last_hb['status']})")

                if delay_min > self.stale_threshold_min:
                    alerts_needed.append(f"🚨 ALERT: {name} is STALLED! Last heartbeat was {delay_min:.1f} minutes ago.")

            except Exception as e:
                logger.error(f"Failed to check {name}: {e}")
                report.append(f"⚠️ {name}: Check failed ({e})")

        # Log to console
        logger.info("\n" + "\n".join(report))

        # Send Telegram alerts if needed
        if alerts_needed:
            # 🔥 ACTIVE HEALING: If any service is stalled, run the Janitor to clear stuck signals
            logger.warning("🩹 Watchdog: Stalled services detected. Running Janitor active healing...")
            Janitor.run_sync()

            if self.notifier:
                alert_msg = "🚨 *QUANTIX CRITICAL ALERT*\n\n" + "\n".join(alerts_needed) + "\n\n🩹 *Action:* Janitor auto-cleanup triggered.\n\nCc: @admin"
                self.notifier.send_message(alert_msg)

if __name__ == "__main__":
    watchdog = QuantixWatchdog()
    watchdog.run()
