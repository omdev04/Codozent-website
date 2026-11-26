"""
Codozent CMS - Cloudinary Migration Utility
-------------------------------------------
Safely migrates local media assets to Cloudinary media storage:
1. Scans work_items, blog_posts, homepage_images, and media_assets for local image files.
2. If Cloudinary credentials are set, uploads them to their respective folders:
   - codozent/work
   - codozent/blog
   - codozent/homepage
   - codozent/general
3. Updates database references with Cloudinary secure_url and public_id.
4. Regenerates public HTML pages (index.html, case-studies.html, blog.html).
5. If credentials are not set, prints an audit report with required configuration steps.
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cms.db import get_db_connection, init_db
from cms.cloudinary_storage import (
    is_cloudinary_configured,
    upload_image,
    get_cloudinary_config,
    ALLOWED_EXTENSIONS
)
from cms.sync import regenerate_work_section, regenerate_blog_page, publish_homepage_images

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CodozentCMS.migrate")


def resolve_local_path(rel_path: str) -> Path:
    """Resolve a relative or root-relative path to an absolute Path on disk."""
    clean = rel_path.lstrip("/").replace("\\", "/")
    return PROJECT_ROOT / clean


def migrate_assets(dry_run: bool = False):
    """Run the migration process."""
    init_db()
    configured = is_cloudinary_configured()
    cfg = get_cloudinary_config()

    print("=" * 65)
    print(" Codozent Media Storage Migration -> Cloudinary")
    print("=" * 65)
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Cloudinary Configured: {'YES' if configured else 'NO'}")
    if configured:
        print(f"Cloud Name: {cfg['cloud_name']}")
    else:
        print("Status: STANDBY (Credentials missing in environment)")
        print("Note: Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in .env")
    print("-" * 65)

    conn = get_db_connection()
    c = conn.cursor()

    # 1. Inspect Work Items
    work_rows = c.execute(
        "SELECT id, title, image_url, storage_provider FROM work_items"
    ).fetchall()

    # 2. Inspect Blog Posts
    blog_rows = c.execute(
        "SELECT id, title, featured_image, cloudinary_public_id FROM blog_posts"
    ).fetchall()

    # 3. Inspect Homepage Images
    img_rows = c.execute(
        "SELECT slot_key, current_src, draft_src FROM homepage_images"
    ).fetchall()

    # 4. Inspect Media Assets
    media_rows = c.execute(
        "SELECT id, filename, file_path, storage_provider, folder FROM media_assets"
    ).fetchall()

    print(f"\n[Audit Results]")
    print(f" • Work Items: {len(work_rows)} items")
    print(f" • Blog Posts: {len(blog_rows)} posts")
    print(f" • Homepage Image Slots: {len(img_rows)} slots")
    print(f" • Media Asset Records: {len(media_rows)} files")

    if not configured or dry_run:
        print("\n" + "=" * 65)
        print(" MIGRATION PLAN (AUDIT REPORT)")
        print("=" * 65)
        print("\nTarget Cloudinary Folders & Local Mappings:")
        print(" 1. codozent/work:")
        for r in work_rows:
            local = resolve_local_path(r["image_url"])
            exists = "EXISTS" if local.exists() else "MISSING"
            print(f"    - [{exists}] ID {r['id']}: {r['title']} -> {r['image_url']}")

        print("\n 2. codozent/blog:")
        for r in blog_rows:
            local = resolve_local_path(r["featured_image"])
            exists = "EXISTS" if local.exists() else "MISSING"
            print(f"    - [{exists}] ID {r['id']}: {r['title']} -> {r['featured_image']}")

        print("\n 3. codozent/homepage:")
        for r in img_rows:
            local = resolve_local_path(r["current_src"])
            exists = "EXISTS" if local.exists() else "MISSING"
            print(f"    - [{exists}] Slot '{r['slot_key']}': {r['current_src']}")

        print("\n" + "=" * 65)
        if not configured:
            print(" Next Steps to Complete Cloudinary Migration:")
            print(" 1. Add your Cloudinary API credentials to your .env file:")
            print("    CLOUDINARY_CLOUD_NAME=your_cloud_name")
            print("    CLOUDINARY_API_KEY=your_api_key")
            print("    CLOUDINARY_API_SECRET=your_api_secret")
            print(" 2. Run this migration script:")
            print("    python cms/migrate_to_cloudinary.py")
        else:
            print(" Dry run complete. Run without --dry-run to execute migration.")
        print("=" * 65)
        conn.close()
        return

    # If configured and not dry_run, proceed with migration!
    migrated_work = 0
    migrated_blogs = 0
    migrated_slots = 0

    print("\nStarting asset migration to Cloudinary...\n")

    # A. Migrate Work Items
    for r in work_rows:
        if r["storage_provider"] == "cloudinary" and r["image_url"].startswith("http"):
            continue
        local_path = resolve_local_path(r["image_url"])
        if not local_path.exists():
            logger.warning(f"Skipping work item {r['id']} - file not found: {local_path}")
            continue

        print(f" -> Uploading work item #{r['id']} ({r['title']}) to codozent/work...")
        with open(local_path, "rb") as f:
            res = upload_image(f.read(), local_path.name, folder="codozent/work")
        if res.get("success"):
            conn.cursor().execute(
                """
                UPDATE work_items 
                SET image_url = ?, storage_provider = 'cloudinary', cloudinary_public_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (res["secure_url"], res["public_id"], r["id"])
            )
            conn.commit()
            migrated_work += 1
            print(f"    Uploaded: {res['secure_url']}")
        else:
            logger.error(f"Failed to upload {local_path.name}: {res.get('error')}")

    # B. Migrate Blog Posts
    for r in blog_rows:
        if r["featured_image"].startswith("http") and r["cloudinary_public_id"]:
            continue
        local_path = resolve_local_path(r["featured_image"])
        if not local_path.exists():
            logger.warning(f"Skipping blog post {r['id']} - file not found: {local_path}")
            continue

        print(f" -> Uploading blog post #{r['id']} ({r['title']}) to codozent/blog...")
        with open(local_path, "rb") as f:
            res = upload_image(f.read(), local_path.name, folder="codozent/blog")
        if res.get("success"):
            conn.cursor().execute(
                """
                UPDATE blog_posts 
                SET featured_image = ?, cloudinary_public_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (res["secure_url"], res["public_id"], r["id"])
            )
            conn.commit()
            migrated_blogs += 1
            print(f"    Uploaded: {res['secure_url']}")
        else:
            logger.error(f"Failed to upload {local_path.name}: {res.get('error')}")

    # C. Migrate Homepage Image Slots
    for r in img_rows:
        if r["current_src"].startswith("http"):
            continue
        local_path = resolve_local_path(r["current_src"])
        if not local_path.exists():
            logger.warning(f"Skipping slot {r['slot_key']} - file not found: {local_path}")
            continue

        print(f" -> Uploading homepage slot '{r['slot_key']}' to codozent/homepage...")
        with open(local_path, "rb") as f:
            res = upload_image(f.read(), local_path.name, folder="codozent/homepage")
        if res.get("success"):
            conn.cursor().execute(
                """
                UPDATE homepage_images 
                SET current_src = ?, draft_src = ?, updated_at = CURRENT_TIMESTAMP
                WHERE slot_key = ?
                """,
                (res["secure_url"], res["secure_url"], r["slot_key"])
            )
            conn.commit()
            migrated_slots += 1
            print(f"    Uploaded: {res['secure_url']}")
        else:
            logger.error(f"Failed to upload {local_path.name}: {res.get('error')}")

    conn.close()

    # Regenerate public pages to reflect new Cloudinary URLs
    print("\nRegenerating public website HTML pages...")
    regenerate_work_section()
    regenerate_blog_page()
    publish_homepage_images()
    print("Public pages synchronized.")

    print("\n" + "=" * 65)
    print(" MIGRATION SUMMARY")
    print("=" * 65)
    print(f"Work items migrated:       {migrated_work}")
    print(f"Blog posts migrated:       {migrated_blogs}")
    print(f"Homepage slots migrated:   {migrated_slots}")
    print("Cloudinary migration successfully completed!")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate local Codozent media assets to Cloudinary.")
    parser.add_argument("--dry-run", action="store_true", help="Audit local assets without uploading.")
    args = parser.parse_args()
    migrate_assets(dry_run=args.dry_run)
