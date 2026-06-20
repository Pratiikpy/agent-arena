"""Entry point for the Adaptive Regime (Conflict-Gated) Playbook.

Historical replay path: fetch bars -> backtest.run() -> write a REAL equity/NAV
curve (publish anti-fabrication requirement) + a small backtest_report.json with
corrected strategy-basis metrics -> emit a signal. Live path emits a flat signal
(this Playbook is signal_only).
"""

import json
import math
from pathlib import Path
from typing import Any

from getagent import backtest, data, runtime

OUT = Path("/workspace/output")


def _finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _extract_curve(reports: dict, initial_capital: float) -> list[dict]:
    """Best-effort REAL equity curve from Nautilus reports. Never fabricated."""
    points: list[dict] = []
    raw_curve = reports.get("equity_curve")

    def _push(ts: Any, val: Any, nav: Any = None) -> None:
        try:
            v = float(val)
        except (TypeError, ValueError):
            return
        n = None
        if nav is not None:
            try:
                n = float(nav)
            except (TypeError, ValueError):
                n = None
        if n is None:
            n = v / initial_capital if initial_capital else 1.0
        points.append({"timestamp": ts if ts is not None else "", "value": round(v, 4), "nav": round(n, 6)})

    if isinstance(raw_curve, list):
        for d in raw_curve:
            if isinstance(d, dict):
                ts = d.get("timestamp") or d.get("time") or d.get("ts") or d.get("date")
                val = d.get("value")
                if val is None:
                    val = d.get("equity")
                if val is None:
                    val = d.get("total")
                if val is None:
                    val = d.get("balance")
                _push(ts, val, d.get("nav"))
            elif isinstance(d, (list, tuple)) and len(d) >= 2:
                _push(d[0], d[1], d[2] if len(d) > 2 else None)
    elif isinstance(raw_curve, dict) and raw_curve:
        for ts, val in raw_curve.items():
            _push(ts, val)

    return points


def run() -> None:
    cfg = runtime.manifest.get("strategy_config", {}) or {}
    symbols = cfg.get("trading_symbols") or ["BTCUSDT"]
    symbol = symbols[0]
    interval = cfg.get("bar_interval", "1h")

    bars = data.crypto.futures.kline(symbol=symbol, interval=interval, limit=1000)
    frame = backtest.prepare_frame(bars, datetime_index="date")
    if frame is None or frame.empty:
        runtime.emit_signal(
            action="watch", symbol=symbol, confidence=0.0,
            metrics={"rows": 0}, meta={"reason": "no historical bars returned"},
        )
        return

    instrument_key = f"{symbol}.BINANCE"
    result = backtest.run(ohlcv_data={instrument_key: frame}, spec=runtime.backtest_spec)
    chart_path = backtest.generate_chart(result)

    summary = result.summary or {}
    raw = dict(result.raw or {})
    reports = dict(raw.get("reports", {}) or {})

    initial_capital = 0.0
    try:
        spec = runtime.backtest_spec or {}
        initial_capital = float(spec.get("venue", {}).get("starting_balances", [{}])[0].get("amount") or 0)
    except Exception:
        initial_capital = 0.0
    if not initial_capital:
        try:
            initial_capital = float(summary.get("starting_balance") or 0)
        except (TypeError, ValueError):
            initial_capital = 0.0
    if not initial_capital:
        initial_capital = 100000.0

    curve = _extract_curve(reports, initial_capital)
    if curve:
        ending_total = curve[-1]["value"]
    else:
        try:
            ending_total = initial_capital + float(summary.get("net_pnl", 0) or 0)
        except (TypeError, ValueError):
            ending_total = initial_capital

    net_pnl = ending_total - initial_capital
    strategy_return_pct = (net_pnl / initial_capital * 100.0) if initial_capital else 0.0

    raw["net_pnl"] = round(net_pnl, 4)
    raw["total_return_pct"] = round(strategy_return_pct, 4)
    raw["starting_balance"] = initial_capital
    if isinstance(raw.get("reports"), dict):
        raw["reports"] = {k: v for k, v in raw["reports"].items() if k != "equity_curve"}

    OUT.mkdir(parents=True, exist_ok=True)
    try:
        (OUT / "backtest_report.json").write_text(json.dumps(raw, default=str), encoding="utf-8")
    except Exception:
        (OUT / "backtest_report.json").write_text(
            json.dumps(
                {
                    "net_pnl": raw["net_pnl"],
                    "total_return_pct": raw["total_return_pct"],
                    "starting_balance": initial_capital,
                },
                default=str,
            ),
            encoding="utf-8",
        )

    csv_lines = ["timestamp,value,nav"]
    for point in curve:
        csv_lines.append(f"{point['timestamp']},{point['value']},{point['nav']}")
    (OUT / "equity_curve.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    metrics = {
        "total_return_pct": _finite(result.total_return_pct),
        "net_pnl": _finite(net_pnl),
        "starting_balance": initial_capital,
        "sharpe_ratio": _finite(result.sharpe_ratio),
        "max_drawdown_pct": _finite(result.max_drawdown_pct),
        "win_rate": _finite(result.win_rate),
        "total_trades": result.total_trades,
        "profit_factor": _finite(result.profit_factor),
        "rows": len(frame),
        "equity_points": len(curve),
    }
    action = "long" if net_pnl > 0 else "watch"
    runtime.emit_signal(
        action=action,
        symbol=symbol,
        confidence=_finite(result.win_rate) or 0.0,
        metrics=metrics,
        meta={"chart_path": chart_path, "report_keys": list(reports.keys())},
    )


if __name__ == "__main__":
    run()
