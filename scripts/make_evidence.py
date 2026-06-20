"""Generate the reproducible evidence pack (deterministic, offline).

Writes under evidence/:
  - firewall_demos.json   : ALLOW / ALLOW_CAPPED / REJECT verdicts + a tamper-detection proof
  - synthetic_run/        : a deterministic tournament (leaderboard + signed trade logs)
  - regime_scenario/      : trend -> chop -> trend, showing how conflict-gating behaves

Real-Bitget evidence is produced separately by run_arena.py --source bitget.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from bitarena.agents import (
    BuyAndHold,
    ConflictGatedSwarm,
    MomentumBaseline,
    PersonaTeam,
    QLearningAgent,
    RegimeAgent,
)
from bitarena.arena import Arena
from bitarena.config import load_settings
from bitarena.connectors import PaperExchange, ReplayMarketData, synthetic_series
from bitarena.domain import (
    Candle,
    InstrumentType,
    Side,
    TradeIntent,
    default_arena_mandate,
)
from bitarena.firewall import EvalContext, Firewall, verify_certificate

OUT = Path("evidence")


def _verdict_dump(verdict) -> dict:
    return {
        "decision": verdict.decision.value,
        "reason": verdict.reason,
        "effective_notional_usd": verdict.effective_notional_usd,
        "certificate": verdict.certificate.model_dump() if verdict.certificate else None,
        "certificate_valid": verify_certificate(verdict.certificate) if verdict.certificate else None,
    }


def firewall_demos(firewall: Firewall) -> None:
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=60, start_price=60_000, seed=1)})
    md.set_cursor(59)
    quote = md.get_quote("BTCUSDT")

    def evaluate(notional: float, exposure: float = 0.0):
        mandate = default_arena_mandate(10_000, allowed_symbols=("BTCUSDT",))
        intent = TradeIntent(
            agent_id="demo", symbol="BTCUSDT", side=Side.BUY,
            instrument=InstrumentType.SPOT, notional_usd=notional,
        )
        ctx = EvalContext(
            mandate=mandate, equity_usd=10_000, quote=quote,
            current_exposure_usd=exposure, now_ms=quote.ts, max_quote_age_ms=10 ** 15,
        )
        return firewall.evaluate(intent, ctx)

    allow = evaluate(50)
    capped = evaluate(999_999)
    reject = evaluate(5_000, exposure=30_000)  # exposure cap fully used -> no headroom

    tampered = allow.certificate.model_copy(update={"effective_notional_usd": 1_000_000_000.0})
    demos = {
        "allow": _verdict_dump(allow),
        "allow_capped": _verdict_dump(capped),
        "reject": _verdict_dump(reject),
        "tamper_detection": {
            "original_valid": verify_certificate(allow.certificate),
            "after_mutation_valid": verify_certificate(tampered),
            "note": "mutating any signed field invalidates the certificate",
        },
    }
    (OUT / "firewall_demos.json").write_text(json.dumps(demos, indent=2), encoding="utf-8")
    print(f"firewall demos: allow={allow.decision.value} capped={capped.decision.value} "
          f"reject={reject.decision.value} tamper_detected={not demos['tamper_detection']['after_mutation_valid']}")


def _candles_from_closes(closes: np.ndarray, start_ts: int = 0, step_ms: int = 60_000) -> list[Candle]:
    out: list[Candle] = []
    for i, close in enumerate(closes):
        open_ = float(closes[i - 1]) if i > 0 else float(close)
        out.append(
            Candle(
                ts=start_ts + i * step_ms,
                open=open_,
                high=max(open_, float(close)) * 1.001,
                low=min(open_, float(close)) * 0.999,
                close=float(close),
                volume=1_000.0,
            )
        )
    return out


def _regime_closes(seed: int = 7, seg: int = 200) -> np.ndarray:
    rng = np.random.default_rng(seed)
    price = 100.0
    closes: list[float] = []
    for _ in range(seg):  # trend up
        price *= np.exp(rng.normal(0.0015, 0.005))
        closes.append(price)
    level = price
    for _ in range(seg):  # mean-reverting chop (whipsaw)
        price += (level - price) * 0.05 + rng.normal(0.0, 1.5)
        closes.append(max(1.0, price))
    for _ in range(seg):  # trend up
        price *= np.exp(rng.normal(0.0015, 0.005))
        closes.append(price)
    return np.array(closes)


def run_tournament(market: ReplayMarketData, firewall: Firewall, out: Path, label: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    arena = Arena(
        agents=[ConflictGatedSwarm(), RegimeAgent(), PersonaTeam(), QLearningAgent(), MomentumBaseline(), BuyAndHold()],
        exchange=PaperExchange(market),
        market=market,
        symbol="BTCUSDT",
        firewall=firewall,
        signer=firewall._signer,
        instrument=InstrumentType.PERP,
        starting_cash=10_000.0,
        ledger_dir=out / "ledgers",
    )
    result = arena.run()
    result["label"] = label
    (out / "leaderboard.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for agent_id, ledger in arena.ledgers.items():
        ledger.write_csv(out / f"trades_{agent_id}.csv")
    board = " | ".join(f"{r['agent_id']}={r['final_equity']:,.0f}(t{r['trades']})" for r in result["leaderboard"])
    print(f"{label}: {board} | ledger_ok={result['ledger_verified']} pbo={result['overfitting'].get('pbo')}")
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    firewall = Firewall.with_key(load_settings().signing_key_path)

    firewall_demos(firewall)

    synth = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=600, start_price=60_000, seed=11, drift=0.0008, vol=0.012)})
    run_tournament(synth, firewall, OUT / "synthetic_run", "synthetic")

    regime = ReplayMarketData({"BTCUSDT": _candles_from_closes(_regime_closes())})
    run_tournament(regime, firewall, OUT / "regime_scenario", "regime(trend-chop-trend)")

    print(f"\nEvidence written under {OUT.resolve()}")


if __name__ == "__main__":
    main()
