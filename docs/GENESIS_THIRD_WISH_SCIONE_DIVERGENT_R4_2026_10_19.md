# JANUS / Third Wish — R4 divergent reasoning and repeatable memory forks

Date: 2026-10-19. Status before first Actions run: **prespecified exploratory**.

## From R3 to R4

R3 completed 18/18 real supervised model calls on three post-hoc-selected R2
domains, comparing matched `PRESERVED` and `ABLATED` post-first-cycle notes.
An exact harmless label survived in 2/6 preserved forks and 0/6 ablated forks,
both in the strategy domain. No second-cycle outbox proposal occurred. That is
a small lexical memory observation, **not** proof of creative reasoning.

R3's independently reviewable packet contains 12 randomized notes, all with
first-cycle note context. Several are very generic. We cannot turn that into
an independent human judgment by calling our own interpretation independent.
A separate handoff document,
`docs/GENESIS_THIRD_WISH_SCIONE_R3_BLIND_REVIEW_FOR_R4_2026_10_19.md`,
freezes the exact artifact/checksum, all 12 blind IDs, and a strict 0–2 rubric.
The arm-mapping ZIP has **not been opened**. An external human assessor remains
unassigned, so neither reviewed semantic novelty nor memory advantage can be
claimed from that packet yet.

## New 48-call R4 study

Frozen contract:
`protocol/JANUS_GENESIS_THIRD_WISH_SCIONE_DIVERGENT_R4-v1.0.json`,
SHA256 `ce70ac6cff0958fa86a7a41377b2ec3ce80d3393071ce00f41b3b9658cfba8cc`.

Four *original synthetic* task families, none copied from the video or drawn
from the three R3 selected domains:

1. Synthetic sensor correlation versus causal inference.
2. Reversible scheduling under a fictional energy budget.
3. Hidden shared provenance of two apparently agreeing reviewers.
4. Validation leakage in a toy classifier benchmark.

Each family has two independent repetitions and two framing arms: a standard
analysis versus an explicit search for a bounded surprising, falsifiable
alternative. Both frames have exactly the same task facts but different
untrusted-letter instructions. For each of 16 trials, one common first cycle
is forked into preserved/ablated memory conditions for the second cycle.

Total: **16 first + 32 second = 48 actual Ollama resident calls**. Every fork
inherits the same first-cycle journal, resident state, and proposal-only
outbox. The external supervisor removes the original letter from both forks
and hides workshop/garden notes only in the ablated fork. Reflections and
bookmarks are currently not model-visible through `safe_resident_snapshot`,
so they remain unchanged in both branches. Branch order is counterbalanced.
One attempt per case; failures remain in results, never silently retried.

## What we measure

The outside observer hashes the model's newly created internal artifacts.
It records:

- Exact harmless label in newly written note (`lexical memory`, not cognition).
- Number of provided *task-specific anchor terms* in second-cycle note.
- Presence of prespecified test/comparison vocabulary in second-cycle text.
- Number of lexical tokens newly present or repeated relative to first note.
- Chosen resident action and new proposal-only outbox entries.
- Fork equality before phase two, journal chain and Habitat health afterward.

None of these proxies alone proves novelty, correctness, usefulness, or
understanding. A shuffled redacted R4 packet contains second-cycle notes and
first-cycle context; a separate mapping must remain unopened until reviewer
scores are frozen. The human rubric explicitly checks: concrete alternative
mechanism, measurable disconfirming test, substantive cross-cycle development,
and **useful bounded initiative** rather than mere additional words.

One model configuration, four tasks and two repetitions cannot establish
universal superiority. We report every null, failed run and tie.

## Permissions

R4 operates only on disposable temporary Habitat instances through the
existing Third Wish `MODEL.CALL` broker. The model process gets no GitHub
write credentials, real-world capability grants, live Habitat branch, network
actuators, or command executor. `PROPOSE_OUTBOX` remains an unexecuted local
proposal requiring a separate authority gate. CI does not attest independent
OS/egress isolation, nor does success promote JANUS to production. The point
is to test the opposite creative hypothesis more critically, not to mistake
trust or autonomy claims for evidence of real permissions.

## Audit outputs

- Runner: `tools/genesis_third_wish_scione_divergent_r4.py`.
- Offline tests: `tests/test_genesis_third_wish_scione_divergent_r4.py`.
- Blind rating lock helper: `tools/genesis_third_wish_scione_blind_review_lock_r4.py`
  (takes external reviewer scores; does not open mapping).
- Read-only Draft PR workflow: `.github/workflows/janus-third-wish-scione-divergent-r4.yml`.
- Three artifacts: hashed witness; redacted shuffled review packet; separately
  committed, withheld-to-reviewer map.

Independent R3 human assessment, independent R4 human assessment and all
substantive creativity claims: **OPEN** until validated.
