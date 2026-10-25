"""V1: per-turn stage timestamps, for the voice latency baseline.

Owner, 2026-10-25: "Instrument the pipeline with timestamps at: request
received, pre-gate done, retrieval done, doses built, LLM first token, LLM
last token, validator done, response sent. Log them per turn in the session
log." No behaviour change: nothing here is read by the pipeline, and nothing
in the pipeline may branch on it.

A turn is a plain dict. main.py starts one when the request arrives and hands
it to query_with_rag, which activates it in the worker thread; the pipeline
marks stages on whatever turn is active. With no active turn (tests, a direct
caller), mark() does nothing.

Every time is time.perf_counter(); the log carries offsets in ms from
request_received. A stage the turn never reached (a deterministic card makes
no retrieval and no model call) is null, present and null, so it is never
read as zero.
"""
import contextvars
import time
from typing import Optional

STAGES = ("request_received", "pre_gate_done", "retrieval_done", "doses_built",
          "llm_first_token", "llm_last_token", "validator_done", "response_sent")

_TURN: contextvars.ContextVar = contextvars.ContextVar("v1_latency_turn", default=None)


def start(origin: str = "http", t: Optional[float] = None) -> dict:
    """A new turn, request_received now (or at `t`). Not yet active here."""
    t0 = time.perf_counter() if t is None else t
    return {"origin": origin, "t0": t0, "marks": {"request_received": t0},
            "llm_first_token_source": None, "deferred_log": None}


def activate(turn: Optional[dict]) -> None:
    _TURN.set(turn)


def current() -> Optional[dict]:
    return _TURN.get()


def mark(stage: str, t: Optional[float] = None) -> None:
    """The first time a stage is reached wins."""
    turn = _TURN.get()
    if turn is not None:
        turn["marks"].setdefault(stage, time.perf_counter() if t is None else t)


def mark_last(stage: str, t: float) -> None:
    """The last time wins: llm_last_token is the end of the last generator call."""
    turn = _TURN.get()
    if turn is not None:
        turn["marks"][stage] = t


def record(turn: Optional[dict]) -> Optional[dict]:
    """The log's `timings` object: ms from request_received per stage, null
    where not reached, and where the first-token time came from."""
    if turn is None:
        return None
    t0 = turn["t0"]
    out = {s: (round((turn["marks"][s] - t0) * 1000, 1) if s in turn["marks"] else None)
           for s in STAGES}
    out["llm_first_token_source"] = turn.get("llm_first_token_source")
    out["origin"] = turn.get("origin")
    return out


def finish(turn: Optional[dict]) -> None:
    """main.py, as the response leaves its hands: response_sent, then the log
    line query_with_rag deferred to now. Runs the log write once."""
    if turn is None:
        return
    turn["marks"].setdefault("response_sent", time.perf_counter())
    write, turn["deferred_log"] = turn.get("deferred_log"), None
    if write is not None:
        write()
