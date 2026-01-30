"""
Database migration script to add university_id column to tasks table.
Run this using Python instead of psql.
"""

from sqlalchemy import create_engine, text
from config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Add university_id column to tasks table."""
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Check if column already exists
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'tasks' 
                AND column_name = 'university_id'
            """)
            
            result = conn.execute(check_query)
            exists = result.fetchone() is not None
            
            if exists:
                logger.info("Column 'university_id' already exists in tasks table")
                return
            
            # Add the column
            logger.info("Adding university_id column to tasks table...")
            alter_query = text("""
                ALTER TABLE tasks
                ADD COLUMN university_id INTEGER NULL
            """)
            conn.execute(alter_query)
            conn.commit()
            
            # Add index for performance
            logger.info("Creating index on university_id...")
            index_query = text("""
                CREATE INDEX IF NOT EXISTS idx_tasks_university_id 
                ON tasks(university_id)
            """)
            conn.execute(index_query)
            conn.commit()
            
            logger.info("✅ Migration completed successfully")
            
            # Verify
            verify_query = text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'tasks'
                ORDER BY ordinal_position
            """)
            result = conn.execute(verify_query)
            logger.info("Tasks table schema:")
            for row in result:
                logger.info(f"  - {row.column_name}: {row.data_type} (nullable: {row.is_nullable})")
                
    except Exception as e:
        logger.error(f"❌ Migration failed: {str(e)}")
        raise

if __name__ == "__main__":
    run_migration()
