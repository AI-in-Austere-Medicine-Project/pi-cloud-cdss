"""D6 gap (owner, 2026-10-01): rows are 4,300-5,600 tokens (a ~5,000-token
system prompt) and mlx_lm.lora's default max_seq_length of 2048 truncated the
tail, which is the answer. The Makefile now trains with --max-seq-length
$(MAXSEQ) (default 6656: v1's longest row is 6,537), and preflight measures the longest row in DATA with
the base tokenizer's chat template and refuses if it exceeds MAXSEQ.

Offline: the tokenizer is a stand-in; the real one is loaded on the Mac.
"""
import argparse
import importlib.util
import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
MAKEFILE = (REPO / "tools/distill/Makefile").read_text()

spec = importlib.util.spec_from_file_location("d6", REPO / "tools/distill/d6.py")
d6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d6)


def _row(system_words, answer_words):
    return {"messages": [{"role": "system", "content": "w " * system_words},
                         {"role": "user", "content": "Clinical query: q"},
                         {"role": "assistant", "content": "a " * answer_words}]}


def _data(tmp_path, train, valid):
    for name, rows in (("train", train), ("valid", valid)):
        (tmp_path / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return tmp_path


def count_words(messages):
    return sum(len(m["content"].split()) for m in messages)


# ── the Makefile ────────────────────────────────────────────────────────────
def test_maxseq_defaults_to_6656_and_can_be_overridden():
    # Owner, 2026-10-01: raise the limit and keep v1's longest row (6,537 tokens).
    assert re.search(r"^MAXSEQ\s*\?=\s*6656\s*$", MAKEFILE, re.M)


def test_train_passes_max_seq_length():
    train = MAKEFILE.split("\ntrain:")[1].split("\n\n")[0]
    assert "--max-seq-length $(MAXSEQ)" in train
    assert "mlx_lm.lora" in train


def test_preflight_measures_the_longest_row_with_the_base_tokenizer():
    pre = MAKEFILE.split("\npreflight:")[1].split("\n\n")[0]
    assert "d6.py seqlen $(BASE_4BIT) $(DATA_DIR) $(MAXSEQ)" in pre
    # train depends on preflight, so the check runs before every training run
    assert re.search(r"^train: preflight\b", MAKEFILE, re.M)


# ── the check ───────────────────────────────────────────────────────────────
def test_refuses_when_the_longest_row_exceeds_maxseq(tmp_path, capsys):
    data = _data(tmp_path, [_row(100, 10), _row(5000, 600)], [_row(200, 10)])
    with pytest.raises(SystemExit) as e:
        d6.check_seqlen(data, 4096, count_words)
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "train.jsonl:2" in err and "5603" in err and "4096" in err


def test_passes_and_reports_when_every_row_fits(tmp_path, capsys):
    data = _data(tmp_path, [_row(100, 10), _row(4000, 300)], [_row(200, 10)])
    d6.check_seqlen(data, 6144, count_words)
    out = capsys.readouterr().out
    assert "longest 4303" in out and "train.jsonl:2" in out and "6144" in out


def test_a_row_exactly_at_maxseq_fits_and_one_over_does_not(tmp_path):
    # 100 system words + "Clinical query: q" (3) + an empty answer = 103
    data = _data(tmp_path, [_row(100, 0)], [_row(98, 0)])
    d6.check_seqlen(data, 103, count_words)
    with pytest.raises(SystemExit):
        d6.check_seqlen(data, 102, count_words)


def test_reports_how_many_rows_the_trainer_default_would_cut(tmp_path, capsys):
    data = _data(tmp_path, [_row(3000, 300), _row(100, 10)], [_row(2500, 300)])
    d6.check_seqlen(data, 6144, count_words)
    assert "over 2048 (mlx_lm.lora's default): 2" in capsys.readouterr().out


# ── the count is the chat template the trainer uses ────────────────────────
class _Tok:
    def __init__(self, shape):
        self.shape = shape

    def apply_chat_template(self, messages, tokenize=False, **kw):
        assert tokenize is True
        ids = list(range(count_words(messages) + 3 * len(messages)))  # role markers
        return {"input_ids": ids} if self.shape == "dict" else ids


@pytest.mark.parametrize("shape", ["list", "dict"])
def test_counts_with_the_tokenizers_chat_template(shape):
    count = d6.chat_token_counter(_Tok(shape))
    msgs = _row(10, 5)["messages"]
    assert count(msgs) == count_words(msgs) + 9
