"""
Supabase database connection and client management
"""
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None
from backend.quantix_core.config.settings import settings
from loguru import logger
from typing import Optional, List, Dict, Any, Union
import asyncio
from contextlib import asynccontextmanager
import requests
import json

# Fallback Class
class SupabaseLite:
    def __init__(self, url, key):
        self.url = url
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
    def table(self, name):
        # Force refresh of cache?
        return SupabaseQueryBuilder(self, name)

class SupabaseQueryBuilder:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.params = {}
        self.method = "GET"
        self.payload = None
        self.filters = []

    def select(self, columns="*"):
        self.method = "GET"
        self.params["select"] = columns
        return self

    def insert(self, data):
        self.method = "POST"
        self.payload = data
        return self

    def update(self, data):
        self.method = "PATCH"
        self.payload = data
        return self

    def delete(self):
        self.method = "DELETE"
        return self

    def eq(self, column, value):
        self.filters.append(f"{column}=eq.{value}")
        return self

    def neq(self, column, value):
        self.filters.append(f"{column}=neq.{value}")
        return self
    
    def lt(self, column, value):
        self.filters.append(f"{column}=lt.{value}")
        return self
        
    def gte(self, column, value):
        self.filters.append(f"{column}=gte.{value}")
        return self

    def limit(self, count):
        self.params["limit"] = count
        return self

    def order(self, column, desc=False):
        self.params["order"] = f"{column}.{'desc' if desc else 'asc'}"
        return self

    def execute(self):
        url = f"{self.client.url}/rest/v1/{self.table}"
        
        # Apply filters to params
        params = self.params.copy()
        for f in self.filters:
            k, v = f.split('=', 1)
            params[k] = v

        try:
            timeout = 10
            if self.method == "GET":
                resp = requests.get(url, headers=self.client.headers, params=params, timeout=timeout)
            elif self.method == "POST":
                resp = requests.post(url, headers=self.client.headers, json=self.payload, timeout=timeout)
            elif self.method == "PATCH":
                resp = requests.patch(url, headers=self.client.headers, json=self.payload, params=params, timeout=timeout)
            elif self.method == "DELETE":
                resp = requests.delete(url, headers=self.client.headers, params=params, timeout=timeout)
            else:
                return MockResponse(None, "Unsupported method")

            if resp.status_code >= 400:
                logger.error(f"SupabaseLite Error {resp.status_code}: {resp.text}")
                return MockResponse(None, resp.text)
                
            return MockResponse(resp.json())
        except Exception as e:
            logger.error(f"SupabaseLite Request Failed: {e}")
            return MockResponse(None, str(e))

class MockResponse:
    def __init__(self, data, error=None):
        self.data = data
        self.error = error

class SupabaseConnection:
    _instance: Optional["SupabaseConnection"] = None
    _client: Optional[Client] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._client is None:
            self._initialize_client()

    def _initialize_client(self):
        try:
            url = settings.SUPABASE_URL
            # Prefer Service Role Key for Backend/Miner
            key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
            
            if not url or not key:
                logger.warning("⚠️ SUPABASE_URL or Key is missing!")
                return
            
            try:
                from supabase import create_client
                self._client = create_client(
                    supabase_url=url,
                    supabase_key=key
                )
                logger.info("✅ Supabase client initialized (Official SDK)")
            except ImportError:
                logger.warning("⚠️ Supabase SDK not found. Using SupabaseLite (Requests fallback)")
                self._client = SupabaseLite(url, key)
            except Exception as e:
                logger.error(f"❌ Official Supabase client init failed: {e}. Falling back to Lite.")
                self._client = SupabaseLite(url, key)
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase client: {e}")
            self._client = None




    @property
    def client(self) -> Client:
        if self._client is None:
            self._initialize_client()
        return self._client

    def health_check(self) -> bool:
        try:
            # Try to query the signals table as a heartbeat
            self._client.table(settings.TABLE_SIGNALS).select("id").limit(1).execute()
            return True
        except Exception as e:
            logger.error(f"❌ Database connection failed: {str(e)}")
            return False

    async def execute(self, query: str, *args):
        # shim for simple INSERT in csv_ingestion router
        if "INSERT INTO ingestion_audit_log" in query:
             data = {
                 "asset": args[0], "timeframe": args[1], "source": args[2],
                 "total_rows": args[3], "tradable_count": args[4],
                 "non_tradable_count": args[5], "avg_learning_weight": float(args[6]),
                 "status": args[7]
             }
             return self.client.table('ingestion_audit_log').insert(data).execute()
        return None

    async def fetch(self, query: str, *args):
        try:
            if not self.client:
                return []

            # 1. Shim for signals
            if "FROM fx_signals" in query:
                q = self.client.table('fx_signals').select('*')
                if "ORDER BY generated_at DESC" in query:
                    q = q.order('generated_at', desc=True)
                if "LIMIT" in query:
                    try:
                        limit_part = query.split("LIMIT")[-1].strip()
                        limit = int(limit_part)
                        q = q.limit(limit)
                    except:
                        q = q.limit(5)
                if "WHERE status = 'ACTIVE'" in query:
                    q = q.eq("status", "ACTIVE")
                    
                res = q.execute()
                return res.data if res.data else []

            # 2. Shim for global stats 
            if "SELECT SUM(tradable_count)" in query:
                res = self.client.table('ingestion_audit_log').select('tradable_count,total_rows,avg_learning_weight').execute()
                if not res.data: return []
                import pandas as pd
                df = pd.DataFrame(res.data)
                return [{
                    "total_learning": int(df['tradable_count'].sum()),
                    "total_ingested": int(df['total_rows'].sum()),
                    "avg_weight": float(df['avg_learning_weight'].mean())
                }]

            # 3. Shim for telemetry aggregation (used in dashboard)
            if "COUNT(*) as total" in query and "FROM fx_signals" in query:
                res = self.client.table('fx_signals').select('*').execute()
                if not res.data:
                    return [{"total": 0, "wins": 0, "losses": 0, "avg_conf": 0, "peak_conf": 0}]
                
                data = res.data
                total = len(data)
                wins = len([s for s in data if s.get("state") == "TP_HIT"])
                losses = len([s for s in data if s.get("state") == "SL_HIT"])
                confidences = [s.get("ai_confidence", 0) for s in data if s.get("ai_confidence") is not None]
                avg_conf = sum(confidences) / len(confidences) if confidences else 0
                peak_conf = max(confidences) if confidences else 0
                
                # Directional breakdown
                buy_sigs = [s for s in data if s.get("direction") == "BUY"]
                sell_sigs = [s for s in data if s.get("direction") == "SELL"]
                
                details = {
                    "BUY": {"wins": len([s for s in buy_sigs if s.get("state") == "TP_HIT"]), "total": len(buy_sigs)},
                    "SELL": {"wins": len([s for s in sell_sigs if s.get("state") == "TP_HIT"]), "total": len(sell_sigs)},
                    "HOLD": {"wins": 0, "total": 0} # Hold is not usually in fx_signals state
                }

                return [{
                    "total": total,
                    "wins": wins,
                    "losses": losses,
                    "avg_conf": avg_conf,
                    "peak_conf": peak_conf,
                    "details": details
                }]

            # 4. Shim for history with specific columns (used in dashboard)
            if "SELECT ai_confidence as v, generated_at as t" in query:
                res = self.client.table('fx_signals').select('ai_confidence,generated_at').order('generated_at', desc=True).limit(10).execute()
                if not res.data: return []
                return [{"v": s.get("ai_confidence", 0), "t": s.get("generated_at")} for s in res.data]

            return []
        except Exception as e:
            logger.error(f"Database fetch error: {e}")
            return []

db = SupabaseConnection()

def get_db() -> Client:
    return db.client

