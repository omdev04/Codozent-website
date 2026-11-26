"""
Codozent CMS Database Layer
Pure Cloud Database Architecture:
Supabase (PostgreSQL) is the sole and exclusive database engine for both Local and Production.
SQLite has been completely removed to prevent dual-database drift and data desynchronization.
"""
import os
import sys
import logging
from datetime import datetime, timezone

# Automatically load environment variables from .env
try:
    from dotenv import load_dotenv
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CodozentCMS.db")


def get_postgres_dsn() -> str:
    """Returns normalized Supabase PostgreSQL connection string from environment."""
    url = (os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL") or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def is_postgres_mode() -> bool:
    """Checks whether the Supabase connection URL is configured."""
    return bool(get_postgres_dsn())


class DBRow(dict):
    """
    Unified database row:
    - dict-like key access: row['title']
    - tuple-like index access: row[0]
    - dict conversion: dict(row)
    - dict methods: row.get('key'), row.keys(), row.values(), row.items()
    """
    def __init__(self, description, values):
        super().__init__()
        self._index_values = list(values)
        if description:
            for i, col in enumerate(description):
                name = col.name if hasattr(col, 'name') else col[0]
                self[name] = values[i]

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._index_values[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        if isinstance(key, int):
            try:
                return self._index_values[key]
            except IndexError:
                return default
        return super().get(key, default)


def _convert_placeholders(query: str) -> str:
    """Replaces unquoted '?' with '%s' for PostgreSQL/psycopg2."""
    parts = []
    in_string = False
    quote_char = None
    i = 0
    n = len(query)
    while i < n:
        char = query[i]
        if char in ("'", '"'):
            if not in_string:
                in_string = True
                quote_char = char
            elif quote_char == char:
                if i + 1 < n and query[i+1] == char:
                    parts.append(char + char)
                    i += 2
                    continue
                in_string = False
                quote_char = None
            parts.append(char)
        elif char == '?' and not in_string:
            parts.append('%s')
        else:
            parts.append(char)
        i += 1
    return "".join(parts)


def _convert_sql_for_postgres(sql: str):
    """
    Translates standard queries into PostgreSQL/Supabase dialect.
    Returns (converted_sql, has_auto_returning)
    """
    s = sql.strip()
    upper_s = s.upper()

    # 1. No-op PRAGMAs on Postgres
    if upper_s.startswith("PRAGMA JOURNAL_MODE") or upper_s.startswith("PRAGMA FOREIGN_KEYS"):
        return "SELECT 1;", False

    # 2. Convert PRAGMA table_info(table_name) -> information_schema query
    if upper_s.startswith("PRAGMA TABLE_INFO("):
        tbl = s[len("PRAGMA TABLE_INFO("):].rstrip("); \t\n").strip().strip('"').strip("'").lower()
        query = (
            f"SELECT 0 as cid, column_name as name, data_type as type, 0 as notnull, "
            f"NULL as dflt_value, 0 as pk FROM information_schema.columns "
            f"WHERE table_name = '{tbl}' ORDER BY ordinal_position"
        )
        return query, False

    # 3. Handle INSERT OR IGNORE
    if "INSERT OR IGNORE INTO" in upper_s:
        idx = upper_s.find("INSERT OR IGNORE INTO")
        tbl_part = s[idx + len("INSERT OR IGNORE INTO"):].strip()
        tbl_name = tbl_part.split()[0].split("(")[0].strip('"').strip('`').lower()
        s = s[:idx] + "INSERT INTO" + s[idx + len("INSERT OR IGNORE INTO"):]
        if tbl_name == "homepage_video_section":
            s = s.rstrip("; \t\n") + " ON CONFLICT (id) DO NOTHING"
        elif tbl_name == "system_settings":
            s = s.rstrip("; \t\n") + " ON CONFLICT (key) DO NOTHING"
        elif tbl_name == "homepage_images":
            s = s.rstrip("; \t\n") + " ON CONFLICT (slot_key) DO NOTHING"
        elif tbl_name == "pages":
            s = s.rstrip("; \t\n") + " ON CONFLICT (page_key) DO NOTHING"
        elif tbl_name == "users":
            s = s.rstrip("; \t\n") + " ON CONFLICT (email) DO NOTHING"
        elif tbl_name == "blog_posts":
            s = s.rstrip("; \t\n") + " ON CONFLICT (slug) DO NOTHING"
        else:
            s = s.rstrip("; \t\n") + " ON CONFLICT DO NOTHING"

    # 4. Handle INSERT OR REPLACE
    elif "INSERT OR REPLACE INTO" in upper_s:
        idx = upper_s.find("INSERT OR REPLACE INTO")
        tbl_part = s[idx + len("INSERT OR REPLACE INTO"):].strip()
        tbl_name = tbl_part.split()[0].split("(")[0].strip('"').strip('`').lower()
        s = s[:idx] + "INSERT INTO" + s[idx + len("INSERT OR REPLACE INTO"):]
        if tbl_name == "system_settings":
            s = s.rstrip("; \t\n") + " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
        elif tbl_name == "homepage_images":
            s = s.rstrip("; \t\n") + " ON CONFLICT (slot_key) DO UPDATE SET current_src = EXCLUDED.current_src, current_alt = EXCLUDED.current_alt, updated_at = EXCLUDED.updated_at"
        elif tbl_name == "pages":
            s = s.rstrip("; \t\n") + " ON CONFLICT (page_key) DO UPDATE SET title = EXCLUDED.title, fields_json = EXCLUDED.fields_json, updated_at = EXCLUDED.updated_at"
        elif tbl_name == "homepage_video_section":
            s = s.rstrip("; \t\n") + " ON CONFLICT (id) DO UPDATE SET video_enabled = EXCLUDED.video_enabled, video_url = EXCLUDED.video_url, image_url = EXCLUDED.image_url, image_alt = EXCLUDED.image_alt, updated_at = EXCLUDED.updated_at"

    # 5. Convert '?' placeholders to '%s'
    s = _convert_placeholders(s)

    # 6. Check for auto RETURNING id for lastrowid
    has_auto_returning = False
    clean_s = s.strip().rstrip(";")
    if clean_s.upper().startswith("INSERT INTO ") and "RETURNING" not in clean_s.upper():
        tbl_part = clean_s[len("INSERT INTO "):].strip()
        tbl_name = tbl_part.split()[0].split("(")[0].strip('"').strip('`').lower()
        if tbl_name in ("users", "work_items", "jobs", "blog_posts", "media_assets", "audit_log"):
            s = clean_s + " RETURNING id"
            has_auto_returning = True

    return s, has_auto_returning


class PostgresCursorWrapper:
    """Wraps psycopg2 cursor to provide standard cursor API."""
    def __init__(self, raw_cursor):
        self._cursor = raw_cursor
        self.lastrowid = None

    def execute(self, query, params=None):
        converted_sql, has_auto_returning = _convert_sql_for_postgres(query)
        if params is not None:
            p = params if isinstance(params, (list, tuple)) else (params,)
            self._cursor.execute(converted_sql, p)
        else:
            self._cursor.execute(converted_sql)

        if has_auto_returning:
            try:
                row = self._cursor.fetchone()
                if row:
                    self.lastrowid = row[0]
            except Exception:
                self.lastrowid = None
        else:
            self.lastrowid = None
        return self

    def executemany(self, query, seq_of_params):
        converted_sql, _ = _convert_sql_for_postgres(query)
        self._cursor.executemany(converted_sql, seq_of_params)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return DBRow(self._cursor.description, row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows:
            return []
        desc = self._cursor.description
        return [DBRow(desc, r) for r in rows]

    def fetchmany(self, size=None):
        rows = self._cursor.fetchmany(size) if size else self._cursor.fetchmany()
        if not rows:
            return []
        desc = self._cursor.description
        return [DBRow(desc, r) for r in rows]

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        return self._cursor.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __iter__(self):
        desc = self._cursor.description
        for row in self._cursor:
            yield DBRow(desc, row)


class PostgresConnectionWrapper:
    """Wraps psycopg2 connection to provide standard DB connection API."""
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor())

    def execute(self, query, params=None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()


def get_postgres_connection():
    """Establishes an SSL-secured connection to Supabase PostgreSQL with retry."""
    import psycopg2
    import time
    dsn = get_postgres_dsn()
    if not dsn:
        raise RuntimeError(
            "CRITICAL: Supabase Database URL is not configured!\n"
            "Please add your Supabase connection string to .env:\n"
            "DATABASE_URL=postgresql://postgres.[REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres\n"
            "(See SUPABASE_SETUP_GUIDE.md for step-by-step instructions)"
        )

    last_err = None
    for attempt in range(1, 4):
        try:
            conn = psycopg2.connect(
                dsn,
                sslmode="require",
                connect_timeout=15,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5
            )
            conn.autocommit = False
            return conn
        except Exception as e:
            last_err = e
            logger.warning("Supabase connect attempt %d failed: %s", attempt, e)
            if attempt < 3:
                time.sleep(2)

    raise last_err


def get_db_connection():
    """
    Returns an active database connection to Supabase PostgreSQL.
    Sole database engine: SQLite has been completely removed.
    """
    raw_conn = get_postgres_connection()
    return PostgresConnectionWrapper(raw_conn)


def test_db_connection() -> dict:
    """Diagnostic health-check for Supabase PostgreSQL database connectivity."""
    dsn = get_postgres_dsn()
    if not dsn:
        return {
            "status": "not_configured",
            "engine": "supabase_postgresql",
            "message": "DATABASE_URL is not set in .env. Please configure your Supabase connection string."
        }
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        return {"status": "ok", "engine": "supabase_postgresql"}
    except Exception as e:
        logger.error("Supabase connection check failed: %s", e)
        return {"status": "error", "engine": "supabase_postgresql", "error": str(e)}


def init_postgres_db(conn):
    """Initializes tables and schema in Supabase PostgreSQL."""
    cursor = conn.cursor()

    # 1. Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin',
        status TEXT NOT NULL DEFAULT 'active',
        session_version INTEGER NOT NULL DEFAULT 1,
        failed_attempts INTEGER DEFAULT 0,
        locked_until TEXT,
        created_at TEXT NOT NULL,
        last_login TEXT
    );
    """)

    # 2. Pages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pages (
        page_key TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        file_name TEXT NOT NULL,
        meta_title TEXT,
        meta_description TEXT,
        meta_keywords TEXT,
        fields_json TEXT NOT NULL,
        has_draft INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL,
        published_at TEXT
    );
    """)

    # 3. Homepage Images table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS homepage_images (
        slot_key TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        section TEXT NOT NULL,
        selector TEXT NOT NULL,
        current_src TEXT NOT NULL,
        draft_src TEXT,
        current_alt TEXT NOT NULL,
        draft_alt TEXT,
        recommended_dims TEXT,
        has_draft INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL
    );
    """)

    # 4. Blog Posts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS blog_posts (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        excerpt TEXT NOT NULL,
        body TEXT NOT NULL,
        author TEXT NOT NULL,
        author_role TEXT,
        category TEXT NOT NULL,
        tags TEXT,
        featured_image TEXT NOT NULL,
        featured_image_alt TEXT NOT NULL,
        published_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'published',
        cloudinary_public_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 5. Jobs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        department TEXT NOT NULL,
        location TEXT NOT NULL,
        employment_type TEXT NOT NULL,
        description TEXT NOT NULL,
        responsibilities TEXT,
        qualifications TEXT,
        deadline TEXT,
        apply_label TEXT NOT NULL DEFAULT 'Apply for Role',
        apply_url TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 6. Media Assets table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS media_assets (
        id SERIAL PRIMARY KEY,
        filename TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        mime_type TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'general',
        storage_provider TEXT NOT NULL DEFAULT 'local',
        cloudinary_asset_id TEXT,
        cloudinary_public_id TEXT,
        cloudinary_version TEXT,
        cloudinary_format TEXT,
        width INTEGER DEFAULT 0,
        height INTEGER DEFAULT 0,
        secure_url TEXT,
        folder TEXT NOT NULL DEFAULT 'codozent',
        alt_text TEXT,
        uploaded_at TEXT NOT NULL
    );
    """)

    # 7. Work Items table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS work_items (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT,
        image_url TEXT NOT NULL,
        image_alt TEXT NOT NULL,
        project_url TEXT,
        display_order INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'published',
        storage_provider TEXT NOT NULL DEFAULT 'local',
        cloudinary_public_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 8. Audit Log table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id SERIAL PRIMARY KEY,
        user_email TEXT NOT NULL,
        action TEXT NOT NULL,
        details TEXT,
        timestamp TEXT NOT NULL
    );
    """)

    # 9. System Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 10. Homepage Video Section table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS homepage_video_section (
        id INTEGER PRIMARY KEY,
        video_enabled INTEGER NOT NULL DEFAULT 1,
        video_url TEXT NOT NULL DEFAULT 'https://www.youtube.com/watch?v=vZE0j_WCRvI',
        image_url TEXT NOT NULL DEFAULT 'assets/images/video/01.webp',
        image_alt TEXT NOT NULL DEFAULT 'Engineering Process',
        title TEXT DEFAULT 'We engineer clean, stable and dependable digital platforms to streamline operations and to accelerate business growth.',
        description TEXT DEFAULT 'Codozent Technologies combines pragmatic architecture with milestone-based delivery to help organizations build maintainable, scalable digital products.',
        updated_at TEXT NOT NULL
    );
    """)

    # Safe migrations for PostgreSQL columns
    for tbl, col, col_def in [
        ("users", "status", "TEXT NOT NULL DEFAULT 'active'"),
        ("users", "session_version", "INTEGER NOT NULL DEFAULT 1"),
        ("media_assets", "storage_provider", "TEXT NOT NULL DEFAULT 'local'"),
        ("media_assets", "cloudinary_asset_id", "TEXT"),
        ("media_assets", "cloudinary_public_id", "TEXT"),
        ("media_assets", "cloudinary_version", "TEXT"),
        ("media_assets", "cloudinary_format", "TEXT"),
        ("media_assets", "width", "INTEGER DEFAULT 0"),
        ("media_assets", "height", "INTEGER DEFAULT 0"),
        ("media_assets", "secure_url", "TEXT"),
        ("media_assets", "folder", "TEXT NOT NULL DEFAULT 'codozent'"),
        ("media_assets", "alt_text", "TEXT"),
        ("blog_posts", "cloudinary_public_id", "TEXT"),
        ("homepage_video_section", "title", "TEXT DEFAULT 'We engineer clean, stable and dependable digital platforms to streamline operations and to accelerate business growth.'"),
        ("homepage_video_section", "description", "TEXT DEFAULT 'Codozent Technologies combines pragmatic architecture with milestone-based delivery to help organizations build maintainable, scalable digital products.'")
    ]:
        try:
            cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {col_def};")
        except Exception as e:
            logger.debug("Column check %s.%s: %s", tbl, col, e)

    # Seed default video section row
    now_init = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
    INSERT INTO homepage_video_section (id, video_enabled, video_url, image_url, image_alt, updated_at)
    VALUES (1, 1, 'https://www.youtube.com/watch?v=vZE0j_WCRvI', 'assets/images/video/01.webp', 'Engineering Process', %s)
    ON CONFLICT (id) DO NOTHING;
    """, (now_init,))

    conn.commit()
    logger.info("Supabase PostgreSQL database schema initialized successfully.")


def init_db():
    """Initializes the database schema in Supabase PostgreSQL."""
    conn = get_postgres_connection()
    try:
        init_postgres_db(conn)
    finally:
        conn.close()


if __name__ == '__main__':
    init_db()
