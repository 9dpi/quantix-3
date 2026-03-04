import asyncio
from backend.quantix_core.database.connection import db
from backend.quantix_core.config.settings import settings

async def check():
    res = db.client.table(settings.TABLE_SIGNALS).select("*").order("generated_at", desc=True).limit(1).execute()
    if res.data:
        for k in res.data[0].keys():
            print(k)

if __name__ == "__main__":
    asyncio.run(check())
