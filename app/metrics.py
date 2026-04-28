"""
metrics.py
Compute SSIM and PSNR quality metrics between original and interpolated frames.
Gracefully handles missing files (e.g., before first pipeline run).
"""

import os
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim_fn
from skimage.metrics import peak_signal_noise_ratio as psnr_fn


def calculate_metrics():
    """
    Compare an original frame vs an interpolated frame.
    Returns SSIM, PSNR, total frame count, and FPS.
    """
    frame0_path = "frames/frame_00.png"
    frame1_path = "frames/frame_01.png"
    interp_paths = [
        "interpolated/pair_0/img1.png",
        "interpolated/pair_0/img2.png",
        "interpolated/pair_0/img3.png",
    ]

    # Count total assembled frames
    total_frames = 0
    if os.path.exists("all_frames"):
        total_frames = len([f for f in os.listdir("all_frames") if f.endswith(".png")])

    # Find the first existing interpolated frame to compare against
    interp_img = None
    for p in interp_paths:
        if os.path.exists(p):
            interp_img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
            if interp_img is not None:
                break

    # Load original frame
    orig_img = None
    if os.path.exists(frame0_path):
        orig_img = cv2.imread(frame0_path, cv2.IMREAD_GRAYSCALE)

    # Compute metrics if both images available and same size
    ssim_val = None
    psnr_val = None

    if orig_img is not None and interp_img is not None:
        try:
            # Resize to match if needed
            if orig_img.shape != interp_img.shape:
                interp_img = cv2.resize(interp_img, (orig_img.shape[1], orig_img.shape[0]))

            ssim_val = float(ssim_fn(orig_img, interp_img))
            psnr_val = float(psnr_fn(orig_img, interp_img))
        except Exception as e:
            print(f"[metrics] Compute error: {e}")

    return {
        "ssim":         round(ssim_val, 4) if ssim_val is not None else None,
        "psnr":         round(psnr_val, 2) if psnr_val is not None else None,
        "total_frames": total_frames if total_frames > 0 else None,
        "fps":          24,
        "source":       _detect_source(),
        "region":       "India (68°E–97°E, 6°N–38°N)",
        "crs":          "EPSG:4326",
        "resolution":   "512×512 px",
    }


def _detect_source():
    """Try to infer which WMS source was used based on frame content."""
    # Simple heuristic: if frame_00.png exists and is a real colour image → real WMS
    path = "frames/frame_00.png"
    if not os.path.exists(path):
        return "unknown"
    img = cv2.imread(path)
    if img is None:
        return "unknown"
    # Synthetic frames are very dark/uniform; real imagery has more variance
    std = float(np.std(img))
    if std < 20:
        return "Synthetic (offline)"
    return "WMS (NASA GIBS / VEDAS)"