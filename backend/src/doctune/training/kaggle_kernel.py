"""The script that runs inside the user's Kaggle kernel (ADR-0002).

`build_source` returns one self-contained Python file: it unpacks our notebook package (embedded as a base64 zip),
installs it with the pinned training stack, and runs `doctune_nb.headless.run`. The job token is part of the source
(Kaggle has no secrets API for API-pushed kernels); the kernel is private to the user's own account, and the token
is job-scoped, expires and is revoked when the job ends. The script never prints it.
"""

import base64
import io
import json
import threading
import uuid
import zipfile
from pathlib import Path

from doctune.core.config import get_settings

_cache_lock = threading.Lock()
_cache: tuple[tuple[str, float], str] | None = None  # ((source dir, newest mtime), base64 zip)

_TEMPLATE = """\
# DocTune training kernel (generated). Runs the pinned training stack headlessly on a Kaggle T4.
import os

os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # Kaggle gives two T4s; train on one

import base64
import io
import json
import subprocess
import sys
import urllib.request
import zipfile

JOB_ID = __JOB_ID__
API_URL = __API_URL__
JOB_TOKEN = __JOB_TOKEN__

print("=" * 60, flush=True)
print("DocTune training run for job " + JOB_ID[:8], flush=True)
print("This kernel was created by DocTune in your own Kaggle account.", flush=True)
print("It stops on its own when training finishes or you cancel in DocTune.", flush=True)
print("=" * 60, flush=True)

os.environ["PYTHONUNBUFFERED"] = "1"  # the work dir defaults to /kaggle/working/doctune (headless.py)

PKG_B64 = (
__PKG_LINES__
)


def report_fatal(message):
    try:
        req = urllib.request.Request(
            API_URL.rstrip("/") + "/jobs/current/fail",
            data=json.dumps({"error": message[:1900], "fatal": True}).encode(),
            headers={"Authorization": "Bearer " + JOB_TOKEN, "Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=30).close()
    except Exception as exc:  # the failure is already printed above
        print("Could not report the failure to DocTune: " + type(exc).__name__, flush=True)


SRC = "/tmp/doctune_nb_src"
zipfile.ZipFile(io.BytesIO(base64.b64decode(PKG_B64))).extractall(SRC)
print("Installing the training stack (a few minutes)...", flush=True)
install = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", SRC + "[train]"], capture_output=True, text=True
)
if install.returncode != 0:
    tail = (install.stdout + install.stderr)[-1500:]
    print(tail, flush=True)
    report_fatal("Installing the training libraries failed on Kaggle: " + tail[-300:])
    raise SystemExit(1)

from doctune_nb.headless import run  # noqa: E402

raise SystemExit(run(token=JOB_TOKEN, api_url=API_URL))
"""


def _package_files(src: Path) -> list[Path]:
    files = [src / "pyproject.toml", *sorted((src / "doctune_nb").rglob("*.py"))]
    readme = src / "README.md"
    if readme.exists():  # pyproject.toml names it as the package readme, so the build needs it
        files.append(readme)
    return files


def package_zip_b64(src: Path | None = None) -> str:
    """Base64 zip of the notebook package, rebuilt only when a source file changes."""
    global _cache
    src = src or get_settings().notebook_src_dir
    files = _package_files(src)
    if not (src / "pyproject.toml").exists():
        raise FileNotFoundError(f"notebook package not found in {src}")
    key = (str(src), max(f.stat().st_mtime for f in files))
    with _cache_lock:
        if _cache is not None and _cache[0] == key:
            return _cache[1]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                if "__pycache__" in f.parts:
                    continue
                zf.write(f, f.relative_to(src).as_posix())
        encoded = base64.b64encode(buf.getvalue()).decode()
        _cache = (key, encoded)
        return encoded


def build_source(job_token: str, api_url: str, job_id: str | uuid.UUID) -> str:
    encoded = package_zip_b64()
    lines = "\n".join(f"    {json.dumps(encoded[i : i + 100])}" for i in range(0, len(encoded), 100))
    return (
        _TEMPLATE.replace("__JOB_ID__", json.dumps(str(job_id)))
        .replace("__API_URL__", json.dumps(api_url))
        .replace("__JOB_TOKEN__", json.dumps(job_token))
        .replace("__PKG_LINES__", lines)
    )


def session_timeout_seconds(est_minutes: float) -> int:
    """Bound the kernel's runtime: twice the estimate plus 45 minutes, never more than Kaggle's 12 hours."""
    return int(min(12 * 3600, (est_minutes * 2 + 45) * 60))
