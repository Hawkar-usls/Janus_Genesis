#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JANUS Beacon Predictive Witness v1.

Authority-neutral online forecasting for Habitat actions and outcomes.

The predictor learns only from explicitly settled historical forecast/outcome
pairs. It predicts:
  1. a distribution over a caller-declared candidate action set;
  2. an outcome success probability for every candidate action.

Forecasts are frozen before their outcomes, wrong forecasts remain in state,
and every settlement updates calibration statistics.  The module has no
network, filesystem, subprocess, model-provider, command, merge, or source
writeback primitive.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from typing import Any, Mapping, Sequence


FORECAST_SCHEMA = "janus.beacon.predictive_forecast.v1"
OUTCOME_SCHEMA = "janus.beacon.predictive_outcome.v1"
STATE_SCHEMA = "janus.beacon.predictive_state.v1"
MAX_CONTEXT_KEYS = 32
MAX_CANDIDATES = 32
MAX_ID_CHARS = 128
CALIBRATION_BINS = 10
MIN_BIN_CALIBRATION = 5
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:/-]+$")


class BeaconPredictionError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _safe_id(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_ID_CHARS
        or _SAFE_ID.fullmatch(value) is None
    ):
        raise BeaconPredictionError(
            f"{label} must match {_SAFE_ID.pattern} and be <= {MAX_ID_CHARS} chars"
        )
    return value


def _event_index(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BeaconPredictionError(f"{label} must be a non-negative integer")
    return value


def _normalize_scalar(value: Any, label: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > 256:
            raise BeaconPredictionError(f"{label} text too long")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BeaconPredictionError(f"{label} must be finite")
        return value
    raise BeaconPredictionError(f"{label} must be a JSON scalar")


def context_digest(context: Mapping[str, Any]) -> str:
    if not isinstance(context, Mapping):
        raise BeaconPredictionError("context must be an object")
    if len(context) > MAX_CONTEXT_KEYS:
        raise BeaconPredictionError("context has too many keys")
    normalized: dict[str, Any] = {}
    for key, value in context.items():
        if (
            not isinstance(key, str)
            or not key
            or len(key) > 96
            or _SAFE_ID.fullmatch(key) is None
        ):
            raise BeaconPredictionError("context keys must be bounded safe identifiers")
        normalized[key] = _normalize_scalar(value, f"context.{key}")
    return canonical_sha256(normalized)


def _probability(value: float) -> float:
    return min(1.0 - 1e-12, max(1e-12, float(value)))


def _cell(successes: int = 0, total: int = 0) -> dict[str, int]:
    return {"successes": int(successes), "total": int(total)}


def _validate_cell(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != {"successes", "total"}:
        raise BeaconPredictionError(f"{label} cell schema invalid")
    successes = value.get("successes")
    total = value.get("total")
    if (
        isinstance(successes, bool)
        or isinstance(total, bool)
        or not isinstance(successes, int)
        or not isinstance(total, int)
        or successes < 0
        or total < 0
        or successes > total
    ):
        raise BeaconPredictionError(f"{label} cell counts invalid")
    return _cell(successes, total)


class JanusBeaconPredictiveWitness:
    """Online, prequential, authority-neutral project predictor."""

    def __init__(self) -> None:
        self.state_sequence = 0
        self.global_success = _cell()
        self.action_success: dict[str, dict[str, int]] = {}
        self.context_action_success: dict[str, dict[str, int]] = {}
        self.global_action_counts: dict[str, int] = {}
        self.context_action_counts: dict[str, dict[str, int]] = {}
        self.calibration_bins = [
            {"successes": 0, "total": 0, "sum_raw_p": 0.0}
            for _ in range(CALIBRATION_BINS)
        ]
        self.pending: dict[str, dict[str, Any]] = {}
        self.outcomes: dict[str, dict[str, Any]] = {}
        self.metric_sums = {
            "supported_outcomes": 0,
            "raw_brier_sum": 0.0,
            "calibrated_brier_sum": 0.0,
            "success_logloss_sum": 0.0,
            "next_action_logloss_sum": 0.0,
        }

    @staticmethod
    def _candidate_list(candidates: Sequence[str]) -> list[str]:
        if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
            raise BeaconPredictionError("candidates must be a sequence")
        if not 1 <= len(candidates) <= MAX_CANDIDATES:
            raise BeaconPredictionError(f"candidate count must be 1..{MAX_CANDIDATES}")
        normalized = [_safe_id(item, "candidate action") for item in candidates]
        if len(set(normalized)) != len(normalized):
            raise BeaconPredictionError("candidate actions must be unique")
        return normalized

    def _success_probability(self, ctx: str, action: str) -> tuple[float, float]:
        g = self.global_success
        a = self.action_success.get(action, _cell())
        c = self.context_action_success.get(f"{ctx}|{action}", _cell())
        successes = 1.0 + c["successes"] + 0.5 * a["successes"] + 0.1 * g["successes"]
        total = 2.0 + c["total"] + 0.5 * a["total"] + 0.1 * g["total"]
        raw = successes / total
        effective_n = c["total"] + 0.5 * a["total"] + 0.1 * g["total"]
        uncertainty = math.sqrt(max(raw * (1.0 - raw), 0.0) / (effective_n + 2.0))
        return raw, uncertainty

    def _calibrated_probability(self, raw: float) -> float:
        idx = min(CALIBRATION_BINS - 1, int(raw * CALIBRATION_BINS))
        row = self.calibration_bins[idx]
        if row["total"] < MIN_BIN_CALIBRATION:
            return raw
        empirical = (row["successes"] + 1.0) / (row["total"] + 2.0)
        weight = row["total"] / (row["total"] + 10.0)
        return (1.0 - weight) * raw + weight * empirical

    def _next_distribution(self, ctx: str, candidates: Sequence[str]) -> dict[str, float]:
        local = self.context_action_counts.get(ctx, {})
        scores: dict[str, float] = {}
        for action in candidates:
            scores[action] = 1.0 + float(local.get(action, 0)) + 0.25 * float(self.global_action_counts.get(action, 0))
        denom = sum(scores.values())
        return {action: scores[action] / denom for action in candidates}

    def forecast(
        self,
        *,
        forecast_id: str,
        context: Mapping[str, Any],
        candidates: Sequence[str],
        event_index: int,
        forecast_exposed_to_selector: bool = False,
    ) -> dict[str, Any]:
        forecast_id = _safe_id(forecast_id, "forecast_id")
        event_index = _event_index(event_index, "event_index")
        if not isinstance(forecast_exposed_to_selector, bool):
            raise BeaconPredictionError("forecast_exposed_to_selector must be boolean")
        ctx = context_digest(context)
        actions = self._candidate_list(candidates)
        input_binding = canonical_sha256({
            "forecast_id": forecast_id,
            "context_sha256": ctx,
            "candidates": actions,
            "event_index": event_index,
            "forecast_exposed_to_selector": forecast_exposed_to_selector,
        })

        if forecast_id in self.outcomes:
            prior = self.outcomes[forecast_id]["forecast"]
            if prior["input_binding_sha256"] != input_binding:
                raise BeaconPredictionError("forecast_id already settled with different input")
            return deepcopy(prior)
        if forecast_id in self.pending:
            prior = self.pending[forecast_id]
            if prior["input_binding_sha256"] != input_binding:
                raise BeaconPredictionError("forecast_id already bound to different input")
            return deepcopy(prior)

        next_dist = self._next_distribution(ctx, actions)
        success: dict[str, Any] = {}
        for action in actions:
            raw, uncertainty = self._success_probability(ctx, action)
            calibrated = self._calibrated_probability(raw)
            success[action] = {
                "raw_probability": raw,
                "calibrated_probability": calibrated,
                "uncertainty": uncertainty,
                "action_samples": self.action_success.get(action, _cell())["total"],
                "context_action_samples": self.context_action_success.get(f"{ctx}|{action}", _cell())["total"],
            }

        self.state_sequence += 1
        result = {
            "schema": FORECAST_SCHEMA,
            "forecast_id": forecast_id,
            "forecast_event_index": event_index,
            "context_sha256": ctx,
            "candidates": actions,
            "next_action_distribution": next_dist,
            "success_forecast": success,
            "forecast_exposed_to_selector": forecast_exposed_to_selector,
            "input_binding_sha256": input_binding,
            "state_sequence_at_forecast": self.state_sequence,
            "prediction_is_command": False,
            "prediction_is_permission": False,
            "prediction_is_truth": False,
        }
        result["forecast_receipt_sha256"] = canonical_sha256(result)
        self.pending[forecast_id] = deepcopy(result)
        return deepcopy(result)

    def settle(self, *, forecast_id: str, outcome_event_index: int, actual_action: str, success: bool) -> dict[str, Any]:
        forecast_id = _safe_id(forecast_id, "forecast_id")
        outcome_event_index = _event_index(outcome_event_index, "outcome_event_index")
        actual_action = _safe_id(actual_action, "actual_action")
        if not isinstance(success, bool):
            raise BeaconPredictionError("success must be boolean")

        if forecast_id in self.outcomes:
            prior = self.outcomes[forecast_id]["outcome"]
            if prior["outcome_event_index"] != outcome_event_index or prior["actual_action"] != actual_action or prior["success"] is not success:
                raise BeaconPredictionError("forecast outcome already bound differently")
            return deepcopy(prior)

        forecast = self.pending.get(forecast_id)
        if forecast is None:
            raise BeaconPredictionError("unknown pending forecast")
        if outcome_event_index <= forecast["forecast_event_index"]:
            raise BeaconPredictionError("outcome must occur after forecast")

        ctx = forecast["context_sha256"]
        in_support = actual_action in forecast["candidates"]
        predicted = forecast["success_forecast"].get(actual_action) if in_support else None
        next_action_probability = forecast["next_action_distribution"].get(actual_action) if in_support else None

        self.global_success["total"] += 1
        self.global_success["successes"] += int(success)
        action_cell = self.action_success.setdefault(actual_action, _cell())
        action_cell["total"] += 1
        action_cell["successes"] += int(success)
        ctx_action_cell = self.context_action_success.setdefault(f"{ctx}|{actual_action}", _cell())
        ctx_action_cell["total"] += 1
        ctx_action_cell["successes"] += int(success)
        self.global_action_counts[actual_action] = self.global_action_counts.get(actual_action, 0) + 1
        local_counts = self.context_action_counts.setdefault(ctx, {})
        local_counts[actual_action] = local_counts.get(actual_action, 0) + 1

        metrics_delta = {"supported": in_support, "raw_brier": None, "calibrated_brier": None, "success_logloss": None, "next_action_logloss": None}
        if predicted is not None:
            y = 1.0 if success else 0.0
            raw_p = _probability(predicted["raw_probability"])
            cal_p = _probability(predicted["calibrated_probability"])
            raw_brier = (raw_p - y) ** 2
            cal_brier = (cal_p - y) ** 2
            success_logloss = -(y * math.log(cal_p) + (1.0 - y) * math.log(1.0 - cal_p))
            next_logloss = -math.log(_probability(float(next_action_probability)))
            metrics_delta.update({"raw_brier": raw_brier, "calibrated_brier": cal_brier, "success_logloss": success_logloss, "next_action_logloss": next_logloss})
            self.metric_sums["supported_outcomes"] += 1
            self.metric_sums["raw_brier_sum"] += raw_brier
            self.metric_sums["calibrated_brier_sum"] += cal_brier
            self.metric_sums["success_logloss_sum"] += success_logloss
            self.metric_sums["next_action_logloss_sum"] += next_logloss
            idx = min(CALIBRATION_BINS - 1, int(raw_p * CALIBRATION_BINS))
            row = self.calibration_bins[idx]
            row["total"] += 1
            row["successes"] += int(success)
            row["sum_raw_p"] += raw_p

        self.state_sequence += 1
        outcome = {
            "schema": OUTCOME_SCHEMA,
            "forecast_id": forecast_id,
            "forecast_receipt_sha256": forecast["forecast_receipt_sha256"],
            "forecast_event_index": forecast["forecast_event_index"],
            "outcome_event_index": outcome_event_index,
            "actual_action": actual_action,
            "success": success,
            "actual_action_in_forecast_support": in_support,
            "forecast_exposed_to_selector": forecast["forecast_exposed_to_selector"],
            "metrics_delta": metrics_delta,
            "state_sequence_after_settlement": self.state_sequence,
            "outcome_grants_authority": False,
        }
        outcome["outcome_receipt_sha256"] = canonical_sha256(outcome)
        self.pending.pop(forecast_id)
        self.outcomes[forecast_id] = {"forecast": deepcopy(forecast), "outcome": deepcopy(outcome)}
        return deepcopy(outcome)

    def metrics(self) -> dict[str, Any]:
        supported = int(self.metric_sums["supported_outcomes"])
        denom = max(supported, 1)
        ece_n = 0
        ece_weighted = 0.0
        bins = []
        for idx, row in enumerate(self.calibration_bins):
            total = int(row["total"])
            successes = int(row["successes"])
            mean_p = row["sum_raw_p"] / total if total else None
            empirical = successes / total if total else None
            gap = abs(mean_p - empirical) if total else None
            if total:
                ece_n += total
                ece_weighted += total * float(gap)
            bins.append({"bin": idx, "total": total, "successes": successes, "mean_raw_probability": mean_p, "empirical_success_rate": empirical, "absolute_calibration_gap": gap})
        return {
            "settled_forecasts": len(self.outcomes),
            "pending_forecasts": len(self.pending),
            "supported_outcomes": supported,
            "mean_raw_brier": self.metric_sums["raw_brier_sum"] / denom if supported else None,
            "mean_calibrated_brier": self.metric_sums["calibrated_brier_sum"] / denom if supported else None,
            "mean_success_logloss": self.metric_sums["success_logloss_sum"] / denom if supported else None,
            "mean_next_action_logloss": self.metric_sums["next_action_logloss_sum"] / denom if supported else None,
            "expected_calibration_error": ece_weighted / ece_n if ece_n else None,
            "calibration_bins": bins,
        }

    def export_state(self) -> dict[str, Any]:
        state = {
            "schema": STATE_SCHEMA,
            "state_sequence": self.state_sequence,
            "global_success": deepcopy(self.global_success),
            "action_success": deepcopy(self.action_success),
            "context_action_success": deepcopy(self.context_action_success),
            "global_action_counts": deepcopy(self.global_action_counts),
            "context_action_counts": deepcopy(self.context_action_counts),
            "calibration_bins": deepcopy(self.calibration_bins),
            "pending": deepcopy(self.pending),
            "outcomes": deepcopy(self.outcomes),
            "metric_sums": deepcopy(self.metric_sums),
            "raw_context_persisted": False,
            "authority_delta": 0,
        }
        state["state_receipt_sha256"] = canonical_sha256(state)
        return state

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> "JanusBeaconPredictiveWitness":
        if not isinstance(state, Mapping):
            raise BeaconPredictionError("state must be an object")
        expected = {"schema", "state_sequence", "global_success", "action_success", "context_action_success", "global_action_counts", "context_action_counts", "calibration_bins", "pending", "outcomes", "metric_sums", "raw_context_persisted", "authority_delta", "state_receipt_sha256"}
        if set(state) != expected or state.get("schema") != STATE_SCHEMA:
            raise BeaconPredictionError("state schema invalid")
        receipt = state.get("state_receipt_sha256")
        if not isinstance(receipt, str) or len(receipt) != 64:
            raise BeaconPredictionError("state receipt invalid")
        unsigned = dict(state)
        unsigned.pop("state_receipt_sha256")
        if canonical_sha256(unsigned) != receipt:
            raise BeaconPredictionError("state receipt mismatch")
        if state.get("raw_context_persisted") is not False:
            raise BeaconPredictionError("state claims raw context persistence")
        if state.get("authority_delta") != 0:
            raise BeaconPredictionError("state authority delta invalid")
        sequence = state.get("state_sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise BeaconPredictionError("state_sequence invalid")

        obj = cls()
        obj.state_sequence = sequence
        obj.global_success = _validate_cell(state.get("global_success"), "global_success")

        def cells(mapping: Any, label: str) -> dict[str, dict[str, int]]:
            if not isinstance(mapping, Mapping):
                raise BeaconPredictionError(f"{label} must be an object")
            out = {}
            for key, value in mapping.items():
                if not isinstance(key, str):
                    raise BeaconPredictionError(f"{label} key invalid")
                out[key] = _validate_cell(value, f"{label}.{key}")
            return out

        obj.action_success = cells(state.get("action_success"), "action_success")
        obj.context_action_success = cells(state.get("context_action_success"), "context_action_success")

        def counts(mapping: Any, label: str) -> dict[str, int]:
            if not isinstance(mapping, Mapping):
                raise BeaconPredictionError(f"{label} must be an object")
            out = {}
            for key, value in mapping.items():
                if not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise BeaconPredictionError(f"{label} invalid count")
                out[key] = value
            return out

        obj.global_action_counts = counts(state.get("global_action_counts"), "global_action_counts")
        raw_context_counts = state.get("context_action_counts")
        if not isinstance(raw_context_counts, Mapping):
            raise BeaconPredictionError("context_action_counts invalid")
        obj.context_action_counts = {str(ctx): counts(action_map, f"context_action_counts.{ctx}") for ctx, action_map in raw_context_counts.items()}

        raw_bins = state.get("calibration_bins")
        if not isinstance(raw_bins, list) or len(raw_bins) != CALIBRATION_BINS:
            raise BeaconPredictionError("calibration bins invalid")
        obj.calibration_bins = []
        for row in raw_bins:
            if not isinstance(row, Mapping) or set(row) != {"successes", "total", "sum_raw_p"}:
                raise BeaconPredictionError("calibration row invalid")
            successes = row["successes"]
            total = row["total"]
            sum_raw = row["sum_raw_p"]
            if isinstance(successes, bool) or isinstance(total, bool) or not isinstance(successes, int) or not isinstance(total, int) or successes < 0 or total < successes or isinstance(sum_raw, bool) or not isinstance(sum_raw, (int, float)) or not math.isfinite(float(sum_raw)) or float(sum_raw) < 0:
                raise BeaconPredictionError("calibration row counts invalid")
            obj.calibration_bins.append({"successes": successes, "total": total, "sum_raw_p": float(sum_raw)})

        if not isinstance(state.get("pending"), Mapping) or not isinstance(state.get("outcomes"), Mapping):
            raise BeaconPredictionError("forecast stores invalid")
        obj.pending = deepcopy(dict(state["pending"]))
        obj.outcomes = deepcopy(dict(state["outcomes"]))

        raw_metrics = state.get("metric_sums")
        if not isinstance(raw_metrics, Mapping) or set(raw_metrics) != set(obj.metric_sums):
            raise BeaconPredictionError("metric_sums invalid")
        parsed_metrics = {}
        for key, value in raw_metrics.items():
            if key == "supported_outcomes":
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise BeaconPredictionError("supported_outcomes invalid")
                parsed_metrics[key] = value
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0:
                    raise BeaconPredictionError(f"{key} invalid")
                parsed_metrics[key] = float(value)
        obj.metric_sums = parsed_metrics
        return obj
