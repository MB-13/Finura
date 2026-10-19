"""The .ipynb is valid nbformat 4, every code cell parses, and it follows the Colab free-tier rules."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from doctune_nb import __version__

NB = Path(__file__).resolve().parent.parent / "doctune_train.ipynb"


@pytest.fixture(scope="module")
def nb() -> dict:
    return json.loads(NB.read_text(encoding="utf-8"))


def code_cells(nb: dict) -> list[str]:
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def python_only(src: str) -> str:
    return "\n".join("" if line.lstrip().startswith(("%", "!")) else line for line in src.splitlines())


def test_valid_nbformat(nb: dict) -> None:
    assert nb["nbformat"] == 4
    try:
        import nbformat
    except ImportError:  # pragma: no cover
        return
    nbformat.validate(nbformat.reads(NB.read_text(), as_version=4))


def test_every_code_cell_parses(nb: dict) -> None:
    for src in code_cells(nb):
        ast.parse(python_only(src))


def test_install_pins_this_version(nb: dict) -> None:
    install = code_cells(nb)[0]
    m = re.search(r'"doctune-nb\[train\] @ git\+https://github\.com/[^@]+@nb-v([\d.]+)#subdirectory=notebook"', install)
    assert m and m.group(1) == __version__


def test_tokens_via_getpass_never_printed(nb: dict) -> None:
    src = "\n".join(code_cells(nb))
    assert 'getpass("Paste your DocTune job token: ")' in src
    assert "HF_TOKEN = getpass(" in src
    for line in src.splitlines():
        if "print(" in line:
            assert not re.search(r"print\([^)]*\b(HF_TOKEN|JOB_TOKEN|token)\b\s*[),]", line), line
    assert "API_URL = " in src and "RELEASE" in src


def test_no_free_tier_violations(nb: dict) -> None:
    src = "\n".join(code_cells(nb)).lower()
    for banned in (
        "ngrok",
        "cloudflared",
        "localtunnel",
        "while true",
        "javascript",
        "gradio",
        "streamlit",
        "flask",
        "uvicorn",
        "threading",
        "ssh ",
        "keep_alive",
        "keepalive",
        "setinterval",
    ):
        assert banned not in src, banned


def test_cells_in_plan_order(nb: dict) -> None:
    src = code_cells(nb)
    order = [
        "%pip install",
        "DocTuneClient(",
        "dt_env.check(client)",
        "client.config()",
        "HF_TOKEN",
        "drive.mount",
        "train.run(",
        "evaluate.run(",
        "upload_adapter_and_finish(",
        "export_optional(",
    ]
    positions = [next(i for i, s in enumerate(src) if key in s) for key in order]
    assert positions == sorted(positions)
    first_md = "".join(nb["cells"][0]["source"])
    assert "T4 GPU" in first_md and "keep this tab open" in first_md
