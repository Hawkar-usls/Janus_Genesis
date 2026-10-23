# -*- coding: utf-8 -*-
"""JANUS POWER v1 — bounded, capability-truthful compute fabric.

The user-facing magic vocabulary is retained, but capability discovery is not
fictionalized. A tier is available only when a real executor is registered.
Built-ins are deliberately narrow:

- LOCAL_CPU: bounded matrix add/multiply/solve/inverse
- QUANTUM_SIM: classical state-vector simulation for H/X/Y/Z/I/CNOT

GPU, cloud, distributed and Minecraft executors are optional registrations.
External-effect executors require per-request admission; a token/config file by
itself never makes a cloud tier available.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import itertools
import json
import math
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping, Optional


class ComputeTier(Enum):
    MINECRAFT = 0
    LOCAL_CPU = 1
    LOCAL_GPU = 2
    CLOUD = 3
    DISTRIBUTED = 4
    QUANTUM_SIM = 5
    HYBRID = 10  # selection policy, never a physical executor


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class PowerError(RuntimeError):
    pass


class BlueprintError(PowerError):
    pass


class CapabilityUnavailable(PowerError):
    pass


class EffectAdmissionRequired(PowerError):
    pass


class ComputeCancelled(PowerError):
    pass


class ComputeDeadlineExceeded(PowerError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


@dataclass
class ComputeRequest:
    task_id: str
    blueprint: dict[str, Any]
    priority: str
    blueprint_sha256: str
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: TaskStatus = TaskStatus.QUEUED
    result: Any = None
    error: Optional[str] = None
    used_tier: Optional[ComputeTier] = None
    executor_name: Optional[str] = None
    performance_metrics: dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False
    done_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    execution_task: Optional[asyncio.Task[Any]] = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "type": self.blueprint.get("type", "unknown"),
            "status": self.status.value,
            "tier": self.used_tier.name if self.used_tier else None,
            "executor": self.executor_name,
            "created": self.created,
            "blueprint_sha256": self.blueprint_sha256,
            "metrics": dict(self.performance_metrics),
            "error": self.error,
        }


ExecutorHandler = Callable[[ComputeRequest], Any | Awaitable[Any]]


@dataclass(frozen=True)
class ExecutorRegistration:
    name: str
    tier: ComputeTier
    capabilities: frozenset[str]
    handler: ExecutorHandler
    external_effect: bool
    cancellation_note: str


class JanusPowerCore:
    """Priority compute dispatcher with explicit executor/effect boundaries."""

    PRIORITY = {"high": 0, "normal": 10, "low": 20}
    TIER_ALIASES = {
        "MINECRAFT": ComputeTier.MINECRAFT,
        "CPU": ComputeTier.LOCAL_CPU,
        "LOCAL_CPU": ComputeTier.LOCAL_CPU,
        "GPU": ComputeTier.LOCAL_GPU,
        "LOCAL_GPU": ComputeTier.LOCAL_GPU,
        "CLOUD": ComputeTier.CLOUD,
        "DISTRIBUTED": ComputeTier.DISTRIBUTED,
        "QUANTUM": ComputeTier.QUANTUM_SIM,
        "QUANTUM_SIM": ComputeTier.QUANTUM_SIM,
        "HYBRID": ComputeTier.HYBRID,
    }

    def __init__(
        self,
        kernel: Any = None,
        *,
        max_task_seconds: float = 30.0,
        max_matrix_dimension: int = 256,
        max_qubits: int = 16,
        max_workers: int = 4,
    ) -> None:
        if max_task_seconds <= 0:
            raise ValueError("max_task_seconds must be > 0")
        if max_matrix_dimension < 1:
            raise ValueError("max_matrix_dimension must be >= 1")
        if not 1 <= max_qubits <= 24:
            raise ValueError("max_qubits must be in 1..24")
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")

        self.kernel = kernel
        self.max_task_seconds = float(max_task_seconds)
        self.max_matrix_dimension = max_matrix_dimension
        self.max_qubits = max_qubits
        self.max_workers = max_workers
        self.tasks: dict[str, ComputeRequest] = {}
        self._queue: asyncio.PriorityQueue[tuple[int, int, str]] = asyncio.PriorityQueue()
        self._sequence = itertools.count()
        self._workers: list[asyncio.Task[None]] = []
        self._executors: dict[str, ExecutorRegistration] = {}
        self._started = False
        self._closing = False
        self.completed_order: list[str] = []  # deterministic test/telemetry surface

        self.register_executor(
            name="builtin-local-cpu",
            tier=ComputeTier.LOCAL_CPU,
            capabilities={"matrix_operations"},
            handler=self._execute_matrix_operations,
            external_effect=False,
            cancellation_note="COOPERATIVE_ASYNC",
        )
        self.register_executor(
            name="builtin-quantum-sim",
            tier=ComputeTier.QUANTUM_SIM,
            capabilities={"quantum_simulation"},
            handler=self._execute_quantum_simulation,
            external_effect=False,
            cancellation_note="COOPERATIVE_ASYNC",
        )

    @property
    def available_tiers(self) -> list[ComputeTier]:
        tiers = {registration.tier for registration in self._executors.values()}
        if tiers:
            tiers.add(ComputeTier.HYBRID)
        return sorted(tiers, key=lambda tier: tier.value)

    def register_executor(
        self,
        *,
        name: str,
        tier: ComputeTier,
        capabilities: set[str] | frozenset[str],
        handler: ExecutorHandler,
        external_effect: bool,
        cancellation_note: str = "EXECUTOR_DEFINED",
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("executor name required")
        if name in self._executors:
            raise ValueError(f"executor already registered: {name}")
        if tier is ComputeTier.HYBRID:
            raise ValueError("HYBRID is a selection policy, not an executor tier")
        normalized_capabilities = frozenset(str(x) for x in capabilities if str(x))
        if not normalized_capabilities:
            raise ValueError("executor requires at least one capability")
        if not callable(handler):
            raise TypeError("executor handler must be callable")
        if external_effect and not inspect.iscoroutinefunction(handler):
            raise TypeError(
                "effectful external executors must be async so cancellation is observable"
            )
        self._executors[name] = ExecutorRegistration(
            name=name,
            tier=tier,
            capabilities=normalized_capabilities,
            handler=handler,
            external_effect=bool(external_effect),
            cancellation_note=str(cancellation_note),
        )

    async def start(self, worker_count: Optional[int] = None) -> None:
        if self._started:
            return
        if self._closing:
            raise RuntimeError("power core is closing")
        count = self.max_workers if worker_count is None else worker_count
        if not 1 <= count <= self.max_workers:
            raise ValueError("worker_count outside configured bounds")
        self._workers = [
            asyncio.create_task(self._worker_loop(i), name=f"janus-power-worker-{i}")
            for i in range(count)
        ]
        self._started = True

    async def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        for request in self.tasks.values():
            if request.status is TaskStatus.QUEUED:
                request.status = TaskStatus.CANCELLED
                request.error = "POWER_CORE_SHUTDOWN"
                request.done_event.set()
            elif request.status is TaskStatus.RUNNING:
                request.cancel_requested = True
                if request.execution_task is not None:
                    request.execution_task.cancel()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def compute(self, blueprint: Mapping[str, Any], priority: str = "normal") -> str:
        if self._closing:
            raise RuntimeError("power core is closing")
        if priority not in self.PRIORITY:
            raise BlueprintError("priority must be high, normal, or low")
        normalized = self._validate_blueprint(blueprint)
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        request = ComputeRequest(
            task_id=task_id,
            blueprint=normalized,
            priority=priority,
            blueprint_sha256=canonical_sha256(normalized),
        )
        self.tasks[task_id] = request
        await self._queue.put((self.PRIORITY[priority], next(self._sequence), task_id))
        await self._remember_event(
            {
                "event": "COMPUTE_QUEUED",
                "task_id": task_id,
                "type": normalized["type"],
                "blueprint_sha256": request.blueprint_sha256,
            }
        )
        return task_id

    def _validate_blueprint(self, blueprint: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(blueprint, Mapping):
            raise BlueprintError("blueprint must be an object")
        try:
            normalized = json.loads(_canonical_bytes(dict(blueprint)).decode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise BlueprintError(f"blueprint is not canonical JSON: {exc}") from exc
        task_type = normalized.get("type")
        if not isinstance(task_type, str) or not task_type:
            raise BlueprintError("blueprint.type required")
        constraints = normalized.get("constraints", {})
        if not isinstance(constraints, dict):
            raise BlueprintError("constraints must be an object")
        if "max_time" in constraints:
            value = constraints["max_time"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise BlueprintError("constraints.max_time must be > 0")
        effects = normalized.get("effects", {})
        if not isinstance(effects, dict):
            raise BlueprintError("effects must be an object")
        if "allow_external_compute" in effects and not isinstance(
            effects["allow_external_compute"], bool
        ):
            raise BlueprintError("effects.allow_external_compute must be boolean")
        preferred = normalized.get("preferred_tier")
        if preferred is not None:
            if not isinstance(preferred, str) or preferred.upper() not in self.TIER_ALIASES:
                raise BlueprintError("preferred_tier is unknown")
        return normalized

    async def get_result(
        self, task_id: str, *, wait: bool = False, timeout: float = 30.0
    ) -> dict[str, Any]:
        request = self.tasks.get(task_id)
        if request is None:
            return {"error": "Task not found"}
        if wait and not request.done_event.is_set():
            try:
                await asyncio.wait_for(request.done_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                return {"error": "Timeout waiting for result", "task": request.to_dict()}
        payload = {"task": request.to_dict()}
        if request.status is TaskStatus.COMPLETED:
            payload["result"] = request.result
        return payload

    async def cancel(self, task_id: str) -> bool:
        request = self.tasks.get(task_id)
        if request is None or request.done_event.is_set():
            return False
        request.cancel_requested = True
        if request.status is TaskStatus.QUEUED:
            request.status = TaskStatus.CANCELLED
            request.error = "CANCELLED_BEFORE_EXECUTION"
            request.done_event.set()
            return True
        if request.status is TaskStatus.RUNNING and request.execution_task is not None:
            request.execution_task.cancel()
            return True
        return True

    async def _worker_loop(self, worker_id: int) -> None:
        while True:
            _, _, task_id = await self._queue.get()
            try:
                request = self.tasks.get(task_id)
                if request is None or request.status is TaskStatus.CANCELLED:
                    continue
                await self._process_request(request, worker_id)
            finally:
                self._queue.task_done()

    async def _process_request(self, request: ComputeRequest, worker_id: int) -> None:
        request.status = TaskStatus.RUNNING
        request.performance_metrics["worker_id"] = worker_id
        started = time.monotonic()
        try:
            registration = self._select_executor(request)
            request.used_tier = registration.tier
            request.executor_name = registration.name
            timeout = self._applied_timeout(request)
            request.performance_metrics["applied_timeout_seconds"] = timeout
            request.performance_metrics["external_effect_executor"] = registration.external_effect
            request.performance_metrics["cancellation_note"] = registration.cancellation_note
            request.execution_task = asyncio.create_task(
                self._invoke_executor(registration, request),
                name=f"janus-power-exec-{request.task_id}",
            )
            try:
                request.result = await asyncio.wait_for(request.execution_task, timeout=timeout)
            finally:
                request.execution_task = None
            request.status = TaskStatus.COMPLETED
            request.performance_metrics["result_sha256"] = canonical_sha256(request.result)
        except asyncio.TimeoutError:
            request.status = TaskStatus.TIMEOUT
            request.error = "TASK_TIMEOUT"
        except (asyncio.CancelledError, ComputeCancelled):
            if request.cancel_requested or self._closing:
                request.status = TaskStatus.CANCELLED
                request.error = "TASK_CANCELLED"
            else:
                request.status = TaskStatus.FAILED
                request.error = "EXECUTION_CANCELLED_UNEXPECTEDLY"
        except Exception as exc:
            request.status = TaskStatus.FAILED
            request.error = f"{type(exc).__name__}: {exc}"
        finally:
            request.performance_metrics["execution_time_seconds"] = max(
                0.0, time.monotonic() - started
            )
            self.completed_order.append(request.task_id)
            request.done_event.set()
            await self._remember_event(
                {
                    "event": "COMPUTE_TERMINAL",
                    "task_id": request.task_id,
                    "status": request.status.value,
                    "tier": request.used_tier.name if request.used_tier else None,
                    "executor": request.executor_name,
                    "blueprint_sha256": request.blueprint_sha256,
                    "result_sha256": request.performance_metrics.get("result_sha256"),
                    "error": request.error,
                }
            )

    def _applied_timeout(self, request: ComputeRequest) -> float:
        requested = request.blueprint.get("constraints", {}).get(
            "max_time", self.max_task_seconds
        )
        return min(float(requested), self.max_task_seconds)

    def _select_executor(self, request: ComputeRequest) -> ExecutorRegistration:
        task_type = request.blueprint["type"]
        effects = request.blueprint.get("effects", {})
        allow_external = effects.get("allow_external_compute", False)
        preferred_name = request.blueprint.get("preferred_tier")
        preferred = (
            self.TIER_ALIASES[preferred_name.upper()] if preferred_name else ComputeTier.HYBRID
        )

        candidates = [
            registration
            for registration in self._executors.values()
            if task_type in registration.capabilities
        ]
        if preferred is not ComputeTier.HYBRID:
            candidates = [c for c in candidates if c.tier is preferred]
        if not candidates:
            raise CapabilityUnavailable(f"NO_EXECUTOR_FOR_{task_type}")

        order = {
            ComputeTier.LOCAL_GPU: 0,
            ComputeTier.LOCAL_CPU: 1,
            ComputeTier.QUANTUM_SIM: 2,
            ComputeTier.CLOUD: 3,
            ComputeTier.DISTRIBUTED: 4,
            ComputeTier.MINECRAFT: 5,
        }
        candidates.sort(key=lambda item: (order[item.tier], item.name))
        for candidate in candidates:
            if candidate.external_effect and not allow_external:
                continue
            return candidate
        raise EffectAdmissionRequired("EXTERNAL_COMPUTE_REQUIRES_REQUEST_ADMISSION")

    async def _invoke_executor(
        self, registration: ExecutorRegistration, request: ComputeRequest
    ) -> Any:
        if registration.external_effect and not request.blueprint.get("effects", {}).get(
            "allow_external_compute", False
        ):
            raise EffectAdmissionRequired("EXTERNAL_COMPUTE_REQUIRES_REQUEST_ADMISSION")
        handler = registration.handler
        if inspect.iscoroutinefunction(handler):
            return await handler(request)
        # Cancellation of the await does not hard-kill a Python worker thread.
        # Effectful handlers are therefore forbidden from using this sync path.
        return await asyncio.to_thread(handler, request)

    async def _cooperate(self, request: ComputeRequest, deadline: float) -> None:
        if request.cancel_requested:
            raise ComputeCancelled("TASK_CANCEL_REQUESTED")
        if time.monotonic() > deadline:
            raise ComputeDeadlineExceeded("COOPERATIVE_DEADLINE_EXCEEDED")
        await asyncio.sleep(0)

    @staticmethod
    def _number(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BlueprintError("matrix values must be finite numbers")
        value = float(value)
        if not math.isfinite(value):
            raise BlueprintError("matrix values must be finite numbers")
        return value

    def _matrix(self, value: Any, name: str) -> list[list[float]]:
        if not isinstance(value, list) or not value or not all(isinstance(r, list) for r in value):
            raise BlueprintError(f"{name} must be a non-empty matrix")
        width = len(value[0])
        if width < 1 or any(len(row) != width for row in value):
            raise BlueprintError(f"{name} must be rectangular")
        if len(value) > self.max_matrix_dimension or width > self.max_matrix_dimension:
            raise BlueprintError(f"{name} exceeds matrix dimension bound")
        return [[self._number(cell) for cell in row] for row in value]

    async def _execute_matrix_operations(self, request: ComputeRequest) -> Any:
        data = request.blueprint.get("data")
        if not isinstance(data, dict):
            raise BlueprintError("matrix_operations.data must be an object")
        operation = request.blueprint.get("operation", "multiply")
        A = self._matrix(data.get("A"), "A")
        deadline = time.monotonic() + self._applied_timeout(request)

        if operation == "multiply":
            B = self._matrix(data.get("B"), "B")
            if len(A[0]) != len(B):
                raise BlueprintError("matrix multiply shape mismatch")
            result = [[0.0 for _ in range(len(B[0]))] for _ in range(len(A))]
            ops = 0
            for i in range(len(A)):
                for k in range(len(B)):
                    aik = A[i][k]
                    for j in range(len(B[0])):
                        result[i][j] += aik * B[k][j]
                        ops += 1
                        if ops % 4096 == 0:
                            await self._cooperate(request, deadline)
            return result

        if operation == "add":
            B = self._matrix(data.get("B"), "B")
            if len(A) != len(B) or len(A[0]) != len(B[0]):
                raise BlueprintError("matrix add shape mismatch")
            return [
                [A[i][j] + B[i][j] for j in range(len(A[0]))]
                for i in range(len(A))
            ]

        if operation in {"solve", "inverse"}:
            if len(A) != len(A[0]):
                raise BlueprintError(f"{operation} requires square A")
            n = len(A)
            if operation == "inverse":
                rhs = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
                vector_rhs = False
            else:
                raw_b = data.get("B")
                vector_rhs = isinstance(raw_b, list) and bool(raw_b) and not isinstance(raw_b[0], list)
                if vector_rhs:
                    if len(raw_b) != n:
                        raise BlueprintError("solve vector B length mismatch")
                    rhs = [[self._number(x)] for x in raw_b]
                else:
                    rhs = self._matrix(raw_b, "B")
                    if len(rhs) != n:
                        raise BlueprintError("solve matrix B row mismatch")
            solved = await self._gauss_jordan(A, rhs, request, deadline)
            if operation == "inverse":
                return solved
            if vector_rhs:
                return [row[0] for row in solved]
            return solved

        if operation == "eigen":
            raise CapabilityUnavailable("EIGEN_REQUIRES_REGISTERED_NUMERICAL_EXECUTOR")
        raise BlueprintError(f"unknown matrix operation: {operation}")

    async def _gauss_jordan(
        self,
        A: list[list[float]],
        B: list[list[float]],
        request: ComputeRequest,
        deadline: float,
    ) -> list[list[float]]:
        n = len(A)
        width_b = len(B[0])
        aug = [A[i][:] + B[i][:] for i in range(n)]
        for col in range(n):
            pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
            if abs(aug[pivot][col]) < 1e-12:
                raise BlueprintError("matrix is singular")
            aug[col], aug[pivot] = aug[pivot], aug[col]
            scale = aug[col][col]
            aug[col] = [value / scale for value in aug[col]]
            for row in range(n):
                if row == col:
                    continue
                factor = aug[row][col]
                if factor:
                    aug[row] = [
                        aug[row][j] - factor * aug[col][j]
                        for j in range(n + width_b)
                    ]
            await self._cooperate(request, deadline)
        return [row[n:] for row in aug]

    async def _execute_quantum_simulation(self, request: ComputeRequest) -> Any:
        n_qubits = request.blueprint.get("qubits", 2)
        if isinstance(n_qubits, bool) or not isinstance(n_qubits, int):
            raise BlueprintError("qubits must be an integer")
        if not 1 <= n_qubits <= self.max_qubits:
            raise BlueprintError("qubits outside configured bound")
        circuit = request.blueprint.get("circuit", [])
        if not isinstance(circuit, list):
            raise BlueprintError("circuit must be a list")
        dimension = 1 << n_qubits
        state = [0j] * dimension
        state[0] = 1 + 0j
        sqrt2 = math.sqrt(2.0)
        one_qubit = {
            "H": ((1 / sqrt2, 1 / sqrt2), (1 / sqrt2, -1 / sqrt2)),
            "X": ((0, 1), (1, 0)),
            "Y": ((0, -1j), (1j, 0)),
            "Z": ((1, 0), (0, -1)),
            "I": ((1, 0), (0, 1)),
        }
        deadline = time.monotonic() + self._applied_timeout(request)

        for gate_index, spec in enumerate(circuit):
            if not isinstance(spec, dict):
                raise BlueprintError("each gate must be an object")
            gate = spec.get("gate")
            target = spec.get("target", 0)
            if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < n_qubits:
                raise BlueprintError("gate target out of range")
            if gate == "CNOT":
                control = spec.get("control")
                if isinstance(control, bool) or not isinstance(control, int):
                    raise BlueprintError("CNOT control required")
                if not 0 <= control < n_qubits or control == target:
                    raise BlueprintError("CNOT control invalid")
                control_mask = 1 << control
                target_mask = 1 << target
                for basis in range(dimension):
                    if (basis & control_mask) and not (basis & target_mask):
                        partner = basis | target_mask
                        state[basis], state[partner] = state[partner], state[basis]
            elif gate in one_qubit:
                matrix = one_qubit[gate]
                mask = 1 << target
                for basis in range(dimension):
                    if basis & mask:
                        continue
                    partner = basis | mask
                    a0, a1 = state[basis], state[partner]
                    state[basis] = matrix[0][0] * a0 + matrix[0][1] * a1
                    state[partner] = matrix[1][0] * a0 + matrix[1][1] * a1
            else:
                raise BlueprintError(f"unsupported quantum gate: {gate}")
            if gate_index % 4 == 0:
                await self._cooperate(request, deadline)

        probabilities = [float(abs(amplitude) ** 2) for amplitude in state]
        total = sum(probabilities)
        if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise PowerError("quantum simulator normalization drift")

        seed = request.blueprint.get("seed")
        measurement = None
        if seed is not None:
            if isinstance(seed, bool) or not isinstance(seed, int):
                raise BlueprintError("seed must be an integer")
            r = random.Random(seed).random()
            cumulative = 0.0
            chosen = dimension - 1
            for index, probability in enumerate(probabilities):
                cumulative += probability
                if r <= cumulative:
                    chosen = index
                    break
            measurement = format(chosen, f"0{n_qubits}b")

        return {
            "qubits": n_qubits,
            "bit_order": "target_0_is_least_significant_bit",
            "state_vector": [
                {"real": float(value.real), "imag": float(value.imag)} for value in state
            ],
            "probabilities": probabilities,
            "measurement": measurement,
            "measurement_seed": seed,
            "simulator": "classical_state_vector",
            "quantum_hardware": False,
            "quantum_speedup_claimed": False,
        }

    async def summon_power(self, incantation: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(incantation, Mapping) or not isinstance(incantation.get("spell"), str):
            raise BlueprintError("incantation.spell required")
        blueprint = self._incantation_to_blueprint(dict(incantation))
        task_id = await self.compute(blueprint, priority="high")
        timeout = min(
            float(incantation.get("sacrifice", {}).get("time_limit", self.max_task_seconds)),
            self.max_task_seconds,
        )
        response = await self.get_result(task_id, wait=True, timeout=timeout + 0.5)
        task = response.get("task", {})
        return {
            "success": task.get("status") == TaskStatus.COMPLETED.value,
            "spell": incantation["spell"],
            "task": task,
            "result": response.get("result"),
            "claim_ceiling": "SPELL_NAME_IS_INTERFACE_METAPHOR_NOT_CAPABILITY_PROOF",
        }

    def _incantation_to_blueprint(self, incantation: dict[str, Any]) -> dict[str, Any]:
        spell = incantation["spell"]
        params = incantation.get("parameters", {})
        if not isinstance(params, dict):
            raise BlueprintError("incantation.parameters must be an object")
        sacrifice = incantation.get("sacrifice", {})
        if not isinstance(sacrifice, dict):
            raise BlueprintError("incantation.sacrifice must be an object")
        constraints = {"max_time": sacrifice.get("time_limit", self.max_task_seconds)}

        if spell == "solve_equation":
            return {
                "type": "matrix_operations",
                "operation": "solve",
                "data": {"A": params.get("A"), "B": params.get("B")},
                "constraints": constraints,
            }
        if spell == "summon_demon":
            return {
                "type": "quantum_simulation",
                "qubits": int(params.get("qubits", 2)),
                "circuit": [
                    {"gate": "H", "target": 0},
                    {"gate": "CNOT", "control": 0, "target": 1},
                ],
                "seed": params.get("seed", 0),
                "constraints": constraints,
            }
        if spell == "create_universe":
            return {
                "type": "physics_simulation",
                "parameters": params,
                "constraints": constraints,
                "preferred_tier": incantation.get("preferred_tier", "HYBRID"),
                "effects": incantation.get("effects", {}),
            }
        if spell == "predict_future":
            return {
                "type": "predict_future",
                "parameters": params,
                "constraints": constraints,
                "preferred_tier": incantation.get("preferred_tier", "HYBRID"),
                "effects": incantation.get("effects", {}),
            }
        raise BlueprintError(f"unknown spell: {spell}")

    async def handle_game_command(self, command: str, args: list[str]) -> str:
        if command == "/power":
            return json.dumps(
                {
                    "tasks_total": len(self.tasks),
                    "tasks_pending": sum(
                        task.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}
                        for task in self.tasks.values()
                    ),
                    "available_tiers": [tier.name for tier in self.available_tiers],
                    "queue_size": self._queue.qsize(),
                },
                ensure_ascii=False,
            )
        if command == "/result":
            if not args:
                return "Usage: /result <task_id>"
            return json.dumps(await self.get_result(args[0]), ensure_ascii=False)[:2000]
        return "Unknown command"

    async def _remember_event(self, event: dict[str, Any]) -> None:
        memory = getattr(self.kernel, "memory", None) if self.kernel is not None else None
        remember = getattr(memory, "remember", None)
        if not callable(remember):
            return
        try:
            value = remember(source="JANUS-POWER", content=event)
            if inspect.isawaitable(value):
                await value
        except Exception as exc:
            # Compute truth must not be changed by telemetry failure.
            event_type = event.get("event", "UNKNOWN")
            # Store only the class name; do not echo arbitrary memory backend secrets.
            if event_type == "COMPUTE_TERMINAL":
                task = self.tasks.get(str(event.get("task_id")))
                if task is not None:
                    task.performance_metrics["memory_log_error"] = type(exc).__name__


async def run(kernel: Any) -> JanusPowerCore:
    """Plugin entry: register a bounded compute core and return immediately."""
    core = JanusPowerCore(kernel)
    await core.start()
    kernel.power = core
    return core
