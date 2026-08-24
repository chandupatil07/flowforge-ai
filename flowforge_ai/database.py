import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from flowforge_ai.config.settings import settings

logger = logging.getLogger("flowforge_ai")

db_url = settings.DATABASE_URL

# Fallback mechanism if PostgreSQL is configured but no driver is available
if db_url.startswith("postgresql"):
    try:
        import psycopg2
    except ImportError:
        try:
            import asyncpg
        except ImportError:
            logger.warning(
                "PostgreSQL python driver (psycopg2 or asyncpg) not found. "
                "Falling back to local SQLite database for local verification/testing."
            )
            db_url = "sqlite:///flowforge.db"

# SQLite-specific optimization for thread safety
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(db_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
