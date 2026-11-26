"""
Codozent CMS - Cloudinary Media Storage Adapter
Handles signed uploads, image transformations, metadata extraction,
and safe asset deletion with fallback support.
"""
import os
import time
import hashlib
import logging
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
try:
    from PIL import Image
except ImportError:
    Image = None
import io

logger = logging.getLogger("CodozentCMS.cloudinary")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_UPLOADS_DIR = os.path.join(ROOT_DIR, "assets", "images", "uploads")
os.makedirs(LOCAL_UPLOADS_DIR, exist_ok=True)

# Allowed image MIME types and extensions
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.svg'}
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/svg+xml'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def get_cloudinary_config() -> Dict[str, str]:
    return {
        "cloud_name": os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip(),
        "api_key": os.environ.get("CLOUDINARY_API_KEY", "").strip(),
        "api_secret": os.environ.get("CLOUDINARY_API_SECRET", "").strip()
    }

def is_cloudinary_configured() -> bool:
    cfg = get_cloudinary_config()
    return bool(cfg["cloud_name"] and cfg["api_key"] and cfg["api_secret"])

def configure_cloudinary():
    """Initializes the official Cloudinary SDK if credentials are present."""
    if is_cloudinary_configured():
        try:
            import cloudinary
            cfg = get_cloudinary_config()
            cloudinary.config(
                cloud_name=cfg["cloud_name"],
                api_key=cfg["api_key"],
                api_secret=cfg["api_secret"],
                secure=True
            )
            logger.info("Cloudinary SDK configured for cloud_name: %s", cfg["cloud_name"])
            return True
        except Exception as e:
            logger.error("Failed to configure Cloudinary SDK: %s", e)
    return False

def generate_signed_upload_params(folder: str = "codozent/general") -> Dict[str, Any]:
    """
    Generates server-side timestamp and signature for secure signed browser uploads.
    The secret is strictly preserved server-side and never exposed.
    """
    cfg = get_cloudinary_config()
    if not is_cloudinary_configured():
        raise ValueError("Cloudinary credentials are not configured in environment variables.")

    timestamp = int(time.time())
    params = {
        "folder": folder,
        "timestamp": str(timestamp)
    }

    # Sort parameters alphabetically by key and concatenate as key=value&key=value
    sorted_pairs = [f"{k}={params[k]}" for k in sorted(params.keys())]
    to_sign = "&".join(sorted_pairs) + cfg["api_secret"]
    signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

    return {
        "cloud_name": cfg["cloud_name"],
        "api_key": cfg["api_key"],
        "timestamp": timestamp,
        "folder": folder,
        "signature": signature
    }

def validate_image_file(filename: str, file_bytes: bytes, mime_type: str = "") -> Tuple[int, int]:
    """Validates file extension, MIME type, size, and extracts dimensions."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Invalid file extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(f"File size exceeds maximum limit of 10MB ({len(file_bytes)} bytes)")

    width, height = 0, 0
    if ext != '.svg':
        if Image is not None:
            try:
                with Image.open(io.BytesIO(file_bytes)) as img:
                    width, height = img.size
            except Exception as e:
                raise ValueError(f"Invalid or corrupted image data: {e}")
        else:
            width, height = 1200, 800
    else:
        # SVG files
        width, height = 800, 600

    return width, height

def upload_image(file_bytes: bytes, filename: str, folder: str = "codozent/general", alt_text: str = "") -> Dict[str, Any]:
    """
    Uploads an image file to Cloudinary if configured, or saves to local uploads
    directory as a safe verified fallback.
    Returns metadata dict for database persistence.
    """
    width, height = validate_image_file(filename, file_bytes)
    ext = Path(filename).suffix.lower()
    base_name = Path(filename).stem
    safe_stem = "".join([c if c.isalnum() or c in "-_" else "_" for c in base_name])
    timestamp = int(time.time())

    # Try Cloudinary upload if configured
    if is_cloudinary_configured() and configure_cloudinary():
        try:
            import cloudinary.uploader
            logger.info("Uploading %s to Cloudinary (folder: %s)...", filename, folder)
            upload_result = cloudinary.uploader.upload(
                file_bytes,
                folder=folder,
                public_id=f"{safe_stem}_{timestamp}",
                resource_type="image",
                overwrite=True
            )

            secure_url = upload_result.get("secure_url") or upload_result.get("url")
            return {
                "success": True,
                "storage_provider": "cloudinary",
                "asset_id": upload_result.get("asset_id", ""),
                "public_id": upload_result.get("public_id", ""),
                "version": str(upload_result.get("version", "")),
                "format": upload_result.get("format", ext.lstrip(".")),
                "width": upload_result.get("width", width),
                "height": upload_result.get("height", height),
                "bytes": upload_result.get("bytes", len(file_bytes)),
                "secure_url": secure_url,
                "folder": folder,
                "alt_text": alt_text,
                "filename": filename,
                "created_at": upload_result.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
        except Exception as e:
            logger.error("Cloudinary upload failed: %s. Falling back to local storage.", e)

    # Local storage fallback (when Cloudinary keys are not provided or network unavailable)
    local_filename = f"{safe_stem}_{timestamp}{ext}"
    local_path = os.path.join(LOCAL_UPLOADS_DIR, local_filename)
    with open(local_path, "wb") as f:
        f.write(file_bytes)

    local_url = f"/assets/images/uploads/{local_filename}"
    logger.info("Image saved locally at %s", local_url)

    return {
        "success": True,
        "storage_provider": "local",
        "asset_id": f"local_{timestamp}",
        "public_id": f"{folder}/{safe_stem}_{timestamp}",
        "version": "1",
        "format": ext.lstrip("."),
        "width": width,
        "height": height,
        "bytes": len(file_bytes),
        "secure_url": local_url,
        "folder": folder,
        "alt_text": alt_text,
        "filename": filename,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

def delete_image(public_id: str, storage_provider: str = "cloudinary", local_url: Optional[str] = None) -> bool:
    """Deletes the image from Cloudinary or local storage."""
    if storage_provider == "cloudinary" and is_cloudinary_configured() and configure_cloudinary():
        try:
            import cloudinary.uploader
            res = cloudinary.uploader.destroy(public_id)
            logger.info("Cloudinary destroy result for %s: %s", public_id, res)
            return res.get("result") in ["ok", "not found"]
        except Exception as e:
            logger.error("Failed to delete from Cloudinary: %s", e)
            return False

    if local_url and local_url.startswith("/assets/images/uploads/"):
        fname = os.path.basename(local_url)
        local_file = os.path.join(LOCAL_UPLOADS_DIR, fname)
        if os.path.exists(local_file):
            try:
                os.remove(local_file)
                logger.info("Deleted local upload file: %s", local_file)
                return True
            except Exception as e:
                logger.error("Error removing local file: %s", e)
                return False

    return True

def get_optimized_delivery_url(url: str, width: Optional[int] = None, height: Optional[int] = None, crop: str = "fill") -> str:
    """
    Constructs an optimized Cloudinary delivery URL with f_auto, q_auto and dimensions,
    ensuring image slots maintain exact rendered dimensions without stretching.
    """
    if "res.cloudinary.com" not in url or "/upload/" not in url:
        return url

    parts = url.split("/upload/")
    if len(parts) != 2:
        return url

    transformations = ["f_auto", "q_auto"]
    if width and height:
        transformations.append(f"c_{crop},w_{width},h_{height}")
    elif width:
        transformations.append(f"w_{width}")
    elif height:
        transformations.append(f"h_{height}")

    trans_str = ",".join(transformations)
    return f"{parts[0]}/upload/{trans_str}/{parts[1]}"
