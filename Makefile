# Agent Arena — one-command workflows. Requires `uv` (https://docs.astral.sh/uv/).

.PHONY: setup test lint arena firewall firewall-value redteam killswitch allocator funding walkforward overfit-trap bench evidence check-docs verify-evidence integrate playbook-validate serve live demo verify

setup:           ## create venv + install everything
	uv venv && uv pip install -e ".[dev,api,mcp,llm]"

test:            ## run the full offline test suite
	uv run pytest

lint:            ## static lint
	uv run --with ruff ruff check .

arena:           ## run a tournament on real Bitget BTC perp (1h)
	uv run python scripts/run_arena.py --source bitget --symbol BTCUSDT --instrument perp

firewall:        ## one signed firewall verdict (oversized -> ALLOW_CAPPED)
	uv run python scripts/demo_firewall.py --symbol BTCUSDT --side buy --notional 999999

redteam:         ## adversarial battery — proves 0 unsafe orders pass
	uv run python scripts/redteam.py

killswitch:      ## quantify the market-wide kill-switch in a flash crash (contained vs not)
	uv run python scripts/regime_killswitch.py

firewall-value:  ## quantify the firewall's containment value (rogue agent: contained vs not)
	uv run python scripts/firewall_value.py

allocator:       ## TrustAllocator vs equal-weight (regime market)
	uv run python scripts/allocator_demo.py --regime

funding:         ## funding-carry edge study on real Bitget funding data
	uv run python scripts/funding_study.py

walkforward:     ## walk-forward robustness of agents across real-Bitget folds
	uv run python scripts/walk_forward.py --symbol BTCUSDT --instrument perp

overfit-trap:    ## verification value — DSR/PBO catch naive best-of-N selection on noise
	uv run python scripts/overfit_trap.py

bench:           ## firewall latency benchmark (signed verdicts/sec)
	uv run python scripts/bench_firewall.py

evidence:        ## regenerate the deterministic evidence pack
	uv run python scripts/make_evidence.py

check-docs:      ## fail if any cited number drifts from the source of truth
	uv run python scripts/check_docs.py

verify-evidence: ## re-verify the whole evidence pack (signed, chained, issuer-pinned)
	uv run python scripts/verify_evidence.py

integrate:       ## third-party integration demo: vet + offline-verify trades vs the live deploy
	uv run python scripts/integrate_example.py

playbook-validate: ## locally validate the published Playbook package (needs the getagent skill)
	uv run --with pyyaml python "$(GETAGENT)/scripts/validate.py" ./playbook/adaptive-regime/

serve:           ## serve the UI + API at http://localhost:8000
	uv run uvicorn bitarena.api.app:app --port 8000

live:            ## advance the LIVE arena one step on real Bitget data (run on a schedule)
	uv run python scripts/live_step.py --symbol BTCUSDT --instrument perp --state evidence/live

demo: test firewall redteam   ## quick end-to-end proof: tests + signed verdict + red-team
	@echo "Agent Arena demo complete."

verify: test lint check-docs verify-evidence redteam  ## full quality gate (mirrors CI)
	@echo "Agent Arena verified: tests + lint + doc-numbers + evidence pack + red-team all green."
