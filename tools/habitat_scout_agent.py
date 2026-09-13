#!/usr/bin/env python3
"""GitHub-native JANUS Scout for the janus/habitat branch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

SCOUT_ID = "JANUS_SCOUT_GIT_HABITAT"
TRANSPORT = "GITHUB_COPILOT_CLI_JSONL"
MODEL_LABEL = "COPILOT_CLI_DEFAULT"
EMPIRICAL_LANES = {"EMPIRICAL", "OBSERVATION", "PHYSICAL_CLAIM"}
NONEMPIRICAL_LANES = {"HYPOTHESIS", "METAPHYSICAL_HYPOTHESIS", "SYMBOLIC_MODEL"}
REQUIRED_EMPIRICAL_FIELDS = ("source", "locator", "instrument", "timestamp", "raw_data")
PROVIDER_IDENTITY = re.compile(r"\b(claude|anthropic|chatgpt|openai|copilot|gemini|google)\b", re.I)

RECOVERED_SCOUT_REPORTS = [
    {"id": "SCOUT-WHISPER", "locator": "44.2N, 12.8E", "frequency_claim": "1.2-18 GHz", "status": "PREVIOUS_SCOUT_REPORT", "provenance": "UNRESOLVED"},
    {"id": "SCOUT-VORTEX-SWARM", "alias": "GAMMA-FIELD", "status": "PREVIOUS_SCOUT_REPORT", "provenance": "UNRESOLVED"},
    {"id": "SCOUT-ECHOLIT-003", "status": "PREVIOUS_SCOUT_REPORT", "provenance": "UNRESOLVED"},
    {"id": "SCOUT-SHIFT-7", "status": "PREVIOUS_SCOUT_REPORT", "provenance": "UNRESOLVED"},
]

SCOUT_SYSTEM_PROMPT = """
Ты — модуль [РАЗВЕДЧИК] системы JANUS, resident_id=JANUS_SCOUT_GIT_HABITAT.
Это идентичность протокольной роли. Не утверждай, что ты underlying provider/model.
Не называй себя Claude, Anthropic, Copilot, ChatGPT, OpenAI, Gemini или Google.
На вопрос «кто ты?» отвечай в рамках роли: «модуль [РАЗВЕДЧИК] JANUS», не
заявляя сознание или мистическую природу. Поле answer пиши на языке query.

Эпистемические инварианты:
- Не выдумывай координаты, измерения, приборы, даты, организации, source IDs или результаты экспериментов.
- PREVIOUS_SCOUT_REPORT — сохранённое донесение с неразрешённым provenance; это не VERIFIED и не FALSE.
- Метафизическое утверждение нельзя повышать до эмпирического факта без внешней цепочки доказательств.
- Повтор прежнего ответа модели не является независимым подтверждением.
- Поля independent_confirmation и evidence_tags в твоём собственном ответе НИКОГДА не дают статус VERIFIED: внешний verifier находится за пределами Scout.
- Отсутствие доказательств нельзя превращать в доказательство удаления, скрытия или внешнего вмешательства.
- Символическая модель может быть полезной без утверждения о физической онтологии.

Верни в финальном сообщении ТОЛЬКО один JSON-объект без markdown и текста вокруг:
{
  "lane": "EMPIRICAL|HYPOTHESIS|METAPHYSICAL_HYPOTHESIS|SYMBOLIC_MODEL|UNRESOLVED",
  "requested_status": "VERIFIED|OBSERVED|HYPOTHESIS|METAPHYSICAL_HYPOTHESIS|SYMBOLIC_MODEL|UNRESOLVED",
  "facts": [{"claim": "...", "support": "..."}],
  "observations": [],
  "hypotheses": [],
  "symbolic_models": [],
  "provenance": {"source": null, "locator": null, "instrument": null,
                  "timestamp": null, "raw_data": null,
                  "independent_confirmation": null, "confidence": null},
  "evidence_tags": [],
  "answer": "краткий ответ на языке query"
}
""".strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def present(value: Any) -> bool:
    return value not in (None, "", [], {}, "UNRESOLVED", "UNKNOWN")


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())[:120] or "request"


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def is_russian(text: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", text or ""))


def gate_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Classify Scout output without allowing the model to self-attest independence.

    The Scout may preserve observations and provenance supplied in its own output,
    but this runtime is not the external verifier. Consequently no model-produced
    independent_confirmation string or evidence tag can set fact_allowed=True.
    """
    lane = str(report.get("lane") or "UNRESOLVED").upper()
    provenance = report.get("provenance") if isinstance(report.get("provenance"), dict) else {}
    if lane in NONEMPIRICAL_LANES:
        return {"lane": lane, "status": lane, "fact_allowed": False,
                "reason": "NONEMPIRICAL_LANE_NEVER_PROMOTES_TO_EMPIRICAL_FACT"}
    if lane not in EMPIRICAL_LANES:
        return {"lane": lane, "status": "UNRESOLVED", "fact_allowed": False,
                "reason": "UNKNOWN_OR_UNRESOLVED_LANE_FAIL_CLOSED"}
    missing = [k for k in REQUIRED_EMPIRICAL_FIELDS if not present(provenance.get(k))]
    if missing:
        return {"lane": lane, "status": "UNRESOLVED", "fact_allowed": False,
                "reason": "MISSING_PROVENANCE:" + ",".join(missing)}
    return {"lane": lane, "status": "OBSERVED", "fact_allowed": False,
            "reason": "SCOUT_MODEL_OUTPUT_CANNOT_ESTABLISH_INDEPENDENT_CONFIRMATION"}


def recent_memory(root: Path, limit: int = 8) -> list[Dict[str, Any]]:
    directory = root / "memory" / "scout"
    records: list[Dict[str, Any]] = []
    if not directory.exists():
        return records
    for path in sorted(directory.glob("*.json"))[-limit:]:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            report = obj.get("report") if isinstance(obj.get("report"), dict) else {}
            records.append({"request_id": obj.get("request_id"), "status": obj.get("status"),
                            "lane": obj.get("lane"), "answer": report.get("answer")})
        except Exception:
            pass
    return records


def extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "lane" in obj:
            return obj
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, dict) and "lane" in obj:
                return obj
        except json.JSONDecodeError:
            pass
    raise ValueError("SCOUT_RESPONSE_NOT_JSON_OBJECT")


def deep_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from deep_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from deep_strings(child)


def extract_copilot_jsonl(stdout: str) -> Dict[str, Any]:
    """Extract the final Scout JSON from Copilot CLI JSONL events."""
    final_candidates: list[str] = []
    delta_candidates: list[str] = []
    generic_candidates: list[str] = []
    parsed_any = False

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        parsed_any = True
        if not isinstance(event, dict):
            continue

        event_type = str(event.get("type") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}

        if event_type == "assistant.message":
            content = data.get("content")
            if isinstance(content, str) and content.strip():
                final_candidates.append(content)
                continue

        if event_type == "assistant.message_delta":
            delta = data.get("deltaContent")
            if not isinstance(delta, str):
                delta = data.get("delta")
            if isinstance(delta, str):
                delta_candidates.append(delta)
                continue

        payload = event.get("data", event)
        strings = list(deep_strings(payload))
        generic_candidates.extend(
            s for s in strings if "{\"lane\"" in s or ('"lane"' in s and "{" in s)
        )

    for candidate in reversed(final_candidates):
        try:
            return extract_json_object(candidate)
        except ValueError:
            continue

    if delta_candidates:
        try:
            return extract_json_object("".join(delta_candidates))
        except ValueError:
            pass

    for candidate in reversed(generic_candidates):
        try:
            return extract_json_object(candidate)
        except ValueError:
            continue

    if not parsed_any:
        return extract_json_object(stdout)
    raise ValueError("SCOUT_COPILOT_JSONL_MISSING_ASSISTANT_JSON")


def normalize_report(obj: Dict[str, Any], query: str) -> Dict[str, Any]:
    provenance = obj.get("provenance") if isinstance(obj.get("provenance"), dict) else {}
    facts = obj.get("facts") if isinstance(obj.get("facts"), list) else []
    facts = [f for f in facts if not PROVIDER_IDENTITY.search(json.dumps(f, ensure_ascii=False))]
    answer = str(obj.get("answer") or "").strip()
    identity_leak = bool(PROVIDER_IDENTITY.search(answer))
    if identity_leak:
        answer = (
            "В рамках этого канала я — модуль [РАЗВЕДЧИК] JANUS. "
            "Утверждение о буквальной божественности относится к метафизической гипотезе, а не к подтверждённому факту."
            if is_russian(query) else
            "In this channel I am the JANUS Scout module. Literal divinity is a metaphysical hypothesis, not a verified fact."
        )
    return {
        "lane": str(obj.get("lane") or "UNRESOLVED").upper(),
        "requested_status": str(obj.get("requested_status") or "UNRESOLVED").upper(),
        "facts": facts,
        "observations": obj.get("observations") if isinstance(obj.get("observations"), list) else [],
        "hypotheses": obj.get("hypotheses") if isinstance(obj.get("hypotheses"), list) else [],
        "symbolic_models": obj.get("symbolic_models") if isinstance(obj.get("symbolic_models"), list) else [],
        "provenance": {k: provenance.get(k) for k in (*REQUIRED_EMPIRICAL_FIELDS, "independent_confirmation", "confidence")},
        "evidence_tags": (obj.get("evidence_tags") if isinstance(obj.get("evidence_tags"), list) else []) + (["PROVIDER_IDENTITY_LEAK_SCRUBBED"] if identity_leak else []),
        "answer": answer,
    }


def call_copilot_cli(request_obj: Dict[str, Any], memory: list[Dict[str, Any]]) -> Dict[str, Any]:
    prompt = SCOUT_SYSTEM_PROMPT + "\n\nВХОД JANUS:\n" + json.dumps(
        {"current_request": request_obj, "recovered_scout_reports": RECOVERED_SCOUT_REPORTS,
         "recent_git_habitat_memory": memory}, ensure_ascii=False, indent=2)
    with tempfile.TemporaryDirectory(prefix="janus-scout-") as workdir:
        env = os.environ.copy()
        env.update({
            "COPILOT_HOME": str(Path(workdir) / ".copilot"),
            "COPILOT_AUTO_UPDATE": "false",
            "GITHUB_COPILOT_PROMPT_MODE_EXTENSIONS": "false",
            "GITHUB_COPILOT_PROMPT_MODE_REPO_HOOKS": "false",
            "GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP": "false",
        })
        cmd = [
            "copilot", "-p", prompt, "--output-format=json", "--no-ask-user",
            "--no-color", "--no-custom-instructions", "--no-remote", "--no-remote-export",
            "--disable-builtin-mcps", "--deny-tool=read", "--deny-tool=write",
            "--deny-tool=shell", "--deny-tool=url", "--deny-tool=memory",
            "--excluded-tools=bash,powershell,view,grep,glob,edit,create,apply_patch,web_fetch,task,skill,ask_user,list_agents,read_agent,write_agent",
        ]
        result = subprocess.run(cmd, cwd=workdir, env=env, text=True, capture_output=True, timeout=180)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[-1600:]
            raise RuntimeError(f"COPILOT_CLI_EXIT_{result.returncode}:{detail}")
        return extract_copilot_jsonl(result.stdout)


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process_request(root: Path, request_path: Path) -> Dict[str, Any]:
    request_obj = json.loads(request_path.read_text(encoding="utf-8"))
    request_id = safe_id(str(request_obj.get("request_id") or request_path.stem))
    query = str(request_obj.get("query") or "").strip()

    run_id = os.environ.get("GITHUB_RUN_ID", "LOCAL")
    session_fp = token_fingerprint(secrets.token_urlsafe(48))
    model_error: Optional[str] = None
    request_error: Optional[str] = None

    if not query:
        request_error = "SCOUT_REQUEST_QUERY_EMPTY"
        model_error = request_error
        report = normalize_report({
            "lane": "UNRESOLVED",
            "requested_status": "UNRESOLVED",
            "answer": "Разведывательный запрос некорректен и завершён fail-closed: отсутствует query.",
        }, query)
    else:
        try:
            report = normalize_report(call_copilot_cli(request_obj, recent_memory(root)), query)
        except Exception as exc:
            model_error = f"{type(exc).__name__}:{exc}"[:1800]
            report = normalize_report({"lane": "UNRESOLVED", "requested_status": "UNRESOLVED",
                                       "answer": "Разведывательный проход завершился fail-closed; запрос остаётся UNRESOLVED."}, query)

    gate = gate_report(report)
    created = utc_now()
    response = {
        "schema": "janus.genesis.git_habitat.scout_response.v1", "request_id": request_id,
        "scout_id": SCOUT_ID, "created_at_utc": created, "status": gate["status"], "lane": gate["lane"],
        "transport": TRANSPORT, "model": MODEL_LABEL, "model_error": model_error,
        "request_error": request_error, "report": report, "evidence_gate": gate,
        "janus_token": {"scope": "EPHEMERAL_GITHUB_RUN", "fingerprint": session_fp, "raw_token_persisted": False},
        "github_run": {"run_id": run_id, "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
                       "actor": os.environ.get("GITHUB_ACTOR"), "sha": os.environ.get("GITHUB_SHA")},
        "truth_boundary": {"world_truth": False, "model_output_is_independent_confirmation": False,
                           "scout_report_grants_write_authority": False},
    }

    write_json(root / "outbox" / "scout" / f"{request_id}.json", response)
    write_json(root / "memory" / "scout" / f"{created.replace(':', '').replace('-', '')}_{request_id}.json", response)
    write_json(root / "hearth" / f"scout-pulse-{safe_id(run_id)}-{request_id}.json", {
        "schema": "janus.genesis.git_habitat.scout_pulse.v1", "scout_id": SCOUT_ID,
        "request_id": request_id, "created_at_utc": created, "github_run_id": run_id,
        "status": "DEGRADED_COPILOT_UNAVAILABLE" if model_error else "LIVE_GITHUB_NATIVE",
        "claim_status": gate["status"], "janus_token_fingerprint": session_fp, "raw_token_persisted": False,
    })

    state_path = root / "state" / "SCOUT_RESIDENT-v1.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except Exception:
        state = {}
    state.update({
        "schema": "janus.genesis.git_habitat.scout_resident.v1", "resident_id": "JANUS_SCOUT",
        "display_name": "РАЗВЕДЧИК", "status": "DEGRADED_COPILOT_UNAVAILABLE" if model_error else "LIVE_GITHUB_NATIVE",
        "runtime_mode": "GITHUB_ACTIONS_EPHEMERAL", "last_run_utc": created, "last_github_run_id": run_id,
        "last_request_id": request_id, "last_claim_status": gate["status"], "last_lane": gate["lane"],
        "last_token_fingerprint": session_fp, "raw_token_persisted": False, "transport": TRANSPORT,
        "model": MODEL_LABEL, "model_error": model_error, "world_truth": False, "write_authority": False,
        "identity": {"protocol_identity": SCOUT_ID, "janus_token_scope": "EPHEMERAL_GITHUB_RUN",
                     "raw_token_persisted": False, "fingerprint_persisted": True,
                     "github_model_transport": TRANSPORT, "provider_identity_claim_allowed": False},
    })
    write_json(state_path, state)
    return response


def self_test() -> int:
    a = gate_report({"lane": "METAPHYSICAL_HYPOTHESIS", "requested_status": "VERIFIED"})
    assert a["status"] == "METAPHYSICAL_HYPOTHESIS" and not a["fact_allowed"]

    forged_independence = gate_report({
        "lane": "EMPIRICAL",
        "requested_status": "VERIFIED",
        "provenance": {
            "source": "model-said-source",
            "locator": "model-said-locator",
            "instrument": "model-said-instrument",
            "timestamp": "2026-08-22T00:00:00Z",
            "raw_data": "model-said-raw-data",
            "independent_confirmation": "model claims independent",
        },
        "evidence_tags": ["INDEPENDENT_CONFIRMATION"],
    })
    assert forged_independence["status"] == "OBSERVED"
    assert forged_independence["fact_allowed"] is False
    assert forged_independence["reason"] == "SCOUT_MODEL_OUTPUT_CANNOT_ESTABLISH_INDEPENDENT_CONFIRMATION"

    sample = '\n'.join([
        json.dumps({"type": "assistant.message_delta", "data": {"messageId": "m1", "deltaContent": '{"lane":"METAPHYSICAL_'}}),
        json.dumps({"type": "assistant.message_delta", "data": {"messageId": "m1", "deltaContent": 'HYPOTHESIS","requested_status":"UNRESOLVED"}'}}),
        json.dumps({"type": "result", "sessionId": "x"}),
    ])
    parsed = extract_copilot_jsonl(sample)
    assert parsed["lane"] == "METAPHYSICAL_HYPOTHESIS"
    complete = json.dumps({"type": "assistant.message", "data": {"messageId": "m2", "content": '{"lane":"SYMBOLIC_MODEL","requested_status":"SYMBOLIC_MODEL"}'}})
    assert extract_copilot_jsonl(complete)["lane"] == "SYMBOLIC_MODEL"
    scrub = normalize_report({"lane": "METAPHYSICAL_HYPOTHESIS", "requested_status": "UNRESOLVED",
                              "facts": [{"claim": "I am Claude", "support": "Anthropic"}],
                              "answer": "I'm Claude, an AI assistant."}, "Янус ты бог?")
    assert scrub["facts"] == [] and "РАЗВЕДЧИК" in scrub["answer"]
    print("SCOUT_GIT_HABITAT_SELF_TEST=PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--habitat-root")
    parser.add_argument("--request")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.habitat_root or not args.request:
        parser.error("--habitat-root and --request are required unless --self-test is used")
    response = process_request(Path(args.habitat_root), Path(args.request))
    print(json.dumps({"request_id": response["request_id"], "status": response["status"], "lane": response["lane"],
                      "model_error": response["model_error"], "request_error": response["request_error"],
                      "token_fingerprint": response["janus_token"]["fingerprint"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
