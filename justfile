# Factory development commands. NOT stamped into target projects — the
# product recipes live in .claude/skills/sssf/templates/justfile.

test:
    just test-unit
    just test-install
    just test-control-plane
    @echo "known-gap lane is separate: just test-known-gaps"

test-unit:
    uv run --locked --group test --python 3.11 python scripts/checks.py unit

test-install:
    uv run --locked --group test --python 3.11 python scripts/checks.py install

test-control-plane:
    uv run --locked --group test --python 3.11 python scripts/checks.py control-plane

test-known-gaps:
    uv run --locked --group test --python 3.11 python scripts/checks.py known-gaps

# bounded real-Pi smoke acceptance: needs SSSF_SMOKE_MODEL and real auth.
# NEVER runs implicitly via `just test` — it spends tokens and can fail.
smoke-real-pi:
    uv run --locked --group test python scripts/smoke-real-pi.py
