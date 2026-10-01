"""D6 defaults from the first real v1 run on the Mac (owner, 2026-10-01).

48 GB, MAXSEQ 6656: batch 2 and batch 1 both ran out of memory without
gradient checkpointing; with --grad-checkpoint, batch 1 peaked at 12.9 GB and
completed. GRADCKPT=1 and BATCH=1 are the defaults, both overridable.

The recipe is read with `make -n` (print, don't run), so these test what make
would actually execute, not the Makefile's text.
"""
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
DISTILL = REPO / "tools/distill"
MAKEFILE = (DISTILL / "Makefile").read_text()
README = (DISTILL / "README.md").read_text()

needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="GNU make not installed")


def _train_cmd(tmp_path, *overrides):
    out = subprocess.run(["make", "-n", "train", "ADAPTER=probe", f"WORK={tmp_path}", *overrides],
                         cwd=DISTILL, capture_output=True, text=True, timeout=60).stdout
    lines = out.replace("\\\n", " ").splitlines()
    return next(l for l in lines if "mlx_lm.lora" in l)


def test_defaults_in_the_makefile():
    assert re.search(r"^GRADCKPT\s*\?=\s*1\s*$", MAKEFILE, re.M)
    assert re.search(r"^BATCH\s*\?=\s*1\s*$", MAKEFILE, re.M)
    assert re.search(r"^MAXSEQ\s*\?=\s*6656\s*$", MAKEFILE, re.M)


@needs_make
def test_train_checkpoints_gradients_at_batch_1_by_default(tmp_path):
    cmd = _train_cmd(tmp_path)
    assert "--grad-checkpoint" in cmd
    assert "--batch-size 1" in cmd
    assert "--max-seq-length 6656" in cmd


@needs_make
def test_gradckpt_0_turns_it_off_and_batch_is_overridable(tmp_path):
    cmd = _train_cmd(tmp_path, "GRADCKPT=0", "BATCH=2")
    assert "--grad-checkpoint" not in cmd
    assert "--batch-size 2" in cmd


def test_the_readme_documents_the_knobs_and_the_run_outside_make():
    assert "GRADCKPT" in README and "--grad-checkpoint" in README
    assert "12.9 GB" in README
    # a trainer run outside make does not record the adapter for fuse/gguf/ship
    assert re.search(r"outside .?make.?", README, re.I)
    assert "ADAPTER=" in README
