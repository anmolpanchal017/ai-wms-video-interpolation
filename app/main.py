from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os

from app.generate_frames import generate_frames
from app.interpolation import run_interpolation
from app.video_generator import prepare_all_frames, create_video
from app.metrics import calculate_metrics

app = FastAPI(
    title="SatFrame AI",
    description="Satellite Frame Interpolation Pipeline — ISRO Minor Project",
    version="1.0.0"
)

# ── CORS (kept as backup, but less needed now that frontend is served from same origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve the frontend HTML at root "/"  ───────────────────────────────────────
# index.html can be at project root OR in frontend/ — we check both
FRONTEND_PATH = "frontend/index.html" if os.path.exists("frontend/index.html") else "index.html"

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend():
    """Serve the main frontend UI."""
    if os.path.exists(FRONTEND_PATH):
        with open(FRONTEND_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Frontend not found. Place index.html at project root.</h1>", status_code=404)

# ── Serve static assets (images, CSS, JS files if any) ────────────────────────
if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="static")

# ── API Endpoints ──────────────────────────────────────────────────────────────

@app.post("/generate-video", summary="Run full pipeline and return satellite video")
async def generate_video(request: Request):
    """
    Runs the complete pipeline:
    1. Fetch satellite frames
    2. RIFE AI interpolation
    3. FFmpeg video assembly
    """
    try:
        data = await request.json()
    except Exception:
        data = {}

    bbox = data.get("bbox", "68.0,6.0,97.0,38.0")
    num_frames = data.get("num_frames", 5) # original frames to fetch
    fps = data.get("fps", 5)               # slow playback
    resolution = data.get("resolution", 1024)
    target_total = data.get("target_total", 30) # roughly how many frames user wants total
    date_str = data.get("date", "2024-03-15")
    start_time_str = data.get("start_time", "06:00:00")
    end_time_str = data.get("end_time", "08:00:00")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_pipeline, bbox, num_frames, fps, resolution, target_total, date_str, start_time_str, end_time_str)
    
    return FileResponse(
        "output/satellite_video.mp4",
        media_type="video/mp4",
        filename="satellite_video.mp4"
    )

def _run_pipeline(bbox, num_frames, fps, resolution, target_total, date_str, start_time_str, end_time_str):
    """Synchronous pipeline — runs in thread pool executor."""
    generate_frames(out_dir="frames", num_frames=num_frames, bbox=bbox, width=resolution, height=resolution, date_str=date_str, start_time_str=start_time_str, end_time_str=end_time_str)
    run_interpolation(num_frames=num_frames, target_total=target_total)
    prepare_all_frames(num_frames=num_frames)
    create_video(fps=fps)


@app.get("/metrics", summary="Get quality metrics for the last generated video")
async def get_metrics():
    """Returns SSIM, PSNR, total frames, FPS and source info."""
    return calculate_metrics()


@app.get("/health", summary="Health check")
async def health():
    return {"status": "ok", "service": "SatFrame AI", "version": "1.0.0"}