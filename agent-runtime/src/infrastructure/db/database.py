import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/app"


def get_async_database_url() -> str:
    raw_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    # 确保驱动使用 asyncpg
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql+psycopg://"):
        return raw_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    return raw_url


engine = create_async_engine(
    get_async_database_url(),
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    echo=False,
    connect_args={"server_settings": {"timezone": "Asia/Shanghai"}},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
