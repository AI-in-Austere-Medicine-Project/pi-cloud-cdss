"""D6 bench, A22 context (owner, 2026-10-08): the next distillation bench must
not run its local arm truncated.

A22 makes every local call through providers ask Ollama for num_ctx 8192 with
truncate false. bench_remote.sh's two arms go through the target snapshot's
providers, so they get it; its tok/s probe calls /api/generate directly, with
no num_ctx: that loads the model at Ollama's default 4096 (a different setting
from the arms, and a 65 s reload when the arms start) and would cut any prompt
over the context silently. The probe now asks for the arms' context and
refuses to truncate; the script exports one value for every local client and
records it in meta.json.
"""
import pathlib
import re

DISTILL = pathlib.Path(__file__).resolve().parents[2] / "tools" / "distill"
SH = (DISTILL / "jetson" / "bench_remote.sh").read_text()


def _probe():
    return SH[SH.index("# ── generation tok/s"):SH.index("# ── the 30-scenario set")]


def test_the_script_exports_one_context_for_every_local_client():
    assert re.search(r'export CDSS_LOCAL_NUM_CTX="?\$\{CDSS_LOCAL_NUM_CTX:-8192\}"?', SH)


def test_the_probe_asks_for_that_context_and_refuses_to_truncate():
    probe = _probe()
    assert "num_ctx" in probe and "CDSS_LOCAL_NUM_CTX" in probe
    assert '"truncate": False' in probe


def test_the_bench_records_the_context():
    meta = SH[SH.index("json.dump({"):SH.index("open(f\"{W}/meta.json\"")]
    assert "num_ctx" in meta
