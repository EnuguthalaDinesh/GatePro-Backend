import os
import logging
import psycopg2
import psycopg2.extras
from psycopg2 import sql, errors
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("database")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/exam_platform")

def get_db_connection():
    """
    Establishes and returns a connection to the PostgreSQL database.
    Uses RealDictCursor so rows can be accessed as dictionaries like sqlite3.Row.
    """
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=10
        )
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"PostgreSQL Connection Error: {e}")
        # Try constructing from individual env parameters if DATABASE_URL connection failed
        try:
            conn = psycopg2.connect(
                user=os.getenv("POSTGRES_USER", "postgres"),
                password=os.getenv("POSTGRES_PASSWORD", "postgres"),
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                dbname=os.getenv("POSTGRES_DB", "exam_platform"),
                cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=10
            )
            return conn
        except Exception as retry_err:
            logger.critical(f"Failed to connect to PostgreSQL: {retry_err}")
            raise RuntimeError(f"Could not connect to PostgreSQL database: {retry_err}") from retry_err

def init_db():
    """Initializes database schema using PostgreSQL migrations."""
    from migrations import run_migrations
    logger.info("Initializing PostgreSQL Database Schema via Migrations...")
    try:
        run_migrations()
        logger.info("PostgreSQL Database initialized successfully!")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise e

class DatabaseError(Exception):
    """Base custom database exception."""
    pass

class DuplicateKeyError(DatabaseError):
    """Raised when a unique constraint or primary key conflict occurs."""
    pass

def handle_pg_exception(e: Exception, conn=None):
    """Generic error handler for PostgreSQL operations."""
    if conn:
        try:
            conn.rollback()
        except Exception:
            pass
    if isinstance(e, errors.UniqueViolation):
        raise DuplicateKeyError(f"Duplicate entry error: {e.pgerror or str(e)}") from e
    elif isinstance(e, errors.OperationalError):
        raise DatabaseError(f"PostgreSQL Operational/Connection error: {str(e)}") from e
    else:
        raise DatabaseError(f"Database operation failed: {str(e)}") from e
