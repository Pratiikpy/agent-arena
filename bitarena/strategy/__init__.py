"""Natural-language strategy creation: turn an English description into a competing arena agent.

A model emits a single pure ``decide(obs) -> float`` function; ``sandbox`` validates it against a
strict AST allowlist (no imports, no attribute access, no loops, only whitelisted helpers) and
runs it in a restricted namespace; ``backtest`` gates it on a price path before it is admitted.
The result is wrapped as a first-class, firewall-gated competitor.
"""

from .sandbox import HELPERS, StrategyError, compile_strategy, validate

__all__ = ["StrategyError", "validate", "compile_strategy", "HELPERS"]
