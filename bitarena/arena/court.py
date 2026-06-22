"""Overfit Court: a named, public pipeline that judges whether a strategy's edge is real.

A leaderboard ranks by outcome. The Court rules on *trust*: it runs each agent through a fixed
ladder of overfit and robustness checks and hands down one verdict, so a lucky backtest is
labelled as luck before any capital moves. Most candidates should be rejected; that is the point.

No new statistics are computed here. The Court reads the metrics the tournament already produced
(Deflated Sharpe, the run's Probability of Backtest Overfitting, drawdown, profit factor, trade
count) and maps them to a verdict. The thresholds are stated in the open so anyone can recompute
a docket from the published leaderboard.
"""

from __future__ import annotations

from ..agents.persona import persona_for
from ..firewall.signing import Signer, sign_payload

# verdict ladder, worst to best
VERDICTS = (
    "REJECT_OVERFIT",       # the selection itself is likely luck (PBO) or the edge is negative
    "REJECT_COST_SENSITIVE",  # does not survive transaction costs (profit factor <= 1)
    "REJECT_UNSTABLE",      # drawdown too deep to fund
    "PAPER_ONLY",           # not enough evidence yet, keep on paper
    "DUST_APPROVED",        # promising; eligible for dust-sized real capital
    "CAPITAL_APPROVED",     # skill survives the overfit correction; eligible for capital
)

# thresholds, published so a docket is reproducible from the leaderboard
MAX_PBO = 0.50            # above this, naive best-of-N selection is more luck than skill
MIN_PROFIT_FACTOR = 1.0   # must win more than it loses after fees
MAX_DRAWDOWN = 0.25       # a 25%+ realized drawdown is not fundable
DSR_SIGNIFICANT = 0.95    # Deflated Sharpe at which skill is significant vs the trial set
DSR_PROMISING = 0.50      # Deflated Sharpe at which an agent earns dust probation
MIN_TRADES = 5            # below this there is no track record to judge


def _stage(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def court_verdict(row: dict, pbo: float | None = None) -> dict:
    """Rule on one leaderboard row. Returns the verdict, the stage docket, and the reason."""
    dsr = row.get("dsr")
    dsr = float(dsr) if dsr is not None else None
    pf = float(row.get("profit_factor") or 0.0)
    dd = abs(float(row.get("max_drawdown") or 0.0))
    trades = int(row.get("trades") or 0)
    significant = bool(row.get("skill_significant"))

    has_track = trades >= MIN_TRADES
    pbo_ok = pbo is None or pbo <= MAX_PBO
    cost_ok = pf > MIN_PROFIT_FACTOR
    dd_ok = dd <= MAX_DRAWDOWN
    skill_ok = significant or (dsr is not None and dsr >= DSR_SIGNIFICANT)

    stages = [
        _stage("track record", has_track, f"{trades} trades (min {MIN_TRADES})"),
        _stage("selection not overfit (PBO)", pbo_ok,
                "no run PBO" if pbo is None else f"PBO {pbo:.2f} (max {MAX_PBO:.2f})"),
        _stage("survives costs (profit factor)", cost_ok, f"PF {pf:.2f} (min {MIN_PROFIT_FACTOR:.2f})"),
        _stage("drawdown fundable", dd_ok, f"max DD {dd * 100:.1f}% (max {MAX_DRAWDOWN * 100:.0f}%)"),
        _stage("skill significant (Deflated Sharpe)", skill_ok,
                "DSR n/a" if dsr is None else f"DSR {dsr:.2f} (sig {DSR_SIGNIFICANT:.2f})"),
    ]

    # verdict ladder: a rejection short-circuits; otherwise promote on evidence strength
    if not has_track:
        verdict, reason = "PAPER_ONLY", "not enough trades to judge an edge yet"
    elif not pbo_ok:
        verdict, reason = "REJECT_OVERFIT", "the leaderboard selection is more likely luck than skill"
    elif (dsr is not None and dsr <= 0.0):
        verdict, reason = "REJECT_OVERFIT", "no edge survives the overfit correction"
    elif not cost_ok:
        verdict, reason = "REJECT_COST_SENSITIVE", "does not win more than it loses after fees"
    elif not dd_ok:
        verdict, reason = "REJECT_UNSTABLE", "realized drawdown too deep to fund"
    elif skill_ok:
        verdict, reason = "CAPITAL_APPROVED", "skill is significant after the overfit correction"
    elif dsr is not None and dsr >= DSR_PROMISING:
        verdict, reason = "DUST_APPROVED", "promising but not yet significant; dust-sized capital only"
    else:
        verdict, reason = "PAPER_ONLY", "survives the hard filters but skill is not yet proven"

    return {"verdict": verdict, "reason": reason, "stages": stages}


def build_court(leaderboard: list[dict] | None, run_meta: dict | None = None,
                signer: Signer | None = None) -> dict:
    """Build the full docket for a tournament. Optionally sign it as a tamper-evident report."""
    rows = [r for r in (leaderboard or []) if isinstance(r, dict) and r.get("agent_id")]
    pbo = None
    if isinstance(run_meta, dict):
        of = run_meta.get("overfitting") or {}
        if isinstance(of, dict) and not of.get("insufficient"):
            pbo = of.get("pbo")

    dockets = []
    for r in rows:
        p = persona_for(str(r["agent_id"]))
        v = court_verdict(r, pbo)
        dockets.append({
            "agent_id": r["agent_id"],
            "name": p.name,
            "verdict": v["verdict"],
            "reason": v["reason"],
            "stages": v["stages"],
            "dsr": r.get("dsr"),
            "profit_factor": r.get("profit_factor"),
            "max_drawdown": r.get("max_drawdown"),
            "trades": r.get("trades"),
        })
    dockets.sort(key=lambda d: VERDICTS.index(d["verdict"]), reverse=True)

    tally = {v: 0 for v in VERDICTS}
    for d in dockets:
        tally[d["verdict"]] += 1
    rejected = sum(tally[v] for v in VERDICTS if v.startswith("REJECT"))
    graduated = tally["CAPITAL_APPROVED"] + tally["DUST_APPROVED"]

    report = {
        "tested": len(dockets),
        "rejected": rejected,
        "graduated": graduated,
        "tally": tally,
        "run_pbo": pbo,
        "thresholds": {
            "max_pbo": MAX_PBO, "min_profit_factor": MIN_PROFIT_FACTOR,
            "max_drawdown": MAX_DRAWDOWN, "dsr_significant": DSR_SIGNIFICANT,
            "dsr_promising": DSR_PROMISING, "min_trades": MIN_TRADES,
        },
        "dockets": dockets,
    }
    if signer is not None:
        return sign_payload(report, signer)
    return report
