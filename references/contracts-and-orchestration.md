# Contracts and Orchestration

Read this reference before delegating writes, creating multiple children, scheduling dependencies, using parallelism, or handling an Ultra/unknown parent state.

## Delegation value gate

Use a qualitative comparison rather than an invented score:

```text
delegation value =
  parallel time saved
  + context isolation
  + specialized tool-surface value
  + independent review value
  - handoff cost
  - duplicate reading
  - synchronization cost
  - integration and verification cost
```

Delegate only when the positive side materially wins and the work can be bounded and verified. A worker should normally perform at least two valuable actions or isolate a genuinely different context/tool surface. Do not create a scout that only rereads everything the implementer must read.

Keep these in the parent:

- final synthesis and shared-interface integration;
- a known one-line/local change unless independent review is valuable;
- live sessions or credentials that cannot be safely transferred;
- tasks with an unstable boundary or no acceptance oracle;
- tasks whose required context would make the child duplicate the parent nearly in full;
- work for which only Luna below `xhigh` or Terra below `high` would be economical.

## Orchestration state

Before any manual spawn, establish one of these states:

| State | Meaning | Manual children |
| --- | --- | --- |
| `MANUAL_ALLOWED` | Parent is known non-Ultra, has sufficient integrator capability, and the child limit is known | Allowed within the plan |
| `ULTRA_OWNED` | Root is already using Ultra orchestration | Zero |
| `ORCHESTRATION_UNKNOWN` | Ultra state, parent capability, or concurrency limit cannot be established | Zero |

Ultra is not part of a child escalation ladder. This Skill cannot switch the current root turn into Ultra. It can only respect an existing Ultra root or suggest a later run when the user wants that mode.

An explicitly spawned child must:

- remain a leaf;
- never invoke this Skill or spawn another agent;
- never use `ultra` effort;
- escalate scope, authority, or missing context back to the parent.

## DAG before dispatch

Represent each work unit as a node and each prerequisite as a directed edge. Dispatch only nodes whose dependencies have been accepted.

Preserve natural ordering:

```text
discovery -> design -> implementation -> validation -> independent review -> integration
```

Do not parallelize a serial knowledge dependency merely because files differ. For validation plans, assign each node to an integer `wave`; every dependency must be in an earlier wave.

For Luna-Max-only execution, wave ordering is only the static plan. Before any actual attempt, every dependency must already have a completed `success` result and the attempt's `event_seq` must be later than that result event. The retry edge to its own initial node is the only status exception: the initial is completed `failed`, parent-classified `transient` with evidence, and the retry spawn still occurs after its result event.

## Semantic conflict groups

File ownership is necessary but insufficient. Two different files may implement the same mutable contract.

Declare both concrete mutable surfaces and semantic conflict groups, for example:

```yaml
owned_mutable_surfaces:
  - src/api/user.ts
write_conflict_groups:
  - public-api:user
  - schema:user-v3
  - generated:client-index
```

Treat these as conflict groups when relevant:

- public APIs and shared type contracts;
- schemas and migration order;
- generated sources, indexes, lock files, and build graphs;
- shared manifests and global configuration;
- live browser/device/session state;
- databases, queues, and other externally mutable resources.

Two writers with an overlapping surface or conflict group must be in different waves, normally with an explicit dependency. Read-only nodes may overlap unless the underlying live state makes their evidence inconsistent.

Mutable path declarations must be canonical. Do not use globs, `.`/`..` segments, drive-relative paths, Windows alternate-data-stream syntax, or segments ending in a dot or space. These forms can alias another path and defeat one-writer checks. Use semantic conflict groups for opaque external resources.

## Concurrency

Use the collaboration tool's current limit. Convert it to `max_concurrent_children` after reserving capacity for the parent. If the usable child limit is unknown, manual fan-out fails closed.

Keep critical-path nodes on the fastest qualified evidence-backed route. A high-effort Luna node may be inexpensive but slow, so it often belongs on a non-critical parallel branch rather than the critical path.

Continue useful parent-local work while independent children run, but do not mutate a surface owned by an active child. Reuse an idle completed child for a closely related follow-up when doing so preserves context and ownership.

## Work-unit contract

Every dispatch packet must be self-contained enough for the selected history fork and include:

```yaml
agent_label:
task_name:
dispatch_attempt:
executor_id:
child_policy: adaptive | luna_max_only
work_unit_id:                 # required for luna_max_only
retry_kind: none | transient  # substantive is invalid for luna_max_only
retry_of:                     # null for initial; prior node ID for transient retry
assigned_pair: {model:, family:, effort:}
confirmation_status: confirmed-explicit | confirmed-inherited | fallback-confirmed
dispatch_mode: explicit | inherit_parent
selection_origin: automatic | fallback | inherited | explicit_user
metric_source: runtime | local_telemetry | community_prior | none
metric_as_of:
evidence_id_or_window:
role:
work_class: structured | general | open | critical
reasoning_budget:
objective:
why_delegate:
dependencies:
known_facts:
hypotheses:
owned_mutable_surfaces:
read_only_surfaces:
write_conflict_groups:
forbidden_actions:
deliverables:
acceptance_criteria:
validation_steps:
expected_evidence:
risk: low | medium | high | irreversible
context_scope: bounded | repository | cross_system | unknown
oracle: deterministic | strong | weak | none
access_mode: read_only | workspace_write | external_write
attempt_budget:
recovery_steps:
stop_conditions:
escalate_when:
```

Start the message with:

```text
LEAF EXECUTION MODE. Do not spawn agents or invoke routing skills.
Stay within the owned surfaces and authority below. Escalate instead of expanding scope.
```

For `explicit`, pass both `model` and `reasoning_effort`; never rely on a model's default effort. Use `fork_turns: "none"` or a supported positive history slice and provide the complete dossier. For `inherit_parent`, omit both overrides only after the exact parent pair is known to satisfy the requirements, and use the full-history fork guaranteed by the current collaboration contract. Do not combine `fork_turns: "all"` with explicit overrides.

For `luna_max_only`, `assigned_pair` must be exactly `{model: gpt-5.6-luna, family: luna, effort: max}` and `dispatch_mode` must be `explicit`. Pass both exact override values on every attempt, including an unchanged transient retry. Inheritance, fallback, and model-default resolution are forbidden. A child dossier must not claim that the policy makes general/open/critical or high-risk work suitable for Luna.

Before the tool call, announce the exact agent label, pair, mode, purpose, and planned pair-first task name. After the call, record its accepted or rejected receipt before treating the node as dispatched.

## Result envelope

Require the child to return the fields below. When the parent records a Luna-Max-only result in the ledger, it appends `event_seq` and independently attests `failure_classification`/`failure_evidence`; these are parent-authored audit metadata, not unverified child claims. Use `none` and an empty evidence list for success. For non-success, choose a classification from the failure table in [validation-and-failure.md](validation-and-failure.md) and cite non-empty observable evidence.

```yaml
status: success | partial | blocked | failed | escalate
event_seq:                     # required for luna_max_only; global append-only order
failure_classification:        # required for luna_max_only; parent-verified, none on success
failure_evidence: []           # required; non-empty for a non-success result
dispatch_attempt:
agent_label:
assigned_pair_echo: {model:, family:, effort:}
confirmation_status_echo: confirmed-explicit | confirmed-inherited | fallback-confirmed
facts:
hypotheses:
surfaces_read:
changes:
validation_results:
evidence:
deviations_from_contract:
remaining_risks:
parent_action_required:
```

The child must separate facts from hypotheses. Its routing fields echo the assignment it received; they do not independently prove runtime identity. Runtime proof comes from accepted explicit spawn arguments or accepted guaranteed inheritance. `success` is a claim, not acceptance; only the parent can accept a node after checking the routing chain and actual work evidence.

## Agent labels

For every attempt, report `<role> (<model>, <effort>)`. Encode the exact planned pair at the left edge of the immutable tool name:

```text
<model-slug>_<effort>_<node-id>_a<attempt-number>
```

For example, `gpt_5_6_terra_high_parser_fix_a1`. Pair-first ordering keeps the model and effort visible when a narrow desktop task list truncates the right side. The desktop does not guarantee separate model/effort fields, so this name is a visibility aid while the receipt proves whether the call was accepted. Existing task names are immutable and cannot be repaired retroactively.

Use a plan-local canonical `executor_id` matching `^[a-z][a-z0-9_]{0,63}$`. Reuse it only when the same executor intentionally owns serial nodes; a reviewer and its target must use different canonical IDs.

V2 does not create `runtime_pending` children. If the exact inherited pair is unavailable, record `inherited-unresolved` only as an audit failure, keep the node in the parent or select an explicit qualified pair, and do not spawn. Likewise, explicit model-only dispatch is `default-unresolved` and invalid because the runtime may choose that model's default effort.

Use these confirmation states exactly:

| Status | Meaning | Valid effective child? |
| --- | --- | --- |
| `confirmed-explicit` | Both explicit override fields and the spawn were accepted | Yes |
| `confirmed-inherited` | Exact parent pair is known and accepted full-history spawn guarantees inheritance | Yes |
| `fallback-confirmed` | Accepted explicit pair is the declared fallback | Yes |
| `runtime-rejected` | Attempt produced no child | No |
| `default-unresolved` | Model supplied without verified effort/default resolution | No |
| `inherited-unresolved` | Exact inherited pair or guarantee is unavailable | No |

## Routing-ledger JSON

For complex fan-out or high-risk work, write a temporary JSON routing ledger and validate it before spawning, after every receipt transition, and before final reporting. Start from the machine-checked [complete example](routing-plan.example.json); the regression suite loads that exact file and requires the validator to accept it.

The root object uses `schema_version: aar.routing-ledger.v2` and must contain `ledger_phase`, profile and metric evidence fields, orchestration state, the live runtime catalog, and explicit child nodes. If the invocation omits `profile=`, materialize the default as `profile: balanced`; the field is never omitted. New ledgers should also record `child_policy: adaptive | luna_max_only`; omission is accepted only for backward compatibility and means `adaptive`. The earlier draft identifier `aar.routing-plan.v2` is intentionally incompatible because it cannot record execution receipts. `ledger_phase` is `planning`, `active`, or `finalized`.

For `luna_max_only`, `runtime.available_pairs` becomes an immutable dispatch-time catalog snapshot immediately before the first spawn event. A ledger containing any dispatch event also records `runtime.catalog_snapshot: {captured_at, evidence_ref, available_pairs_sha256}`; `captured_at` is an ISO 8601 date or timezone-aware timestamp, `evidence_ref` identifies the collaboration-tool catalog observation, and the lowercase digest is computed by the validator over the normalized catalog contents. Preserve this snapshot in the finalized ledger even if the live catalog later changes; an accepted exact receipt is historical execution evidence and must not be invalidated by overwriting the snapshot during final reporting. If availability changes before an unspawned node is attempted, leave it unspawned and create a newly validated ledger for any later resume rather than mixing catalog epochs.

Every node must contain the full work-unit contract, `executor_id`, enumerated requirements, selection record, `lifecycle_state`, nullable `dispatch`, and nullable `result`. Economy automatic/fallback nodes additionally contain the strict `economy_evaluation` object defined in [routing-policy.md](routing-policy.md#economy-evaluation-contract); other profiles must not add it, while `explicit_user`/`inherited` Economy nodes omit it and expose the profile bypass. Node transitions are:

```text
planned -> dispatched -> completed
planned -> dispatch_blocked
```

`planned` has no receipt or result. `dispatched` has one accepted effective receipt but no result. `completed` additionally has a matching child routing echo. `dispatch_blocked` contains only rejected attempts and no effective pair or child result. A finalized ledger contains only `completed` or `dispatch_blocked` nodes.

`allowed_model_effort_pairs` contains only current runtime pairs that already satisfy the node's semantic and assurance floors. An unavailable or semantically node-ineligible but globally permitted original request belongs only in `selection.requested_pair`, never in the allowed or fallback lists. Globally denied Luna `low`/`medium`/`high`, Terra `low`/`medium`, and child Ultra pairs may not appear anywhere in a certified ledger, including `selection.requested_pair`. `unavailable` and `policy_rejection` fallback reasons must be true in the declared current state.

`luna_max_only` is the narrow exception to the generic availability wording: its desired singleton target may remain in `allowed_model_effort_pairs` and `selection.selected_pair` while the node is `planned`, or while a matching explicit attempt is terminally `dispatch_blocked`. It cannot become `dispatched` or `completed` unless exact Luna Max is in the runtime catalog. In this policy, the allowed list is exactly the singleton Luna Max pair, `fallback_pairs` is empty, `minimum_child_effort` is `max`, `substantive_attempts` is `1`, and `max_uses` is `1`.

The dispatch record is an auditable list because a runtime rejection may precede a confirmed fallback:

```yaml
dispatch:
  attempts:
    - attempt_index: 1
      event_seq: 1             # required for luna_max_only
      mode: explicit | inherit_parent
      task_name:
      agent_label:
      fork_turns: none | all | "<positive integer>"
      requested_pair: {model:, family:, effort:}
      model:                    # exact spawn argument, null only for inheritance
      reasoning_effort:         # exact spawn argument, null only for inheritance
      receipt_status: accepted | rejected
      receipt_ref: spawn_agent:<agent-id, canonical task, or rejection reference>
      effective_pair: {model:, family:, effort:} | null
      confirmation_status: confirmed-explicit | confirmed-inherited | fallback-confirmed | runtime-rejected | default-unresolved | inherited-unresolved
  effective_attempt: 1 | null
```

A node represents one actual child and therefore has at most one accepted attempt. A retry that creates another child is another node. Receipt references are unique across the ledger. Rejected attempts may precede the one accepted fallback attempt; no attempt may follow acceptance.

Under `luna_max_only`, every node declares `work_unit_id`, `retry_kind`, and `retry_of`. A work unit has exactly one initial node (`retry_kind: none`, `retry_of: null`) and at most one direct transient retry. A cross-node retry must point to the completed failed initial node, whose parent-attested `failure_classification` is `transient` and whose `failure_evidence` is non-empty. It keeps the same executor and contract, preserves the original dependencies plus the initial node, sets its remaining `transient_retries` to zero, and records every retry attempt after the initial result's `event_seq`. The validator caps total dispatch attempts across the work unit and rejects an identical contract relabeled with a different work-unit ID. A substantive retry is invalid; the root must also avoid cosmetic contract edits intended only to evade work-unit identity.

Luna-Max-only execution also maintains one global append-only event order across the ledger. Assign the next positive integer `event_seq` immediately after every accepted or rejected spawn attempt and every completed child result; values are unique, contiguous from 1, and never renumbered. A result sequence must follow every attempt for its node. The validator derives the one failure fence from the earliest non-`success` result or the last rejected attempt of a terminal `dispatch_blocked` node. A later spawn event is invalid unless its node is the one contract-identical direct transient retry of that earliest failed initial. A pre-fence sibling may finish after the fence, but its own later failure cannot authorize a second retry; a same-wave node dispatched after the fence is rejected.

`max_uses: 1` counts an accepted Max child for one node. A rejected spawn receipt has no effective child and therefore does not consume a Max execution; this is why one rejected attempt followed by one accepted unchanged retry remains consistent. If an accepted child itself fails transiently, the single linked retry node may create the second and final accepted child for that work unit.

When `metric_source` is `none`, set `metric_as_of` and `evidence_id_or_window` to `null`. Otherwise both must be non-empty: `metric_as_of` is an ISO 8601 date or timezone-aware timestamp, and the evidence identifier/window contains no invisible or control characters. Economy uses `community_prior`/`none` only for a declared qualitative order; `runtime`/`local_telemetry` require quantitative mode, a complete candidate set, and a full parent estimate bound to the actual parent pair. Candidate and parent references are unique records under `evidence_id_or_window#...`; all formula inputs have at most six decimal places. Do not add a plan-local policy acknowledgment: explicit provenance cannot self-authorize Luna below `xhigh` or Terra below `high`, and such a pair cannot form a V2-certified plan.

`nodes` represent planned child slots and their dispatch history. Parent-local steps are not counted as children. `wave` supplies the proposed dispatch grouping; dependencies must point to earlier waves.

The validator is deliberately conservative. Its successful result means the declarations and recorded receipt chain are internally consistent, not that the task is correct or that a planned spawn will be accepted. On a finalized ledger, `python scripts/validate-routing-plan.py <ledger.json> --report` emits the mandatory per-child Markdown report; it refuses planning or active ledgers.
