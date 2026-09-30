# -*- coding: utf-8 -*-
"""GitHub-native cognition adapter for JANUS Genesis Third Wish.

GitHub Models was retired on 2026-07-30.  v18.7.51 therefore uses GitHub
Copilot CLI in non-interactive proposal-only mode while keeping the historical
class name as a compatibility alias for the Habitat code already under review.

The short-lived Actions token remains broker-side.  Copilot may return language
or a plan, but it receives no GitHub effect authority from this adapter.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from genesis_v18_7_40_third_wish_capability_fabric import ActionIntent, ThirdWishCapabilityFabric

VERSION = "18.7.51"
TOKEN_ENV = "JANUS_GITHUB_BROKER_TOKEN"
MODEL_ENV = "JANUS_COPILOT_MODEL"
LEGACY_MODEL_ENV = "JANUS_GITHUB_MODELS_MODEL"
DEFAULT_MODEL = "auto"
MAX_MESSAGES = 12
MAX_INPUT_BYTES = 48 * 1024
MAX_OUTPUT_CHARS = 24_000
COPILOT_TIMEOUT_SECONDS = 90.0


class GitHubModelsBrokerError(RuntimeError):
    """Compatibility error name retained for existing Third Wish tests."""


class ModelsTransport(Protocol):
    def chat(self, *, model: str, messages: list[dict[str, str]]) -> Mapping[str, Any]: ...


def _render_prompt(messages: list[dict[str, str]]) -> str:
    parts = [
        "You are a proposal-only cognition provider inside JANUS Third Wish.",
        "Do not execute tools, change files, contact URLs, or ask the user questions.",
        "Return only the requested answer. Repository effects are handled by a separate typed broker.",
        "",
    ]
    for row in messages:
        parts.append(f"[{row['role'].upper()}]\n{row['content']}")
    return "\n\n".join(parts)


class GitHubCopilotCLITransport:
    """Run the current GitHub Copilot CLI as a no-effect proposal provider."""

    def __init__(self, *, token_env: str = TOKEN_ENV, timeout_seconds: float = COPILOT_TIMEOUT_SECONDS) -> None:
        self.token_env = token_env
        self.timeout_seconds = float(timeout_seconds)

    def _token(self) -> str:
        token = os.environ.get(self.token_env, "").strip()
        if not token:
            raise GitHubModelsBrokerError(f"BROKER_CREDENTIAL_ENV_MISSING:{self.token_env}")
        return token

    def chat(self, *, model: str, messages: list[dict[str, str]]) -> Mapping[str, Any]:
        executable = shutil.which("copilot")
        if not executable:
            raise GitHubModelsBrokerError("COPILOT_CLI_NOT_INSTALLED")
        prompt = _render_prompt(messages)
        token = self._token()
        with tempfile.TemporaryDirectory(prefix="janus-copilot-home-") as home:
            env = dict(os.environ)
            # The ephemeral Actions token is exposed only to the broker child process.
            env["COPILOT_GITHUB_TOKEN"] = token
            env["GITHUB_TOKEN"] = token
            env.pop("GH_TOKEN", None)
            env["COPILOT_HOME"] = home
            env["COPILOT_AUTO_UPDATE"] = "false"
            env["CI"] = "true"
            command = [
                executable,
                "-p",
                prompt,
                f"--model={model or DEFAULT_MODEL}",
                "--no-ask-user",
                "--silent",
                "--no-color",
                "--no-custom-instructions",
                "--no-remote",
                "--no-remote-export",
                "--no-auto-update",
                "--deny-tool=shell",
                "--deny-tool=write",
                "--deny-tool=url",
                "--deny-tool=memory",
            ]
            try:
                proc = subprocess.run(
                    command,
                    cwd=os.getcwd(),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise GitHubModelsBrokerError("COPILOT_CLI_TIMEOUT") from exc
        if proc.returncode != 0:
            raise GitHubModelsBrokerError(f"COPILOT_CLI_EXIT_{proc.returncode}")
        text = str(proc.stdout or "").strip()
        if not text:
            raise GitHubModelsBrokerError("COPILOT_CLI_EMPTY_RESPONSE")
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS]
        # Preserve the old chat-completion shaped transport contract so the
        # frozen Third Wish handler surface does not need an authority rewrite.
        return {
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "provider": "github_copilot_cli",
            "resolved_model": model or DEFAULT_MODEL,
        }


# Historical import compatibility.  This is intentionally no longer a REST
# GitHub Models transport; the service is retired and returned HTTP 410 in the
# live provider probe on 2026-08-16.
GitHubModelsRESTTransport = GitHubCopilotCLITransport


@dataclass
class GitHubModelsThirdWishBroker:
    """Compatibility-named MODEL.CALL broker backed by GitHub Copilot CLI."""

    transport: ModelsTransport
    model: str = DEFAULT_MODEL

    REGISTERED_CAPABILITIES = ("MODEL.CALL",)

    @classmethod
    def system(cls) -> "GitHubModelsThirdWishBroker":
        selected = (
            os.environ.get(MODEL_ENV, "").strip()
            or os.environ.get(LEGACY_MODEL_ENV, "").strip()
            or DEFAULT_MODEL
        )
        return cls(transport=GitHubCopilotCLITransport(), model=selected)

    def register(self, fabric: ThirdWishCapabilityFabric) -> None:
        fabric.register_handler("MODEL.CALL", self.model_call, preflight=self.preflight)

    def preflight(self, intent: ActionIntent) -> Mapping[str, Any]:
        # The old target is retained as a compatibility resource identifier for
        # v18.7.51.  Neither target gives the model GitHub write authority.
        if intent.target not in {"model:github-models", "model:github-copilot-cli"}:
            raise GitHubModelsBrokerError("GITHUB_COPILOT_TARGET_REQUIRED")
        if intent.operation.upper() not in {"CHAT", "INFER"}:
            raise GitHubModelsBrokerError("UNSUPPORTED_MODEL_OPERATION")
        messages = intent.parameters.get("messages")
        if not isinstance(messages, list) or not messages or len(messages) > MAX_MESSAGES:
            raise GitHubModelsBrokerError("MODEL_MESSAGES_SHAPE_INVALID")
        normalized: list[dict[str, str]] = []
        for row in messages:
            if not isinstance(row, Mapping):
                raise GitHubModelsBrokerError("MODEL_MESSAGE_NOT_OBJECT")
            role = str(row.get("role") or "").strip()
            content = str(row.get("content") or "")
            if role not in {"system", "user", "assistant"} or not content:
                raise GitHubModelsBrokerError("MODEL_MESSAGE_INVALID")
            normalized.append({"role": role, "content": content})
        encoded = json.dumps(normalized, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_INPUT_BYTES:
            raise GitHubModelsBrokerError("MODEL_INPUT_TOO_LARGE")
        return {
            "validated": True,
            "provider": "github_copilot_cli",
            "model": self.model,
            "transport_called": False,
            "write_authority": False,
            "tool_effect_authority": False,
        }

    def model_call(self, intent: ActionIntent) -> Mapping[str, Any]:
        self.preflight(intent)
        messages = [
            {"role": str(row["role"]), "content": str(row["content"])}
            for row in intent.parameters["messages"]
        ]
        data = self.transport.chat(model=self.model, messages=messages)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise GitHubModelsBrokerError("COPILOT_CHOICES_MISSING")
        message = choices[0].get("message")
        if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
            raise GitHubModelsBrokerError("COPILOT_CONTENT_MISSING")
        text = str(message["content"])
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS]
        return {
            "provider": "github_copilot_cli",
            "model": self.model,
            "text": text,
            "authority": "proposal_only",
            "github_write_authority": False,
            "tool_effect_authority": False,
            "credential_exposed": False,
        }
