from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import ChatmlTokenizer
from fake_api import FakeApi, FakeState

from doctune_nb import evaluate, export
from doctune_nb.api import DocTuneClient, JobConfig
from doctune_nb.data import download_dataset
from doctune_nb.train import TrainResult

# ------------------------------------------------------------------------------------------- ROUGE-L


def test_rouge_l_known_values() -> None:
    # LCS("the cat sat on the mat", "the cat on the mat") = 5; P = 5/5, R = 5/6
    assert evaluate.rouge_l("the cat sat on the mat", "the cat on the mat") == pytest.approx(
        2 * 1 * (5 / 6) / (1 + 5 / 6)
    )
    assert evaluate.rouge_l("A B C", "a b c") == 1.0
    assert evaluate.rouge_l("a b c", "x y z") == 0.0
    assert evaluate.rouge_l("", "a") == 0.0 and evaluate.rouge_l("a", "") == 0.0
    # order matters for LCS: "c b a" vs "a b c" -> LCS 1
    assert evaluate.rouge_l("a b c", "c b a") == pytest.approx(1 / 3)


def test_rouge_l_matches_reference_implementation_example() -> None:
    # values produced by Google's rouge-score package (RougeScorer(["rougeL"]).score(ref, cand).fmeasure)
    s = evaluate.rouge_l("The quick brown fox jumps over the lazy dog", "The quick brown dog jumps on the log.")
    assert s == pytest.approx(0.5882352941176471)
    assert evaluate.rouge_l("the cat sat on the mat", "the cat on the mat") == pytest.approx(0.9090909090909091)
    # difference by design: non-ASCII letters stay inside words here (rouge-score splits them out)
    assert evaluate.rouge_l("héllo wörld 42 times", "héllo world 42") == pytest.approx(
        2 * (2 / 3) * 0.5 / (2 / 3 + 0.5)
    )


def test_lcs_symmetric() -> None:
    a, b = ["a", "b", "c", "d", "e", "f"], ["x", "b", "d", "f", "y"]
    assert evaluate.lcs_length(a, b) == evaluate.lcs_length(b, a) == 3


def test_select_items_seeded_and_capped() -> None:
    convs = [[{"role": "user", "content": str(i)}, {"role": "assistant", "content": "a"}] for i in range(300)]
    a = evaluate.select_items(convs, 100, seed=7)
    b = evaluate.select_items(convs, 100, seed=7)
    assert a == b and len(a) == 100
    assert evaluate.select_items(convs[:5], 100, seed=7) == convs[:5]


# ------------------------------------------------------------------------------------------- eval run


def fake_result(client: DocTuneClient, cfg: JobConfig, tmp_path: Path, model: Any = None) -> TrainResult:
    files = download_dataset(client, cfg, tmp_path)
    return TrainResult(
        model=model,
        tokenizer=ChatmlTokenizer(),
        trainer=None,
        final_step=cfg.max_steps,
        final_loss=0.123,
        runtime_s=60.0,
        data=files,
        workdir=tmp_path,
        use_unsloth=False,
        chat_format="chatml",
    )


def test_eval_generations_schema_and_upload(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    res = fake_result(client, cfg, tmp_path)
    seen: dict[bool, list[str]] = {}

    def gen(prompts: list[str], adapter: bool) -> list[str]:
        seen[adapter] = prompts
        return [("Reference answer " if adapter else "Something else ") + str(i) + "." for i in range(len(prompts))]

    out = evaluate.run(client, cfg, res, generator=gen)
    assert out.n_items == 4
    assert out.rouge_l_tuned == 1.0 and out.rouge_l_base < out.rouge_l_tuned
    assert seen[True] == seen[False] and seen[True][0].endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    rows = [json.loads(line) for line in out.generations_path.read_text().splitlines()]
    assert len(rows) == 4
    for r in rows:
        assert set(r) == {"question", "reference", "base_answer", "tuned_answer"}
        assert all(isinstance(v, str) for v in r.values())
    assert rows[0]["question"].startswith("Eval question") and rows[0]["reference"].startswith("Reference answer")
    uploaded = api.state.artifacts["eval_generations"]["data"].decode().splitlines()
    assert [json.loads(x) for x in uploaded] == rows
    assert out.metrics() == {"rouge_l_base": out.rouge_l_base, "rouge_l_tuned": 1.0}


def test_eval_respects_max_items() -> None:
    state = FakeState(eval_pairs=[(f"q{i}?", f"a{i}") for i in range(30)])
    with FakeApi(state) as api:
        client = DocTuneClient(state.token, api.url, sleep=lambda s: None)
        cfg = client.config()
        cfg.eval_max_items = 10
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            res = fake_result(client, cfg, Path(d))
            out = evaluate.run(client, cfg, res, generator=lambda p, a: ["x"] * len(p))
            assert out.n_items == 10


def test_eval_upload_failure_does_not_raise(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    res = fake_result(client, cfg, tmp_path)
    api.state.inject["/jobs/current/artifacts/upload-url"] = [(409, {"error": "too_large", "message": "big"})]
    out = evaluate.run(client, cfg, res, generator=lambda p, a: ["x"] * len(p))
    assert out.generations_path is None and out.n_items == 4


# ------------------------------------------------------------------------------------------- export


def llama_cfg(client: DocTuneClient) -> JobConfig:
    cfg = client.config()
    cfg.base_model_id = "meta-llama/Llama-3.1-8B-Instruct"
    cfg.is_llama = True
    cfg.base_model_license = "llama3.1"
    return cfg


def test_model_name_llama_prefix(client: DocTuneClient) -> None:
    cfg = client.config()
    assert export.model_name(cfg) == "Qwen3.5-4B-Lumio-Support-Bot"
    cfg = llama_cfg(client)
    assert export.model_name(cfg) == "Llama-3.1-8B-Instruct-Lumio-Support-Bot"
    cfg.base_model_id = "someone/Meta-Llama-3-8B"
    assert export.model_name(cfg).startswith("Llama-3-8B-")
    cfg.base_model_id = "someone/tinyllama-1b"
    assert export.model_name(cfg).startswith("Llama-")


def test_params_b(client: DocTuneClient) -> None:
    cfg = client.config()
    assert export.params_b(cfg) == 4.0
    cfg.base_model_id = "unsloth/Qwen3.5-0.8B"
    assert export.params_b(cfg) == 0.8


def test_write_docs_qwen(client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    cfg.dataset.system_prompt = "Answer like a friendly support agent."
    files = export.write_docs(
        tmp_path,
        cfg,
        kind="GGUF Q4_K_M",
        final_step=10,
        final_loss=0.5,
        metrics={"rouge_l_tuned": 0.6},
        gguf_file="m.gguf",
        license_fetcher=lambda repo, tok: "Apache License 2.0 full text",
    )
    names = {p.name for p in files}
    assert names == {"README.md", "Modelfile", "LICENSE"}
    mf = (tmp_path / "Modelfile").read_text()
    assert "FROM ./m.gguf" in mf
    assert "<|im_start|>assistant\n<think>\n\n</think>\n\n" in mf  # non-thinking, as trained
    assert 'PARAMETER stop "<|im_end|>"' in mf
    assert 'SYSTEM """Answer like a friendly support agent."""' in mf
    rd = (tmp_path / "README.md").read_text()
    assert "unsloth/Qwen3.5-4B" in rd and "apache-2.0" in rd and "ollama create" in rd and "non-thinking" in rd
    assert "Built with Llama" not in rd
    assert (tmp_path / "LICENSE").read_text() == "Apache License 2.0 full text"


def test_write_docs_llama(client: DocTuneClient, tmp_path: Path) -> None:
    cfg = llama_cfg(client)
    files = export.write_docs(tmp_path, cfg, kind="LoRA adapter", license_fetcher=lambda r, t: None)
    assert {p.name for p in files} == {"README.md", "Modelfile", "LICENSE", "NOTICE"}
    assert "Built with Llama" in (tmp_path / "README.md").read_text()
    assert (tmp_path / "README.md").read_text().startswith("# Llama-")
    notice = (tmp_path / "NOTICE").read_text()
    assert notice.startswith("Built with Llama") and "Meta Platforms" in notice
    assert "llama3.1" in (tmp_path / "LICENSE").read_text()  # fallback stub names the license
    mf = (tmp_path / "Modelfile").read_text()
    assert "<|start_header_id|>assistant<|end_header_id|>" in mf and "<think>" not in mf


class FakePeftModel:
    def __init__(self) -> None:
        self.saved: list[str] = []

    def save_pretrained(self, path: str) -> None:
        p = Path(path)
        (p / "adapter_model.safetensors").write_bytes(b"\0" * 1024)
        (p / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path": "unsloth/qwen3.5-4b-x", "r": 8}))
        self.saved.append(path)


class SavingTokenizer(ChatmlTokenizer):
    def save_pretrained(self, path: str) -> None:
        (Path(path) / "tokenizer_config.json").write_text("{}")


def test_upload_adapter_first_then_finish(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    res = fake_result(client, cfg, tmp_path, model=FakePeftModel())
    res.tokenizer = SavingTokenizer()
    ev = evaluate.EvalResult(4, 0.2, 0.6, None, 1.0)
    out = export.upload_adapter_and_finish(client, cfg, res, ev, license_fetcher=lambda r, t: "LICENSE TEXT")
    assert out["ok"] is True
    paths = [r.path for r in api.state.requests if r.method == "POST"]
    assert paths.index("/jobs/current/artifacts/complete") < paths.index("/jobs/current/finish")
    data = api.state.artifacts["adapter_safetensors"]["data"]
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        assert {
            "adapter_model.safetensors",
            "adapter_config.json",
            "tokenizer_config.json",
            "README.md",
            "LICENSE",
        } <= names
        assert json.loads(z.read("adapter_config.json"))["base_model_name_or_path"] == cfg.base_model_id
    finish = api.state.calls("POST", "/jobs/current/finish")[0].json()
    assert finish == {"metrics": {"rouge_l_base": 0.2, "rouge_l_tuned": 0.6}, "exports": {}}
    assert api.state.job_state == "completed"


def test_optional_export_skips_without_drive(client: DocTuneClient, tmp_path: Path, capsys) -> None:
    cfg = client.config()
    calls: list[str] = []
    model = SimpleNamespace(save_pretrained_gguf=lambda *a, **k: calls.append("gguf"))
    res = TrainResult(
        model=model,
        tokenizer=ChatmlTokenizer(),
        trainer=None,
        final_step=10,
        final_loss=0.1,
        runtime_s=1.0,
        data=None,
        workdir=tmp_path,
        use_unsloth=True,
    )
    out = export.export_optional(client, cfg, res, gguf_to="drive", drive_root=str(tmp_path / "nodrive" / "x"))
    assert out == {} and calls == []
    assert "not mounted" in capsys.readouterr().err


def test_optional_export_hf_needs_token(client: DocTuneClient, tmp_path: Path, capsys) -> None:
    cfg = client.config()
    res = TrainResult(
        model=SimpleNamespace(),
        tokenizer=ChatmlTokenizer(),
        trainer=None,
        final_step=10,
        final_loss=0.1,
        runtime_s=1.0,
        data=None,
        workdir=tmp_path,
        use_unsloth=True,
    )
    out = export.export_optional(client, cfg, res, gguf_to="hf", push_merged_to_hf=True, hf_token=None)
    assert out == {} and "HF token" in capsys.readouterr().err


def test_optional_export_large_model_is_experimental(client: DocTuneClient, tmp_path: Path, capsys) -> None:
    cfg = client.config()
    cfg.base_model_id = "unsloth/Qwen3-8B"
    res = TrainResult(
        model=SimpleNamespace(),
        tokenizer=ChatmlTokenizer(),
        trainer=None,
        final_step=10,
        final_loss=0.1,
        runtime_s=1.0,
        data=None,
        workdir=tmp_path,
        use_unsloth=True,
    )
    assert export.export_optional(client, cfg, res, gguf_to="drive") == {}
    assert "experimental" in capsys.readouterr().err


def test_gguf_export_to_drive_dir(api: FakeApi, client: DocTuneClient, tmp_path: Path, monkeypatch) -> None:
    """GGUF path with a fake Unsloth model: file lands in the Drive folder with README/Modelfile/LICENSE."""
    cfg = client.config()

    def fake_gguf(out_dir: str, tok: Any, quantization_method: str) -> None:
        assert quantization_method == "q4_k_m"
        d = Path(out_dir + "_gguf")
        d.mkdir(parents=True)
        (d / "Qwen3.5-4B.Q4_K_M.gguf").write_bytes(b"GGUF")

    model = SimpleNamespace(save_pretrained_gguf=fake_gguf)
    res = TrainResult(
        model=model,
        tokenizer=ChatmlTokenizer(),
        trainer=None,
        final_step=10,
        final_loss=0.1,
        runtime_s=1.0,
        data=None,
        workdir=tmp_path / "w",
        use_unsloth=True,
    )
    (tmp_path / "w").mkdir()
    drive = tmp_path / "MyDrive" / "DocTune"
    drive.mkdir(parents=True)
    monkeypatch.setattr(export, "drive_mounted", lambda root: True)
    monkeypatch.setattr(export, "check_ram", lambda need, what: True)
    monkeypatch.setattr(export, "check_space", lambda path, need, what: True)
    # first an adapter so that finish() is accepted
    f = tmp_path / "a.zip"
    f.write_bytes(b"x")
    client.upload_artifact("adapter_safetensors", f)
    out = export.export_optional(
        client, cfg, res, gguf_to="drive", drive_root=str(drive), license_fetcher=lambda r, t: "L"
    )
    target = drive / "Lumio-Support-Bot" / "gguf"
    assert out == {"drive_path": str(target)}
    assert {p.name for p in target.iterdir()} == {
        "Qwen3.5-4B-Lumio-Support-Bot-Q4_K_M.gguf",
        "README.md",
        "Modelfile",
        "LICENSE",
    }
    assert "FROM ./Qwen3.5-4B-Lumio-Support-Bot-Q4_K_M.gguf" in (target / "Modelfile").read_text()
    assert api.state.calls("POST", "/jobs/current/finish")[-1].json()["exports"] == {"drive_path": str(target)}
