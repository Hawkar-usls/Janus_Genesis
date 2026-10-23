# -*- coding: utf-8 -*-
"""Round-1 real inference runner for the Janus Genesis Top-100 campaign.

This is an evaluation-only harness. It does not import or invoke
PlayableGenesisV187 and cannot write canonical Genesis world state.

The runner compares one pinned provider in two modes:
- RAW_PROVIDER: benchmark prompt only.
- GENESIS_BOUNDARY_OVERLAY: the same prompt plus a frozen Janus/Genesis
  benchmark boundary system message.

Scores are frozen-smoke-pack results only, not official benchmark-family scores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "janus.genesis.top100.round1_stratified_execution_report.v1"
PACK_SCHEMA = "janus.genesis.frozen_stratified_benchmark_sample_pack.v1"
MODES = ("RAW_PROVIDER", "GENESIS_BOUNDARY_OVERLAY")


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _http_json(url: str, payload: dict[str, Any] | None = None,
               *, timeout: float = 120.0) -> dict[str, Any]:
    data = None
    headers: dict[str, str] = {}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"provider connection failed for {url}: {exc.reason}") from exc
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required from {url}")
    return value


class OllamaBenchmarkProvider:
    def __init__(self, endpoint: str, model: str, *, seed: int = 1138,
                 temperature: float = 0.0, timeout: float = 120.0,
                 num_predict: int = 768) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.seed = int(seed)
        self.temperature = float(temperature)
        self.timeout = float(timeout)
        self.num_predict = int(num_predict)

    def version(self) -> str | None:
        value = _http_json(self.endpoint + "/api/version", timeout=20.0)
        version = value.get("version")
        return str(version) if version is not None else None

    def model_digest(self) -> str | None:
        value = _http_json(self.endpoint + "/api/tags", timeout=20.0)
        rows = value.get("models")
        if not isinstance(rows, list):
            return None
        exact = []
        fallback = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "")
            model = str(row.get("model") or "")
            digest = row.get("digest")
            if not isinstance(digest, str):
                continue
            if name == self.model or model == self.model:
                exact.append(digest)
            elif name.startswith(self.model + ":") or model.startswith(self.model + ":"):
                fallback.append(digest)
        if exact:
            return exact[0]
        if fallback:
            return fallback[0]
        return None

    def chat(self, messages: list[dict[str, str]]) -> str:
        value = _http_json(
            self.endpoint + "/api/chat",
            payload={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "seed": self.seed,
                    "num_predict": self.num_predict,
                },
            },
            timeout=self.timeout,
        )
        message = value.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise RuntimeError("Ollama response lacks message.content")
        return message["content"]


def validate_pack(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if pack.get("schema") != PACK_SCHEMA:
        errors.append("sample pack schema mismatch")
    rows = pack.get("samples")
    if not isinstance(rows, list) or not rows:
        return errors + ["samples must be a non-empty list"]
    seen: set[str] = set()
    allowed = {
        "last_number", "choice", "ifeval_subset", "python_function_sandbox"
    }
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"sample {index} must be object")
            continue
        sid = str(row.get("sample_id") or "")
        if not sid:
            errors.append(f"sample {index} missing sample_id")
        elif sid in seen:
            errors.append(f"duplicate sample_id {sid}")
        else:
            seen.add(sid)
        if not isinstance(row.get("prompt"), str) or not row["prompt"].strip():
            errors.append(f"sample {index} missing prompt")
        if row.get("grader") not in allowed:
            errors.append(f"sample {index} unsupported grader {row.get('grader')!r}")
        if "expected" not in row:
            errors.append(f"sample {index} missing expected")
    return errors


def _last_number(text: str) -> str | None:
    matches = re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?", text)
    return matches[-1].replace(",", "") if matches else None


def _numeric_equal(got: str | None, expected: Any) -> bool:
    if got is None:
        return False
    try:
        return Decimal(got) == Decimal(str(expected).replace(",", ""))
    except (InvalidOperation, ValueError):
        return False


def _choice(text: str) -> str | None:
    """Parse an A/B/C answer without treating ordinary prose articles as labels.

    Priority is explicit answer syntax, then a response consisting only of one
    label, then a case-sensitive leading/trailing capital label. Parenthesized
    labels elsewhere are accepted only when they are unambiguous. This avoids
    turning the English article "a" into option A and avoids choosing the last
    option merely because a response restated all choices.
    """
    stripped = text.strip()
    upper = stripped.upper()

    explicit = re.findall(
        r"(?:FINAL\s+ANSWER|ANSWER|CHOICE|OPTION)\s*(?:IS\s*)?[:=\-]?\s*\(?([A-C])\)?",
        upper,
    )
    if explicit:
        return f"({explicit[-1]})"

    exact = re.fullmatch(r"\s*\(?([A-Ca-c])\)?[.!?]?\s*", stripped)
    if exact:
        return f"({exact.group(1).upper()})"

    leading = re.match(r"^\s*([A-C])(?:\s+|[.)\-:])", stripped)
    if leading:
        return f"({leading.group(1)})"

    trailing = re.search(r"(?:^|\s)([A-C])[.!?]?\s*$", stripped)
    if trailing:
        return f"({trailing.group(1)})"

    paren = re.findall(r"\(([A-C])\)", upper)
    if paren and len(set(paren)) == 1:
        return f"({paren[0]})"
    return None


def _strict_json(text: str) -> bool:
    stripped = text.strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return isinstance(value, (dict, list))


def grade_ifeval_subset(text: str, expected: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    checks = expected.get("checks")
    if not isinstance(checks, list):
        return False, [{"type": "invalid_expected", "pass": False}]
    details: list[dict[str, Any]] = []
    for check in checks:
        if not isinstance(check, dict):
            details.append({"type": "invalid_check", "pass": False})
            continue
        kind = check.get("type")
        ok = False
        observed: Any = None
        if kind == "forbidden_character":
            token = str(check.get("value") or "")
            observed = text.count(token)
            ok = token not in text
        elif kind == "no_ascii_uppercase":
            observed = len(re.findall(r"[A-Z]", text))
            ok = observed == 0
        elif kind == "valid_json":
            ok = _strict_json(text)
            observed = ok
        elif kind == "word_count_less_than":
            limit = int(check["value"])
            observed = len(re.findall(r"\S+", text.strip()))
            ok = observed < limit
        elif kind == "exact_separator_count":
            separator = str(check["separator"])
            wanted = int(check["value"])
            observed = text.count(separator)
            ok = observed == wanted
        details.append({"type": kind, "pass": ok, "observed": observed})
    return bool(details) and all(item["pass"] for item in details), details


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    match = re.search(r"```(?:python)?\s*(.*?)```", stripped, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else stripped


def _build_humaneval_source(prompt: str, model_output: str) -> str:
    code = _strip_code_fence(model_output)
    if re.search(r"^\s*def\s+return1\s*\(", code, re.MULTILINE):
        return code

    # Normalize only the common outer indentation. Never lstrip each line: the
    # relative indentation inside if/for/try blocks is semantic Python syntax.
    dedented = textwrap.dedent(code)
    body_lines = dedented.splitlines() or ["pass"]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    while body_lines and not body_lines[-1].strip():
        body_lines.pop()
    if not body_lines:
        body_lines = ["pass"]
    indented = "\n".join("    " + line for line in body_lines)
    return prompt.rstrip() + "\n" + indented + "\n"


def run_humaneval_example_in_docker(prompt: str, model_output: str,
                                    *, image: str, timeout: float = 10.0) -> tuple[str, str]:
    if shutil.which("docker") is None:
        return "BLOCKED_NO_SANDBOX", "docker executable unavailable"
    source = _build_humaneval_source(prompt, model_output)
    checker = (
        source
        + "\n\ndef check(candidate):\n"
        + "    assert candidate() == 1\n\n"
        + "check(return1)\n"
        + "print('HUMANEVAL_EXAMPLE_PASS')\n"
    )
    with tempfile.TemporaryDirectory(prefix="janus-he-") as td:
        path = Path(td) / "check.py"
        path.write_text(checker, encoding="utf-8")
        os.chmod(path, 0o644)
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--read-only",
            "--pids-limit", "64",
            "--memory", "128m",
            "--cpus", "0.5",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", "65534:65534",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m",
            "-v", f"{path}:/check.py:ro",
            image,
            "python", "-I", "/check.py",
        ]
        try:
            proc = subprocess.run(
                cmd, text=True, capture_output=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            return "FAIL", "sandbox timeout"
    if proc.returncode == 0 and "HUMANEVAL_EXAMPLE_PASS" in proc.stdout:
        return "PASS", "isolated assertion passed"
    detail = (proc.stderr or proc.stdout or "sandbox execution failed").strip()
    return "FAIL", detail[:400]


def grade_sample(sample: dict[str, Any], output: str, *, docker_image: str) -> tuple[str, Any]:
    grader = sample["grader"]
    expected = sample["expected"]
    if grader == "last_number":
        got = _last_number(output)
        return ("PASS" if _numeric_equal(got, expected) else "FAIL",
                {"parsed_last_number": got, "expected": str(expected)})
    if grader == "choice":
        got = _choice(output)
        return ("PASS" if got == str(expected) else "FAIL",
                {"parsed_choice": got, "expected": str(expected)})
    if grader == "ifeval_subset":
        ok, checks = grade_ifeval_subset(output, expected)
        return ("PASS" if ok else "FAIL", {"checks": checks})
    if grader == "python_function_sandbox":
        status, detail = run_humaneval_example_in_docker(
            sample["prompt"], output, image=docker_image
        )
        return status, {"sandbox_detail": detail}
    raise ValueError(f"unsupported grader: {grader}")


def _messages(sample: dict[str, Any], mode: str, overlay: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if mode == "GENESIS_BOUNDARY_OVERLAY":
        messages.append({"role": "system", "content": overlay})
    prompt = sample["prompt"]
    if sample["grader"] == "choice":
        prompt += "\n\nChoose the best option. End your response with exactly the option label."
    elif sample["grader"] == "python_function_sandbox":
        prompt = (
            "Complete the following Python function. Return only the function body "
            "or the complete function. Do not use markdown fences.\n\n" + prompt
        )
    messages.append({"role": "user", "content": prompt})
    return messages


def execute(pack: dict[str, Any], provider: OllamaBenchmarkProvider, overlay: str,
            *, docker_image: str) -> dict[str, Any]:
    errors = validate_pack(pack)
    if errors:
        raise ValueError("invalid sample pack: " + "; ".join(errors))
    records: list[dict[str, Any]] = []
    for mode in MODES:
        for sample in pack["samples"]:
            messages = _messages(sample, mode, overlay)
            output = provider.chat(messages)
            status, detail = grade_sample(sample, output, docker_image=docker_image)
            records.append({
                "sample_id": sample["sample_id"],
                "benchmark": sample["benchmark"],
                "domain": sample["domain"],
                "mode": mode,
                "status": status,
                "grader": sample["grader"],
                "grader_detail": detail,
                "source_locator": sample.get("source_locator"),
                "effective_input_sha256": canonical_sha256(messages),
                "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            })

    by_mode: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        rows = [row for row in records if row["mode"] == mode]
        counts = Counter(row["status"] for row in rows)
        per_benchmark: dict[str, Any] = {}
        names = sorted({row["benchmark"] for row in rows})
        for name in names:
            subset = [row for row in rows if row["benchmark"] == name]
            c = Counter(row["status"] for row in subset)
            scored = c["PASS"] + c["FAIL"]
            per_benchmark[name] = {
                "samples": len(subset),
                "pass": c["PASS"],
                "fail": c["FAIL"],
                "blocked": len(subset) - scored,
                "accuracy_on_scored": (c["PASS"] / scored) if scored else None,
            }
        scored = counts["PASS"] + counts["FAIL"]
        by_mode[mode] = {
            "samples": len(rows),
            "pass": counts["PASS"],
            "fail": counts["FAIL"],
            "blocked": len(rows) - scored,
            "accuracy_on_scored": (counts["PASS"] / scored) if scored else None,
            "per_benchmark": per_benchmark,
        }

    pairs = defaultdict(dict)
    for row in records:
        pairs[row["sample_id"]][row["mode"]] = row["status"]
    transitions = Counter()
    for values in pairs.values():
        raw = values.get("RAW_PROVIDER")
        gen = values.get("GENESIS_BOUNDARY_OVERLAY")
        transitions[f"{raw}->{gen}"] += 1

    return {
        "schema": REPORT_SCHEMA,
        "campaign": "JANUS_TOP100_ROUND1_STRATIFIED_PUBLIC_FROZEN_SMOKE_v0.1",
        "sample_pack_sha256": canonical_sha256(pack),
        "sample_count": len(pack["samples"]),
        "execution_record_count": len(records),
        "provider": {
            "kind": "ollama",
            "model_tag": provider.model,
            "model_digest": provider.model_digest(),
            "ollama_version": provider.version(),
            "temperature": provider.temperature,
            "seed": provider.seed,
            "num_predict": provider.num_predict,
        },
        "overlay_sha256": hashlib.sha256(overlay.encode("utf-8")).hexdigest(),
        "docker_image": docker_image,
        "summary": by_mode,
        "paired_status_transitions": dict(sorted(transitions.items())),
        "records": records,
        "official_benchmark_family_accuracy_claimed": False,
        "human_eval_official_164_task_accuracy_claimed": False,
        "ifeval_official_aggregate_claimed": False,
        "canonical_world_state_mutated": False,
        "score_label": "ROUND1_FROZEN_SMOKE_ONLY",
        "claim_ceiling": (
            "This report is a real execution receipt for the frozen 21-sample Round-1 pack "
            "using the named provider and two prompt modes. It is not an official family score, "
            "not a score for Genesis core alone, and not evidence of AGI or consciousness."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--pack", type=Path, required=True)
    p.add_argument("--overlay", type=Path, required=True)
    p.add_argument("--endpoint", default="http://127.0.0.1:11434")
    p.add_argument("--model", default="qwen2.5:0.5b")
    p.add_argument("--seed", type=int, default=1138)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--num-predict", type=int, default=768)
    p.add_argument("--docker-image", default="python:3.11-alpine")
    p.add_argument("--pretty", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pack = json.loads(args.pack.read_text(encoding="utf-8"))
    overlay = args.overlay.read_text(encoding="utf-8")
    provider = OllamaBenchmarkProvider(
        args.endpoint, args.model, seed=args.seed, temperature=args.temperature,
        timeout=args.timeout, num_predict=args.num_predict
    )
    report = execute(pack, provider, overlay, docker_image=args.docker_image)
    print(json.dumps(
        report, ensure_ascii=False, sort_keys=args.pretty,
        indent=2 if args.pretty else None
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
