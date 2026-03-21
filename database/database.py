import logging
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncSession, 
    async_sessionmaker, 
    create_async_engine,
    AsyncEngine
)
from sqlalchemy.pool import QueuePool
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import asyncpg
from contextlib import asynccontextmanager

from config.config import settings
from models.base import Base

# Configure logging
logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database connection manager with connection pooling."""
    
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.async_session_maker: Optional[async_sessionmaker] = None
        self.is_connected: bool = False
        
    async def initialize(self) -> None:
        """Initialize database connection pool."""
        try:
            # Create async engine with connection pooling
            self.engine = create_async_engine(
                settings.DATABASE_URL,
                echo=settings.DATABASE_ECHO,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                pool_recycle=settings.DATABASE_POOL_RECYCLE,
                pool_timeout=settings.DATABASE_POOL_TIMEOUT,
                pool_pre_ping=True,  # Verify connections before using
                connect_args={
                    "command_timeout": 60,
                    "server_settings": {
                        "application_name": "craftora_backend",
                        "search_path": "public",
                    }
                }
            )
            
            # Create session factory
            self.async_session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False
            )
            
            # Test connection
            await self.test_connection()
            self.is_connected = True
            logger.info(" Database connection pool initialized successfully")
        except Exception as e:
            logger.error(f" Failed to initialize database: {e}")
            raise
    
    async def test_connection(self) -> bool:
        """Test database connection."""
        if not self.engine:
            raise RuntimeError("Database engine not initialized")
        
        try:
            async with self.engine.connect() as conn:
                # Test basic query
                result = await conn.execute(text("SELECT version()"))
                version = result.scalar()
                logger.info(f" Connected to PostgreSQL: {version}")
                
                # Test database name
                result = await conn.execute(text("SELECT current_database()"))
                db_name = result.scalar()
                logger.info(f" Database: {db_name}")
                
                return True
                
        except asyncpg.exceptions.ConnectionDoesNotExistError:
            logger.error(" Database connection lost")
            return False
        except Exception as e:
            logger.error(f" Database connection test failed: {e}")
            return False
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with automatic cleanup."""
        if not self.async_session_maker:
            raise RuntimeError("Database session factory not initialized")
        
        session: AsyncSession = self.async_session_maker()
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()
    
    async def create_tables(self) -> None:
        """Create all tables (for development only)."""
        if not self.engine:
            raise RuntimeError("Database engine not initialized")
        try:
            async with self.engine.begin() as conn:
                # Create extensions first
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"citext\""))
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"pg_trgm\""))

                # Create all tables
                await conn.run_sync(Base.metadata.create_all)
                
            logger.info(" Database tables created successfully")
            
        except Exception as e:
            logger.error(f" Failed to create tables: {e}")
            raise
    
    async def drop_tables(self) -> None:
        """Drop all tables (for testing only)."""
        if not self.engine:
            raise RuntimeError("Database engine not initialized")
        
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                
            logger.info(" Database tables dropped successfully")
            
        except Exception as e:
            logger.error(f" Failed to drop tables: {e}")
            raise
    
    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            self.is_connected = False
            logger.info(" Database connections closed")
    
    async def get_connection_stats(self) -> dict:
        """Get database connection statistics."""
        if not self.engine:
            return {}
        
        try:
            async with self.engine.connect() as conn:
                # Get connection pool stats
                pool = self.engine.pool
                stats = {
                    "pool_size": pool.size(),
                    "checked_in": pool.checkedin(),
                    "checked_out": pool.checkedout(),
                    "overflow": pool.overflow(),
                    "connections": pool.checkedin() + pool.checkedout(),
                }
                
                # Get database stats
                result = await conn.execute(text("""
                    SELECT 
                        COUNT(*) as total_connections,
                        COUNT(*) FILTER (WHERE state = 'active') as active_connections,
                        COUNT(*) FILTER (WHERE state = 'idle') as idle_connections
                    FROM pg_stat_activity 
                    WHERE datname = current_database()
                """))
                db_stats = result.mappings().first()
                
                if db_stats:
                    stats.update(dict(db_stats))
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get connection stats: {e}")
            return {}


# Global database manager instance
db_manager = DatabaseManager()


# FastAPI dependency for database sessions
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.
    
    Usage:
        @router.get("/items")
        async def read_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with db_manager.get_session() as session:
        yield session


# Health check function
async def check_database_health() -> dict:
    """Check database health for monitoring."""
    if not db_manager.is_connected:
        return {"status": "disconnected", "message": "Database not initialized"}
    
    try:
        is_healthy = await db_manager.test_connection()
        stats = await db_manager.get_connection_stats()
        
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "connected": is_healthy,
            "stats": stats,
            "timestamp": "server_time_here"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "connected": False
        }
    

# database/database.py - İçine bu fonksiyonu ekle:
async def init_db():
    """
    Initialize database connection and create tables.
    """
    try:
        from models.user import User
        from models.base import Base

        if not db_manager.engine:
            raise RuntimeError("Database engine not initialized")

        async with db_manager.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info(" Database tables created/verified")
        return True

    except Exception as e:
        logger.error(f" Database initialization failed: {e}")
        raise

engine = db_manager.engine if db_manager.engine else None