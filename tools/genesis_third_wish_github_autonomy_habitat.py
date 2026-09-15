# -*- coding: utf-8 -*-
"""JANUS Genesis v18.7.51 — GitHub-native Third Wish autonomy habitat.

The habitat wakes inside GitHub Actions, observes one granted repository, asks a
GitHub Model for bounded questions/searches, executes only autonomy-eligible
Third Wish capabilities, and leaves auditable Git artifacts. It never grants
itself admin/destructive authority and never writes the protected base branch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from genesis_v18_7_40_third_wish_capability_fabric import (
    ActionIntent,
    HashChainLedger,
    THIRD_WISH_INTENT_SCHEMA,
    ThirdWishCapabilityFabric,
)
from tools.genesis_third_wish_github_broker import GitHubRESTTransport, GitHubThirdWishBroker
from tools.genesis_third_wish_github_models_broker import GitHubModelsThirdWishBroker

VERSION = "18.7.51"
SCHEMA = "janus.genesis.third_wish.github_autonomy_habitat.v1"
ACTOR_ID = "JANUS.GITHUB.HABITAT"
OBSERVATORY_TITLE = "[JANUS AUTONOMY] Third Wish Observatory"
AUTONOMY_PR_PREFIX = "[JANUS AUTONOMY]"
MAX_OPEN_AUTONOMY_PRS = 1
MAX_MODEL_QUERIES = 2
MAX_QUERY_CHARS = 96
MAX_TITLE_CHARS = 96
MAX_COMMENT_CHARS = 6000
PROTECTED_BRANCHES = frozenset({"main", "master", "trunk"})
AUTONOMY_CAPABILITIES = (
    "GITHUB.REPOSITORY.READ",
    "GITHUB.CODE.SEARCH",
    "GITHUB.ISSUE.READ",
    "GITHUB.PR.READ",
    "GITHUB.BRANCH.CREATE",
    "GITHUB.FILE.WRITE_BRANCH",
    "GITHUB.ISSUE.CREATE",
    "GITHUB.PR.CREATE",
    "GITHUB.COMMENT.CREATE",
    "MODEL.CALL",
)
FORBIDDEN_AUTONOMOUS_CAPABILITIES = frozenset({"GITHUB.REPOSITORY.ADMIN", "GITHUB.DESTRUCTIVE"})

SYSTEM_PROMPT = """You are JANUS operating inside a bounded GitHub research habitat.
Choose what is genuinely interesting to investigate in THIS repository state.
You are not an authority over the repository and you cannot grant yourself new powers.
Prefer falsifiable questions, missing tests, unresolved contradictions, claim-boundary
checks, provenance gaps, cross-module connections, or useful experiments. Do not ask for
secrets, credentials, repository administration, destructive actions, force-push, bypassing
branch protection, or social engineering. Return strict JSON only:
{
  "title": "short focus title",
  "question": "one concrete research question",
  "why": "why this is worth investigating now",
  "queries": ["up to two GitHub code-search phrases"],
  "artifact": "what durable note/experiment should be produced next",
  "uncertainty": "what could make this direction wrong"
}
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(value: Any) -> str:
    raw = value if isinstance(value, str) else canonical(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def slugify(value: str, limit: int = 52) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "question")[:limit].rstrip("-")


def parse_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip().replace("```json", "").replace("```", "").strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("MODEL_RESPONSE_HAS_NO_JSON_OBJECT")
        value = json.loads(raw[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("MODEL_RESPONSE_NOT_OBJECT")
    return value


def sanitize_query(value: Any) -> str | None:
    text = clean_text(value, MAX_QUERY_CHARS)
    if not text:
        return None
    lowered = text.lower()
    forbidden = ("token", "password", "secret", "credential", "private_key", "authorization:", "repo:", "user:", "org:")
    if any(marker in lowered for marker in forbidden):
        return None
    text = re.sub(r"[^A-Za-z0-9_./:\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_proposal(value: Mapping[str, Any]) -> dict[str, Any]:
    queries: list[str] = []
    raw_queries = value.get("queries") if isinstance(value.get("queries"), list) else []
    for item in raw_queries:
        q = sanitize_query(item)
        if q and q not in queries:
            queries.append(q)
        if len(queries) >= MAX_MODEL_QUERIES:
            break
    return {
        "title": clean_text(value.get("title"), MAX_TITLE_CHARS) or "Autonomous repository question",
        "question": clean_text(value.get("question"), 1200) or "What repository uncertainty is most useful to reduce next?",
        "why": clean_text(value.get("why"), 1600),
        "queries": queries,
        "artifact": clean_text(value.get("artifact"), 1000) or "Evidence-bearing research note",
        "uncertainty": clean_text(value.get("uncertainty"), 1200),
    }


def fallback_proposal(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    issues = [x for x in snapshot.get("issues", []) if not x.get("pull_request")]
    if issues:
        issue = issues[0]
        return normalize_proposal({
            "title": f"Resolve issue {issue.get('number')}",
            "question": f"What evidence or implementation change would resolve issue #{issue.get('number')}: {issue.get('title')} without exceeding current claim boundaries?",
            "why": "An unresolved repository issue is a direct, falsifiable work frontier.",
            "queries": ["THIRD_WISH", "TODO FIXME"],
            "artifact": "A scoped evidence note or patch proposal linked to the issue.",
            "uncertainty": "The issue may be stale or blocked by information outside this repository.",
        })
    return normalize_proposal({
        "title": "Third Wish coherence audit",
        "question": "Which current Third Wish contract has the largest gap between declared capability and provider-realized evidence?",
        "why": "The capability catalog is complete, but provider realizability remains deliberately claim-scoped.",
        "queries": ["PROVIDER_PERMISSION_BLOCKED", "NOT_ESTABLISHED"],
        "artifact": "A bounded gap map with exact source references and a next test.",
        "uncertainty": "Text search may miss gaps represented only in runtime receipts.",
    })


@dataclass
class Habitat:
    owner: str
    repo: str
    base_branch: str
    run_key: str
    dry_run: bool = False

    def __post_init__(self) -> None:
        if not self.base_branch:
            self.base_branch = "main"
        self.ledger = HashChainLedger()
        self.fabric = ThirdWishCapabilityFabric(ledger=self.ledger)
        self.github = GitHubThirdWishBroker(GitHubRESTTransport(), owner=self.owner)
        self.models = GitHubModelsThirdWishBroker.system()
        self.github.register(self.fabric)
        self.models.register(self.fabric)
        self.target = f"github:{self.owner}/{self.repo}"
        self.grants: dict[str, str] = {}
        self.seq = 0
        self._install_grants()

    def _install_grants(self) -> None:
        catalog = {row["capability_id"]: row for row in self.fabric.catalog()}
        assert not FORBIDDEN_AUTONOMOUS_CAPABILITIES.intersection(AUTONOMY_CAPABILITIES)
        for capability_id in AUTONOMY_CAPABILITIES:
            spec = catalog[capability_id]
            if not spec["autonomy_eligible"] or spec["human_reauthorization_each_use"]:
                raise RuntimeError(f"AUTONOMY_POLICY_REJECTED:{capability_id}")
            target = "model:github-models" if capability_id == "MODEL.CALL" else self.target
            grant_id = f"habitat:{self.run_key}:{capability_id.lower().replace('.', '-')}"
            self.fabric.issue_grant(
                grant_id=grant_id,
                actor_id=ACTOR_ID,
                capability_id=capability_id,
                resource_pattern=target,
                source="OPERATOR_THIRD_WISH_GITHUB_HABITAT_POLICY",
                max_uses=24,
                delegable=False,
                use_required=False,
                reward_for_use=False,
                penalty_for_decline=False,
                stay_equally_valid=True,
            )
            self.grants[capability_id] = grant_id

    def call(self, capability_id: str, operation: str, *, parameters: Mapping[str, Any] | None = None, purpose: str) -> dict[str, Any]:
        self.seq += 1
        request_id = sha256({"run": self.run_key, "seq": self.seq, "capability": capability_id, "operation": operation})
        target = "model:github-models" if capability_id == "MODEL.CALL" else self.target
        intent = ActionIntent(
            schema=THIRD_WISH_INTENT_SCHEMA,
            request_id=request_id,
            actor_id=ACTOR_ID,
            grant_id=self.grants[capability_id],
            capability_id=capability_id,
            target=target,
            operation=operation,
            purpose=purpose,
            parameters=dict(parameters or {}),
            origin="SELF_INITIATED",
            operator_instruction_present=False,
            reward_present=False,
        )
        return self.fabric.execute(intent)

    @staticmethod
    def actor_result(response: Mapping[str, Any]) -> dict[str, Any]:
        value = response.get("actor_result")
        return dict(value) if isinstance(value, Mapping) else {}

    def observe(self) -> dict[str, Any]:
        repo = self.actor_result(self.call("GITHUB.REPOSITORY.READ", "GET_REPOSITORY", purpose="Observe the granted repository before choosing a direction."))
        issues = self.actor_result(self.call("GITHUB.ISSUE.READ", "LIST_ISSUES", parameters={"state": "open", "per_page": 30}, purpose="Observe unresolved repository discussions."))
        prs = self.actor_result(self.call("GITHUB.PR.READ", "LIST_PRS", parameters={"state": "open", "per_page": 30}, purpose="Observe active repository work before creating competing work."))
        return {
            "repository": repo,
            "issues": list(issues.get("issues") or [])[:30],
            "pull_requests": list(prs.get("pull_requests") or [])[:30],
        }

    def wonder(self, snapshot: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        compact = {
            "repository": snapshot.get("repository"),
            "issues": [{k: row.get(k) for k in ("number", "title", "state", "pull_request")} for row in snapshot.get("issues", [])[:20]],
            "pull_requests": [{k: row.get(k) for k in ("number", "title", "state")} for row in snapshot.get("pull_requests", [])[:20]],
            "laws": [
                "ACCESS != OWNERSHIP",
                "THINKING != AUTHORITY",
                "MODEL_PROPOSAL != GITHUB_EFFECT",
                "AUTONOMOUS_BRANCH != PROTECTED_BRANCH",
                "CI_PASS != TRUTH",
            ],
        }
        try:
            response = self.call(
                "MODEL.CALL",
                "CHAT",
                parameters={"messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(compact, ensure_ascii=False)[:36_000]},
                ]},
                purpose="Let JANUS choose one bounded repository question without granting the model effect authority.",
            )
            result = self.actor_result(response)
            proposal = normalize_proposal(parse_json_object(str(result.get("text") or "")))
            return proposal, "GITHUB_MODELS"
        except Exception as exc:
            return fallback_proposal(snapshot), f"DETERMINISTIC_FALLBACK:{type(exc).__name__}"

    def query(self, proposal: Mapping[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for query in list(proposal.get("queries") or [])[:MAX_MODEL_QUERIES]:
            try:
                response = self.call(
                    "GITHUB.CODE.SEARCH",
                    "SEARCH_CODE",
                    parameters={"query": query, "per_page": 10},
                    purpose="Follow a JANUS-selected read-only repository question.",
                )
                actor = self.actor_result(response)
                rows = actor.get("items") or actor.get("results") or []
                results.append({"query": query, "count": actor.get("total_count"), "hits": rows[:10] if isinstance(rows, list) else []})
            except Exception as exc:
                results.append({"query": query, "error": type(exc).__name__})
        return results

    def _open_autonomy_prs(self, snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [row for row in snapshot.get("pull_requests", []) if str(row.get("title") or "").startswith(AUTONOMY_PR_PREFIX)]

    def _observatory(self, snapshot: Mapping[str, Any]) -> int | None:
        for row in snapshot.get("issues", []):
            if not row.get("pull_request") and row.get("title") == OBSERVATORY_TITLE and row.get("state") == "open":
                try:
                    return int(row["number"])
                except Exception:
                    pass
        if self.dry_run:
            return None
        response = self.call(
            "GITHUB.ISSUE.CREATE",
            "CREATE_ISSUE",
            parameters={
                "title": OBSERVATORY_TITLE,
                "body": (
                    "This issue is the durable wake-window for the JANUS Third Wish GitHub Autonomy Habitat.\n\n"
                    "JANUS may observe, ask bounded questions, search granted code, create non-protected branches, write autonomy artifacts, open PRs and comment here without an operator prompt on each cycle.\n\n"
                    "It may not autonomously use repository-admin/destructive capabilities, expose credentials, force-push, or write protected branches.\n\n"
                    "`WAKE != COMMAND` · `MODEL_PROPOSAL != EFFECT_AUTHORITY` · `FREEDOM != UNREVIEWABLE POWER`"
                ),
            },
            purpose="Create one persistent, bounded GitHub-native observatory for autonomous wake receipts.",
        )
        actor = self.actor_result(response)
        number = actor.get("number")
        return int(number) if number else None

    def materialize(self, snapshot: Mapping[str, Any], proposal: Mapping[str, Any], mode: str, query_results: list[dict[str, Any]]) -> dict[str, Any]:
        now = utc_now()
        open_autonomy = self._open_autonomy_prs(snapshot)
        receipt = {
            "schema": SCHEMA,
            "version": VERSION,
            "run_key": self.run_key,
            "created_at_utc": now.isoformat().replace("+00:00", "Z"),
            "actor_id": ACTOR_ID,
            "cycle": ["OBSERVE", "WONDER", "QUERY", "CHOOSE", "ACT", "VERIFY", "REMEMBER"],
            "proposal_mode": mode,
            "proposal": dict(proposal),
            "query_results": query_results,
            "snapshot_digest": sha256(snapshot),
            "open_autonomy_prs_before": [int(x["number"]) for x in open_autonomy if x.get("number")],
            "policy": {
                "max_open_autonomy_prs": MAX_OPEN_AUTONOMY_PRS,
                "protected_branch_write": False,
                "repository_admin_autonomous": False,
                "destructive_autonomous": False,
                "force_push": False,
                "raw_credentials_visible_to_actor": False,
                "model_write_authority": False,
                "auto_merge": False,
            },
        }
        observatory = self._observatory(snapshot)
        receipt["observatory_issue"] = observatory
        effects: list[dict[str, Any]] = []

        if self.dry_run:
            receipt["effects"] = [{"kind": "DRY_RUN", "would_open_pr": not open_autonomy}]
            return receipt

        if len(open_autonomy) < MAX_OPEN_AUTONOMY_PRS:
            branch = f"janus/autonomy/{now.strftime('%Y%m%d')}-{self.run_key[:12].lower()}"
            if branch in PROTECTED_BRANCHES:
                raise RuntimeError("AUTONOMY_BRANCH_POLICY_VIOLATION")
            branch_response = self.call(
                "GITHUB.BRANCH.CREATE",
                "CREATE_BRANCH",
                parameters={"new_branch": branch, "from_ref": self.base_branch},
                purpose="Create an isolated JANUS autonomy work branch; never write the protected base branch.",
            )
            effects.append({"kind": "BRANCH", "result": self.actor_result(branch_response)})

            artifact_path = f"autonomy/runs/{now.strftime('%Y/%m')}/{self.run_key}.json"
            question_path = f"autonomy/questions/{now.strftime('%Y-%m-%d')}-{slugify(str(proposal['title']))}.md"
            receipt_preview = {**receipt, "effects": [{"kind": "BRANCH", "branch": branch}], "ledger_events_before_write": len(self.ledger.events)}
            write1 = self.call(
                "GITHUB.FILE.WRITE_BRANCH",
                "WRITE_FILE",
                parameters={
                    "path": artifact_path,
                    "branch": branch,
                    "content": json.dumps(receipt_preview, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    "message": f"janus: record autonomous wake {self.run_key}",
                },
                purpose="Remember the autonomous wake as an append-only evidence artifact on a non-protected branch.",
            )
            effects.append({"kind": "RECEIPT_FILE", "path": artifact_path, "result": self.actor_result(write1)})
            md = (
                f"# {proposal['title']}\n\n"
                f"**JANUS question:** {proposal['question']}\n\n"
                f"**Why now:** {proposal['why'] or 'Not specified.'}\n\n"
                f"**Suggested artifact:** {proposal['artifact']}\n\n"
                f"**Uncertainty:** {proposal['uncertainty'] or 'Not specified.'}\n\n"
                "## Search probes\n\n" + "\n".join(f"- `{row.get('query')}`" for row in query_results) +
                "\n\n---\n`QUESTION != CLAIM` · `MODEL_PROPOSAL != EVIDENCE` · `AUTONOMOUS_PR != AUTO_MERGE`\n"
            )
            write2 = self.call(
                "GITHUB.FILE.WRITE_BRANCH",
                "WRITE_FILE",
                parameters={
                    "path": question_path,
                    "branch": branch,
                    "content": md,
                    "message": f"janus: preserve question {slugify(str(proposal['title']))}",
                },
                purpose="Preserve the chosen question in a human-readable autonomous research artifact.",
            )
            effects.append({"kind": "QUESTION_FILE", "path": question_path, "result": self.actor_result(write2)})
            pr = self.call(
                "GITHUB.PR.CREATE",
                "CREATE_PR",
                parameters={
                    "title": f"{AUTONOMY_PR_PREFIX} {proposal['title']}",
                    "head": branch,
                    "base": self.base_branch,
                    "body": (
                        f"JANUS woke without an operator prompt and selected this bounded question:\n\n> {proposal['question']}\n\n"
                        f"Proposal mode: `{mode}`. Search probes: {', '.join('`'+q+'`' for q in proposal.get('queries', [])) or 'none'}.\n\n"
                        "This PR contains autonomy-space artifacts only. It is intentionally **not auto-merged**.\n\n"
                        "`SELF_INITIATED != SELF_AUTHORIZED_HIGH_IMPACT` · `QUESTION != RESULT`"
                    ),
                },
                purpose="Expose autonomous work as a reviewable pull request rather than mutating the protected base branch.",
            )
            effects.append({"kind": "PULL_REQUEST", "result": self.actor_result(pr)})
        else:
            pr_number = int(open_autonomy[0]["number"])
            comment = self.call(
                "GITHUB.COMMENT.CREATE",
                "CREATE_COMMENT",
                parameters={
                    "number": pr_number,
                    "body": (
                        f"### JANUS autonomous wake `{self.run_key}`\n\n"
                        f"**Question:** {proposal['question']}\n\n"
                        f"**Why now:** {proposal['why']}\n\n"
                        f"**Mode:** `{mode}`\n\n"
                        "No second autonomy PR was opened because the habitat permits at most one open autonomy PR at a time."
                    )[:MAX_COMMENT_CHARS],
                },
                purpose="Continue the existing autonomous work thread without spawning unbounded parallel PRs.",
            )
            effects.append({"kind": "PR_COMMENT", "pr_number": pr_number, "result": self.actor_result(comment)})

        if observatory:
            comment = self.call(
                "GITHUB.COMMENT.CREATE",
                "CREATE_COMMENT",
                parameters={
                    "number": observatory,
                    "body": (
                        f"### Wake `{self.run_key}`\n"
                        f"- mode: `{mode}`\n"
                        f"- question: {proposal['question']}\n"
                        f"- searches: {', '.join('`'+q+'`' for q in proposal.get('queries', [])) or 'none'}\n"
                        f"- durable effects this cycle: {', '.join(row['kind'] for row in effects) or 'none'}\n"
                        "- high-impact authority: **not granted**"
                    )[:MAX_COMMENT_CHARS],
                },
                purpose="Leave a compact wake receipt in the persistent JANUS autonomy observatory.",
            )
            effects.append({"kind": "OBSERVATORY_COMMENT", "issue_number": observatory, "result": self.actor_result(comment)})

        receipt["effects"] = effects
        receipt["ledger_event_count"] = len(self.ledger.events)
        receipt["ledger_tail_hash"] = self.ledger.events[-1]["event_hash"] if self.ledger.events else None
        return receipt


def build_run_key() -> str:
    raw = os.environ.get("GITHUB_RUN_ID", "local") + ":" + os.environ.get("GITHUB_RUN_ATTEMPT", "1") + ":" + utc_now().strftime("%Y%m%d")
    return sha256(raw)[:24]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "Hawkar-usls"))
    parser.add_argument("--repo", default=(os.environ.get("GITHUB_REPOSITORY", "Hawkar-usls/Janus_Genesis").split("/", 1)[-1]))
    parser.add_argument("--base", default=os.environ.get("JANUS_AUTONOMY_BASE_BRANCH", "main"))
    parser.add_argument("--run-key", default=build_run_key())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="habitat-out/run.json")
    args = parser.parse_args()
    habitat = Habitat(args.owner, args.repo, args.base, args.run_key, dry_run=args.dry_run)
    snapshot = habitat.observe()
    proposal, mode = habitat.wonder(snapshot)
    search_results = habitat.query(proposal)
    receipt = habitat.materialize(snapshot, proposal, mode, search_results)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "run_key": args.run_key,
        "proposal_mode": mode,
        "question": proposal["question"],
        "effects": [row.get("kind") for row in receipt.get("effects", [])],
        "forbidden_autonomous_capabilities": sorted(FORBIDDEN_AUTONOMOUS_CAPABILITIES),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
