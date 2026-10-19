"""Runtime detection: GPU, VRAM, platform, library versions, work directory, free RAM/disk.

Portable: works on Colab, and on any Python + GPU + internet machine (Kaggle / Lightning / local later).
"""

from __future__ import annotations

import os
import platform as _platform
import shutil
import sys
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doctune_nb import __version__, ui

if TYPE_CHECKING:
    from doctune_nb.api import DocTuneClient

TRACKED_LIBS = ("unsloth", "unsloth_zoo", "torch", "transformers", "trl", "peft", "bitsandbytes")


class NoGPU(ui.StopNotebook):
    pass


@dataclass
class Env:
    has_gpu: bool
    gpu_name: str | None
    vram_gb: float | None
    bf16_supported: bool
    platform: str
    python: str
    torch: str | None
    cuda: str | None

    @property
    def is_t4(self) -> bool:
        return bool(self.gpu_name and "T4" in self.gpu_name)

    def runtime(self) -> dict[str, Any]:
        """Body for POST /start `runtime`."""
        return {
            "gpu_name": (self.gpu_name or None) and self.gpu_name[:100],
            "vram_gb": self.vram_gb,
            "platform": self.platform[:50],
            "python": self.python[:20],
            "torch": (self.torch or None) and self.torch[:40],
            "cuda": (self.cuda or None) and self.cuda[:20],
            "notebook_version": __version__,
        }

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_platform() -> str:
    if "google.colab" in sys.modules or os.environ.get("COLAB_RELEASE_TAG") or os.environ.get("COLAB_GPU"):
        return "colab"
    if os.environ.get("KAGGLE_KERNEL_RUN_TYPE"):
        return "kaggle"
    if os.environ.get("LIGHTNING_CLOUD_PROJECT_ID"):
        return "lightning"
    return "local"


def detect() -> Env:
    """Detect the GPU with torch (imported lazily). No torch or no CUDA -> has_gpu False."""
    torch_version = cuda = gpu = None
    vram = None
    has_gpu = bf16 = False
    try:
        import torch

        torch_version = torch.__version__
        cuda = torch.version.cuda
        if torch.cuda.is_available():
            has_gpu = True
            gpu = torch.cuda.get_device_name(0)
            vram = round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2)
            bf16 = bool(torch.cuda.is_bf16_supported())
    except ImportError:
        pass
    return Env(
        has_gpu=has_gpu,
        gpu_name=gpu,
        vram_gb=vram,
        bf16_supported=bf16,
        platform=detect_platform(),
        python=_platform.python_version(),
        torch=torch_version,
        cuda=cuda,
    )


def check(client: DocTuneClient | None = None, *, step: int | None = None, detect_fn: Any = detect) -> Env:
    """Cell 3. Shows the GPU; without one, reports pause(no_gpu) to DocTune and stops the notebook."""
    env = detect_fn()
    if not env.has_gpu:
        if client is not None:
            try:
                client.pause("no_gpu", step)
            except Exception as exc:  # the message below matters more than the report
                ui.warn(f"Could not tell DocTune about the missing GPU: {exc}")
        ui.error(ui.NO_GPU_HELP)
        raise NoGPU("No GPU available. " + ui.NO_GPU_HELP)
    ui.info(f"GPU: {env.gpu_name} ({env.vram_gb} GB), platform: {env.platform}, Python {env.python}, torch {env.torch}")
    if not env.is_t4:
        ui.warn(f"This GPU is {env.gpu_name}, not a T4. DocTune is tuned for a T4; training should still work.")
    return env


def installed_versions(names: tuple[str, ...] = TRACKED_LIBS) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for name in names:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def version_mismatches(expected: dict[str, str], installed: dict[str, str | None] | None = None) -> dict[str, tuple]:
    """{lib: (expected, installed)} where they differ (local labels like +cu130 are ignored)."""
    installed = installed if installed is not None else installed_versions(tuple(expected))
    out = {}
    for name, want in expected.items():
        have = installed.get(name)
        if have is None or have.split("+")[0] != want.split("+")[0]:
            out[name] = (want, have)
    return out


def warn_version_mismatches(expected: dict[str, str]) -> dict[str, tuple]:
    mism = version_mismatches(expected)
    for name, (want, have) in mism.items():
        ui.warn(
            f"{name} {have or 'not installed'} is installed, but this job was set up for {want}. "
            "Resuming with different versions can change results."
        )
    return mism


def workdir() -> Path:
    """Where data/checkpoints/exports go. /content/doctune on Colab, ~/doctune elsewhere (override: DOCTUNE_WORKDIR)."""
    if os.environ.get("DOCTUNE_WORKDIR"):
        root = Path(os.environ["DOCTUNE_WORKDIR"])
    elif Path("/content").is_dir() and detect_platform() == "colab":
        root = Path("/content/doctune")
    else:
        root = Path.home() / "doctune"
    root.mkdir(parents=True, exist_ok=True)
    return root


def free_disk_bytes(path: str | os.PathLike[str]) -> int:
    return shutil.disk_usage(path).free


def available_ram_bytes() -> int | None:
    try:
        import psutil

        return int(psutil.virtual_memory().available)
    except ImportError:
        pass
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None
