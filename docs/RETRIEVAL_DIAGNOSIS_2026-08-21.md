# Why burn queries fell through to general reference

**2026-08-21.** Burn scenario testing. The clinical router named *Burn Wound
Management in Prolonged Field Care* with HIGH confidence, the corpus held 233
burn chunks across two CPGs, and retrieval still reported:

```
📚 INSUFFICIENT (top: 0.055)
📚 GENERAL_MEDICAL (top: 0.151)
```

so the answers came from general medical knowledge instead of the guideline that
was sitting in the index.

## Method

The live ChromaDB (`server/cache/chromadb`, 8,559 chunks) was copied read-only
and every chunk re-embedded with the same model the server uses —
`all-MiniLM-L6-v2`, from the same `~/.cache/chroma` ONNX file, with Chroma's own
pipeline (256-token truncation, attention-masked mean pooling, L2 normalisation).
Scores below are exact brute-force cosine, not HNSW approximations. Production
was not touched and nothing was restarted.

## The score scale, which is the first thing that misled everyone

The collection is built with `space: l2` over already-normalised vectors, so the
distance Chroma returns is **squared** L2 = `2 − 2·cos`, and
`classify_retrieval`'s `score = 1 − distance` is therefore:

```
score = 2·cos − 1
```

Two consequences that the printed number hides:

| band | threshold | actual cosine required |
|---|---|---|
| `JTS_GROUNDED` | ≥ 0.35 | **≥ 0.675** |
| `GENERAL_MEDICAL` | ≥ 0.10 | ≥ 0.550 |

and below cosine 0.5 the score goes **negative**, where `max(0.0, …)` clamps it.
A hopeless retrieval and a merely weak one both print as a small positive
number. `top: 0.055` was not "slightly under the bar" — it was a floor reading.

The `📚` log line now prints the cosine alongside. No threshold was changed.

## The corpus and the chunking are fine

This was the first hypothesis and it is wrong. Clean burn queries retrieve burn
CPG chunks comfortably inside `JTS_GROUNDED`:

| query | top score | band | top chunk |
|---|---|---|---|
| `40% TBSA burns, what fluid resuscitation does he need?` | **+0.507** | JTS_GROUNDED | Burn Management PFC p.17 |
| `parkland formula fluid volume for a burn patient` | **+0.403** | JTS_GROUNDED | Burn Management PFC p.17 |
| `burn resuscitation rule of ten` | **+0.406** | JTS_GROUNDED | Burn Care CPG p.30 |

Chunks do start mid-word — but that is a property of the whole corpus (67% of
all chunks begin without a capital), not of this document (64%). **Re-chunking
the burn CPG would not have helped.**

## The actual cause: narrative dilution

The live queries were not clean. They were conversational and carried four or
five topics each:

> *"My patient is 30 years old and maybe like 190 lbs. his Tesla rear ended a
> semi and he's got broken bones and estimated 70% burns."*

Mean pooling averages every token into one 384-dim vector. "Tesla", "semi",
"190 lbs", "30 years old" and "broken bones" are all in there with "burns", and
the burn signal is one clause of six:

| live query | medic's words | as sent to Chroma | band |
|---|---|---|---|
| Tesla / semi / broken bones / 70% burns | **−0.023** | **+0.095** | INSUFFICIENT |
| burns + broken bones from a car wreck | **−0.116** | **+0.060** | INSUFFICIENT |
| "Ok so I think his burn is at 70%" | **+0.128** | *(router LOW, unchanged)* | GENERAL_MEDICAL |

On its own words, query 2 scored **−0.116** — its nearest neighbours were
*Orthopaedic Trauma: Extremity Fractures* and *Nutrition Using Enteral and
Parenteral Methods*. The best burn chunk sat at −0.167. That is not a threshold
being slightly too strict; the burn document was nowhere near the top of the
list.

## The router is the mitigation, not the cause

Appending `burn care prolonged field care TCCC` moved those queries by **+0.118**
and **+0.176**, and it is the only reason burn chunks surfaced at all. On short
clean queries the same boilerplate costs about −0.04 by pulling the vector
toward a generic centroid.

Net: the router is doing the right thing in exactly the case that matters. It
should not be "simplified" without measuring this.

## Secondary: PDF ligature corruption

The burn CPG is a ligature outlier — text extracted with `ﬁ`/`ﬂ` as single
Unicode glyphs rather than ASCII pairs:

| | burn CPGs | corpus |
|---|---|---|
| chunks containing an f-ligature | **53%** | 9% |

`ﬂuid` appears in 50 burn chunks; ASCII `fluid` in only 26. The WordPiece
tokenizer splits `ﬂuid` into the rare glyph token `ﬂ` plus `##uid` instead of
the single token `fluid`, and in this model:

```
cos("fluid", "ﬂuid") = 0.37
```

So more than half the burn CPG's fluid-resuscitation language is spelled in a
form a medic will never type and the encoder barely relates to the real word.
This is real and worth fixing, but it is **secondary** — it does not explain a
−0.116, and fixing it needs a re-ingest with NFKC normalisation, which is a
deploy rather than a patch.

## What was changed here

Only the log line, so the next person reads a cosine instead of a clamped score.
Everything else is scoped in TODO.md under *Retrieval*, for the eval-harness
phase where a routing change can actually be scored:

- query construction for multi-topic narratives (clause splitting, multi-query,
  reranking) — this is the real fix
- letting a HIGH-confidence router match reach its own document via
  source-filtered or source-boosted retrieval
- re-ingesting with NFKC normalisation to kill the ligatures
- whether `confidence` on the wire should stop being clamped at zero

**No retrieval threshold was tuned.**
