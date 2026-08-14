---
name: adaptive-agent-routing
description: Route explicitly invoked Codex work across deep-review, general-worker, and fast-leaf roles using the models and reasoning efforts exposed by the current runtime, with bounded dispatch, model/effort labels, post-spawn label resolution, fallback, escalation, and parent verification. In adaptive mode, deep-review roles inherit the parent model and reasoning effort exactly; strict-5.6 explicitly overrides them with its fixed mapping when available. Use only when the user explicitly invokes $adaptive-agent-routing or selects it; that invocation authorizes the root agent to decide whether subagents are worthwhile for the current task, while tiny or local work may remain single-agent. Supports adaptive routing and strict-5.6 routing.
---

# Adaptive Agent Routing

Coordinate subagents only from the root task. Keep routing explicit, capability-aware, bounded, and verifiable.

## Establish authority and mode

1. Treat the explicit `$adaptive-agent-routing` invocation or UI selection as sufficient authority for the root agent to decide whether subagents materially help in the current task. Do not require the user to repeat "use subagents", "delegate", or equivalent wording.
2. If this skill was not explicitly invoked or selected, do not activate this workflow. Continue under the normal Codex rules instead.
3. Treat a later instruction such as "do not use subagents" as overriding the invocation and keep the task in the parent.
4. If the current task is itself a spawned subagent, do not activate this workflow and do not spawn more agents. Complete the assigned leaf task or escalate to the parent.
5. Respect the user's model, effort, scope, safety, and file-ownership instructions before this skill.
6. Select the mode from the invocation:
   - Default: adaptive routing. Deep architect/reviewer roles inherit the parent model and reasoning effort exactly.
   - `strict-5.6`: prefer the exact GPT-5.6 mapping below when the runtime exposes it. Its deep-role mapping explicitly overrides the parent model and reasoning effort.

This skill applies only to the current invoked task. Do not persist its model choices into `AGENTS.md`, `config.toml`, MCP configuration, or future tasks.

## Decide whether to delegate

Classify the task before spawning:

- **Tiny/local:** a simple answer, deterministic command, known one-file edit, or mechanical check. Keep it in the parent task unless an independent check has concrete value.
- **General:** a coherent implementation or debugging bundle spanning related files or tools. Use one general worker that can inspect, act, and validate end to end.
- **Deep/high-risk:** ambiguous architecture, critical design, security-sensitive work, concurrency, migration, or final review. Use a deep architect/reviewer; inherit the parent settings in adaptive mode and apply the fixed deep mapping only in `strict-5.6` mode.
- **Parallelizable:** two or more independent read surfaces, non-overlapping implementation bundles, or distinct review dimensions. Delegate only the independent parts.

Spawn only when a worker will perform at least two valuable actions or isolate a materially different context/tool surface. Do not create scouts that merely reread the files an implementer must read. Do not split a cohesive small patch just to use more agents.

## Route by current capabilities

Read the current `spawn_agent` tool description and model catalog before choosing an override for a non-deep role or for `strict-5.6`. Prefer the runtime's current semantic model descriptions over remembered model names. Never claim that a model or effort was used unless the tool accepted it.

Use these adaptive roles:

| Role | Work | Preferred capability | Effort |
| --- | --- | --- | --- |
| Deep architect/reviewer | Architecture, critical decisions, security analysis, hard diagnosis, final review | Inherit the parent model exactly | Inherit the parent reasoning effort exactly |
| General worker | Multi-file implementation, ordinary debugging, tool-heavy work, integration | Current balanced production model; prefer Terra when exposed, then Sol | `medium` normally, `high` for complex or risky writes |
| Fast leaf | Clear, short, bounded, independently verifiable execution | Current fastest suitable leaf model; prefer Luna when exposed | **Minimum `xhigh`**; use `xhigh` by default and `max` only for short, difficult, high-value work with explicit acceptance criteria |

Apply these Luna hard boundaries:

- Never use Luna below `xhigh`.
- If Luna does not expose `xhigh` or `max`, treat Luna as unavailable and use the fallback chain.
- Use Luna only for clear leaf execution such as bounded file mapping, focused edits, exact checks, targeted evidence collection, or concise transformations.
- Do not use Luna for open-ended architecture, unknown-root-cause debugging, long-horizon planning, cross-module integration, or final synthesis.
- Instruct every Luna worker to return the blocker to the parent instead of expanding scope or delegating.

For every adaptive-mode deep architect/reviewer, including agents named `deep_review` or equivalent:

- Omit `model` and `reasoning_effort` from `spawn_agent`; do not raise, lower, or otherwise replace either parent setting.
- Use a full-history fork when the current tool requires it to guarantee model and effort inheritance.
- If the inherited values are not exposed before spawning, use the provisional inherited label described below and create the child anyway. Missing label metadata is not a reason to cancel useful delegation.

These inheritance rules apply even when a stronger deep model or higher reasoning effort is available.

### Strict GPT-5.6 mapping

When the invocation includes `strict-5.6`, use these exact preferences only when the current tool catalog exposes them. This mapping overrides adaptive-mode deep inheritance: explicitly set critical deep roles to `gpt-5.6-sol` at `max`, ignoring the parent model and reasoning effort.

| Work | Model | Effort |
| --- | --- | --- |
| Critical design, important reasoning, security, final review | `gpt-5.6-sol` | `max` |
| General implementation and normal debugging | `gpt-5.6-terra` | `medium`, or `high` for complex/risky writes |
| Clear short leaf task | `gpt-5.6-luna` | `xhigh` by default; `max` for short-and-hard work |

Do not invent unavailable slugs. Keep the task moving with an explicit fallback and report the substitution.

### Fallback chain

1. If Luna or its required `xhigh`/`max` effort is unavailable, use Terra at the lowest sufficient supported effort, normally `medium` or `high`.
2. If Terra is unavailable, use the runtime's current default general model.
3. In `strict-5.6` mode only, if Sol Max is unavailable, use the strongest exposed deep model and supported effort.
4. In adaptive mode, do not apply a model-selection fallback to deep roles; inherit the parent model and reasoning effort exactly.
5. If model overrides are unavailable for a non-deep role, inherit the parent/default model and preserve the role, scope, leaf boundary, and verification contract.

Record fallbacks for the final summary. Never silently downgrade Luna below `xhigh`.

## Label every spawned agent

Resolve the effective model and reasoning effort before each spawn. Use the explicit selected pair after capability checks or the parent's live runtime pair for an inherited deep role. Never infer the pair from a configuration default when a live turn override may differ.

For an inherited role, exhaust live parent-turn metadata before using a provisional name:

1. Read the current task's model and effort directly from runtime/app context when exposed.
2. In a local Codex CLI or desktop session, if the pair is not already in context, locate the current task's session record and read only the latest `turn_context` model and effort fields. Do not print or summarize unrelated transcript contents.
3. Treat that latest live pair as authoritative for naming, while still omitting `model` and `reasoning_effort` from the inherited `spawn_agent` call.
4. Use a provisional name only when neither live source exists or can be read. Do not block a useful spawn solely because label metadata remains unavailable.

Create both forms from the same resolved pair:

- User-visible label: `<role> (<exact-model>, <exact-effort>)`, for example `deep_review (gpt-5.6-sol, max)`.
- `task_name`: encode the same values with only lowercase letters, digits, and underscores, for example `deep_review_gpt_5_6_sol_max`. Replace every run of unsupported characters with one underscore and trim leading or trailing underscores. Add a short ordinal before the model suffix when otherwise duplicated.

When an inherited pair is not exposed before spawning:

- Do not expose `<role>_inherit_parent` as a normal task name; it is an implementation placeholder that the desktop UI renders misleadingly as if it were a mode.
- Use provisional `task_name` `<role>_runtime_pending`, for example `deep_review_runtime_pending`, and user-visible label `<role> (parent runtime pending)`. Set `MODEL_LABEL_STATUS: provisional` in the dispatch packet.
- After the spawn succeeds, inspect the child runtime/session metadata. If the exact pair becomes available, announce `<role> (<exact-model>, <exact-effort>)` in commentary and use that resolved label in all later reporting.
- Treat the spawned child's internal `task_name` as immutable. The current `spawn_agent` and collaboration surface does not expose a post-spawn rename operation, so do not claim that a corrected reporting label renamed the desktop entry. If the user explicitly requires an exact UI name, explain that satisfying it requires a replacement child created with the correct `task_name`; do not restart useful work solely for a cosmetic correction without that instruction.
- If the exact pair remains unavailable, continue the delegated work and state that the child inherits the parent but the client did not expose the resolved values. Do not guess.

The parent-generated user-visible label is authoritative. `AGENT_LABEL` is a dispatch/reporting field, not an official `spawn_agent` naming property, so a child's echoed value is advisory and cannot verify or rename the UI entry. Verify model and effort from accepted spawn parameters and live runtime metadata instead.

For a known pair, announce the user-visible label in commentary with the child's scope and set `MODEL_LABEL_STATUS: confirmed`. Put the label and status in the dispatch packet; ask the child to return it for traceability, but do not require an exact echo for success. A rejected spawn does not establish the pair; when falling back, rebuild both names from the fallback pair and announce only the successful one.

## Build bounded dispatch packets

When overriding model or reasoning effort, set `fork_turns: "none"` and make the message self-contained. Use a small positive history slice only when the tool supports it and the exact recent turns are essential. For an adaptive-mode deep role, omit both overrides and use full history to preserve exact parent inheritance. A strict-5.6 deep role is an explicit override, so use `fork_turns: "none"` and a self-contained packet.

Include this information in every worker message:

```text
LEAF EXECUTION MODE. Do not spawn agents. Do not invoke this routing skill.

AGENT_LABEL:
MODEL_LABEL_STATUS: confirmed | provisional
ROLE:
REASONING BUDGET:
OBJECTIVE:
OWNED FILES OR SURFACE:
READ-ONLY FILES OR SURFACE:
MUST READ:
FORBIDDEN ACTIONS OR PATHS:
TASKS:
DELIVERABLES:
VALIDATION:
STOP CONDITIONS:

Return:
AGENT_LABEL:
MODEL_LABEL_STATUS: confirmed | provisional
STATUS: success | partial | blocked | failed | ESCALATE_TO_PARENT
SUMMARY:
FILES_READ:
FILES_CHANGED:
VALIDATION:
EVIDENCE:
RISKS:
PARENT_ACTION:
```

Require workers to distinguish confirmed facts from hypotheses and cite files, symbols, commands, or other concrete evidence. If required context is missing or the scope must expand, require `ESCALATE_TO_PARENT` instead of guessing.

## Control ownership and parallelism

- Keep one writer per file. Never assign overlapping write scopes concurrently.
- Designate one owner for shared manifests, generated indexes, interface contracts, migrations, and other conflict-prone files.
- Parallelize independent read work and genuinely disjoint write bundles only.
- Keep dependency chains serial: discovery or design before dependent implementation, implementation before dependent final review.
- Obey the runtime thread limit. Unless a lower limit is exposed, use at most three child agents at once so the parent retains one slot.
- Continue useful parent-local work while independent children run; do not spawn a child and remain idle without reason.
- Reuse an idle completed agent for closely related follow-up work when that preserves context and ownership.

## Handle results and failures

Treat child output as evidence, not authority.

1. Wait for every child required by the current dependency stage before integrating or launching dependent work.
2. Inspect actual files, diffs, commands, test output, and cited evidence.
3. For reviews, merge duplicate findings at the same location, keep different issues separate, and calibrate severity from impact and likelihood.
4. Route a failed validation back to its implementation owner with the exact failure evidence when possible.
5. Retry a transient command, network, or worker failure once with the same bounded task.
6. On the same failure twice, diagnose and replan or escalate to a stronger model. Do not fan out more equal workers.
7. Escalate permission failures, dirty-worktree conflicts, destructive uncertainty, or missing user decisions to the parent/user.
8. Do not mark work complete until the parent verifies the acceptance criteria proportionally to risk.

## Report the routing outcome

In the final response, state only the routing facts useful to the user:

- which user-visible agent labels were used and why, and whether any remained provisional;
- which validations passed or failed;
- any model or effort fallback, especially unavailable Luna or strict-5.6 Sol Max;
- remaining risks, blockers, or user decisions.

Do not expose private reasoning, raw orchestration transcripts, or unnecessary model chatter.
