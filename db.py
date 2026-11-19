import os
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, URL, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()
logger = logging.getLogger(__name__)

# Base declarative class
Base = declarative_base()

def get_engine():
    """
    Initializes SQLAlchemy engine.
    Checks environment for DATABASE_URL.
    If TiDB / MySQL is configured but fails to connect, gracefully falls back to SQLite.
    """
    env_db_url = os.getenv("DATABASE_URL", "").strip()

    # If DATABASE_URL is explicitly set to SQLite or another URL
    if env_db_url.startswith("sqlite"):
        return create_engine(env_db_url, connect_args={"check_same_thread": False})

    # Default TiDB URL from original project configuration
    tidb_url = URL.create(
        "mysql+pymysql",
        username=os.getenv("TIDB_USER", "kfSC8P2ejB8BaYT.root"),
        password=os.getenv("TIDB_PASSWORD", "RKQ81W63XDsEW0ul"),
        host=os.getenv("TIDB_HOST", "gateway01.ap-northeast-1.prod.aws.tidbcloud.com"),
        port=int(os.getenv("TIDB_PORT", 4000)),
        database=os.getenv("TIDB_DATABASE", "test"),
    )

    db_target = env_db_url if env_db_url else tidb_url

    try:
        engine = create_engine(
            db_target,
            pool_pre_ping=True,
            connect_args={"ssl": {"ssl": True}} if "tidbcloud.com" in str(db_target) else {}
        )
        # Quick test connection with a short timeout
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[Database] Successfully connected to TiDB/MySQL database.")
        return engine
    except Exception as e:
        print(f"[Database Warning] Could not connect to remote DB ({e}). Falling back to local SQLite: resume_ai.db")
        sqlite_engine = create_engine("sqlite:///resume_ai.db", connect_args={"check_same_thread": False})
        return sqlite_engine

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Create all tables in the database"""
    Base.metadata.create_all(bind=engine)
