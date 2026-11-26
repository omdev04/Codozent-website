"""
Codozent CMS REST API Router
Handles Authentication, User Management, Pages, Homepage Images, Blog Posts, Careers, and Media Library.
Strict server-side role-based access control and atomic synchronization across public templates.
"""
import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, field_validator
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response, Request
from cms.db import get_db_connection
from cms.auth import (
    get_current_user,
    require_admin,
    require_content_manager,
    authenticate_user,
    create_access_token,
    hash_password,
    verify_password
)
from cms.sync import (
    publish_page_text,
    publish_homepage_images,
    sync_homepage_video_section,
    regenerate_career_page,
    regenerate_blog_page,
    regenerate_work_section,
    ROOT_DIR
)
from cms.cloudinary_storage import (
    upload_image,
    delete_image,
    generate_signed_upload_params,
    is_cloudinary_configured,
    get_optimized_delivery_url
)

logger = logging.getLogger("CodozentCMS.api")
router = APIRouter(prefix="/api")

UPLOAD_DIR = os.path.join(ROOT_DIR, "assets", "images", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp", "image/svg+xml", "image/gif"]
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 # 10MB

# ----------------- PYDANTIC SCHEMAS -----------------

class LoginRequest(BaseModel):
    email: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class UserCreate(BaseModel):
    email: str
    full_name: str
    password: str
    role: str = "editor" # 'admin', 'editor', 'viewer'

    @field_validator('role')
    def validate_role(cls, v):
        if v not in ['admin', 'editor', 'viewer']:
            raise ValueError("Role must be 'admin', 'editor', or 'viewer'.")
        return v

    @field_validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v

class UserUpdate(BaseModel):
    full_name: str
    role: str
    status: str = "active" # 'active', 'disabled'

    @field_validator('role')
    def validate_role(cls, v):
        if v not in ['admin', 'editor', 'viewer']:
            raise ValueError("Role must be 'admin', 'editor', or 'viewer'.")
        return v

    @field_validator('status')
    def validate_status(cls, v):
        if v not in ['active', 'disabled']:
            raise ValueError("Status must be 'active' or 'disabled'.")
        return v

class UserResetPassword(BaseModel):
    new_password: str

    @field_validator('new_password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v

class PageUpdateRequest(BaseModel):
    fields: dict
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None

class HomepageImageUpdateRequest(BaseModel):
    draft_src: str
    draft_alt: str

class VideoSectionUpdateRequest(BaseModel):
    video_enabled: bool
    video_url: Optional[str] = "https://www.youtube.com/watch?v=vZE0j_WCRvI"
    image_url: Optional[str] = "assets/images/video/01.webp"
    image_alt: Optional[str] = "Engineering Process"

    @field_validator('video_url')
    @classmethod
    def validate_url(cls, v: Optional[str]) -> str:
        clean = (v or "").strip()
        if not clean:
            return "https://www.youtube.com/watch?v=vZE0j_WCRvI"
        return clean

class BlogPostCreate(BaseModel):
    title: str
    slug: str
    excerpt: str
    body: str
    author: str
    author_role: Optional[str] = "Engineering Team"
    category: str
    tags: Optional[str] = ""
    featured_image: str
    featured_image_alt: str
    published_date: Optional[str] = None
    status: Optional[str] = "draft"

    @field_validator('slug')
    def validate_slug(cls, v):
        v = v.strip().lower()
        if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens.")
        return v

class BlogPostUpdate(BaseModel):
    title: str
    slug: str
    excerpt: str
    body: str
    author: str
    author_role: Optional[str] = "Engineering Team"
    category: str
    tags: Optional[str] = ""
    featured_image: str
    featured_image_alt: str
    published_date: Optional[str] = None
    status: Optional[str] = "draft"

    @field_validator('slug')
    def validate_slug(cls, v):
        v = v.strip().lower()
        if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens.")
        return v

class MediaAddUrlRequest(BaseModel):
    url: str
    alt_text: Optional[str] = ""
    category: Optional[str] = "general"
    folder: Optional[str] = "codozent"

class JobCreate(BaseModel):
    title: str
    department: str
    location: str
    employment_type: str
    description: str
    responsibilities: Optional[str] = ""
    qualifications: Optional[str] = ""
    deadline: Optional[str] = ""
    apply_label: Optional[str] = "Apply for Role"
    apply_url: str
    status: Optional[str] = "draft"

    @field_validator('apply_url')
    def validate_apply_url(cls, v):
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("mailto:")):
            raise ValueError("Apply Link must start with https://, http://, or mailto:")
        return v

class JobUpdate(BaseModel):
    title: str
    department: str
    location: str
    employment_type: str
    description: str
    responsibilities: Optional[str] = ""
    qualifications: Optional[str] = ""
    deadline: Optional[str] = ""
    apply_label: Optional[str] = "Apply for Role"
    apply_url: str
    status: Optional[str] = "draft"

    @field_validator('apply_url')
    def validate_apply_url(cls, v):
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("mailto:")):
            raise ValueError("Apply Link must start with https://, http://, or mailto:")
        return v

class WorkItemCreate(BaseModel):
    title: str
    category: str
    description: Optional[str] = ""
    image_url: str
    image_alt: str
    project_url: Optional[str] = "case-studies.html"
    display_order: Optional[int] = 0
    status: Optional[str] = "published"
    storage_provider: Optional[str] = "local"
    cloudinary_public_id: Optional[str] = None

class WorkItemUpdate(BaseModel):
    title: str
    category: str
    description: Optional[str] = ""
    image_url: str
    image_alt: str
    project_url: Optional[str] = "case-studies.html"
    display_order: Optional[int] = 0
    status: Optional[str] = "published"
    storage_provider: Optional[str] = "local"
    cloudinary_public_id: Optional[str] = None

def log_audit(user_email: str, action: str, details: str = ""):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO audit_log (user_email, action, details, timestamp) VALUES (?, ?, ?, ?)",
        (user_email, action, details, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()

# ----------------- AUTH ROUTES -----------------

@router.post("/auth/login")
def login(req: LoginRequest, response: Response):
    user = authenticate_user(req.email, req.password)
    token = create_access_token({
        "sub": user["email"],
        "name": user["full_name"],
        "role": user["role"],
        "sv": user.get("session_version", 1)
    })
    
    # Set HttpOnly, SameSite cookie
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
        secure=False
    )
    # Also set legacy cookie for compatibility
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
        secure=False
    )
    log_audit(user["email"], "LOGIN_SUCCESS", "User authenticated into system.")
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"]
        }
    }

@router.post("/auth/logout")
def logout(response: Response, current_user: dict = Depends(get_current_user)):
    # Invalidate session on server by incrementing session_version
    conn = get_db_connection()
    conn.execute("UPDATE users SET session_version = session_version + 1 WHERE id = ?", (current_user["id"],))
    conn.commit()
    conn.close()

    response.delete_cookie("admin_session")
    response.delete_cookie("admin_token")
    log_audit(current_user["email"], "LOGOUT", "Session revoked and user logged out.")
    return {"success": True, "message": "Logged out successfully."}

@router.get("/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "success": True,
        "user": current_user
    }

@router.post("/auth/change-password")
def change_password(req: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long.")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, salt FROM users WHERE id = ?", (current_user["id"],))
    row = cursor.fetchone()

    if not verify_password(req.current_password, row["password_hash"], row["salt"]):
        conn.close()
        raise HTTPException(status_code=400, detail="Current password incorrect.")

    new_hash, new_salt = hash_password(req.new_password)
    # Increment session_version to revoke any stale sessions elsewhere
    cursor.execute(
        "UPDATE users SET password_hash = ?, salt = ?, session_version = session_version + 1 WHERE id = ?",
        (new_hash, new_salt, current_user["id"])
    )
    conn.commit()
    conn.close()

    log_audit(current_user["email"], "PASSWORD_CHANGED")
    return {"success": True, "message": "Password changed successfully."}

# ----------------- USERS MANAGEMENT (ADMIN ONLY) -----------------

@router.get("/admin/users")
def list_users(current_admin: dict = Depends(require_admin)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, full_name, role, status, created_at, last_login FROM users ORDER BY id ASC")
    users = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "users": users}

@router.post("/admin/users")
def create_user(req: UserCreate, current_admin: dict = Depends(require_admin)):
    email_clean = req.email.strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE email = ?", (email_clean,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"User with email '{email_clean}' already exists.")

    pass_hash, salt = hash_password(req.password)
    now_str = datetime.now(timezone.utc).isoformat()

    cursor.execute(
        """
        INSERT INTO users (email, password_hash, salt, full_name, role, status, session_version, created_at)
        VALUES (?, ?, ?, ?, ?, 'active', 1, ?)
        """,
        (email_clean, pass_hash, salt, req.full_name.strip(), req.role, now_str)
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit(current_admin["email"], "USER_CREATED", f"Created user: {email_clean} (Role: {req.role})")
    return {"success": True, "user_id": new_id, "message": f"User '{email_clean}' created successfully."}

@router.put("/admin/users/{user_id}")
def update_user(user_id: int, req: UserUpdate, current_admin: dict = Depends(require_admin)):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found.")

    # Privilege escalation / Lockout prevention:
    # If the user being modified is an admin and the last active admin, do not allow demotion or disabling
    if target["role"] == "admin" and (req.role != "admin" or req.status != "active"):
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND status = 'active' AND id != ?", (user_id,))
        other_admins = cursor.fetchone()[0]
        if other_admins == 0:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail="Cannot demote or disable this account: It is the only active administrator on the system."
            )

    # If status is changed to disabled, increment session_version to immediately revoke access
    session_version_incr = 1 if req.status == "disabled" else 0

    cursor.execute(
        """
        UPDATE users
        SET full_name = ?, role = ?, status = ?, session_version = session_version + ?
        WHERE id = ?
        """,
        (req.full_name.strip(), req.role, req.status, session_version_incr, user_id)
    )
    conn.commit()
    conn.close()

    log_audit(current_admin["email"], "USER_UPDATED", f"Updated user ID {user_id} ({target['email']}) -> Role: {req.role}, Status: {req.status}")
    return {"success": True, "message": "User updated successfully."}

@router.post("/admin/users/{user_id}/reset-password")
def reset_user_password(user_id: int, req: UserResetPassword, current_admin: dict = Depends(require_admin)):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found.")

    new_hash, new_salt = hash_password(req.new_password)
    # Revoke sessions
    cursor.execute(
        "UPDATE users SET password_hash = ?, salt = ?, session_version = session_version + 1 WHERE id = ?",
        (new_hash, new_salt, user_id)
    )
    conn.commit()
    conn.close()

    log_audit(current_admin["email"], "USER_PASSWORD_RESET", f"Reset password for user ID {user_id} ({target['email']})")
    return {"success": True, "message": f"Password reset successfully for {target['email']}."}

@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current_admin: dict = Depends(require_admin)):
    if user_id == current_admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own administrative account.")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT email, role FROM users WHERE id = ?", (user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found.")

    if target["role"] == "admin":
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND id != ?", (user_id,))
        if cursor.fetchone()[0] == 0:
            conn.close()
            raise HTTPException(status_code=400, detail="Cannot delete the sole administrator account.")

    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    log_audit(current_admin["email"], "USER_DELETED", f"Deleted user ID {user_id} ({target['email']})")
    return {"success": True, "message": f"User '{target['email']}' deleted successfully."}

# ----------------- DASHBOARD STATS -----------------

@router.get("/admin/stats")
def get_stats(current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM pages")
    pages_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM homepage_images")
    images_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM blog_posts WHERE status = 'published'")
    published_blogs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM blog_posts WHERE status = 'draft'")
    draft_blogs = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'published'")
    published_jobs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'draft'")
    draft_jobs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'closed'")
    closed_jobs = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM work_items WHERE status = 'published'")
    published_work = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM work_items")
    total_work = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM media_assets")
    media_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
    users_count = c.fetchone()[0]

    conn.close()

    return {
        "success": True,
        "stats": {
            "pages": pages_count,
            "images": images_count,
            "published_blogs": published_blogs,
            "draft_blogs": draft_blogs,
            "published_jobs": published_jobs,
            "draft_jobs": draft_jobs,
            "closed_jobs": closed_jobs,
            "published_work": published_work,
            "total_work": total_work,
            "media_assets": media_count,
            "users": users_count,
            "cloudinary_configured": is_cloudinary_configured()
        }
    }

# ----------------- PAGES MANAGEMENT -----------------

@router.get("/admin/pages")
def list_pages(current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT page_key, title, file_name, has_draft, updated_at, published_at FROM pages ORDER BY page_key")
    pages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"success": True, "pages": pages}

@router.get("/admin/pages/{page_key}")
def get_page(page_key: str, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE page_key = ?", (page_key,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Page not found.")

    data = dict(row)
    data["fields"] = json.loads(data["fields_json"])
    del data["fields_json"]
    return {"success": True, "page": data}

@router.put("/admin/pages/{page_key}")
def update_page_draft(page_key: str, req: PageUpdateRequest, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE page_key = ?", (page_key,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Page not found.")

    existing_fields = json.loads(row["fields_json"])
    has_changes = False
    for k, new_val in req.fields.items():
        if k in existing_fields:
            if existing_fields[k].get("draft_value") != new_val:
                existing_fields[k]["draft_value"] = new_val
                has_changes = True

    now_str = datetime.now(timezone.utc).isoformat()
    meta_title = req.meta_title if req.meta_title is not None else row["meta_title"]
    meta_desc = req.meta_description if req.meta_description is not None else row["meta_description"]

    cursor.execute(
        """
        UPDATE pages
        SET fields_json = ?, meta_title = ?, meta_description = ?, has_draft = 1, updated_at = ?
        WHERE page_key = ?
        """,
        (json.dumps(existing_fields), meta_title, meta_desc, now_str, page_key)
    )
    conn.commit()
    conn.close()

    log_audit(current_user["email"], "PAGE_DRAFT_SAVED", f"Draft saved for page: {page_key}")
    return {"success": True, "message": "Draft saved successfully."}

@router.post("/admin/pages/{page_key}/publish")
def publish_page(page_key: str, current_user: dict = Depends(require_content_manager)):
    success, msg = publish_page_text(page_key)
    if not success:
        raise HTTPException(status_code=500, detail=msg)
    log_audit(current_user["email"], "PAGE_PUBLISHED", f"Published page: {page_key}")
    return {"success": True, "message": f"Page '{page_key}' published live successfully."}

@router.post("/admin/pages/{page_key}/discard-draft")
def discard_page_draft(page_key: str, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE page_key = ?", (page_key,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Page not found.")

    fields = json.loads(row["fields_json"])
    for k, v in fields.items():
        v["draft_value"] = v["current_value"]

    cursor.execute(
        "UPDATE pages SET fields_json = ?, has_draft = 0 WHERE page_key = ?",
        (json.dumps(fields), page_key)
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "Draft discarded. Reverted to published content."}

# ----------------- HOMEPAGE IMAGES -----------------

@router.get("/admin/homepage-images")
def list_homepage_images(current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM homepage_images ORDER BY slot_key")
    slots = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "images": slots}

@router.put("/admin/homepage-images/{slot_key}")
@router.post("/admin/homepage-images/{slot_key}")
def update_homepage_image_draft(slot_key: str, req: HomepageImageUpdateRequest, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM homepage_images WHERE slot_key = ?", (slot_key,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Image slot not found.")

    clean_src = req.draft_src.strip()
    if clean_src.startswith("res.cloudinary.com"):
        clean_src = f"https://{clean_src}"

    clean_alt = req.draft_alt.strip()
    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """
        UPDATE homepage_images
        SET draft_src = ?, draft_alt = ?, has_draft = 1, updated_at = ?
        WHERE slot_key = ?
        """,
        (clean_src, clean_alt, now_str, slot_key)
    )

    if slot_key == "video_thumbnail":
        cursor.execute(
            "UPDATE homepage_video_section SET image_url = ?, image_alt = ?, updated_at = ? WHERE id = 1",
            (clean_src, clean_alt, now_str)
        )

    conn.commit()
    conn.close()
    return {"success": True, "message": "Image draft saved with Cloudinary / Asset URL."}

@router.post("/admin/homepage-images/publish")
def publish_all_homepage_images(current_user: dict = Depends(require_content_manager)):
    publish_homepage_images()
    log_audit(current_user["email"], "HOMEPAGE_IMAGES_PUBLISHED", "Published draft homepage images to live website.")
    return {"success": True, "message": "Homepage images published live successfully."}

# ----------------- HOMEPAGE VIDEO SECTION -----------------

@router.get("/admin/video-section")
@router.get("/admin/video-section/")
def get_video_section_settings(current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM homepage_video_section WHERE id = 1")
    row = cursor.fetchone()
    if not row:
        now_init = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
        INSERT OR IGNORE INTO homepage_video_section (id, video_enabled, video_url, image_url, image_alt, updated_at)
        VALUES (1, 1, 'https://www.youtube.com/watch?v=vZE0j_WCRvI', 'assets/images/video/01.webp', 'Engineering Process', ?)
        """, (now_init,))
        conn.commit()
        cursor.execute("SELECT * FROM homepage_video_section WHERE id = 1")
        row = cursor.fetchone()
    data = dict(row)
    data["video_enabled"] = bool(data["video_enabled"])
    conn.close()
    return {"success": True, "video_section": data}

@router.post("/admin/video-section")
@router.put("/admin/video-section")
@router.post("/admin/video-section/")
@router.put("/admin/video-section/")
def update_video_section_settings(req: VideoSectionUpdateRequest, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    clean_img = (req.image_url or "assets/images/video/01.webp").strip()
    if clean_img.startswith("res.cloudinary.com"):
        clean_img = f"https://{clean_img}"

    clean_vid = req.video_url.strip()
    enabled_int = 1 if req.video_enabled else 0
    clean_alt = (req.image_alt or "Engineering Process").strip()

    cursor.execute("""
    UPDATE homepage_video_section
    SET video_enabled = ?, video_url = ?, image_url = ?, image_alt = ?, updated_at = ?
    WHERE id = 1
    """, (enabled_int, clean_vid, clean_img, clean_alt, now_str))

    # Also keep homepage_images 'video_thumbnail' slot in exact sync
    cursor.execute("""
    UPDATE homepage_images
    SET current_src = ?, draft_src = ?, current_alt = ?, draft_alt = ?, has_draft = 0, updated_at = ?
    WHERE slot_key = 'video_thumbnail'
    """, (clean_img, clean_img, clean_alt, clean_alt, now_str))

    conn.commit()
    conn.close()

    # Sync live to index.html
    sync_homepage_video_section(
        video_enabled=req.video_enabled,
        video_url=clean_vid,
        image_url=clean_img,
        image_alt=clean_alt
    )

    status_label = "ENABLED (YouTube Video & Play Icon Active)" if req.video_enabled else "DISABLED (Static Image Only Mode)"
    log_audit(current_user["email"], "VIDEO_SECTION_UPDATED", f"Updated Homepage Video Section: {status_label}")
    return {
        "success": True,
        "message": f"Homepage video section updated successfully ({status_label}).",
        "video_section": {
            "video_enabled": req.video_enabled,
            "video_url": clean_vid,
            "image_url": clean_img,
            "image_alt": clean_alt,
            "updated_at": now_str
        }
    }

@router.get("/public/video-section")
@router.get("/public/video-section/")
def get_public_video_section():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT video_enabled, video_url, image_url, image_alt FROM homepage_video_section WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {
            "success": True,
            "video_enabled": True,
            "video_url": "https://www.youtube.com/watch?v=vZE0j_WCRvI",
            "image_url": "assets/images/video/01.webp",
            "image_alt": "Engineering Process"
        }
    data = dict(row)
    data["video_enabled"] = bool(data["video_enabled"])
    return {"success": True, **data}

# ----------------- HOMEPAGE WORK / PORTFOLIO ITEMS -----------------

@router.get("/admin/work")
def list_work_items(status: Optional[str] = None, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    if status and status != 'all':
        cursor.execute("SELECT * FROM work_items WHERE status = ? ORDER BY display_order ASC, id ASC", (status,))
    else:
        cursor.execute("SELECT * FROM work_items ORDER BY display_order ASC, id ASC")
    items = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "items": items}

@router.get("/admin/work/{item_id}")
def get_work_item(item_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM work_items WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Work item not found.")
    return {"success": True, "item": dict(row)}

@router.post("/admin/work")
def create_work_item(req: WorkItemCreate, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    clean_url = req.image_url.strip()
    if clean_url.startswith("res.cloudinary.com"):
        clean_url = f"https://{clean_url}"
    provider = "cloudinary" if "cloudinary" in clean_url.lower() else (req.storage_provider or "local")

    cursor.execute(
        """
        INSERT INTO work_items (title, category, description, image_url, image_alt, project_url, display_order, status, storage_provider, cloudinary_public_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            req.title.strip(),
            req.category.strip(),
            req.description.strip() if req.description else "",
            clean_url,
            req.image_alt.strip(),
            req.project_url.strip() if req.project_url else "case-studies.html",
            req.display_order or 0,
            req.status or "published",
            provider,
            req.cloudinary_public_id,
            now_str,
            now_str
        )
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Atomically synchronize public templates (index.html and case-studies.html)
    regenerate_work_section()
    log_audit(current_user["email"], "WORK_ITEM_CREATED", f"Created work item ID {new_id}: {req.title}")
    return {"success": True, "item_id": new_id, "message": "Work item created successfully."}

@router.put("/admin/work/{item_id}")
def update_work_item(item_id: int, req: WorkItemUpdate, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM work_items WHERE id = ?", (item_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Work item not found.")

    now_str = datetime.now(timezone.utc).isoformat()
    clean_url = req.image_url.strip()
    if clean_url.startswith("res.cloudinary.com"):
        clean_url = f"https://{clean_url}"
    provider = "cloudinary" if "cloudinary" in clean_url.lower() else (req.storage_provider or "local")

    cursor.execute(
        """
        UPDATE work_items
        SET title = ?, category = ?, description = ?, image_url = ?, image_alt = ?, project_url = ?, display_order = ?, status = ?, storage_provider = ?, cloudinary_public_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            req.title.strip(),
            req.category.strip(),
            req.description.strip() if req.description else "",
            clean_url,
            req.image_alt.strip(),
            req.project_url.strip() if req.project_url else "case-studies.html",
            req.display_order or 0,
            req.status or "published",
            provider,
            req.cloudinary_public_id,
            now_str,
            item_id
        )
    )
    conn.commit()
    conn.close()

    regenerate_work_section()
    log_audit(current_user["email"], "WORK_ITEM_UPDATED", f"Updated work item ID {item_id}: {req.title}")
    return {"success": True, "message": "Work item updated successfully."}

@router.post("/admin/work/{item_id}/publish")
def publish_work_item(item_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE work_items SET status = 'published', updated_at = ? WHERE id = ?", (now_str, item_id))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Work item not found.")
    conn.commit()
    conn.close()

    regenerate_work_section()
    log_audit(current_user["email"], "WORK_ITEM_PUBLISHED", f"Published work item ID {item_id}")
    return {"success": True, "message": "Work item published live."}

@router.post("/admin/work/{item_id}/unpublish")
def unpublish_work_item(item_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE work_items SET status = 'draft', updated_at = ? WHERE id = ?", (now_str, item_id))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Work item not found.")
    conn.commit()
    conn.close()

    regenerate_work_section()
    log_audit(current_user["email"], "WORK_ITEM_UNPUBLISHED", f"Unpublished work item ID {item_id}")
    return {"success": True, "message": "Work item moved to draft."}

@router.delete("/admin/work/{item_id}")
def delete_work_item(item_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM work_items WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Work item not found.")

    cursor.execute("DELETE FROM work_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

    regenerate_work_section()
    log_audit(current_user["email"], "WORK_ITEM_DELETED", f"Deleted work item ID {item_id} ({row['title']})")
    return {"success": True, "message": f"Work item '{row['title']}' deleted successfully."}

# ----------------- CAREERS & JOBS (HIGHEST PRIORITY) -----------------

@router.get("/admin/jobs")
def list_jobs(status: Optional[str] = None, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    if status and status != "all":
        cursor.execute("SELECT * FROM jobs WHERE status = ? ORDER BY id DESC", (status,))
    else:
        cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
    jobs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "jobs": jobs}

@router.get("/admin/jobs/{job_id}")
def get_job(job_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job opening not found.")
    return {"success": True, "job": dict(row)}

@router.post("/admin/jobs")
def create_job(req: JobCreate, current_user: dict = Depends(require_content_manager)):
    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO jobs (title, department, location, employment_type, description, responsibilities, qualifications, deadline, apply_label, apply_url, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            req.title.strip(),
            req.department.strip(),
            req.location.strip(),
            req.employment_type.strip(),
            req.description.strip(),
            req.responsibilities.strip(),
            req.qualifications.strip(),
            req.deadline.strip() if req.deadline else None,
            req.apply_label.strip() or "Apply for Role",
            req.apply_url.strip(),
            req.status or "draft",
            now_str,
            now_str
        )
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    if req.status == "published":
        regenerate_career_page()

    log_audit(current_user["email"], "JOB_CREATED", f"Created job: {req.title} (ID: {new_id}, Status: {req.status})")
    return {"success": True, "job_id": new_id, "message": "Job opening created successfully."}

@router.put("/admin/jobs/{job_id}")
def update_job(job_id: int, req: JobUpdate, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job opening not found.")

    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """
        UPDATE jobs
        SET title = ?, department = ?, location = ?, employment_type = ?, description = ?,
            responsibilities = ?, qualifications = ?, deadline = ?, apply_label = ?, apply_url = ?,
            status = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            req.title.strip(),
            req.department.strip(),
            req.location.strip(),
            req.employment_type.strip(),
            req.description.strip(),
            req.responsibilities.strip(),
            req.qualifications.strip(),
            req.deadline.strip() if req.deadline else None,
            req.apply_label.strip() or "Apply for Role",
            req.apply_url.strip(),
            req.status or "draft",
            now_str,
            job_id
        )
    )
    conn.commit()
    conn.close()

    regenerate_career_page()
    log_audit(current_user["email"], "JOB_UPDATED", f"Updated job: {req.title} (ID: {job_id})")
    return {"success": True, "message": "Job opening updated and public page refreshed."}

@router.post("/admin/jobs/{job_id}/publish")
def publish_job(job_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job opening not found.")

    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE jobs SET status = 'published', updated_at = ? WHERE id = ?", (now_str, job_id))
    conn.commit()
    conn.close()

    regenerate_career_page()
    log_audit(current_user["email"], "JOB_PUBLISHED", f"Published job: {row['title']} (ID: {job_id})")
    return {"success": True, "message": f"Job '{row['title']}' is now live on the public Careers page."}

@router.post("/admin/jobs/{job_id}/unpublish")
def unpublish_job(job_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job opening not found.")

    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE jobs SET status = 'draft', updated_at = ? WHERE id = ?", (now_str, job_id))
    conn.commit()
    conn.close()

    regenerate_career_page()
    log_audit(current_user["email"], "JOB_UNPUBLISHED", f"Unpublished job: {row['title']} (ID: {job_id})")
    return {"success": True, "message": f"Job '{row['title']}' converted to draft and removed from public page."}

@router.post("/admin/jobs/{job_id}/close")
def close_job(job_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job opening not found.")

    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE jobs SET status = 'closed', updated_at = ? WHERE id = ?", (now_str, job_id))
    conn.commit()
    conn.close()

    regenerate_career_page()
    log_audit(current_user["email"], "JOB_CLOSED", f"Closed job: {row['title']} (ID: {job_id})")
    return {"success": True, "message": f"Job '{row['title']}' marked as closed and removed from public page."}

@router.delete("/admin/jobs/{job_id}")
def delete_job(job_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job opening not found.")

    cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

    regenerate_career_page()
    log_audit(current_user["email"], "JOB_DELETED", f"Deleted job: {row['title']} (ID: {job_id})")
    return {"success": True, "message": "Job opening deleted permanently."}

# ----------------- BLOG MANAGEMENT (COMPLETE SYNCHRONIZATION) -----------------

@router.get("/admin/blog")
def list_blog_posts(status: Optional[str] = None, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    if status and status != "all":
        cursor.execute("SELECT * FROM blog_posts WHERE status = ? ORDER BY published_date DESC, id DESC", (status,))
    else:
        cursor.execute("SELECT * FROM blog_posts ORDER BY published_date DESC, id DESC")
    posts = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "posts": posts}

@router.get("/admin/blog/{post_id}")
def get_blog_post(post_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Blog post not found.")
    return {"success": True, "post": dict(row)}

@router.post("/admin/blog")
def create_blog_post(req: BlogPostCreate, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM blog_posts WHERE slug = ?", (req.slug,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"The slug '{req.slug}' is already in use by another article. Please choose a unique slug.")

    now_str = datetime.now(timezone.utc).isoformat()
    pub_date = req.published_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    cursor.execute(
        """
        INSERT INTO blog_posts (title, slug, excerpt, body, author, author_role, category, tags, featured_image, featured_image_alt, published_date, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            req.title.strip(),
            req.slug,
            req.excerpt.strip(),
            req.body.strip(),
            req.author.strip(),
            req.author_role.strip() if req.author_role else "Engineering Team",
            req.category.strip(),
            req.tags.strip() if req.tags else "",
            req.featured_image.strip(),
            req.featured_image_alt.strip(),
            pub_date,
            req.status or "draft",
            now_str,
            now_str
        )
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Regenerate blog listing, homepage Latest Insights, and sitemap
    if req.status == "published":
        regenerate_blog_page()

    log_audit(current_user["email"], "BLOG_CREATED", f"Created blog post: {req.title} (ID: {new_id})")
    return {"success": True, "post_id": new_id, "message": "Blog post created successfully."}

@router.put("/admin/blog/{post_id}")
def update_blog_post(post_id: int, req: BlogPostUpdate, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Blog post not found.")

    cursor.execute("SELECT id FROM blog_posts WHERE slug = ? AND id != ?", (req.slug, post_id))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"The slug '{req.slug}' is already in use by another article.")

    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """
        UPDATE blog_posts
        SET title = ?, slug = ?, excerpt = ?, body = ?, author = ?, author_role = ?, category = ?,
            tags = ?, featured_image = ?, featured_image_alt = ?, published_date = ?, status = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            req.title.strip(),
            req.slug,
            req.excerpt.strip(),
            req.body.strip(),
            req.author.strip(),
            req.author_role.strip() if req.author_role else "Engineering Team",
            req.category.strip(),
            req.tags.strip() if req.tags else "",
            req.featured_image.strip(),
            req.featured_image_alt.strip(),
            req.published_date or row["published_date"],
            req.status or "draft",
            now_str,
            post_id
        )
    )
    conn.commit()
    conn.close()

    # Synchronize all pages (blog.html, index.html, sitemap.xml)
    regenerate_blog_page()
    log_audit(current_user["email"], "BLOG_UPDATED", f"Updated blog post: {req.title} (ID: {post_id})")
    return {"success": True, "message": "Blog post updated and all public pages synchronized."}

@router.post("/admin/blog/{post_id}/publish")
def publish_blog_post(post_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Blog post not found.")

    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE blog_posts SET status = 'published', updated_at = ? WHERE id = ?", (now_str, post_id))
    conn.commit()
    conn.close()

    # Synchronize all pages (blog.html, index.html, sitemap.xml)
    regenerate_blog_page()
    log_audit(current_user["email"], "BLOG_PUBLISHED", f"Published blog post: {row['title']} (ID: {post_id})")
    return {"success": True, "message": f"Article '{row['title']}' published live across all public pages."}

@router.post("/admin/blog/{post_id}/unpublish")
def unpublish_blog_post(post_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Blog post not found.")

    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE blog_posts SET status = 'draft', updated_at = ? WHERE id = ?", (now_str, post_id))
    conn.commit()
    conn.close()

    # Synchronize all pages: removes from blog.html, index.html, and sitemap.xml!
    regenerate_blog_page()
    log_audit(current_user["email"], "BLOG_UNPUBLISHED", f"Unpublished blog post: {row['title']} (ID: {post_id})")
    return {"success": True, "message": f"Article '{row['title']}' moved to draft and removed from public listings."}

@router.delete("/admin/blog/{post_id}")
def delete_blog_post(post_id: int, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE id = ?", (post_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Blog post not found.")

    cursor.execute("DELETE FROM blog_posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()

    # CRITICAL: Synchronize all public pages immediately!
    # Removes the deleted article from blog.html, blog-grid.html, index.html, and sitemap.xml!
    regenerate_blog_page()
    log_audit(current_user["email"], "BLOG_DELETED", f"Deleted blog post: {row['title']} (ID: {post_id})")
    return {"success": True, "message": "Blog post deleted permanently from database and all public pages."}

# ----------------- MEDIA UPLOAD & LIBRARY (CLOUDINARY INTEGRATED) -----------------

@router.get("/admin/media")
def list_media(current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM media_assets ORDER BY id DESC")
    assets = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {
        "success": True,
        "media": assets,
        "cloudinary_configured": is_cloudinary_configured()
    }

@router.get("/admin/media/signature")
def get_media_upload_signature(folder: str = "codozent/general", current_user: dict = Depends(require_content_manager)):
    if not is_cloudinary_configured():
        raise HTTPException(
            status_code=400,
            detail="Cloudinary is not configured. Please supply CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in your environment."
        )
    try:
        signed_params = generate_signed_upload_params(folder)
        return {"success": True, "params": signed_params}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    folder: Optional[str] = Form("codozent/general"),
    alt_text: Optional[str] = Form(""),
    category: Optional[str] = Form("general"),
    current_user: dict = Depends(require_content_manager)
):
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum 10MB limit (File size: {len(contents) / (1024*1024):.2f} MB)."
        )

    try:
        upload_meta = upload_image(
            file_bytes=contents,
            filename=file.filename,
            folder=folder,
            alt_text=alt_text or ""
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error("Media upload error: %s", e)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO media_assets (
            filename, file_path, file_size, mime_type, category,
            storage_provider, cloudinary_asset_id, cloudinary_public_id,
            cloudinary_version, cloudinary_format, width, height,
            secure_url, folder, alt_text, uploaded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            upload_meta["filename"],
            upload_meta["secure_url"],
            upload_meta["bytes"],
            f"image/{upload_meta['format']}",
            category,
            upload_meta["storage_provider"],
            upload_meta.get("asset_id", ""),
            upload_meta.get("public_id", ""),
            upload_meta.get("version", ""),
            upload_meta.get("format", ""),
            upload_meta.get("width", 0),
            upload_meta.get("height", 0),
            upload_meta["secure_url"],
            upload_meta["folder"],
            upload_meta.get("alt_text", ""),
            now_str
        )
    )
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit(current_user["email"], "MEDIA_UPLOADED", f"Uploaded media: {upload_meta['secure_url']} (Provider: {upload_meta['storage_provider']})")
    upload_meta["id"] = asset_id
    return {
        "success": True,
        "asset": upload_meta,
        "message": f"Asset uploaded successfully ({upload_meta['storage_provider'].capitalize()})."
    }

@router.post("/admin/media/add-url")
def add_media_by_url(req: MediaAddUrlRequest, current_user: dict = Depends(require_content_manager)):
    clean_url = req.url.strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="Image URL is required.")
    if clean_url.startswith("res.cloudinary.com"):
        clean_url = f"https://{clean_url}"

    parsed_path = clean_url.split("?")[0].rstrip("/")
    filename = parsed_path.split("/")[-1] or "cloudinary_image"
    if not ("." in filename):
        filename = f"{filename}.webp"

    is_cloudinary = "cloudinary" in clean_url.lower()
    provider = "cloudinary" if is_cloudinary else "external"

    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO media_assets (
            filename, file_path, file_size, mime_type, category,
            storage_provider, secure_url, folder, alt_text, uploaded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            filename,
            clean_url,
            0,
            "image/webp",
            req.category or "general",
            provider,
            clean_url,
            req.folder or "codozent",
            req.alt_text or filename,
            now_str
        )
    )
    asset_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_audit(current_user["email"], "MEDIA_URL_ADDED", f"Added media via URL: {clean_url}")
    return {
        "success": True,
        "message": "Image asset registered successfully in Media Library.",
        "asset": {
            "id": asset_id,
            "filename": filename,
            "file_path": clean_url,
            "secure_url": clean_url,
            "storage_provider": provider,
            "alt_text": req.alt_text or filename
        }
    }

@router.delete("/admin/media/{asset_id}")
def delete_media(asset_id: int, force: bool = False, current_user: dict = Depends(require_content_manager)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM media_assets WHERE id = ?", (asset_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Media asset not found.")

    file_path = row["file_path"]
    secure_url = row["secure_url"] or file_path

    # Check references across CMS content
    references = []
    # 1. Homepage slots
    cursor.execute("SELECT slot_key, label FROM homepage_images WHERE current_src = ? OR draft_src = ? OR current_src = ? OR draft_src = ?", (file_path, file_path, secure_url, secure_url))
    for r in cursor.fetchall():
        references.append(f"Homepage slot: {r['label']}")

    # 2. Blog posts
    cursor.execute("SELECT id, title FROM blog_posts WHERE featured_image = ? OR featured_image = ?", (file_path, secure_url))
    for r in cursor.fetchall():
        references.append(f"Blog post: {r['title']}")

    # 3. Work items
    cursor.execute("SELECT id, title FROM work_items WHERE image_url = ? OR image_url = ?", (file_path, secure_url))
    for r in cursor.fetchall():
        references.append(f"Work item: {r['title']}")

    if references and not force:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete asset: It is currently referenced by: {', '.join(references)}. Please replace the image reference before deleting, or pass force=true."
        )

    # Delete from storage provider
    delete_image(row["cloudinary_public_id"] or "", row["storage_provider"] or "local", local_url=file_path)

    cursor.execute("DELETE FROM media_assets WHERE id = ?", (asset_id,))
    conn.commit()
    conn.close()

    log_audit(current_user["email"], "MEDIA_DELETED", f"Deleted asset ID {asset_id}: {file_path}")
    return {"success": True, "message": "Media asset deleted successfully."}

# ----------------- PUBLIC READ-ONLY ENDPOINTS -----------------

@router.get("/public/work")
def get_public_work():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, category, description, image_url, image_alt, project_url, display_order FROM work_items WHERE status = 'published' ORDER BY display_order ASC, id ASC")
    items = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "work": items}

@router.get("/public/jobs")
def get_public_jobs():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, department, location, employment_type, description, qualifications, deadline, apply_label, apply_url FROM jobs WHERE status = 'published' ORDER BY id DESC")
    jobs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "jobs": jobs}

@router.get("/public/blog")
def get_public_blog():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, slug, excerpt, author, author_role, category, featured_image, featured_image_alt, published_date FROM blog_posts WHERE status = 'published' ORDER BY published_date DESC")
    posts = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "posts": posts}

@router.get("/public/blog/{slug}")
def get_public_blog_by_slug(slug: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE slug = ? AND status = 'published'", (slug,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Article not found or not published.")
    return {"success": True, "post": dict(row)}

@router.get("/public/homepage-images")
@router.get("/public/homepage-images/")
def get_public_homepage_images():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT slot_key, label, section, selector, current_src, current_alt, recommended_dims FROM homepage_images")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"success": True, "images": rows}

@router.get("/public/pages/{page_key}")
@router.get("/public/pages/{page_key}/")
def get_public_page_data(page_key: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT page_key, title, file_name, meta_title, meta_description, fields_json, updated_at FROM pages WHERE page_key = ?", (page_key,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Page not found.")
    data = dict(row)
    try:
        data["fields"] = json.loads(data["fields_json"])
    except Exception:
        data["fields"] = {}
    return {"success": True, "page": data}


