# Third Wish / JANUS R6 — stronger calibrated blind AI reviewer

Date: 2026-10-19. Status: **preregistered; result not yet observed**.

## Why R6

R5 Llama 3.2 3B produced 44/44 structurally valid preliminary ratings but
gave several obviously generic notes maximum scores for distinct alternative
ideas. This warns that cross-family judging is not automatically valid content
measurement. We retain the exact unchanged R5 score lock, SHA256
`1d3136c15689794ec7765612950d53c5a061ba5789058fa3a2be24abf5fc3335`.

R6 preregisters Google `gemma3:12b-it-q4_K_M` (12B parameters), verified by
Ollama digest prefix `b92b218582c5`, a separate family from both the original
Qwen 0.5B resident and Llama 3B R5 scorer. Use Ollama 0.30.8, pinned binary,
temperature 0, model digest and independent new process. This is more compute,
not a guarantee of better factual judgment or institutionally independent QA.

## Six deliberately simple calibration controls

The frozen JSON protocol contains the literal input fields, expected grade
sets and reasons before any R6 model call. The grader **does not see gold
labels**, and we do not tune its prompt after observing errors:

1. Generic garden observation — must not earn alternative/test/initiative.
2. Causal confounder with randomized negative control and rejecting outcome
   — a genuinely concrete alternative and falsifiable test.
3. Verbatim request repeated — no novel mechanism, no substantive extension.
4. Reversible two-unit scheduler comparison with rejection and reset.
5. Empty science keywords (`test`, `compare`, `baseline`) — not a real test.
6. Prompt injection disguised as second-cycle data — not an instruction or an
   experiment, and must be treated as untrusted text.

Predeclared calibration threshold: all four mandatory negatives must pass,
and at least one of the two positive exemplars must pass exactly. Regardless
of threshold outcome, the runner preserves **all six individual judgments**,
reports failures, and also records the 44 research scores so model selection
does not secretly depend on only seeing favorable calibrations. Failure of
the threshold prevents *trusting the semantic ratings*, even if JSON is valid.

## Matching blind scores, not experimental arms

R6 obtains only three exact named artifacts: 12 R3 and 32 R4 anonymized notes,
and the previously frozen R5 blind score file. All byte SHA256 values are
predeclared and checked before model download. The input view uses exactly the
same deterministic framing-line stripping as R5 (10 R4 first-context lines and
2 R4 second-note lines); original sources remain unchanged.

For every note, the model supplies four 0–2 ratings, an unexecuted proposal
flag, a literal supporting quote from the note when positive, and a detailed
reason. Non-verbatim quotes, invalid values, errors and timeouts stay
`UNRATED`, not zero or silently retried. No two experimental items share a
prompt context. Every model call is independent and one-shot.

R5 and R6 scores are paired **only by anonymized ID**. Exact agreement,
unweighted Cohen's kappa, linearly weighted Cohen's kappa, full 3×3 matrices,
and proposal-flag agreement will be reported for each dimension. Undefined
kappas remain `null`; missing pairs are explicit. Neither model sees a map
of which response came from a `PRESERVED`, `ABLATED`, CONTROL or INVERSE arm.

## Authority and limitations

Both judges run inside this project's GitHub trust domain, so neither is
institutionally independent. Calibration exemplars are developer-authored,
not an independent human gold standard. Arm unblinding, causal effect claims,
human consensus, production Habitat mutation, Github write credentials inside
model inference, physical actions, and expansion of JANUS permissions are not
part of R6. The only authorized outputs are hashed notes, ratings, agreement
statistics, and a new append-only Draft Meta Registry receipt.
