"""
Codozent CMS: Automated SQLite to Supabase Data Migration Tool
Copies all existing local data (admin credentials, homepage images, work items,
blogs, jobs, media assets, and settings) into your live Supabase PostgreSQL database.

Usage:
  python -m cms.migrate_to_supabase
  python -m cms.migrate_to_supabase --url "postgresql://postgres.[ref]:[pass]@aws-0-[region].pooler.supabase.com:6543/postgres"
"""
import os
import sys
import argparse
import sqlite3
import logging
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from cms.db import init_postgres_db

LOCAL_SQLITE_PATH = os.path.join(BASE_DIR, 'data', 'cms.db')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CodozentCMS.Migration")

TABLES_TO_MIGRATE = [
    {
        "table": "system_settings",
        "conflict_col": "key",
        "has_serial": False,
        "update_cols": ["value", "updated_at"]
    },
    {
        "table": "users",
        "conflict_col": "email",
        "has_serial": True,
        "update_cols": ["password_hash", "salt", "full_name", "role", "status", "session_version", "failed_attempts", "locked_until", "last_login"]
    },
    {
        "table": "pages",
        "conflict_col": "page_key",
        "has_serial": False,
        "update_cols": ["title", "file_name", "meta_title", "meta_description", "meta_keywords", "fields_json", "has_draft", "updated_at", "published_at"]
    },
    {
        "table": "homepage_images",
        "conflict_col": "slot_key",
        "has_serial": False,
        "update_cols": ["label", "section", "selector", "current_src", "draft_src", "current_alt", "draft_alt", "recommended_dims", "has_draft", "updated_at"]
    },
    {
        "table": "homepage_video_section",
        "conflict_col": "id",
        "has_serial": False,
        "update_cols": ["video_enabled", "video_url", "image_url", "image_alt", "title", "description", "updated_at"]
    },
    {
        "table": "work_items",
        "conflict_col": "id",
        "has_serial": True,
        "update_cols": ["title", "category", "description", "image_url", "image_alt", "project_url", "display_order", "status", "storage_provider", "cloudinary_public_id", "updated_at"]
    },
    {
        "table": "jobs",
        "conflict_col": "id",
        "has_serial": True,
        "update_cols": ["title", "department", "location", "employment_type", "description", "responsibilities", "qualifications", "deadline", "apply_label", "apply_url", "status", "updated_at"]
    },
    {
        "table": "blog_posts",
        "conflict_col": "id",
        "has_serial": True,
        "update_cols": ["title", "slug", "excerpt", "body", "author", "author_role", "category", "tags", "featured_image", "featured_image_alt", "published_date", "status", "cloudinary_public_id", "updated_at"]
    },
    {
        "table": "media_assets",
        "conflict_col": "id",
        "has_serial": True,
        "update_cols": ["filename", "file_path", "file_size", "mime_type", "category", "storage_provider", "cloudinary_asset_id", "cloudinary_public_id", "cloudinary_version", "cloudinary_format", "width", "height", "secure_url", "folder", "alt_text", "uploaded_at"]
    },
    {
        "table": "audit_log",
        "conflict_col": "id",
        "has_serial": True,
        "update_cols": []
    }
]


def run_migration(target_db_url: str):
    import psycopg2
    from psycopg2.extras import execute_values

    legacy_path = os.path.join(BASE_DIR, 'data', 'cms_sqlite_legacy.db.bak')
    sqlite_source = LOCAL_SQLITE_PATH if os.path.exists(LOCAL_SQLITE_PATH) else legacy_path
    if not os.path.exists(sqlite_source):
        logger.error("Local SQLite database not found at %s. Nothing to migrate.", LOCAL_SQLITE_PATH)
        return False

    # Normalize URL
    url = target_db_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    logger.info("Connecting to target Supabase PostgreSQL database...")
    try:
        pg_conn = psycopg2.connect(url, sslmode="require", connect_timeout=15)
        pg_conn.autocommit = False
    except Exception as e:
        logger.error("Could not connect to Supabase PostgreSQL: %s", e)
        return False

    logger.info("Initializing Supabase schema...")
    try:
        init_postgres_db(pg_conn)
    except Exception as e:
        logger.error("Failed to initialize Supabase schema: %s", e)
        pg_conn.close()
        return False

    # Connect to local SQLite
    sqlite_conn = sqlite3.connect(sqlite_source)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()

    summary = {}

    try:
        for item in TABLES_TO_MIGRATE:
            table = item["table"]
            conflict_col = item["conflict_col"]
            update_cols = item["update_cols"]

            # Check if table exists in SQLite
            sqlite_cur.execute(f"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='{table}'")
            if sqlite_cur.fetchone()[0] == 0:
                logger.info("Table '%s' does not exist in SQLite, skipping.", table)
                continue

            # Fetch all rows from SQLite
            sqlite_cur.execute(f"SELECT * FROM {table}")
            rows = sqlite_cur.fetchall()
            if not rows:
                logger.info("Table '%s' has 0 rows in SQLite.", table)
                summary[table] = 0
                continue

            cols = [col[0] for col in sqlite_cur.description]
            cols_str = ", ".join([f'"{c}"' for c in cols])
            placeholders = ", ".join(["%s"] * len(cols))

            if update_cols:
                set_clauses = [f'"{c}" = EXCLUDED."{c}"' for c in update_cols if c in cols]
                conflict_action = f"DO UPDATE SET {', '.join(set_clauses)}"
            else:
                conflict_action = "DO NOTHING"

            insert_sql = f"""
            INSERT INTO {table} ({cols_str})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_col}) {conflict_action}
            """

            count = 0
            for r in rows:
                values = [r[c] for c in cols]
                pg_cur.execute(insert_sql, values)
                count += 1

            # Reset sequence if table has serial ID
            if item["has_serial"]:
                try:
                    pg_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(max(id), 1)) FROM {table};")
                except Exception as seq_err:
                    logger.debug("Could not reset sequence for %s: %s", table, seq_err)

            summary[table] = count
            logger.info("Migrated %d rows for table '%s'", count, table)

        pg_conn.commit()
        logger.info("Migration completed successfully!")
        print("\n" + "="*50)
        print("CODOZENT CMS: SUPABASE MIGRATION SUMMARY")
        print("="*50)
        for tbl, cnt in summary.items():
            print(f"  - {tbl:<25} : {cnt:>4} rows transferred")
        print("="*50)
        print("All data is now permanently safe and active on Supabase PostgreSQL!\n")
        return True

    except Exception as e:
        pg_conn.rollback()
        logger.error("Migration failed with error: %s", e)
        return False
    finally:
        sqlite_conn.close()
        pg_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate Codozent CMS SQLite data to Supabase PostgreSQL.")
    parser.add_argument("--url", help="Supabase PostgreSQL connection string (postgresql://...)")
    args = parser.parse_args()

    db_url = args.url or os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("\nError: No Supabase connection URL provided.")
        print("Provide via --url argument or set SUPABASE_DB_URL / DATABASE_URL in your environment.")
        print('Example: python -m cms.migrate_to_supabase --url "postgresql://postgres.[ref]:[pass]@aws-0-[region].pooler.supabase.com:6543/postgres"\n')
        sys.exit(1)

    success = run_migration(db_url)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
