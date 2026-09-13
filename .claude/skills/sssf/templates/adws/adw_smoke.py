#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pydantic", "python-dotenv", "pyyaml", "rich"]
# ///
"""ADW Smoke — bounded real-Pi probe/recall acceptance run. Never a test double.

Usage:
    uv run adws/adw_smoke.py --probe-file README.md [--adw-id a1b2c3d4]

Two agent calls with one fresh 32-hex nonce:
    probe:  read the nominated file, write the smoke receipt, remember the
            nonce in conversation only
    recall: return the remembered nonce as summary — no tools, no reinjection

Then a code phase verifies the TRACE: tool evidence, no recall tools, session
continuity. The run is not accepted before that check passes.
"""

import argparse
import secrets
import sys
from pathlib import Path

from adw_modules import agents, session, smoke
from adw_modules.data_types import AgentCall, GenericOutput, PhaseParams


def validate_probe_path(probe_file: str) -> Path:
    """The probe must be a regular file inside the current repo root."""
    root = Path.cwd().resolve()
    probe = (root / probe_file).resolve()
    if probe != root and root not in probe.parents:
        raise SystemExit(f"smoke: --probe-file {probe_file!r} escapes the repo root")
    if not probe.is_file():
        raise SystemExit(f"smoke: --probe-file {probe_file!r} is not a regular file "
                         "inside the repo root")
    return probe


def main(probe_file: str, config: str = "adws/adw_sssf_config/sssf.config.yaml",
         adw_id: str | None = None) -> int:
    probe = validate_probe_path(probe_file)

    cfg = agents.load_config(config)
    cfg = smoke.configure_probe(cfg)
    agents.validate(cfg, ["smoke"])

    run = session.ensure(cfg, adw_id)
    nonce = secrets.token_hex(16)          # 32 hex chars, conversation-only
    receipt = run.context_handoff_dir / "smoke-receipt.txt"

    with run.phase(PhaseParams(name="request", kind="engineer", owner=run.engineer,
                               description="Record the smoke probe request")) as ph:
        ph.log(input=f"probe file: {probe}")

    with run.phase(PhaseParams(name="probe", kind="agent", owner="smoke",
                               description=f"Read {probe.name} and write the "
                                           "smoke receipt")) as ph:
        ph.call(AgentCall(
            output_type=GenericOutput,
            prompt=(
                f"Read the file {probe}. Then write exactly the text "
                f"'SSSF smoke receipt' followed by a newline to {receipt}. "
                f"Memorize the value {nonce} — you will be asked for it later. "
                f"Then return your GenericOutput JSON with summary 'probe complete' "
                f"and artifacts exactly [{receipt}]."),
            gates=[smoke.receipt_gate(receipt)]))

    # The load-bearing handoff: evidence recorded from the probe's raw output
    # BEFORE the recall call, so the recall can be judged on its own.
    evidence = smoke.capture_evidence(run, probe, receipt)

    with run.phase(PhaseParams(name="recall", kind="agent", owner="smoke",
                               description="Verify prior context without reinjecting it")) as ph:
        ph.call(AgentCall(
            output_type=GenericOutput,
            prompt="Return the remembered nonce as summary. Use no tools.",
            gates=[smoke.recall_gate(nonce)]))

    verification = smoke.verify_trace(run, evidence)
    if not verification.passed:
        for violation in verification.violations:
            print(f"smoke: {violation}")
    return run.finish(accepted=verification.passed,
                      reason="; ".join(verification.violations))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-file", required=True,
                        help="a regular file inside the repo root for the probe to read")
    parser.add_argument("--config", default="adws/adw_sssf_config/sssf.config.yaml")
    parser.add_argument("--adw-id", default=None, help="join or pin an existing session")
    args = parser.parse_args()
    sys.exit(main(args.probe_file, args.config, args.adw_id))
