"""Personas make the roster legible without changing any decision logic."""

from __future__ import annotations

from bitarena.agents.persona import PERSONAS, persona_for


def test_every_default_roster_agent_has_an_explicit_persona():
    roster = [
        "swarm", "regime", "persona-team", "llm-swarm", "rl-qlearn",
        "baseline-momentum", "benchmark-buyhold", "funding-carry",
    ]
    for aid in roster:
        assert aid in PERSONAS, f"{aid} is missing a persona"
        p = persona_for(aid)
        assert p.agent_id == aid
        assert p.name and p.philosophy and p.lens  # all populated, no blanks


def test_personas_are_distinct():
    names = [p.name for p in PERSONAS.values()]
    assert len(names) == len(set(names))  # no two agents share a name


def test_unknown_agent_gets_a_clean_default():
    p = persona_for("my_custom_bot")
    assert p.name == "My Custom Bot"
    assert p.lens == "custom"
    assert "my_custom_bot" not in PERSONAS  # default is not registered


def test_leaderboard_rows_carry_persona_fields():
    from bitarena.arena.leaderboard import build_leaderboard
    from bitarena.arena.portfolio import Portfolio

    pf = Portfolio(agent_id="swarm", starting_cash=10_000.0,
                   equity_curve=[10_000.0, 10_050.0, 10_010.0, 10_080.0])
    rows = build_leaderboard({"swarm": pf})
    assert rows[0]["name"] == "The Consensus"
    assert rows[0]["philosophy"]
    assert rows[0]["lens"] == "agreement"
