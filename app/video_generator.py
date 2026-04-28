import subprocess
import os
import shutil

def prepare_all_frames(num_frames=5):
    """
    Merge original frames + interpolated frames into all_frames/ in order.
    Pattern: [frame_0] [interp pair_0] [frame_1] [interp pair_1] ... [frame_N]
    """
    os.makedirs("all_frames", exist_ok=True)

    # Clear previous run
    for f in os.listdir("all_frames"):
        os.remove(os.path.join("all_frames", f))

    idx = 0
    num_pairs = num_frames - 1

    for i in range(num_pairs):
        # Copy original frame i
        src = f"frames/frame_{i:02d}.png"
        if os.path.exists(src):
            shutil.copy(src, f"all_frames/frame_{idx:04d}.png")
            idx += 1
        else:
            print(f"[WARN] Missing {src}")

        # Copy interpolated frames for pair i (skip first & last — they ARE frame_i & frame_i+1)
        interp_dir = f"interpolated/pair_{i}"
        if os.path.exists(interp_dir):
            files = sorted(f for f in os.listdir(interp_dir) if f.endswith(".png"))
            # RIFE outputs: img0.png (=frame_i), img1..imgN-1 (interpolated), imgN.png (=frame_i+1)
            # Skip first and last to avoid duplicates
            middle_files = files[1:-1]
            for fname in middle_files:
                shutil.copy(
                    os.path.join(interp_dir, fname),
                    f"all_frames/frame_{idx:04d}.png"
                )
                idx += 1
        else:
            print(f"[WARN] Missing interpolated/pair_{i}/")

    # Append the final original frame (frame_04.png)
    last_frame = f"frames/frame_{num_pairs:02d}.png"
    if os.path.exists(last_frame):
        shutil.copy(last_frame, f"all_frames/frame_{idx:04d}.png")
        idx += 1

    print(f"[OK] Total frames assembled: {idx}")


def create_video(fps=5):
    """Combine all_frames/ into a smooth MP4 using ffmpeg."""
    os.makedirs("output", exist_ok=True)
    output_path = "output/satellite_video.mp4"

    # Remove old video if exists
    if os.path.exists(output_path):
        os.remove(output_path)

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", "all_frames/frame_%04d.png",
            "-vcodec", "libx264",
            "-crf", "18",           # quality (lower = better, 18 is near-lossless)
            "-pix_fmt", "yuv420p",  # required for browser/QuickTime compatibility
            output_path
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"[ERROR] ffmpeg failed:\n{result.stderr}")
    else:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[OK] Video created: {output_path} ({size_mb:.2f} MB)")