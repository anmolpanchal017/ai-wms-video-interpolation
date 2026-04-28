"""
generate_frames.py
Fetch a time-series of satellite images using the 4-tier priority chain:
  1. ISRO VEDAS  (INSAT-3D sub-hourly — 30 min intervals)
  2. Bhuvan NRSC (ISRO WMS — static, no TIME, great for demos)
  3. NASA GIBS   (MODIS Terra / VIIRS — daily composites)
  4. Synthetic   (generated locally, offline fallback)

PROBE STRATEGY:
  We send ONE test request per source BEFORE committing to fetch all frames.
  If the probe fails → skip that source entirely (no wasted timeouts).
"""

from datetime import datetime, timedelta
import os

from app.wms_fetcher import (
    ISRO_VEDAS_SOURCES,
    BHUVAN_SOURCES,
    NASA_GIBS_SOURCES,
    probe_source,
    _try_fetch_one,
    _make_synthetic_frame,
)

# Hardcoded fallback lists removed as we now use user-provided date/time


def _fetch_sequence(sources, start_dt, num_frames, out_dir, bbox=None, width=1024, height=1024, interval_days=0, interval_minutes=30):
    """
    Fetch `num_frames` images from `sources` at regular time intervals.
    Tries each source per frame and returns count of successful fetches.
    """
    ok = 0
    for i in range(num_frames):
        dt = start_dt + timedelta(days=i * interval_days,
                                  minutes=i * interval_minutes if interval_days == 0 else 0)
        
        # Round dt to nearest 30 minutes for VEDAS to prevent 404s
        minute = (dt.minute // 30) * 30
        dt = dt.replace(minute=minute, second=0, microsecond=0)

        time_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        path = os.path.join(out_dir, f"frame_{i:02d}.png")

        for src in sources:
            if _try_fetch_one(src, time_str, path, bbox, width, height):
                print(f"    ✅ [{src['name']}] frame_{i:02d}.png")
                ok += 1
                break
        else:
            # All sources failed for this frame slot
            pass

    return ok


def generate_frames(out_dir="frames", num_frames=5, bbox=None, width=1024, height=1024, date_str="2024-03-15", start_time_str="06:00:00", end_time_str="08:00:00"):
    """
    Fetch satellite frames using 4-tier priority with robust fallback to ensure real images.
    """
    os.makedirs(out_dir, exist_ok=True)
    source_used = None

    try:
        # Add seconds if missing
        if start_time_str.count(":") == 1: start_time_str += ":00"
        if end_time_str.count(":") == 1: end_time_str += ":00"
        
        start_dt = datetime.strptime(f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(f"{date_str} {end_time_str}", "%Y-%m-%d %H:%M:%S")
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(hours=2)
    except ValueError:
        start_dt = datetime(2024, 3, 15, 6, 0)
        end_dt = datetime(2024, 3, 15, 8, 0)

    # Calculate interval minutes to fit num_frames between start and end
    total_mins = (end_dt - start_dt).total_seconds() / 60.0
    calc_interval = int(total_mins / max(1, num_frames - 1))
    if calc_interval < 30:
        calc_interval = 30 # Minimum 30 min for ISRO

    # Round start_dt to nearest 30 mins
    minute = (start_dt.minute // 30) * 30
    start_dt = start_dt.replace(minute=minute, second=0, microsecond=0)
    probe_time = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Priority 1: ISRO VEDAS ─────────────────────────────────────────────────
    print("\n  🛰️  [Priority 1] ISRO VEDAS (INSAT-3D)")
    vedas_alive = False

    for src in ISRO_VEDAS_SOURCES:
        print(f"    Probing {src['name']}...", end=" ")
        
        # Try finding a valid time by walking back up to 2 times
        probe_success = False
        test_dt = start_dt
        for attempt in range(2):
            test_probe_time = test_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            if probe_source(src, test_probe_time, bbox, width, height):
                probe_success = True
                start_dt = test_dt # Use this valid start time
                break
            test_dt -= timedelta(minutes=30)
            
        if probe_success:
            print("✅ alive!")
            vedas_alive = True
            print(f"    Fetching from {start_dt.strftime('%Y-%m-%d %H:%M')} UTC (interval {calc_interval}m)...")
            ok = _fetch_sequence([src], start_dt, num_frames, out_dir, bbox, width, height,
                                 interval_days=0, interval_minutes=calc_interval)
            if ok > 0:
                source_used = "ISRO VEDAS"
                break
        else:
            print("❌ dead")

    if source_used:
        print(f"\n  📦 Source: {source_used}")
        return _summary(out_dir)

    if vedas_alive:
        print("    ⚠️  VEDAS probed OK but incomplete data — falling through")

    # ── Priority 2: Bhuvan NRSC (ISRO) ────────────────────────────────────────
    print("\n  🗺️  [Priority 2] Bhuvan NRSC (ISRO Geoportal)")
    for src in BHUVAN_SOURCES:
        print(f"    Probing {src['name']}...", end=" ")
        if probe_source(src, None, bbox, width, height):
            print("✅ alive!")
            # Bhuvan has no TIME support → fetch same frame 5 times
            # (still valid for showing the region; interpolation adds smooth transitions)
            print("    Note: Bhuvan has no TIME param — fetching static frames")
            ok = 0
            for i in range(num_frames):
                path = os.path.join(out_dir, f"frame_{i:02d}.png")
                if _try_fetch_one(src, None, path, bbox, width, height):
                    print(f"    ✅ frame_{i:02d}.png (static)")
                    ok += 1
            if ok > 0:
                source_used = "Bhuvan NRSC (ISRO)"
                break
        else:
            print("❌ dead")

    if source_used:
        print(f"\n  📦 Source: {source_used}")
        return _summary(out_dir)

    # ── Priority 3: NASA GIBS ─────────────────────────────────────────────────
    if not source_used:
        print("\n  🌍  [Priority 3] NASA GIBS (MODIS Terra / VIIRS)")
        for src in NASA_GIBS_SOURCES:
            print(f"    Probing {src['name']}...", end=" ")
            
            # GIBS needs real dates. Try up to 2 days back.
            probe_success = False
            gibs_start_dt = start_dt
            for attempt in range(2):
                test_probe_time = gibs_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                if probe_source(src, test_probe_time, bbox, width, height):
                    probe_success = True
                    break
                gibs_start_dt -= timedelta(days=1)
                
            if probe_success:
                print("✅ alive!")
                print(f"    Fetching from {gibs_start_dt.strftime('%Y-%m-%d')} (daily steps)...")
                ok = _fetch_sequence([src], gibs_start_dt, num_frames, out_dir, bbox, width, height,
                                     interval_days=1, interval_minutes=0)
                if ok > 0:
                    source_used = "NASA GIBS"
                    break
            else:
                print("❌ dead")

    if source_used:
        print(f"\n  📦 Source: {source_used}")
        return _summary(out_dir)

    # ── Priority 4: Synthetic fallback ────────────────────────────────────────
    print("\n  ⚠️  [Priority 4] All WMS sources unavailable — generating synthetic frames")
    print("     Pipeline will work identically; swap real data when WMS is back online")
    for i in range(num_frames):
        _make_synthetic_frame(os.path.join(out_dir, f"frame_{i:02d}.png"), i)
    source_used = "Synthetic (offline)"

    print(f"\n  📦 Source: {source_used}")
    return _summary(out_dir)


def _summary(out_dir):
    saved = [f for f in os.listdir(out_dir) if f.endswith(".png")]
    print(f"  📁 Frames saved: {len(saved)} PNG files in {out_dir}/")
    return len(saved)