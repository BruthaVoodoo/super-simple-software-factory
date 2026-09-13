# Factory development commands. NOT stamped into target projects — the
# product recipes live in .claude/skills/sssf/templates/justfile.

test:
    just test-unit
    just test-install
    just test-control-plane

test-unit:
    uv run --locked --group test --python 3.11 python scripts/checks.py unit

test-install:
    uv run --locked --group test --python 3.11 python scripts/checks.py install

test-control-plane:
    uv run --locked --group test --python 3.11 python scripts/checks.py control-plane

# bounded real-Pi smoke acceptance: needs SSSF_SMOKE_MODEL and real auth.
# NEVER runs implicitly via `just test` — it spends tokens and can fail.
smoke-real-pi:
    uv run --locked --group test python scripts/smoke-real-pi.py

# generate deterministic fixture traces for visualizer development
fixture-trace DIR:
    uv run --locked --group test python scripts/fixture-trace.py {{DIR}}
