# Visualizer trace/API contract — FROZEN (M5)

The visualizer is a read-only UI over a target repo's trace. This document is
the contract between the tracer (Python, `adw_modules/tracer.py`) and the
visualizer (`apps/visualizer/`). **Additive changes are allowed. Removals,
renames, or semantic changes break the contract** and must update this
document and `tests/unit/test_visualizer_contract.py` in the same task.
Rule: the UI is never redesigned against an undocumented contract.

## Database

The db lives in the TARGET repo (`observability.db`, default
`adws/adw_data/sssf.db`), is in WAL mode, and is opened by the server
readonly — except one deliberate write, `setArchived`, on its own connection.

### `sessions`

`adw_id` (PK), `adw_name`, `request`, `status`, `engineer`, `started_at`,
`ended_at`, `total_tokens`, `total_cost`, `archived`.

- `status` enum: `running` | `success` | `fail`. A run whose acceptance
  criterion failed is `fail` WITH a `not_accepted` error event (see events) —
  the UI renders that as its own state, not a generic failure.
- `archived` is review triage, written only by the UI's archive button.

### `phases`

`phase_id` (PK, `<adw_id>_<seq>_<name>`), `adw_id`, `seq`, `name`, `kind`
(`engineer|agent|code`), `owner`, `description`, `status`, `attempt`,
`retries`, `error`, `started_at`, `ended_at`.

- `status` enum: `queued` (unused in v1) | `running` | `success` | `fail`.
  Success must be earned; the default is `fail`.

### `events`

Rowid cursor (insertion order — the polling page key), `event_id`, `adw_id`,
`phase_id`, `parent_id`, `type`, `name`, `payload_json`, `tokens`,
`started_at`, `ended_at`.

Types the UI renders: `phase_start`, `phase_end`, `agent_start`, `agent_end`,
`tool_call`, `handoff`, `gate_pass`, `gate_fail`, `log`, `error`.

Named payloads the UI depends on:

- `agent_start`: `model`, `thinking`, `color`, `session_id`,
  `session_continued` (bool, M4), `coding_agent`, `purpose`, `tools`,
  `harness_engineering`.
- `agent_end`: `tokens` column + payload `cost`, `usage`
  (`input/output/cache_read/cache_write/reasoning/total_tokens`, costs),
  `context_tokens`, `context_window`.
- `tool_call`: `tool`, `tool_call_id`, `args`, `ok`, `result_snippet`,
  `duration_ms`, `label`; spans via the `started_at`/`ended_at` columns.
  Quality blocks emit `tool_call` rows with `name = "quality:<block>"` and
  payload `area`, `operation`, `command`, `returncode`, `passed`,
  `output_artifact`.
- `log` `repair_summary` (M4): `agent`, `sends`, `json_attempts`,
  `gate_attempts`, `violations`, `outcome` (`success | parse_exhausted |
  gate_exhausted | status_fail | permission_breach | error`).
- `log` `session_continued` (M4): `agent`, `session_id`.
- `log` `paths_touched`: `agent`, `paths` — what the agent actually changed.
- `log` `branch_isolated` (M2): `branch`, `base`.
- `error` `not_accepted`: `reason` — the unmet acceptance criterion.
- `error` `permission_breach`: `agent`, `error`, `writes`, `during`.

### `envelopes`

`envelope_id`, `adw_id`, `phase_id`, `agent`, `output_type`, `payload_json`,
`valid`, `attempt`, `created_at`. Invalid rows (parse failures) are kept with
`valid=0` and the raw text — they are the failure evidence.

### `gate_results`

`id`, `adw_id`, `phase_id`, `attempt`, `gate`, `passed`, `violations_json`,
`checks_json`, `created_at`. `checks_json` is `[{item, ok, note}]` — WHAT the
gate verified, not only the verdict.

### `processes`

`id`, `adw_id`, `kind` (`adw` | `agent`), `name`, `pid`, `command`,
`started_at`, `ended_at` (NULL = believed alive).

### `agent_sessions`

`adw_id`, `agent`, `coding_agent`, `model`, `color`, `session_id`,
`context_tokens`, `context_window`, `created_at`, `last_used_at`. Written
after the envelope persists — a running agent has only its `agent_start`
event (the server merges both views).

## API surface

Served by `apps/visualizer/server/index.ts` (bun), SPA fallback for
client-side routes:

- `GET /api/health`
- `GET /api/sessions?limit=N` — most recent first, each with embedded phases
  and agents (progress dots without extra requests); archived excluded
- `GET /api/sessions/:adw_id` — session + phases + agents + usage
  (`usage` = raw tokens read/written, derived from `agent_end` payloads)
- `GET /api/sessions/:adw_id/events?after=<rowid>&limit=N` — bounded page,
  rowid cursor, `has_more`
- `POST /api/sessions/:adw_id/archive` — the ONE write; review triage only

`tests/unit/test_visualizer_contract.py` pins the UI columns above and the
route list. A live-server response-shape check runs at acceptance time
(outside the offline lanes).
