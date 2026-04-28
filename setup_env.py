# setup_env.py
# Run this ONCE from project root: python setup_env.py
# It installs all required packages using pip

import subprocess
import sys

def pip_install(packages):
    print(f"\n📦 Installing: {', '.join(packages)}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install"] + packages,
        capture_output=False   # show live output
    )
    return result.returncode == 0

# ── Core dependencies ──────────────────────────────────────
packages = [
    # Computer Vision
    "opencv-python",       # cv2 — RIFE needs this
    "Pillow",              # PIL

    # Deep Learning (CPU-safe, no CUDA required)
    "torch",               # RIFE needs torch
    "torchvision",

    # Satellite/WMS fetching
    "requests",

    # FastAPI backend
    "fastapi",
    "uvicorn[standard]",

    # Quality metrics
    "scikit-image",

    # Numerics
    "numpy",
]

success = pip_install(packages)

if success:
    print("\n✅ All packages installed successfully!")
    print("\n▶ Now run: python test_pipeline.py")
else:
    print("\n❌ Some packages failed. Try running manually:")
    print(f"   {sys.executable} -m pip install opencv-python torch torchvision fastapi uvicorn requests scikit-image numpy Pillow")
