# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator
from core.config import settings

# Create async engine based on database type
engine_kwargs = {
    "echo": settings.DEBUG,
    "future": True,
}

if settings.DATABASE_TYPE.lower() == "postgres":
    engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
    })

engine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


# Dependency to get DB session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()