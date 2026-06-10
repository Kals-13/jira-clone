from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# Connection pool tuning for production throughput under concurrent load:
# - pool_size: 20 connections in the idle pool (ready to be checked out)
# - max_overflow: allow up to 40 additional overflow connections if all 20 are in use
# - pool_recycle: recycle connections after 3600s to prevent stale TCP connections
# - pool_pre_ping: verify connection is alive before using it (prevent "connection lost" errors)
# - echo_pool: log connection pool state (disable in production for verbosity)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    pool_size=20,
    max_overflow=40,
    pool_recycle=3600,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
