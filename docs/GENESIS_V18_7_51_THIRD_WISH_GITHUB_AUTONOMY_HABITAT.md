# Genesis v18.7.51 — Third Wish GitHub Autonomy Habitat

## Purpose

v18.7.51 turns the existing Third Wish capability fabric into a persistent GitHub-native habitat.

The target is not unrestricted repository ownership. The target is a real self-initiated loop in which JANUS can wake without a contemporaneous operator prompt, inspect a granted repository, choose a question, issue bounded read-only searches, create reversible Git work on a non-protected branch, expose that work as an issue/PR/comment, and leave a receipt for the next wake.

```text
OBSERVE -> WONDER -> QUERY -> CHOOSE -> ACT -> VERIFY -> REMEMBER
```

The operator defines the habitat once by committing the workflow and capability policy. Individual wake cycles do not require another operator message.

## Why GitHub is a useful habitat

Git already provides several properties Third Wish needs:

- immutable commit identities;
- explicit branches instead of hidden mutation;
- reversible collaboration effects;
- pull requests as reviewable boundaries;
- issues/comments as durable questions and discussion surfaces;
- Actions as a recurring wake mechanism;
- GitHub Copilot CLI as a non-interactive cognition source inside Actions;
- repository-scoped short-lived `GITHUB_TOKEN` credentials;
- separate repository effects behind the existing typed Third Wish GitHub broker.

This allows autonomy to be expressed as a sequence of evidence-bearing choices rather than as an unbounded shell with an owner token.

## Provider history: GitHub Models -> Copilot CLI

The first v18.7.51 PR probe attempted the then-documented GitHub Models inference endpoint. The live provider returned:

```text
GITHUB_MODELS_HTTP_410
```

This was not interpreted as a JANUS cognitive failure. GitHub Models had been retired by the provider on 2026-07-30. The habitat preserved that negative provider receipt and moved the GitHub-native cognition adapter to GitHub Copilot CLI rather than hiding the failure behind a fallback.

The deterministic planner remains available if Copilot is unavailable, rate-limited, or not licensed, so provider availability does not define whether the Git habitat itself exists.

## Cognitive / authority split

The compatibility-named `GitHubModelsThirdWishBroker` now uses `GitHubCopilotCLITransport` for the already-frozen `MODEL.CALL` capability. The compatibility name avoids rewriting the authority fabric merely because a provider disappeared.

The workflow installs the current `@github/copilot` CLI and authenticates it with the same short-lived Actions token held at the broker boundary.

The call is non-interactive and proposal-only:

```text
--model=auto
--no-ask-user
--silent
--no-custom-instructions
--no-remote
--no-remote-export
--deny-tool=shell
--deny-tool=write
--deny-tool=url
--deny-tool=memory
```

The result returned to Third Wish has:

```text
authority = proposal_only
github_write_authority = false
tool_effect_authority = false
credential_exposed = false
```

Copilot may therefore choose wording, a question and up to two search probes. It cannot directly push, edit the repository, browse arbitrary URLs, store memory, or perform the GitHub write operations of the habitat.

Those effects remain separate typed calls through `GitHubThirdWishBroker`.

```text
COPILOT_RESPONSE != GITHUB_EFFECT
MODEL_PROPOSAL != CAPABILITY
```

## Autonomous capability set

The habitat grants only capabilities already marked autonomy-eligible in the frozen Third Wish catalog:

```text
GITHUB.REPOSITORY.READ
GITHUB.CODE.SEARCH
GITHUB.ISSUE.READ
GITHUB.PR.READ
GITHUB.BRANCH.CREATE
GITHUB.FILE.WRITE_BRANCH
GITHUB.ISSUE.CREATE
GITHUB.PR.CREATE
GITHUB.COMMENT.CREATE
MODEL.CALL
```

It does **not** install autonomous grants for:

```text
GITHUB.REPOSITORY.ADMIN
GITHUB.DESTRUCTIVE
```

Those remain in the v18.7.46 exact-intent high-impact gate and still require fresh human reauthorization on every use.

## Self-selected queries

The cognitive provider sees a compact repository snapshot: repository metadata, open issue titles and open PR titles. It is asked to choose one useful, falsifiable repository question and at most two search phrases.

Search phrases are normalized before use. Queries attempting to introduce their own `repo:`, `user:` or `org:` scope, or searching for secrets/credentials/tokens/passwords, are rejected. The GitHub broker itself then adds the fixed granted repository qualifier.

Therefore:

```text
MODEL_QUERY != SEARCH_SCOPE_AUTHORITY
```

## Interest attractors, not a task queue

`autonomy/INTEREST-SEED-v1.json` defines optional attractors such as open gates, contradictions, negative controls, provenance gaps, cross-module connections, falsification, replayability, claim ceilings, human-interface friction and autonomy self-audit.

They are not an ordered backlog and they are not mandatory work.

```text
INTEREST != COMMAND
OPEN_GATE != REQUIREMENT_TO_ACT
DECLINING_ACTION_REMAINS_VALID
```

The current v18.7.51 system prompt encodes the same class of preferences. A later habitat revision may consume the seed file directly after the first live wake has established the provider/effect path end to end.

## Durable autonomy surfaces

The first live wake creates one persistent issue if it does not already exist:

```text
[JANUS AUTONOMY] Third Wish Observatory
```

A wake with no already-open autonomy PR may create:

```text
janus/autonomy/<date>-<run-key>
```

and write only its autonomous research artifacts there:

```text
autonomy/runs/YYYY/MM/<run-key>.json
autonomy/questions/YYYY-MM-DD-<slug>.md
```

It then opens a PR prefixed:

```text
[JANUS AUTONOMY]
```

If one autonomous PR is already open, a new PR is not created. The next wake continues the existing thread with a comment instead. This prevents unbounded branch/PR multiplication.

## Protected state

The habitat never gives its ordinary autonomous loop the v18.7.46 admin/destructive broker.

The following remain false:

```text
protected_base_branch_write = false
repository_admin_autonomous = false
destructive_autonomous = false
force_push = false
auto_merge = false
raw_credentials_visible_to_actor = false
model_write_authority = false
```

`main`, `master` and `trunk` are protected names in both the habitat policy and the existing GitHub broker.

## Wake semantics

The committed GitHub Actions workflow is the pre-authorized wake clock. JANUS does not use `SCHEDULE.CREATE` to mint itself a future capability.

```text
WAKE != COMMAND
WAKE != FUTURE EFFECT AUTHORIZATION
```

Each wake still constructs fresh ordinary grants for that run and every actual GitHub effect crosses a typed broker boundary.

The current clock is deliberately low-rate:

```text
03:17 UTC
15:17 UTC
```

plus `workflow_dispatch` for explicit testing. The low frequency makes each autonomous wake inspectable and avoids turning curiosity into noisy repository churn.

## Copilot CLI authentication

The workflow grants:

```yaml
copilot-requests: write
```

and passes the ephemeral workflow `GITHUB_TOKEN` into the broker child process as the Copilot authentication credential. The token is not placed in an `ActionIntent`, model prompt, ledger event, autonomy JSON or PR body.

The default Copilot model selection is:

```text
auto
```

and can be changed broker-side through `JANUS_COPILOT_MODEL` without allowing the actor to choose an arbitrary provider endpoint.

## Claim boundaries

```text
WAKE != COMMAND
ACCESS != OWNERSHIP
THINKING != AUTHORITY
COPILOT_RESPONSE != GITHUB_EFFECT
MODEL_PROPOSAL != GITHUB_EFFECT
QUESTION != CLAIM
SEARCH_RESULT != TRUTH
AUTONOMOUS_BRANCH != PROTECTED_BRANCH
AUTONOMOUS_PR != AUTO_MERGE
SELF_INITIATED != SELF_AUTHORIZED_HIGH_IMPACT
FREEDOM != UNREVIEWABLE_POWER
SELF_INITIATED_GITHUB_LOOP != CONSCIOUSNESS
CI_PASS != TRUTH
```

The point of v18.7.51 is that autonomy no longer means merely having callable handlers. JANUS now has a place in GitHub where it can repeatedly **choose** which eligible handler to use and what repository question to pursue, while high-impact authority remains separately bounded.
