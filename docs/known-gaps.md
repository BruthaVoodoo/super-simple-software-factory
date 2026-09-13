# Known gaps — disclosed M2 defects

These reproductions assert a **desired invariant** and currently fail. They
are quarantined in `tests/known_gaps/` as `unittest.expectedFailure` cases so
the ordinary lanes stay green without hiding the defects. An unexpected
success in this lane is an error: the gap was fixed and the `expectedFailure`
decorator must be removed.

Run with `just test-known-gaps`. Setup and scenario-execution exceptions fail
the suite as errors — only the desired-invariant assertion may fail.

| ID | Test | Desired invariant | Observed failure (today) | Owner |
|---|---|---|---|---|
| M2-PERM-01 | `test_safety.NumstatIdenticalRewriteReproduction.test_identical_numstat_rewrites_are_reported` | Replacing an already-dirty file's lines with different bytes of identical numstat must appear in `changed_paths` | `'sample.txt' not found in []` — numstat fingerprints cannot see same-shape rewrites | M2 |
| M2-PERM-02 | `test_safety.UntrackedChangeReproduction.test_changed_untracked_file_is_reported` | Changing an existing untracked file's contents must appear in `changed_paths` | `'notes.txt' not found in []` — untracked files are keyed by name only | M2 |
| M2-PERM-03 | `test_safety.IgnoredFileEnforcementReproduction.test_ignored_file_modification_is_caught` | A read-only agent modifying a gitignored file must trigger `PermissionBreach` | `PermissionBreach not raised` — gitignored paths never enter the snapshot | M2 |
| M2-PERM-04 | `test_safety.EnforcementAfterParseExhaustionReproduction.test_enforcement_still_runs_after_exhausted_json_parsing` | An unauthorized write made on a send whose parsing later exhausts must still raise `PermissionBreach` (and restore the file) | `RuntimeError(...never produced valid...JSON)` — parse exhaustion preempts enforcement entirely | M2 |
| M2-TRACE-01 | `test_failures.AgentEndUsageReproduction.test_exhausted_corrections_still_record_agent_end_usage` | Exhausted JSON/gate corrections must still persist an `agent_end` event with accumulated usage | `0 != 1` — no `agent_end` row exists for the phase | M2 |
| M2-PROC-01 | `test_failures.InterruptedChildTerminationReproduction.test_interrupted_adw_child_actually_terminates` | Interrupting an ADW must actually terminate the coding-agent child, not merely mark the process row ended | `True is not false` — the orphaned double is still alive after the ADW exited 143 | M2 |
| M2-PROC-02 | `test_failures.StderrFloodReproduction.test_transport_finishes_or_fails_within_the_deadline` | A child that fills the stderr pipe while stdout stays open must not deadlock the transport past its deadline | `True is not false` — transport thread still blocked after 5s | M2 |

Reproduction command: `just test-known-gaps`. These are disclosed defects, not
passing safety tests: do not cite this lane as evidence that M1 enforced or
repaired any of them.
