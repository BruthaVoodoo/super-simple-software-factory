# Known gaps — retired

All seven defects disclosed during M1 (M2-PERM-01…04, M2-TRACE-01,
M2-PROC-01/02) are fixed in M2. Their reproductions were promoted to ordinary
passing tests in the lanes they belong to:

| ID | Now covered by |
|---|---|
| M2-PERM-01 | `tests/unit/test_permissions.py::FingerprintTests` |
| M2-PERM-02 | `tests/unit/test_permissions.py::FingerprintTests` |
| M2-PERM-03 | `tests/unit/test_permissions.py::IgnoredPathTests` |
| M2-PERM-04 | `tests/control_plane/test_agents.py::EnforcementOnFailureTests` |
| M2-TRACE-01 | `tests/control_plane/test_agents.py::FailureTraceTests` |
| M2-PROC-01 | `tests/control_plane/test_lifecycle.py::InterruptedChildTerminationTests` |
| M2-PROC-02 | `tests/control_plane/test_pi_transport.py::StderrFloodTests` |

There is no expected-failure lane anymore: every lane is a certification lane.
A newly discovered defect goes through the same cycle — narrow reproduction,
documented desired invariant, fix, decorator-free test.
