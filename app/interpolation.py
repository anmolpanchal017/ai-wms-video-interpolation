import subprocess
import os
import shutil
import sys
import cv2   # used for pre-validating frames before passing to RIFE

def _validate_image(path):
    """Return True if path is a valid, readable 3-channel image."""
    if not os.path.exists(path):
        print(f"  [SKIP] File not found: {path}")
        return False
    img = cv2.imread(path)
    if img is None:
        print(f"  [SKIP] cv2 cannot read (corrupt/invalid): {path}")
        return False
    if len(img.shape) < 3 or img.shape[2] < 3:
        print(f"  [SKIP] Not a 3-channel image (shape={img.shape}): {path}")
        return False
    return True

def run_interpolation(num_frames=5, target_total=30):
    """
    Run RIFE interpolation on consecutive frame pairs.
    """
    os.makedirs("interpolated", exist_ok=True)

    # Determine interpolation factor (exp)
    num_pairs = num_frames - 1
    if num_pairs <= 0:
        print("[SKIP] Not enough frames to interpolate.")
        return

    frames_per_pair = max(1, target_total // num_pairs)
    if frames_per_pair <= 2:
        exp_val = "1" # 2x (1 inserted)
    elif frames_per_pair <= 4:
        exp_val = "2" # 4x (3 inserted)
    elif frames_per_pair <= 8:
        exp_val = "3" # 8x (7 inserted)
    else:
        exp_val = "4" # 16x (15 inserted)
    os.makedirs("interpolated", exist_ok=True)

    # Absolute paths so subprocess can find files regardless of cwd
    project_root = os.path.abspath(".")
    rife_dir = os.path.join(project_root, "ECCV2022-RIFE")
    rife_output = os.path.join(rife_dir, "output")

    for i in range(num_pairs):
        frame_A = os.path.join(project_root, f"frames/frame_{i:02d}.png")
        frame_B = os.path.join(project_root, f"frames/frame_{i+1:02d}.png")
        dest_dir = os.path.join(project_root, f"interpolated/pair_{i}")
        os.makedirs(dest_dir, exist_ok=True)

        # Clear RIFE's output folder before each run
        if os.path.exists(rife_output):
            shutil.rmtree(rife_output)

        # ── Pre-flight: validate both frames before calling RIFE ──────
        if not _validate_image(frame_A) or not _validate_image(frame_B):
            print(f"[SKIP] pair_{i}: one or both frames invalid — re-run generate_frames first")
            continue

        print(f"[RIFE] Interpolating pair {i}: frame_{i:02d}.png ↔ frame_{i+1:02d}.png")

        result = subprocess.run(
            [
                sys.executable,       # uses same Python interpreter
                "inference_img.py",
                "--img", frame_A, frame_B,
                "--exp", exp_val,
            ],
            cwd=rife_dir,             # run from RIFE directory so imports work
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"[ERROR] RIFE failed on pair {i}:\n{result.stderr}")
            continue

        print(result.stdout.strip())

        # Move generated frames from RIFE output → our interpolated/pair_i/
        if os.path.exists(rife_output):
            for fname in sorted(os.listdir(rife_output)):
                if fname.endswith(".png"):
                    shutil.copy(
                        os.path.join(rife_output, fname),
                        os.path.join(dest_dir, fname)
                    )
            print(f"[OK] Saved {len(os.listdir(dest_dir))} frames to interpolated/pair_{i}/")
        else:
            print(f"[WARN] No output from RIFE for pair {i}")