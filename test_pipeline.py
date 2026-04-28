# test_pipeline.py
# Run from project root: python test_pipeline.py
# This tests each stage of the pipeline individually

import os
import sys

print("=" * 60)
print("MINOR PROJECT - Satellite Frame Interpolation Pipeline")
print("=" * 60)

# ── STEP 1: Check model weights ─────────────────────────────────
print("\n[1/4] Checking RIFE model weights...")
weights_path = "ECCV2022-RIFE/train_log/flownet.pkl"
if os.path.exists(weights_path):
    size_mb = os.path.getsize(weights_path) / (1024 * 1024)
    print(f"  ✅ flownet.pkl found ({size_mb:.1f} MB)")
else:
    print(f"  ❌ MISSING: {weights_path}")
    print("     Download from RIFE GitHub releases and place in ECCV2022-RIFE/train_log/")
    sys.exit(1)

# ── STEP 2: Test RIFE with demo images ──────────────────────────
print("\n[2/4] Testing RIFE with demo images...")
import subprocess, shutil

demo_img0 = "ECCV2022-RIFE/demo/I0_0.png"
demo_img1 = "ECCV2022-RIFE/demo/I1_0.png"

if not (os.path.exists(demo_img0) and os.path.exists(demo_img1)):
    print(f"  ⚠️  Demo images not found, skipping RIFE test")
else:
    rife_dir = os.path.abspath("ECCV2022-RIFE")
    rife_output = os.path.join(rife_dir, "output")
    if os.path.exists(rife_output):
        shutil.rmtree(rife_output)

    result = subprocess.run(
        [sys.executable, "inference_img.py",
         "--img", os.path.abspath(demo_img0), os.path.abspath(demo_img1),
         "--exp", "2"],
        cwd=rife_dir,
        capture_output=True, text=True
    )

    if result.returncode == 0:
        generated = os.listdir(rife_output) if os.path.exists(rife_output) else []
        print(f"  ✅ RIFE works! Generated {len(generated)} frames")
        print(f"     stdout: {result.stdout.strip()}")
    else:
        print(f"  ❌ RIFE failed!")
        print(f"     stderr: {result.stderr[-800:]}")
        sys.exit(1)

# ── STEP 3: Generate WMS frames ─────────────────────────────────
print("\n[3/4] Fetching satellite frames from WMS...")

# Clear old frames first (previous run may have saved corrupt/error files)
if os.path.exists("frames"):
    for f in os.listdir("frames"):
        os.remove(os.path.join("frames", f))
    print("  Cleared old frames/")

sys.path.insert(0, os.path.abspath("."))
from app.generate_frames import generate_frames

generate_frames()

frame_files = [f for f in os.listdir("frames") if f.endswith(".png")]
if frame_files:
    print(f"  ✅ {len(frame_files)} frames saved in frames/")
else:
    print("  ❌ No frames fetched — check WMS URL / internet connection")
    sys.exit(1)

# ── STEP 4: Run interpolation ────────────────────────────────────
print("\n[4/4] Running RIFE interpolation on frame pairs...")
from app.interpolation import run_interpolation

run_interpolation()

total_interp = 0
for i in range(4):
    d = f"interpolated/pair_{i}"
    if os.path.exists(d):
        n = len([f for f in os.listdir(d) if f.endswith(".png")])
        print(f"  pair_{i}: {n} frames")
        total_interp += n

print(f"\n  ✅ Total interpolated frames: {total_interp}")
print("\n" + "=" * 60)
print("Pipeline test complete! Next steps:")
print("  → python -c \"from app.video_generator import *; prepare_all_frames(); create_video()\"")
print("  → uvicorn app.main:app --reload")
print("=" * 60)
