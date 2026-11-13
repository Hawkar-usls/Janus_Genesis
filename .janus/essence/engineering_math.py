"""ESSENCE engineering calculator: exact Decimal/SI dimensional arithmetic.

No eval/exec/network, no dynamic units, no mutable global state.
Trig is approximate (Python math); arithmetic and square root use Decimal.
All quantities are stored in SI base units. This is not a certified instrument.
"""
from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

ZERO = (0, 0, 0, 0, 0, 0, 0)  # kg, m, s, A, K, mol, cd
BASE_NAMES = ("kg", "m", "s", "A", "K", "mol", "cd")
MAX_NODES = 80
MAX_EXPRESSION = 200
MAX_EXPONENT = 12


def _unit(scale: str, dims: tuple[int, ...]) -> tuple[Decimal, tuple[int, ...]]:
    return Decimal(scale), dims


UNITS = {
    "kg": _unit("1", (1, 0, 0, 0, 0, 0, 0)),
    "g": _unit("0.001", (1, 0, 0, 0, 0, 0, 0)),
    "m": _unit("1", (0, 1, 0, 0, 0, 0, 0)),
    "mm": _unit("0.001", (0, 1, 0, 0, 0, 0, 0)),
    "cm": _unit("0.01", (0, 1, 0, 0, 0, 0, 0)),
    "km": _unit("1000", (0, 1, 0, 0, 0, 0, 0)),
    "s": _unit("1", (0, 0, 1, 0, 0, 0, 0)),
    "min": _unit("60", (0, 0, 1, 0, 0, 0, 0)),
    "h": _unit("3600", (0, 0, 1, 0, 0, 0, 0)),
    "A": _unit("1", (0, 0, 0, 1, 0, 0, 0)),
    "K": _unit("1", (0, 0, 0, 0, 1, 0, 0)),
    "mol": _unit("1", (0, 0, 0, 0, 0, 1, 0)),
    "cd": _unit("1", (0, 0, 0, 0, 0, 0, 1)),
    "Hz": _unit("1", (0, 0, -1, 0, 0, 0, 0)),
    "N": _unit("1", (1, 1, -2, 0, 0, 0, 0)),
    "kN": _unit("1000", (1, 1, -2, 0, 0, 0, 0)),
    "Pa": _unit("1", (1, -1, -2, 0, 0, 0, 0)),
    "kPa": _unit("1000", (1, -1, -2, 0, 0, 0, 0)),
    "MPa": _unit("1000000", (1, -1, -2, 0, 0, 0, 0)),
    "J": _unit("1", (1, 2, -2, 0, 0, 0, 0)),
    "kJ": _unit("1000", (1, 2, -2, 0, 0, 0, 0)),
    "W": _unit("1", (1, 2, -3, 0, 0, 0, 0)),
    "kW": _unit("1000", (1, 2, -3, 0, 0, 0, 0)),
    "V": _unit("1", (1, 2, -3, -1, 0, 0, 0)),
    "Ohm": _unit("1", (1, 2, -3, -2, 0, 0, 0)),
}


@dataclass(frozen=True)
class Quantity:
    si: Decimal
    dimensions: tuple[int, ...] = ZERO

    def checked(self) -> "Quantity":
        if not self.si.is_finite() or (self.si and abs(self.si.adjusted()) > 90):
            raise ValueError("NONFINITE_OR_UNBOUNDED_RESULT")
        if max(map(abs, self.dimensions)) > 24:
            raise ValueError("DIMENSION_LIMIT")
        return self


def _dimensions(x: tuple[int, ...]) -> str:
    parts = [f"{name}^{power}" if power != 1 else name
             for name, power in zip(BASE_NAMES, x) if power]
    return "*".join(parts) if parts else "1"


def _format(value: Decimal) -> str:
    return format(value.normalize(), "f")


def calculate(expression: str, output_unit: str | None = None) -> dict:
    if not isinstance(expression, str) or not 1 <= len(expression) <= MAX_EXPRESSION:
        raise ValueError("EXPRESSION_LIMIT")
    if not re.fullmatch(r"[\w\s.+*/()^,\-]+", expression, re.ASCII):
        raise ValueError("INVALID_EXPRESSION_CHARACTERS")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("INVALID_EXPRESSION") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ValueError("EXPRESSION_AST_LIMIT")
    approximate = False

    def visitor(node) -> Quantity:
        nonlocal approximate
        if isinstance(node, ast.Expression):
            return visitor(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Quantity(Decimal(str(node.value))).checked()
        if isinstance(node, ast.Name) and node.id in UNITS:
            scale, dim = UNITS[node.id]
            return Quantity(scale, dim)
        if isinstance(node, ast.Name) and node.id in ("pi", "e"):
            return Quantity(Decimal("3.14159265358979323846264338327950288419716939937510")
                            if node.id == "pi" else
                            Decimal("2.71828182845904523536028747135266249775724709369995"))
        if isinstance(node, ast.Name) and node.id == "deg":
            pi = Decimal("3.14159265358979323846264338327950288419716939937510")
            return Quantity(pi / Decimal(180))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            q = visitor(node.operand)
            return Quantity(-q.si if isinstance(node.op, ast.USub) else q.si, q.dimensions)
        if isinstance(node, ast.BinOp):
            a, b = visitor(node.left), visitor(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                if a.dimensions != b.dimensions:
                    raise ValueError("DIMENSION_MISMATCH")
                return Quantity(a.si + b.si if isinstance(node.op, ast.Add)
                                else a.si - b.si, a.dimensions).checked()
            if isinstance(node.op, ast.Mult):
                return Quantity(a.si * b.si, tuple(x + y for x, y in zip(a.dimensions, b.dimensions))).checked()
            if isinstance(node.op, ast.Div):
                if b.si == 0:
                    raise ValueError("DIVISION_BY_ZERO")
                return Quantity(a.si / b.si, tuple(x - y for x, y in zip(a.dimensions, b.dimensions))).checked()
            if isinstance(node.op, ast.Pow):
                if b.dimensions != ZERO or b.si != b.si.to_integral_value() or abs(b.si) > MAX_EXPONENT:
                    raise ValueError("POWER_LIMIT")
                n = int(b.si)
                if n < 0 and a.si == 0:
                    raise ValueError("DIVISION_BY_ZERO")
                return Quantity(a.si ** n, tuple(x * n for x in a.dimensions)).checked()
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and len(node.args) == 1 and not node.keywords):
            name = node.func.id
            a = visitor(node.args[0])
            if name == "sqrt":
                if a.si < 0 or any(x % 2 for x in a.dimensions):
                    raise ValueError("SQRT_DIMENSION_OR_DOMAIN")
                return Quantity(a.si.sqrt(), tuple(x // 2 for x in a.dimensions)).checked()
            if name in ("sin", "cos", "tan", "ln", "log10"):
                if a.dimensions != ZERO:
                    raise ValueError("DIMENSION_MISMATCH")
                if name in ("ln", "log10") and a.si <= 0:
                    raise ValueError("LOG_DOMAIN")
                if abs(a.si) > 1000000:
                    raise ValueError("FUNCTION_ARGUMENT_LIMIT")
                approx = getattr(math, "log" if name == "ln" else name)(float(a.si))
                approximate = True
                return Quantity(Decimal(str(approx))).checked()
        raise ValueError("UNSUPPORTED_EXPRESSION")

    with localcontext() as ctx:
        ctx.prec = 50
        ctx.traps[InvalidOperation] = True
        try:
            answer = visitor(tree).checked()
            factor = Decimal(1)
            if output_unit is not None:
                if output_unit not in UNITS:
                    raise ValueError("UNKNOWN_OUTPUT_UNIT")
                factor, dim = UNITS[output_unit]
                if dim != answer.dimensions:
                    raise ValueError("OUTPUT_DIMENSION_MISMATCH")
            rendered = answer.si / factor
        except (OverflowError, InvalidOperation, ZeroDivisionError) as exc:
            raise ValueError("ARITHMETIC_FAILURE") from exc
        return {
            "schema": "janus.essence.calculator/0.1",
            "value": _format(rendered),
            "si_value": _format(answer.si),
            "unit": output_unit or _dimensions(answer.dimensions),
            "dimensions": list(answer.dimensions),
            "precision": "approx_binary64_functions" if approximate else "decimal_50",
            "exact_constants_and_arithmetic": not approximate,
            "side_effects": False,
        }
