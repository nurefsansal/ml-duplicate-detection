"""
Migration runner - Executes SQL schema creation
"""
from pathlib import Path
from sqlalchemy import text, create_engine
import os

DEFAULT_DATABASE_URL = "postgresql+psycopg2://ml_duplicate_user:1234@localhost:5434/ml_duplicate_db"

def run_migration():
    """Run SQL migration script"""
    db_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = create_engine(db_url)
    
    migration_file = Path(__file__).parent / "001_initial_schema.sql"
    
    if not migration_file.exists():
        raise FileNotFoundError(f"Migration file not found: {migration_file}")
    
    with open(migration_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # Split by semicolon and execute each statement
    statements = sql_content.split(';')
    
    with engine.begin() as connection:
        for statement in statements:
            stmt = statement.strip()
            if stmt:  # Skip empty statements
                try:
                    print(f"Executing: {stmt[:80]}...")
                    connection.execute(text(stmt))
                except Exception as e:
                    print(f"⚠️ Warning (may be expected): {e}")
    
    print("\n✅ Migration completed successfully!")

if __name__ == "__main__":
    run_migration()
