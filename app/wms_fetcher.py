"""
wms_fetcher.py
Priority-based WMS image fetcher with fast probe-before-commit strategy:
  1st → ISRO VEDAS  (INSAT-3D/3DR — sub-hourly, time-series)
  2nd → Bhuvan NRSC (ISRO geoportal — static but Indian & OGC-compliant)
  3rd → NASA GIBS   (MODIS Terra / VIIRS — daily, rock-solid)
  4th → Synthetic   (generated locally, always works, no internet needed)

HOW IT WORKS:
  Before fetching all frames from a source, we send ONE "probe" request.
  If it fails (404, timeout, non-image), we skip that source entirely.
  This avoids the long hang where we wait 30s × 5 frames × 4 date ranges.
"""

import requests
from PIL import Image
import io
import os
import logging

logging.basicConfig(filename='wms_debug.log', level=logging.INFO, 
                    format='%(asctime)s %(levelname)s:%(message)s')

PNG_MAGIC  = b'\x89PNG\r\n\x1a\n'
JPEG_MAGIC = b'\xff\xd8\xff'

VEDAS_TIMEOUT = 5    # VEDAS often down — fail fast
GIBS_TIMEOUT  = 10   # NASA GIBS is reliable — give it more time
MIN_IMAGE_BYTES = 3000  # anything smaller is likely an error page


# ── Source Definitions ─────────────────────────────────────────────────────────

ISRO_VEDAS_SOURCES = [
    {
        "name": "ISRO VEDAS (INSAT-3D TIR1)",
        "url": "https://vedas.sac.gov.in/wms/",
        "params": {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": "INSAT_3D_TIR1", "FORMAT": "image/png",
            "SRS": "EPSG:4326", "BBOX": "68.0,6.0,97.0,38.0",
            "WIDTH": "512", "HEIGHT": "512", "STYLES": "",
        },
        "time_key": "TIME", "date_only": False,
        "timeout": VEDAS_TIMEOUT,
    },
    {
        "name": "ISRO VEDAS (INSAT-3D IR)",
        "url": "https://vedas.sac.gov.in/wms",
        "params": {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": "INSAT_3D_IR", "FORMAT": "image/png",
            "SRS": "EPSG:4326", "BBOX": "68.0,6.0,97.0,38.0",
            "WIDTH": "512", "HEIGHT": "512", "STYLES": "",
        },
        "time_key": "TIME", "date_only": False,
        "timeout": VEDAS_TIMEOUT,
    },
    {
        "name": "ISRO VEDAS (INSAT-3DR TIR1)",
        "url": "https://vedas.sac.gov.in/wms/",
        "params": {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": "INSAT_3DR_TIR1", "FORMAT": "image/png",
            "SRS": "EPSG:4326", "BBOX": "68.0,6.0,97.0,38.0",
            "WIDTH": "512", "HEIGHT": "512", "STYLES": "",
        },
        "time_key": "TIME", "date_only": False,
        "timeout": VEDAS_TIMEOUT,
    },
]

BHUVAN_SOURCES = [
    {
        "name": "Bhuvan NRSC (ISRO — Satellite Imagery)",
        "url": "https://bhuvan-app1.nrsc.gov.in/bhuvan/wms",
        "params": {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": "india_spot",
            "FORMAT": "image/png",
            "SRS": "EPSG:4326", "BBOX": "68.0,6.0,97.0,38.0",
            "WIDTH": "512", "HEIGHT": "512", "STYLES": "",
        },
        "time_key": None,    # Bhuvan does NOT support TIME parameter
        "date_only": False,
        "timeout": VEDAS_TIMEOUT,
    },
    {
        "name": "Bhuvan Vec2 (ISRO — Landuse/Thematic)",
        "url": "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms",
        "params": {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": "lulc50k",
            "FORMAT": "image/png",
            "SRS": "EPSG:4326", "BBOX": "68.0,6.0,97.0,38.0",
            "WIDTH": "512", "HEIGHT": "512", "STYLES": "",
        },
        "time_key": None,
        "date_only": False,
        "timeout": VEDAS_TIMEOUT,
    },
]

NASA_GIBS_SOURCES = [
    {
        "name": "NASA GIBS (MODIS Terra)",
        "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
        "params": {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": "MODIS_Terra_CorrectedReflectance_TrueColor",
            "FORMAT": "image/png",
            "SRS": "EPSG:4326", "BBOX": "68.0,6.0,97.0,38.0",
            "WIDTH": "512", "HEIGHT": "512", "STYLES": "",
        },
        "time_key": "TIME", "date_only": True,
        "timeout": GIBS_TIMEOUT,
    },
    {
        "name": "NASA GIBS (VIIRS SNPP)",
        "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
        "params": {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": "VIIRS_SNPP_CorrectedReflectance_TrueColor",
            "FORMAT": "image/png",
            "SRS": "EPSG:4326", "BBOX": "68.0,6.0,97.0,38.0",
            "WIDTH": "512", "HEIGHT": "512", "STYLES": "",
        },
        "time_key": "TIME", "date_only": True,
        "timeout": GIBS_TIMEOUT,
    },
]


# ── Core fetch logic ───────────────────────────────────────────────────────────

def _build_params(source, time_str, bbox=None, width=1024, height=1024):
    """Build request params for a source, injecting time if supported."""
    params = dict(source["params"])
    if source.get("time_key") and time_str:
        time_val = time_str[:10] if source.get("date_only") else time_str
        params[source["time_key"]] = time_val
    if bbox:
        # We now use WMS 1.1.1 for all sources, which strictly uses minLon,minLat,maxLon,maxLat
        params["BBOX"] = bbox.replace(" ", "") # Ensure no spaces
    if width:
        params["WIDTH"] = str(width)
    if height:
        params["HEIGHT"] = str(height)
    return params


def _is_valid_image(content, content_type=""):
    """Return True if bytes look like a real image (not error XML/HTML)."""
    if len(content) < MIN_IMAGE_BYTES:
        return False
    is_png  = content[:8] == PNG_MAGIC
    is_jpeg = content[:3] == JPEG_MAGIC
    is_img_ct = "image" in content_type
    return is_png or is_jpeg or is_img_ct


def _try_fetch_one(source, time_str, output_path, bbox=None, width=1024, height=1024):
    """
    Fetch a single frame from one source.
    Returns True on success, False on any failure.
    """
    params = _build_params(source, time_str, bbox, width, height)
    timeout = source.get("timeout", GIBS_TIMEOUT)
    try:
        url = source["url"]
        logging.info(f"Requesting {source['name']} - URL: {url} Params: {params}")
        resp = requests.get(url, params=params, timeout=timeout)
        
        if resp.status_code != 200:
            logging.error(f"{source['name']} HTTP {resp.status_code}: {resp.text[:200]}")
            
        resp.raise_for_status()
        content = resp.content
        ct = resp.headers.get("Content-Type", "")

        if not _is_valid_image(content, ct):
            snippet = content[:120].decode("utf-8", errors="replace").replace("\n", " ")
            print(f"    ↳ {source['name']}: bad response ({len(content)} bytes) — {snippet[:70]}")
            logging.error(f"{source['name']} INVALID IMAGE: {snippet}")
            return False

        img = Image.open(io.BytesIO(content)).convert("RGB")
        img.save(output_path, "PNG")
        logging.info(f"{source['name']} SUCCESS - saved to {output_path}")
        return True

    except requests.exceptions.Timeout:
        print(f"    ↳ {source['name']}: timed out ({timeout}s)")
        logging.error(f"{source['name']} TIMEOUT")
    except requests.exceptions.HTTPError as e:
        print(f"    ↳ {source['name']}: HTTP {e.response.status_code}")
        logging.error(f"{source['name']} HTTPError: {e}")
    except requests.exceptions.ConnectionError:
        print(f"    ↳ {source['name']}: connection refused")
        logging.error(f"{source['name']} ConnectionError")
    except Exception as e:
        print(f"    ↳ {source['name']}: {type(e).__name__}: {e}")
        logging.error(f"{source['name']} Exception: {e}")
    return False


def probe_source(source, probe_time_str, bbox=None, width=1024, height=1024):
    """
    Send ONE request to check if a source is alive.
    Returns True if source responds with a valid image.
    This prevents wasting time retrying dead servers.
    """
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        result = _try_fetch_one(source, probe_time_str, tmp_path, bbox, width, height)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return result


def fetch_wms_image(time_str, output_path, bbox=None, width=1024, height=1024):
    """
    Fetch a satellite image using the priority chain.
    Called directly when fetching individual frames.
    Returns: "vedas" | "bhuvan" | "gibs" | "synthetic"
    """
    # 1. VEDAS
    for src in ISRO_VEDAS_SOURCES:
        if _try_fetch_one(src, time_str, output_path, bbox, width, height):
            return "vedas"
    # 2. Bhuvan
    for src in BHUVAN_SOURCES:
        if _try_fetch_one(src, time_str, output_path, bbox, width, height):
            return "bhuvan"
    # 3. NASA GIBS
    for src in NASA_GIBS_SOURCES:
        if _try_fetch_one(src, time_str, output_path, bbox, width, height):
            return "gibs"
    # 4. Synthetic
    idx = int(os.path.basename(output_path).split("_")[1].split(".")[0])
    _make_synthetic_frame(output_path, idx, bbox)
    return "synthetic"


# ── Synthetic frame generator ──────────────────────────────────────────────────

def _make_synthetic_frame(path, idx, bbox=None):
    """Generate a realistic-looking synthetic satellite IR frame."""
    from PIL import ImageDraw, ImageFilter
    import random
    random.seed(idx * 42)
    base = [(8,24,58),(12,32,72),(15,40,85),(10,28,65),(18,45,95)]
    img  = Image.new("RGB", (512, 512), base[idx % len(base)])
    draw = ImageDraw.Draw(img)
    for _ in range(25):
        x, y = random.randint(-30, 550), random.randint(-30, 550)
        rx, ry = random.randint(15, 90), random.randint(10, 50)
        b = random.randint(160, 255)
        draw.ellipse([x-rx, y-ry, x+rx, y+ry],
                     fill=(b, b, min(255, b+random.randint(-20,20))))
    for lx, ly in [(128,256),(200,300),(256,350),(300,280),(256,200)]:
        draw.ellipse([lx-40, ly-30, lx+40, ly+30], fill=(40,80,30))
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    d2  = ImageDraw.Draw(img)
    
    bbox_str = bbox if bbox else "68.0, 6.0, 97.0, 38.0"
    
    d2.text((8, 8),  f"[SYNTHETIC] Frame {idx:02d}",          fill=(255,220,0))
    d2.text((8, 28), f"BBOX: {bbox_str}",                     fill=(200,200,200))
    d2.text((8, 48), "ISRO VEDAS / Bhuvan / NASA unavailable", fill=(255,100,100))
    img.save(path, "PNG")