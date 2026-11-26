"""
Codozent CMS Authentication & Security Layer
PBKDF2-HMAC-SHA256 password hashing, PyJWT tokens with session revocation,
brute-force lockout protection, and role-based access control.
"""
import os
import hashlib
import secrets
import jwt
import logging
from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException, status, Depends
from cms.db import get_db_connection

logger = logging.getLogger("CodozentCMS.auth")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load secret key from environment or secure local storage
SECRET_KEY_PATH = os.path.join(ROOT_DIR, "data", ".secret_key")

def get_secret_key() -> str:
    key = os.environ.get("CMS_SECRET_KEY")
    if key and len(key.strip()) >= 32:
        return key.strip()

    if os.path.exists(SECRET_KEY_PATH):
        try:
            with open(SECRET_KEY_PATH, "r", encoding="utf-8") as f:
                stored = f.read().strip()
                if len(stored) >= 32:
                    return stored
        except Exception:
            pass

    # Generate cryptographically secure 64-char hex key
    new_key = secrets.token_hex(32)
    os.makedirs(os.path.dirname(SECRET_KEY_PATH), exist_ok=True)
    try:
        with open(SECRET_KEY_PATH, "w", encoding="utf-8") as f:
            f.write(new_key)
    except Exception as e:
        logger.warning("Could not persist secret key to disk: %s", e)
    return new_key

SECRET_KEY = get_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12 # 12 hours
MAX_FAILED_ATTEMPTS = 3
LOCKOUT_DURATION_MINUTES = 15

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        600000
    )
    return hashed.hex(), salt

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    hashed, _ = hash_password(password, salt)
    return secrets.compare_digest(hashed, password_hash)

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"}
        )

def seed_owner_admin():
    """
    Bootstraps the site owner admin using verified contact identity in the project
    (codozent.help@gmail.com) and environment variable or secure setup file.
    Does NOT use a hardcoded default password.
    """
    owner_email = os.environ.get("ADMIN_EMAIL", "codozent.help@gmail.com").strip().lower()
    initial_pass = os.environ.get("ADMIN_INITIAL_PASSWORD")

    credentials_file = os.path.join(ROOT_DIR, "data", "admin_bootstrap_credentials.txt")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if owner admin already exists
    cursor.execute("SELECT id, email FROM users WHERE role = 'admin'")
    admin_user = cursor.fetchone()

    if not admin_user:
        if not initial_pass:
            # Generate a secure one-time bootstrap password
            initial_pass = f"Cdz_{secrets.token_urlsafe(12)}!9"
            try:
                os.makedirs(os.path.dirname(credentials_file), exist_ok=True)
                with open(credentials_file, "w", encoding="utf-8") as f:
                    f.write(f"CODOZENT CMS OWNER ADMIN BOOTSTRAP CREDENTIALS\n")
                    f.write(f"Generated at: {datetime.now(timezone.utc).isoformat()}\n")
                    f.write(f"Email: {owner_email}\n")
                    f.write(f"Temporary Password: {initial_pass}\n\n")
                    f.write(f"SECURITY NOTICE: Change this password immediately upon first login.\n")
                logger.info("Owner admin credentials securely written to data/admin_bootstrap_credentials.txt")
            except Exception as e:
                logger.error("Could not write credentials file: %s", e)

        pass_hash, salt = hash_password(initial_pass)
        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO users (email, password_hash, salt, full_name, role, status, session_version, created_at)
            VALUES (?, ?, ?, ?, 'admin', 'active', 1, ?)
            """,
            (owner_email, pass_hash, salt, "Codozent Administrator", now_str)
        )
        conn.commit()
        logger.info("Owner administrator seeded: %s", owner_email)
    else:
        # If no credentials file exists yet and no env pass was set, generate one-time bootstrap credentials
        if not os.path.exists(credentials_file) and not initial_pass:
            initial_pass = f"Cdz_{secrets.token_urlsafe(12)}!9"
            pass_hash, salt = hash_password(initial_pass)
            cursor.execute("UPDATE users SET email = ?, password_hash = ?, salt = ?, status = 'active', session_version = session_version + 1 WHERE id = ?", (owner_email, pass_hash, salt, admin_user["id"]))
            conn.commit()
            try:
                os.makedirs(os.path.dirname(credentials_file), exist_ok=True)
                with open(credentials_file, "w", encoding="utf-8") as f:
                    f.write(f"CODOZENT CMS OWNER ADMIN BOOTSTRAP CREDENTIALS\n")
                    f.write(f"Generated at: {datetime.now(timezone.utc).isoformat()}\n")
                    f.write(f"Email: {owner_email}\n")
                    f.write(f"Temporary Password: {initial_pass}\n\n")
                    f.write(f"SECURITY NOTICE: Change this password immediately upon first login.\n")
                logger.info("Owner admin credentials securely written to data/admin_bootstrap_credentials.txt")
            except Exception as e:
                logger.error("Could not write credentials file: %s", e)
        elif initial_pass:
            pass_hash, salt = hash_password(initial_pass)
            cursor.execute("UPDATE users SET email = ?, password_hash = ?, salt = ?, status = 'active', session_version = session_version + 1 WHERE id = ?", (owner_email, pass_hash, salt, admin_user["id"]))
            conn.commit()
        else:
            cursor.execute("SELECT id FROM users WHERE email = ?", (owner_email,))
            if not cursor.fetchone():
                cursor.execute("UPDATE users SET email = ? WHERE id = ?", (owner_email, admin_user["id"]))
                conn.commit()
                logger.info("Admin email updated to verified owner identity: %s", owner_email)

    conn.close()

# Alias for backwards compatibility
seed_default_admin = seed_owner_admin

def authenticate_user(email: str, password: str) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    user = cursor.fetchone()

    now = datetime.now(timezone.utc)

    # Use constant-time dummy verification if user does not exist to prevent timing attacks
    if not user:
        conn.close()
        dummy_hash, dummy_salt = hash_password("dummy_password_timing_safety")
        verify_password(password, dummy_hash, dummy_salt)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    # Check account active status
    if user['status'] != 'active':
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is currently disabled. Please contact the administrator."
        )

    # Check brute-force lockout
    locked_until_str = user['locked_until']
    if locked_until_str:
        try:
            locked_until = datetime.fromisoformat(locked_until_str)
            if now < locked_until:
                remaining = int((locked_until - now).total_seconds() / 60) + 1
                conn.close()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Account locked due to multiple failed login attempts. Please wait {remaining} minute(s)."
                )
        except ValueError:
            pass

    # Verify password
    if not verify_password(password, user['password_hash'], user['salt']):
        failed_count = (user['failed_attempts'] or 0) + 1
        locked_until_val = None
        if failed_count >= MAX_FAILED_ATTEMPTS:
            locked_until_val = (now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)).isoformat()
            logger.warning("Account %s locked out until %s", email, locked_until_val)

        cursor.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
            (failed_count, locked_until_val, user['id'])
        )
        conn.commit()
        conn.close()

        if locked_until_val:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account locked for {LOCKOUT_DURATION_MINUTES} minutes due to {MAX_FAILED_ATTEMPTS} consecutive failed attempts."
            )
        else:
            attempts_left = MAX_FAILED_ATTEMPTS - failed_count
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid email or password. {attempts_left} attempt(s) remaining before temporary lockout."
            )

    # Success: reset failed attempts & update last_login
    cursor.execute(
        "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login = ? WHERE id = ?",
        (now.isoformat(), user['id'])
    )
    conn.commit()
    user_dict = dict(user)
    conn.close()
    return user_dict

def get_current_user_optional(request: Request) -> dict | None:
    """Returns the authenticated user dict or None if unauthenticated/invalid."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get("admin_session") or request.cookies.get("admin_token")
    if not token:
        token = request.query_params.get("token")

    if not token:
        return None

    try:
        payload = decode_access_token(token)
    except Exception:
        return None

    email = payload.get("sub")
    session_version = payload.get("sv", 1)
    if not email:
        return None

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, full_name, role, status, session_version, last_login FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()

    if not user or user["status"] != "active":
        return None

    # Check session revocation
    if user["session_version"] != session_version:
        return None

    return dict(user)

def get_current_user(request: Request) -> dict:
    """Enforces authentication: raises 401 if not signed in."""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in."
        )
    return user

def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Enforces administrator role: raises 403 / 404 if not admin."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found."
        )
    return user

def require_content_manager(user: dict = Depends(get_current_user)) -> dict:
    """Allows admin or editor role for editing content."""
    if user.get("role") not in ["admin", "editor"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: content editing role required."
        )
    return user
