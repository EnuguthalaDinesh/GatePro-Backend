import os
import glob
import logging
from database import get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrations")

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")

def init_migrations_table(conn):
    """Ensures schema_migrations tracking table exists in PostgreSQL."""
    with conn.cursor() as cursor:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) UNIQUE NOT NULL,
            applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
        """)
    conn.commit()

def get_applied_migrations(conn):
    """Returns set of already applied migration filenames."""
    with conn.cursor() as cursor:
        cursor.execute("SELECT filename FROM schema_migrations;")
        rows = cursor.fetchall()
        return {row["filename"] for row in rows}

def run_migrations():
    """Runs all unapplied SQL migration files in order."""
    if not os.path.exists(MIGRATIONS_DIR):
        logger.warning("No migrations directory found.")
        return

    sql_files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
    if not sql_files:
        logger.info("No migration files found.")
        return

    conn = get_db_connection()
    try:
        init_migrations_table(conn)
        applied = get_applied_migrations(conn)

        for filepath in sql_files:
            filename = os.path.basename(filepath)
            if filename in applied:
                logger.info(f"Skipping already applied migration: {filename}")
                continue

            logger.info(f"Applying migration: {filename}")
            with open(filepath, "r", encoding="utf-8") as f:
                sql_script = f.read()

            with conn.cursor() as cursor:
                cursor.execute(sql_script)
                cursor.execute("INSERT INTO schema_migrations (filename) VALUES (%s);", (filename,))
            conn.commit()
            logger.info(f"Successfully applied: {filename}")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration error: {e}")
        raise e
    finally:
        conn.close()

def rollback_migrations():
    """Rolls back database tables (for development reset)."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            DROP TABLE IF EXISTS question_images CASCADE;
            DROP TABLE IF EXISTS options CASCADE;
            DROP TABLE IF EXISTS study_sessions CASCADE;
            DROP TABLE IF EXISTS user_alarms CASCADE;
            DROP TABLE IF EXISTS leaderboard CASCADE;
            DROP TABLE IF EXISTS test_results CASCADE;
            DROP TABLE IF EXISTS questions CASCADE;
            DROP TABLE IF EXISTS papers CASCADE;
            DROP TABLE IF EXISTS pyqs CASCADE;
            DROP TABLE IF EXISTS users CASCADE;
            DROP TABLE IF EXISTS schema_migrations CASCADE;
            """)
        conn.commit()
        logger.info("Successfully rolled back all tables.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Rollback error: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback_migrations()
    else:
        run_migrations()
