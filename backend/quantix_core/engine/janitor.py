
import asyncio
from datetime import datetime, timezone
from loguru import logger
from backend.quantix_core.database.connection import db
from backend.quantix_core.config.settings import settings

class Janitor:
    """
    Robust health service to clear stuck/hung signals.
    Redundant safety net to ensure pipeline never blocks.
    """
    
    @staticmethod
    def run_sync():
        """Synchronous wrapper for async run (for easy embedding)"""
        try:
            # We use the db.client directly since it's already a wrapper or client
            Janitor._perform_cleanup()
        except Exception as e:
            logger.error(f"Janitor sync run failed: {e}")

    @staticmethod
    def _perform_cleanup():
        """Internal robust cleanup logic"""
        now = datetime.now(timezone.utc)
        logger.info("🧹 Janitor: Starting robust signal cleanup...")
        
        try:
            # 1. Fetch all potentially stuck signals
            # States that should eventually transition: WAITING, ENTRY_HIT, ACTIVE, PUBLISHED
            res = db.client.table(settings.TABLE_SIGNALS).select("*").in_(
                "state", ["WAITING_FOR_ENTRY", "ENTRY_HIT", "ACTIVE", "PUBLISHED", "PENDING"]
            ).execute()
            
            signals = res.data or []
            expired_count = 0
            
            for sig in signals:
                sig_id = sig.get("id")
                state = sig.get("state")
                gen_at_str = sig.get("generated_at")
                hit_at_str = sig.get("entry_hit_at")
                
                if not gen_at_str: continue
                gen_at = datetime.fromisoformat(gen_at_str.replace("Z", "+00:00"))
                
                is_expired = False
                reason = ""
                new_state = "CANCELLED"
                new_status = "EXPIRED"
                new_result = "CANCELLED"
                
                # CASE A: WAITING -> CANCELLED (35m)
                if state in ["WAITING_FOR_ENTRY", "PUBLISHED"]:
                    age_min = (now - gen_at).total_seconds() / 60
                    # Use a small grace buffer (5m) for janitor cleanup to avoid race conditions with Watcher
                    if age_min >= (settings.MAX_PENDING_DURATION_MINUTES + 2):
                        is_expired = True
                        reason = f"Entry window expired ({int(age_min)}m > {settings.MAX_PENDING_DURATION_MINUTES}m)"
                        new_state = "CANCELLED"
                        new_status = "EXPIRED"
                
                # CASE B: ACTIVE -> TIME_EXIT (90m)
                elif state in ["ENTRY_HIT", "ACTIVE"]:
                    # Priority 1: entry_hit_at. Priority 2: generated_at
                    start_time = gen_at
                    if hit_at_str:
                        start_time = datetime.fromisoformat(hit_at_str.replace("Z", "+00:00"))
                    
                    age_min = (now - start_time).total_seconds() / 60
                    if age_min >= (settings.MAX_TRADE_DURATION_MINUTES + 5):
                        is_expired = True
                        reason = f"Trade duration reached ({int(age_min)}m > {settings.MAX_TRADE_DURATION_MINUTES}m)"
                        new_state = "CANCELLED" # Unified to CANCELLED/CLOSED_TIMEOUT for dashboard compatibility
                        new_status = "CLOSED_TIMEOUT"
                        new_result = "CANCELLED"
                
                if is_expired:
                    logger.warning(f"🧹 Janitor: Force-closing Signal {sig_id} ({state}) | {reason}")
                    try:
                        db.client.table(settings.TABLE_SIGNALS).update({
                            "state": new_state,
                            "status": new_status,
                            "result": new_result,
                            "closed_at": now.isoformat()
                        }).eq("id", sig_id).execute()
                        expired_count += 1
                    except Exception as de:
                        logger.error(f"Janitor DB update failed for {sig_id}: {de}")

            if expired_count > 0:
                logger.success(f"✅ Janitor cleaned {expired_count} stuck signals.")
            else:
                logger.debug("Janitor: No stuck signals found.")
                
        except Exception as e:
            logger.error(f"Janitor cleanup failed: {e}")
