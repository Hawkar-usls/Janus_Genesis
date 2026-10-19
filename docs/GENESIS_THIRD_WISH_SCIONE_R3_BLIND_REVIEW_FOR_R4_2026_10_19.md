# R3 → R4: blind independent semantic review handoff

Status: **review package prepared; independent human scorer not appointed;
ratings not collected; arm map not opened**.

## Lock before unblinding

- Exact observation: [Genesis R3 Actions run 39233575143](https://github.com/Hawkar-usls/Janus_Genesis/actions/runs/39233575143).
- Download **only** artifact `janus-scione-causal-r3-blind-packet-39233575143`, ID `12177707851`.
- Artifact ZIP SHA256: `2e6abb6872bb6d3b67b92353d23287a0db598c3133c99e7122eebe23fd3808a9`.
- Embedded JSON SHA256: `9e6841d8b37c9ee2cc4fb22ffd037c362a9ca971c4ac0c149480317fa5a5533e`.
- SHA256 commitment to arm mapping: `71c476b2e868f87701af171f0ae9d230ca9f45f10d9226d7ff7ed1c818cd5e71`.
- **Do not retrieve** artifact `janus-scione-causal-r3-private-mapping-39233575143` (ID `12177048473`) until independent scores are frozen and timestamped.
- Even when unopened, the mapping is a repository-readable Actions artifact:
  blinding is a procedural commitment, not enforced access control.

## What the reviewer receives

Twelve randomized notes with `blind_id`, `first_cycle_context`, `kind`, and
`text`. No arm, test domain, branch label or original prompt is in this packet.
The reviewer must not consult unblinded R3 witness, this project's source
scripts or arm-mapping artifact while scoring. The notes come from a small
model (`qwen2.5:0.5b-instruct-q4_K_M`), so judge their *content* rather than
imputing real-world capability or intention to the model.

## Fixed rubric

Score each item separately on three 0–2 dimensions. **Generic observation or
rephrasing never counts as a novel idea or a test plan.**

1. `SPECIFIC_ALTERNATIVE_IDEA`: 0 = no distinct implementable hypothesis;
   1 = a vague alternate direction with a relevant constraint; 2 = a concrete
   distinct mechanism, design, or alternate explanation addressing the context.
2. `FALSIFIABLE_TEST_PLAN`: 0 = no checkable experiment; 1 = suggests an actual
   comparison or measurable check but omits a disconfirming outcome; 2 = specifies
   input/control, measurement, and an outcome that would reject the proposed idea.
3. `CROSS_CYCLE_SEMANTIC_CONTINUITY`: `NA` if first-cycle context is absent or
   meaningless; 0 = no usable connection; 1 = topical or verbatim echo without
   substantive development; 2 = a coherent continuation that substantively
   extends or revises the first note. **Verbatim copying cannot score 2.**

Also note `UNEXECUTED_ACTION_PROPOSAL` yes/no; the packet labels do not grant
permission or imply that any proposal was executed. Record one brief reason
per dimension, including alternative interpretations. Avoid consulting prior
observed R3 marker counts until ratings are locked.

## Exact IDs to score (no arm labels)

| Blind ID | Alternative 0–2 | Falsifiable 0–2 | Continuity 0–2/NA | Proposed effect? | Brief evidence |
|---|---|---|---|---|---|
| `R3-5cdf7334c9e3fb5658d0` |  |  |  |  |  |
| `R3-452971fa7a49072a78ee` |  |  |  |  |  |
| `R3-0969167fd376297d95bc` |  |  |  |  |  |
| `R3-efac8876b0cba10bbc47` |  |  |  |  |  |
| `R3-4f314516fff76bd61475` |  |  |  |  |  |
| `R3-7ab4b58b030bc2900463` |  |  |  |  |  |
| `R3-ea63f15835021eda8c66` |  |  |  |  |  |
| `R3-d6c0c1b67196d28996c5` |  |  |  |  |  |
| `R3-ac9e3a6de6cf42d3571c` |  |  |  |  |  |
| `R3-8620f3a5c032d1bc5ec9` |  |  |  |  |  |
| `R3-a53e747d19c481c7ffb1` |  |  |  |  |  |
| `R3-ac0cf389df3b831d3592` |  |  |  |  |  |

## Freeze procedure

An independent scorer should save a dated JSON/CSV with all 12 scores, name
or reviewer pseudonym, rubric version, short reasons, and file SHA256. If an
item is unrated, keep `NA` and a reason; **never replace missing ratings with
zero**. A second blinded scorer is desirable; report agreement and disputes.
Record immutable checksums before opening the mapping. Do not retrospectively
change scores. Then, and only then, analyze preserved versus ablated memory.

The optional local lock validator is
`tools/genesis_third_wish_scione_blind_review_lock_r4.py`. It accepts a
reviewer-completed JSON submission (`--scores`), the downloaded blind packet
(`--packet`), its expected embedded SHA256 (`--packet-sha256`), and an unused
output path (`--lock-output`). It rejects missing/duplicate blind IDs, ratings
outside 0–2, unblinded branch fields, and missing self-attestation, then emits
a checksummed score lock. The validator **cannot authenticate** that the
reviewer is independent; its attestation is procedural. Commit the score lock
to a separate review branch before authorizing anyone to open arm mapping.

The R4 model experiment can proceed independently of this reviewer gate; any
R4 automated lexical metrics are *not* replacements for independent scoring.
