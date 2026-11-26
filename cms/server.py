"""
Codozent CMS Web Server
FastAPI application serving the protected Admin Panel, CMS REST API,
dynamic blog routing, and public static website.
"""
import os
import sys
import logging
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse

# Ensure root directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from cms.db import init_db, get_db_connection, test_db_connection
from cms.auth import seed_owner_admin, get_current_user_optional
from cms.sync import seed_content, regenerate_career_page, regenerate_blog_page, regenerate_work_section, regenerate_sitemap
from cms.admin_routes import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CodozentCMS.server")

app = FastAPI(title="Codozent CMS & Website Server")

# ----------------- CORS CONFIGURATION FOR HYBRID DEPLOYMENT -----------------
# Supports Cloudflare Pages frontend communicating with Render/VPS backend API
cors_env = os.environ.get("CORS_ORIGINS", "")
default_origins = [
    "https://codozent.com",
    "https://www.codozent.com",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
]
allowed_origins = [o.strip() for o in cors_env.split(",") if o.strip()] + default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.pages\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
@app.get("/health")
def health_check():
    """Production health-check endpoint for Render / VPS load balancers & uptime monitors."""
    db_status = test_db_connection()
    is_ok = db_status.get("status") == "ok"
    return {
        "status": "healthy" if is_ok else "degraded",
        "service": "codozent-cms",
        "database": db_status,
        "environment": os.environ.get("ENVIRONMENT", "production"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def render_404_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>404 Not Found | Codozent Technologies</title>
    <link rel="icon" type="image/png" href="/assets/images/fav.png">
    <link rel="stylesheet" href="/assets/css/style.css">
    <style>
        .error-area { padding: 120px 0; text-align: center; }
        .error-title { font-size: 72px; font-weight: 800; color: #081836; line-height: 1; }
        .error-sub { font-size: 20px; color: #64748B; margin-top: 15px; margin-bottom: 30px; }
    </style>
</head>
<body>
    <div class="error-area">
        <div class="container">
            <h1 class="error-title">404</h1>
            <p class="error-sub">Page Not Found. The requested URL does not exist on this server.</p>
            <a href="/" class="rts-btn btn-primary">Return to Homepage</a>
        </div>
    </div>
</body>
</html>"""

# Cache Control Middleware: ensure live updates, prevent serving stale HTML/sitemap/API data
@app.middleware("http")
async def add_security_and_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    content_type = response.headers.get("content-type", "")

    # For HTML responses, API requests, admin panel, and sitemap.xml: never cache
    if "text/html" in content_type or path.startswith("/api/") or path.startswith("/admin") or path.endswith(".xml"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response

# Mount API routes
app.include_router(api_router)

# Mount Admin Static Files
admin_static_dir = os.path.join(BASE_DIR, "cms", "static")
app.mount("/admin/static", StaticFiles(directory=admin_static_dir), name="admin_static")

# Mount Website Static Assets
assets_dir = os.path.join(BASE_DIR, "assets")
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# Startup lifecycle
@app.on_event("startup")
def on_startup():
    logger.info("Initializing Codozent CMS database...")
    init_db()
    seed_owner_admin()
    seed_content()
    # Regenerate public pages to ensure parity
    regenerate_career_page()
    regenerate_blog_page()
    regenerate_work_section()
    regenerate_sitemap()
    logger.info("Codozent CMS Server ready. Public site and Admin Panel active.")

# Admin Panel Route - Protected server-side
@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
@app.post("/admin", response_class=HTMLResponse)
@app.post("/admin/", response_class=HTMLResponse)
def get_admin_dashboard(request: Request):
    user = get_current_user_optional(request)
    # Both signed-out visitors and non-admin signed-in users receive a real 404 page!
    if not user or user.get("role") != "admin":
        return HTMLResponse(content=render_404_html(), status_code=status.HTTP_404_NOT_FOUND)

    admin_html_path = os.path.join(admin_static_dir, "admin.html")
    if os.path.exists(admin_html_path):
        with open(admin_html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content=render_404_html(), status_code=status.HTTP_404_NOT_FOUND)

# Dedicated Admin Login Route
@app.get("/admin/login", response_class=HTMLResponse)
def get_admin_login(request: Request):
    user = get_current_user_optional(request)
    if user and user.get("role") == "admin":
        return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)

    login_html_path = os.path.join(admin_static_dir, "login.html")
    if os.path.exists(login_html_path):
        with open(login_html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="Login page not found.")

# Technical SEO: Robots.txt handler
@app.get("/robots.txt")
def get_robots():
    robots_path = os.path.join(BASE_DIR, "robots.txt")
    if os.path.exists(robots_path):
        return FileResponse(robots_path, media_type="text/plain")
    raise HTTPException(status_code=404, detail="robots.txt not found.")

# Technical SEO: Sitemap XML handler
@app.get("/sitemap.xml")
def get_sitemap():
    sitemap_path = os.path.join(BASE_DIR, "sitemap.xml")
    if os.path.exists(sitemap_path):
        return FileResponse(sitemap_path, media_type="application/xml")
    raise HTTPException(status_code=404, detail="sitemap.xml not found.")

# Dynamic Blog Details Handler
@app.get("/blog-details.html", response_class=HTMLResponse)
def get_blog_details(slug: str = None):
    # A missing or empty slug must return 404
    if not slug or not slug.strip():
        raise HTTPException(status_code=404, detail="Article not found.")

    template_path = os.path.join(BASE_DIR, "blog-details.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Blog details template not found.")

    # Query article by slug
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_posts WHERE slug = ?", (slug.strip(),))
    post = cursor.fetchone()
    conn.close()

    # Deleted, missing, or unpublished posts must return 404
    if not post or post["status"] != "published":
        raise HTTPException(status_code=404, detail="Article not found.")

    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject article into template
    soup = BeautifulSoup(html, "html.parser")

    # Update Title tag
    if soup.title:
        soup.title.string = f"{post['title']} | Codozent Insights"

    # Update Canonical and Robots tags in head
    head = soup.find("head")
    if head:
        canon_url = f"https://codozent.com/blog-details.html?slug={post['slug']}"
        canon_tag = head.find("link", rel=lambda v: v and "canonical" in v)
        if not canon_tag:
            canon_tag = soup.new_tag("link", rel="canonical", href=canon_url)
            head.append(canon_tag)
        else:
            canon_tag["href"] = canon_url

        excerpt_val = post["excerpt"] if "excerpt" in post.keys() else None
        if excerpt_val:
            desc_tag = head.find("meta", attrs={"name": "description"})
            if desc_tag:
                desc_tag["content"] = excerpt_val
            else:
                new_desc = soup.new_tag("meta", attrs={"name": "description", "content": excerpt_val})
                head.append(new_desc)

        robots_tag = head.find("meta", attrs={"name": lambda v: v and "robots" in v.lower()})
        if not robots_tag:
            robots_tag = soup.new_tag("meta", attrs={"name": "robots", "content": "index, follow"})
            head.append(robots_tag)
        else:
            robots_tag["content"] = "index, follow"

    # Update Blog Header
    top_title_area = soup.find("div", class_="top-title-area")
    if top_title_area:
        sub_span = top_title_area.find("span", class_="sub")
        if sub_span:
            sub_span.string = post["category"]
        title_h1 = top_title_area.find("h1", class_="title")
        if title_h1:
            title_h1.string = post["title"]

    # Update Featured Image
    thumb_div = soup.find("div", class_="thumbnail")
    if thumb_div:
        img = thumb_div.find("img")
        if img:
            raw_img = (post["featured_image"] or "").strip()
            img["src"] = f"https://{raw_img}" if raw_img.startswith("res.cloudinary.com") else raw_img
            img["alt"] = post["featured_image_alt"]

    # Update Body Content
    content_div = soup.find("div", class_="blog-listing-content")
    if content_div:
        content_div.clear()
        body_soup = BeautifulSoup(post["body"], "html.parser")
        for child in list(body_soup.children):
            content_div.append(child)

    return HTMLResponse(content=str(soup))

# Public Website Route Handlers
@app.get("/", response_class=HTMLResponse)
def get_homepage():
    index_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="index.html not found.")

@app.get("/{page_name:path}")
def get_public_page(page_name: str):
    # Security: prevent directory traversal
    safe_name = os.path.basename(page_name)
    file_path = os.path.join(BASE_DIR, safe_name)

    if os.path.exists(file_path) and os.path.isfile(file_path):
        if safe_name.endswith(".html"):
            return FileResponse(file_path, media_type="text/html")
        elif safe_name.endswith(".css"):
            return FileResponse(file_path, media_type="text/css")
        elif safe_name.endswith(".js"):
            return FileResponse(file_path, media_type="application/javascript")
        elif safe_name.endswith(".png"):
            return FileResponse(file_path, media_type="image/png")
        elif safe_name.endswith(".webp"):
            return FileResponse(file_path, media_type="image/webp")
        elif safe_name.endswith(".svg"):
            return FileResponse(file_path, media_type="image/svg+xml")
        elif safe_name.endswith(".xml"):
            return FileResponse(file_path, media_type="application/xml")
        return FileResponse(file_path)

    # If asking for root index
    if not page_name or page_name == "index":
        return FileResponse(os.path.join(BASE_DIR, "index.html"), media_type="text/html")

    raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found.")

if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser(description="Codozent CMS & Website Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run server on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host IP")
    parser.add_argument("--reload", action="store_true", default=True, help="Enable auto-reload on code change")
    args = parser.parse_args()

    uvicorn.run("cms.server:app", host=args.host, port=args.port, reload=True)
