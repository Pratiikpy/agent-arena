"""The NL-strategy sandbox must compile good strategies and reject every unsafe one."""

from __future__ import annotations

import pytest

from bitarena.strategy.sandbox import StrategyError, compile_strategy

GOOD = """
def decide(obs):
    fast = sma(obs["prices"], 5)
    slow = sma(obs["prices"], 20)
    vol = std(obs["prices"], 20)
    if fast > slow * 1.002:
        return clip(1.0, -1.0, 1.0)
    if fast < slow * 0.998:
        return -1.0
    return 0.0
"""


def test_good_strategy_compiles_and_returns_a_float():
    fn = compile_strategy(GOOD)
    out = fn({"price": 100.0, "prices": [100.0 + i for i in range(40)], "position": 0.0, "equity": 10_000.0})
    assert isinstance(out, float) and -1.0 <= out <= 1.0


@pytest.mark.parametrize(
    "bad",
    [
        "import os\ndef decide(obs):\n    return 0.0",  # import at module level
        "def decide(obs):\n    return __import__('os')",  # banned dunder name
        "def decide(obs):\n    return ().__class__",  # attribute-access escape
        "def decide(obs):\n    eval('1')\n    return 0.0",  # eval
        "def decide(obs):\n    open('x')\n    return 0.0",  # file access
        "def decide(obs):\n    for i in range(1000000000):\n        pass\n    return 0.0",  # loop
        "def decide(obs):\n    while True:\n        pass\n    return 0.0",  # infinite loop
        "def decide(obs):\n    return [x for x in obs['prices']]",  # comprehension
        "f = lambda o: 0\ndef decide(obs):\n    return 0.0",  # extra statement + lambda
        "def predict(obs):\n    return 0.0",  # wrong function name
        "def decide(obs, secret):\n    return 0.0",  # wrong arity
        "def decide(obs):\n    return getattr(obs, 'x')",  # banned call
    ],
)
def test_unsafe_or_invalid_strategies_are_rejected(bad):
    with pytest.raises(StrategyError):
        compile_strategy(bad)


def test_runtime_error_is_caught_on_smoke_run():
    # references an obs key that is not provided -> KeyError at smoke time -> rejected, not admitted
    with pytest.raises(StrategyError):
        compile_strategy("def decide(obs):\n    return obs['does_not_exist'] + 1.0")
