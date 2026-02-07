"""
Webcam Snapshot Capture for GuardianEye.

Replaces the Bambu Lab TLS camera protocol with simple HTTP GET.
Works with any webcam that serves JPEG snapshots (mjpeg-streamer, etc.).
"""

import os
import glob
import logging
import requests

_logger = logging.getLogger("octoprint.plugins.guardianeye.snapshot")

# JPEG magic bytes
_JPEG_MAGIC = b"\xff\xd8"


def capture_snapshot(snapshot_url, output_path, timeout=10):
    """
    Capture a JPEG snapshot from the webcam URL.

    Args:
        snapshot_url: HTTP URL that returns a JPEG image
        output_path: Where to save the file
        timeout: Request timeout in seconds

    Returns:
        Path to the saved snapshot

    Raises:
        ValueError: If response is not a valid JPEG
        requests.RequestException: On network errors
    """
    resp = requests.get(snapshot_url, timeout=timeout, stream=True)
    resp.raise_for_status()

    content = resp.content
    if not content or not content[:2] == _JPEG_MAGIC:
        raise ValueError("Snapshot response is not a valid JPEG image")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(content)

    return output_path


def cleanup_old_snapshots(snapshot_dir, max_keep=100):
    """Delete oldest snapshots beyond the retention limit."""
    pattern = os.path.join(snapshot_dir, "monitor_*.jpg")
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    if len(files) > max_keep:
        for old_file in files[: len(files) - max_keep]:
            try:
                os.remove(old_file)
            except OSError:
                pass


def get_snapshot_url(settings, octoprint_settings=None):
    """
    Determine the snapshot URL to use.

    Priority:
      1. Plugin setting override
      2. OctoPrint webcam snapshot URL
      3. Default mjpeg-streamer URL
    """
    override = settings.get("snapshot_url", "").strip()
    if override:
        return override

    if octoprint_settings is not None:
        try:
            # OctoPrint 1.9+ webcam settings
            webcam_snapshot = octoprint_settings.global_get(["webcam", "snapshot"])
            if webcam_snapshot:
                return webcam_snapshot
        except Exception:
            pass

    return "http://localhost:8080/?action=snapshot"
