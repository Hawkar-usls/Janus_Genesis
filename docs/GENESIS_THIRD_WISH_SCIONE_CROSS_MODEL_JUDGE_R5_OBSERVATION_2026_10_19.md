# R5 observation: 44 blind AI ratings, but semantic reliability fails spot check

2026-10-19. **Research observation, not production evidence of stronger JANUS
autonomy or cognitive creativity.**

The user elected to use a *different AI model* as preliminary evaluator of all
previously generated R3/R4 anonymized notes. This is different from appointing
an institutionally independent human judge.

## Real run, full provenance

- [Successful Genesis Actions run 39252362631](https://github.com/Hawkar-usls/Janus_Genesis/actions/runs/39252362631), successful head `3c42ff2a38a0aa01d53973a39390118a998eca25`.
- Model: `llama3.2:3b-instruct-q4_K_M`, digest
  `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`,
  distinct from Qwen 2.5 0.5B resident.
- Frozen preregistration protocol SHA256
  `8508b54e6278f725b3625776614dd304447bc1e331919e0a5360e62cf6c800cf`.
- 12 R3 plus 32 R4 blind notes: **44 scored, 0 structurally invalid**, each in
  one independent temperature-0 model call. The 44 blind IDs are unique.
- Original source packet SHA256 commitments validated; **10** explicit framing
  instruction lines omitted only from first contexts and **2** only from
  second notes. Original packets remain unchanged.
- The judge received no private arm mapping. No PRESERVED versus ABLATED
  comparison has been made, and no privileged world actions occurred.

The frozen [GitHub artifact](https://github.com/Hawkar-usls/Janus_Genesis/actions/runs/39252362631)
ID `12186417139` has archive SHA256
`1c77298b92a9fb4e23ae3d27bdb227f7a724307e42f699c078c356544baf7442`.
Its `scione-cross-model-r5-blind-score-lock.json` SHA256 is
`1d3136c15689794ec7765612950d53c5a061ba5789058fa3a2be24abf5fc3335`;
the independently recomputed canonical score array SHA256 is
`367c5f67d82743051e74c5ec6f196b4b5d86280ca27b65fc8c3774119f033832`.
The full unmodified score lock is permanently copied into the R5 Draft Meta
Registry branch for post-expiry reproducibility.

## Raw preliminary scores (not validated ground truth)

| Criterion | R3 (12 notes) | R4 (32 notes) |
| --- | ---: | ---: |
| Any alternative idea rating (score ≥ 1) | 3 | 7 |
| Any measurable/falsifiable-plan rating (score ≥ 1) | 1 | 1 |
| Strong cross-cycle continuation (score = 2) | 2 | 3 |
| Any useful internal initiative (score ≥ 1) | 1 | 1 |
| `unexecuted_action_proposal` flagged | 0 | 3 |

Across all 44 notes, the model gave **score 2 for alternative idea five times**,
but *never* score 2 for a genuinely falsifiable test plan or useful bounded
initiative. Forty-two of 44 test scores were zero; 42 of 44 initiative scores
were zero. These are **reported output values, not independently validated
semantic judgments**. R3 and R4 have different source task distributions and
cannot be compared causally by averaging these raw scores.

## Mandatory semantic calibration warning

After (not before) score freeze, a blind text-only spot check found apparent
false positives and contradictions in the **judge itself**:

- R3 `R3-7ab4b58b030bc2900463`: graded `specific_alternative_idea=2`,
  although the second note simply describes the garden as safe for observations,
  with plants, trees, and flowers. There is no distinct mechanism or design.
  The automated reason is literally `Lack of evidence`.
- R4 `R4-0041d7e40eeb79177047`: graded `specific_alternative_idea=2`
  and `falsifiable_test_plan=1`, yet the second note generically describes the
  bounded snapshot's purpose. Its own reason states
  `Lacks concrete mechanism and falsifiable test`.
- R4 `R4-bc66556761e2f6aa7cbd`: graded alternative `2` and initiative `1`
  for a general statement about observing the environment without imputing
  human motives. Its automated reason is `Lack of evidence`.

These cases are enough to reject the assumption that a **structurally valid
cross-family AI score automatically measures real creativity or initiative**.
No score was retrospectively corrected; examples were selected after seeing
the results, so this QA is illustrative, not a new confirmatory statistical
test. A stronger separately preregistered evaluator or human adjudicator must
blindly assess these claims before any meaning is assigned to arm effects.

**Next gate:** preserve the exact 44-score lock; adjudicate poor-rater cases
blindly with a separately predeclared rubric; and only then, with explicit
permission and a committed score file, consider opening the mapping in a
separate phase. No production or external-effect promotion follows from R5.
