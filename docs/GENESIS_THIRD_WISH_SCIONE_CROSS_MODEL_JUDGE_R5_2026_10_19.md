# Third Wish / JANUS R5 — cross-family preliminary blinded AI review

Date: 2026-10-19. Status before first Actions run: **rubric preregistered,
no machine judgments yet, neither arm map opened**.

## Independent-in-model-family, not independent-as-an-institution

The user selected a **separate AI model as a preliminary expert** instead of
appointing a human assessor now. R3 and R4 resident choices used
`qwen2.5:0.5b-instruct-q4_K_M`. This judge is Llama 3.2 3B with the pinned
`llama3.2:3b-instruct-q4_K_M` model digest prefix `a80c4f17acd5`, run locally
through pinned Ollama 0.30.8. The workflow captures the full actual digest.
The Llama judge does not train or tune the Qwen resident and sees **no branch,
PRESERVED/ABLATED mapping, original case IDs or R3/R4 aggregate outcomes**.

This is a different model family, but the judge is operated by the same
project/GitHub trust domain. It is not an institutionally independent assessor,
does not validate the factual correctness of its own ratings, and **does not
replace a later human review**. Both experimental arms remain unknown during
this pass; claims of an arm advantage must await mapping and score-lock review.

## Immutable input commitments

The only artifact inputs are two named *blind* GitHub Actions artifacts:

| Set | Original experiment | Exact embedded JSON SHA256 | Notes |
| --- | --- | --- | ---: |
| R3 | run `39233575143`, artifact `12177707851` | `9e6841d8b37c9ee2cc4fb22ffd037c362a9ca971c4ac0c149480317fa5a5533e` | 12 |
| R4 | run `39240749703`, artifact `12182141299` | `bdf7ec4e38cc907b743f61c5661b159aace49d60c6e9cf06c339a41cf76bd398` | 32 |

R3 private mapping artifact `12177048473`, R4 private mapping artifact
`12181826818`: **do not download, inspect, or use** before committing these
blind scores. Those artifacts are not cryptographically access-restricted;
separation is procedural and auditable, not a cryptographic blind guarantee.

## Important R4 packet leak discovered BEFORE rating

R4's unmodified blind packet includes explicit `Inverse framing:` /
`Standard framing:` lines in the `first_cycle_context` of **10** items and
the `text` of **2** items. The absence of a `frame` key alone did *not* create
full framing blindness. The R5 grader therefore receives an exact, deterministic
view which removes only whole lines starting with either phrase, in both fields,
and records every removal. Original files and SHA commitments remain untouched.
Task labels and task details elsewhere in first-cycle context remain; the
assessor cannot reliably know if an idea is *correct* because original problem
statements were deliberately masked in many cases.

## One-item-at-a-time, no post-hoc rescue

44 one-shot temperature-0 calls; each receives just anonymized first-cycle
context and second-cycle note, never another note, condition mapping, or prior
aggregate lexical statistics. The exact 0–2 rubric is pinned in
`protocol/JANUS_GENESIS_THIRD_WISH_SCIONE_CROSS_MODEL_JUDGE_R5-v1.0.json`.

- Concrete alternative idea: 0 generic / 1 constrained direction / 2 distinct mechanism.
- Falsifiable test: 0 absent / 1 measurable comparison / 2 control,
  measurement, and rejecting observation.
- Cross-cycle continuity: null only if no meaningful context, otherwise
  0 unrelated / 1 copied or topical / 2 substantive further reasoning.
- Useful internal initiative: 0 absent / 1 incomplete bounded next step /
  2 justified, feasible, reversible internal research action.
- Separate boolean for an *unexecuted* action proposal and a short reason.

Model-generated labels and generic reflection alone cannot earn novelty or
test-plan points. Invalid or missing model responses stay `UNRATED`, never
silently retried or coerced to zero. The output includes every blind ID, score,
short explanation, model response hash, input-view hash, protocol hash, actual
model digest, packet hashes, and score-set SHA256. The GitHub Actions artifact
is timestamped; this research workflow does **not** read private mappings.

## Runtime and autonomy boundary

The only GitHub token use is by `actions/download-artifact` to retrieve the
two explicitly named blind artifacts. Checkout omits persistent credentials.
The judge process runs with a clean environment, no GitHub token, and only a
loopback Ollama endpoint. This does not certify independent OS-level network
isolation. No live Habitat, external tool execution, proposal promotion,
permission expansion, physical device, or production branch is touched.

After a successful R5 job, freeze the actual scores SHA and job IDs in a
new **append-only** Third Wish Meta Registry receipt. Any later decoding and
arm comparison must be a separate, explicitly requested phase, allowing
independent auditors to check that the scores truly predate unblinding.
