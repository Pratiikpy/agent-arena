"""Validate and safely compile a model-generated ``decide(obs) -> float`` strategy.

Executing model-generated code is the risky part, so the defense is layered and conservative:

1. A strict AST allowlist. The function must be exactly ``def decide(obs): ...``. Only arithmetic,
   comparisons, conditionals, subscripts, local assignments, and calls to a fixed set of helper
   names are permitted. Imports, attribute access (so no ``().__class__`` escape), loops,
   comprehensions, lambdas, and every dunder name are rejected outright.
2. A restricted namespace. The code runs with ``__builtins__`` cut down to a handful of safe
   numeric builtins plus the whitelisted helpers, nothing else.
3. A smoke run on synthetic input to catch runtime errors before the strategy is ever admitted.

This is an allowlist sandbox, not a hardened OS jail; it bounds model output you generate and
review, which is the threat in scope. The strategy only ever sees a dict of numbers.
"""

from __future__ import annotations

import ast


class StrategyError(ValueError):
    """A generated strategy failed validation, compilation, or its smoke run."""


# --- whitelisted helpers the generated code may call (pure, over a list of recent closes) ---
def _last(xs: list[float]) -> float:
    return float(xs[-1]) if xs else 0.0


def _mean(xs: list[float]) -> float:
    return float(sum(xs) / len(xs)) if xs else 0.0


def _sma(prices: list[float], n: float) -> float:
    n = int(n)
    return _mean(prices[-n:]) if n > 0 else 0.0


def _ema(prices: list[float], n: float) -> float:
    n = int(n)
    if not prices or n <= 0:
        return 0.0
    k = 2.0 / (n + 1.0)
    e = float(prices[0])
    for p in prices[1:]:  # trusted helper: bounded by the (bounded) price window
        e = p * k + e * (1.0 - k)
    return e


def _roc(prices: list[float], n: float) -> float:
    n = int(n)
    if len(prices) <= n or prices[-n - 1] == 0:
        return 0.0
    return float(prices[-1] / prices[-n - 1] - 1.0)


def _std(prices: list[float], n: float) -> float:
    n = int(n)
    w = prices[-n:]
    if len(w) < 2:
        return 0.0
    m = _mean(w)
    return float((sum((x - m) ** 2 for x in w) / (len(w) - 1)) ** 0.5)


def _clip(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


HELPERS = {"sma": _sma, "ema": _ema, "roc": _roc, "std": _std, "last": _last, "mean": _mean, "clip": _clip}
_SAFE_BUILTINS = {"len": len, "min": min, "max": max, "abs": abs, "round": round,
                  "sum": sum, "float": float, "int": int}
_ALLOWED_CALLS = set(HELPERS) | set(_SAFE_BUILTINS)

_ALLOWED_NODES: tuple[type, ...] = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.If, ast.IfExp,
    ast.Assign, ast.Expr, ast.Name, ast.Load, ast.Store, ast.Constant, ast.Call,
    ast.Subscript, ast.List, ast.Tuple,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq,
)
_BANNED_NAMES = {"eval", "exec", "open", "compile", "globals", "locals", "vars",
                 "getattr", "setattr", "delattr", "__import__", "input", "breakpoint"}

_SMOKE_OBS = {"price": 100.0, "prices": [100.0 + 0.1 * i for i in range(60)],
              "position": 0.0, "equity": 10_000.0}


def validate(code: str) -> None:
    """Raise :class:`StrategyError` unless ``code`` is a single safe ``decide(obs)`` function."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise StrategyError(f"syntax error: {exc}") from exc

    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(tree.body) != 1 or not funcs or funcs[0].name != "decide":
        raise StrategyError("must define exactly one function named decide(obs)")
    a = funcs[0].args
    if (len(a.args) != 1 or a.args[0].arg != "obs" or a.vararg or a.kwarg or a.kwonlyargs
            or a.posonlyargs):
        raise StrategyError("decide must take exactly one argument: obs")

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise StrategyError(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLS
        ):
            raise StrategyError(f"disallowed call: {getattr(node.func, 'id', '<expr>')}")
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in _BANNED_NAMES):
            raise StrategyError(f"disallowed name: {node.id}")


def compile_strategy(code: str):
    """Validate, compile in a restricted namespace, smoke-test, and return the ``decide`` callable."""
    validate(code)
    g: dict = {"__builtins__": _SAFE_BUILTINS, **HELPERS}
    loc: dict = {}
    exec(compile(code, "<nl-strategy>", "exec"), g, loc)  # noqa: S102 - allowlisted + restricted ns
    fn = loc.get("decide")
    if not callable(fn):
        raise StrategyError("no decide function was produced")
    try:
        float(fn(dict(_SMOKE_OBS)))
    except Exception as exc:  # any runtime error -> reject before it can ever trade
        raise StrategyError(f"runtime error on smoke test: {exc}") from exc
    return fn
