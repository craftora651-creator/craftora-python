# test2.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from config.config import settings

async def check_columns():
    # Settings'ten database URL'ini al
    engine = create_async_engine(settings.DATABASE_URL)
    
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users' ORDER BY ordinal_position")
        )
        rows = result.fetchall()
        
        print("\n📊 Users tablosu kolonları:")
        for row in rows:
            print(f"  {row[0]:20} {row[1]}")
    
    await engine.dispose()

asyncio.run(check_columns())