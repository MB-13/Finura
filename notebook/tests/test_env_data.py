from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ChatmlTokenizer
from fake_api import FakeApi

from doctune_nb import env as env_mod
from doctune_nb import ui
from doctune_nb.api import DocTuneClient
from doctune_nb.data import (
    DatasetError,
    detect_chat_format,
    download_dataset,
    load_jsonl,
    render_chat,
    split_prompt,
    strip_thinking,
)


def no_gpu() -> env_mod.Env:
    return env_mod.Env(False, None, None, False, "colab", "3.12.0", "2.11.0", None)


def t4() -> env_mod.Env:
    return env_mod.Env(True, "Tesla T4", 15.64, False, "colab", "3.12.0", "2.11.0+cu130", "13.0")


# ------------------------------------------------------------------------------------------- env


def test_no_gpu_pauses_job_and_stops(api: FakeApi, client: DocTuneClient, capsys) -> None:
    with pytest.raises(env_mod.NoGPU) as exc:
        env_mod.check(client, detect_fn=no_gpu)
    assert api.state.calls("POST", "/jobs/current/pause")[0].json() == {"reason": "no_gpu"}
    assert "T4 GPU" in exc.value.message
    assert exc.value._render_traceback_()[0].startswith("[DocTune]")
    assert "Runtime -> Change runtime type" in capsys.readouterr().err


def test_no_gpu_message_even_if_api_down(api: FakeApi, client: DocTuneClient) -> None:
    api.state.inject["/jobs/current/pause"] = [(500, {})] * 10
    with pytest.raises(env_mod.NoGPU):
        env_mod.check(client, detect_fn=no_gpu)


def test_gpu_ok(api: FakeApi, client: DocTuneClient) -> None:
    e = env_mod.check(client, detect_fn=t4)
    assert e.is_t4 and api.state.calls("POST", "/jobs/current/pause") == []
    rt = e.runtime()
    assert rt["gpu_name"] == "Tesla T4" and rt["notebook_version"] == "0.1.0" and rt["cuda"] == "13.0"


def test_detect_without_torch_reports_no_gpu() -> None:
    e = env_mod.detect()
    if "torch" not in sys.modules:
        assert e.has_gpu is False


def test_version_mismatch() -> None:
    got = env_mod.version_mismatches(
        {"torch": "2.11.0", "trl": "1.13.0", "peft": "0.21.1"},
        {"torch": "2.11.0+cu130", "trl": "1.14.0", "peft": None},
    )
    assert got == {"trl": ("1.13.0", "1.14.0"), "peft": ("0.21.1", None)}


def test_package_imports_without_gpu_stack() -> None:
    code = (
        "import sys, doctune_nb\n"
        "from doctune_nb import api, env, data, callbacks, train, evaluate, export, ui\n"
        "bad = [m for m in ('torch','transformers','trl','unsloth','peft','datasets') if m in sys.modules]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_pause_messages_match_design_doc() -> None:
    assert ui.pause_message("session_ended", 64, 100) == (
        "Your Colab session ended at 64%. Progress is saved. Open the notebook and run it again to continue."
    )
    assert ui.pause_message("no_gpu", 32, 50).startswith("Colab has no free GPU for your account right now. ")
    assert "64%" in ui.pause_message("idle_timeout", 64, 100)
    assert (
        ui.pause_message("stopped", 0, 0) == "Training stopped at 0%. Progress is saved. Run the notebook again "
        "to continue."
    )


# ------------------------------------------------------------------------------------------- data


def test_download_dataset_verifies_and_reuses(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    files = download_dataset(client, cfg, tmp_path)
    assert len(load_jsonl(files.train)) == 16 and len(load_jsonl(files.eval)) == 4
    download_dataset(client, cfg, tmp_path)
    assert len(api.state.calls("GET", "/storage/d/train.jsonl")) == 1  # verified local copy reused


def test_download_dataset_sha_mismatch(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    api.state.storage["d/train.jsonl"] += b"\n"
    with pytest.raises(Exception, match="checksum"):
        download_dataset(client, cfg, tmp_path)


@pytest.mark.parametrize(
    ("line", "msg"),
    [
        ("not json", "not valid JSON"),
        ('{"messages": []}', "no messages"),
        ('{"messages": [{"role": "robot", "content": "x"}]}', "invalid message"),
        ('{"messages": [{"role": "user", "content": "q"}]}', "assistant"),
    ],
)
def test_load_jsonl_validates(tmp_path: Path, line: str, msg: str) -> None:
    p = tmp_path / "d.jsonl"
    p.write_text(line + "\n")
    with pytest.raises(DatasetError, match=msg):
        load_jsonl(p)


def test_render_chat_non_thinking(chatml_tok: ChatmlTokenizer) -> None:
    conv = [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    text = render_chat(chatml_tok, conv)
    assert chatml_tok.calls[-1]["enable_thinking"] is False
    assert "<|im_start|>assistant\n<think>\n\n</think>\n\nHello<|im_end|>" in text
    prompt_msgs, ref = split_prompt(conv)
    assert ref == "Hello"
    prompt = render_chat(chatml_tok, prompt_msgs, add_generation_prompt=True)
    assert prompt.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")


def test_render_chat_template_without_thinking_kw() -> None:
    tok = ChatmlTokenizer(thinking_kw=False)
    text = render_chat(tok, [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])
    assert "<think>" not in text and "<|im_start|>assistant\nb" in text


def test_processor_with_inner_tokenizer(chatml_tok: ChatmlTokenizer) -> None:
    class Processor:
        tokenizer = chatml_tok

    assert detect_chat_format(Processor()) == "chatml"


def test_detect_unknown_format() -> None:
    class Plain:
        def apply_chat_template(self, messages, **kw):
            return " ".join(m["content"] for m in messages)

    assert detect_chat_format(Plain()) is None


def test_strip_thinking() -> None:
    assert strip_thinking("<think>\n\n</think>\n\nAnswer.") == "Answer."
    assert strip_thinking("<think>long reasoning</think> Answer") == "Answer"
    assert strip_thinking("  plain ") == "plain"


def test_jsonl_roundtrip_from_server_format(tmp_path: Path) -> None:
    p = tmp_path / "x.jsonl"
    p.write_text(
        json.dumps(
            {"messages": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}], "id": "extra"}
        )
        + "\n\n"
    )
    assert load_jsonl(p) == [[{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]]
