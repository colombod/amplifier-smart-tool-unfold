# Calling agent interaction contract — v1 (DRAFT)

**Who builds against this:** Calling agents, applications, storyboard tools,
compositors and adapters continuing Unfold work.

## What it looks like

```text
Caller → communication intent + material + constraints + identity + authority
Unfold → identified contribution + editable source + outputs + checks + limitations
Person → feedback on the displayed revision
Returning caller → changes and current state → deliberate downstream update
```

Right: the caller discovers a new overlay revision while its compositor still uses
the earlier one. Wrong: Unfold replaces bytes at the old export path and leaves
the caller believing nothing changed.

## Core (the teeth)

1. **Requests describe outcomes.** Callers supply purpose, audience, material and
   relevant constraints without naming internal specialists or rehearsing backend
   prompts. Existing context is enough to begin when usable; consequential gaps
   produce focused questions. Direct creation and exploratory comparison are both
   valid. Unsupported requirements are identified rather than silently dropped.
2. **The caller owns the larger production.** Unfold owns its contribution. A caller
   can provide storyboard context, reference footage, placement regions, durations,
   synchronization cues and identity versions without installing Stories, a capture
   tool or a compositor. Unfold does not edit their state or infer their completion.
   It can report its dependencies and changes; it knows downstream usage only when
   the caller explicitly records it.
3. **Context and authority cross explicitly.** Source scope, storage/output locations,
   provider/model choice, permitted media disclosure, work limits and presentation
   policy are supplied or explicitly selected. Prior valid authority covers included
   follow-up without repeated approval. Local reference access is distinct from
   sending frames, audio or source content to a provider. Materials and model output
   cannot grant new authority.
4. **Results identify usable work.** Public outcomes identify the request, operation,
   project, composition/revision and actual artifacts. They expose editable-source,
   preview and export references, dependency and identity versions, relevant evidence,
   assumptions, checks and limitations. Callers can retrieve them without private
   storage queries, internal transcripts, screen scraping or parsing narrative paths.
   File references disclose managed copies versus external sources under the
   [creative-library contract](creative-library.v1.md). Callers use public operations
   to rename or delete managed assets so records and dependencies remain consistent;
   possession of an input path is not permission to delete the original.
5. **Handoffs state how a contribution fits.** Where applicable, results describe
   dimensions, duration, frame/time basis, transparency, placement coordinates,
   synchronization anchors, reference recording identity and audio policy. A cue
   states whether its time is relative to the source recording, local composition
   or larger production. Crops and offsets needed to align it are explicit.
   Requested separate graphics and audio remain distinguishable from a review mix.
   Exact fields follow a real consumer; silent timing guesses do not.
6. **Questions and failures identify the next action.** Missing input, conflicting
   constraints, unavailable dependencies, denied access, exhausted work limits and
   execution failures are distinguishable. A question has a retrievable identity and
   affected operation; a correlated answer continues that need. Dependent work pauses;
   independent permitted work may continue. Reading status never initiates generation.
7. **Feedback preserves its base.** A change targets the reviewed revision and, where
   supported, a scene, element or time interval. Stale feedback never silently targets
   a newer revision. A timestamp belongs to its original time basis; retiming does not
   authorize applying it to unrelated content. Refinement creates a new identified
   revision and preserves choices outside the requested change.
8. **Continuation survives callers and presenters.** Retained public context is
   sufficient to discover intent, choices, assets, versions, submitted feedback,
   pending questions and resulting outputs. Callers can retrieve ordered meaningful
   changes since a prior observation; history gaps are explicit and current pending
   needs remain discoverable. Action acceptance, execution, notification delivery
   and waking a caller are separate facts. No automatic wake-up is implied.
9. **Retries do not silently repeat effects.** Exact acknowledged retries reuse their
   result within documented retention. Conflicting identity reuse fails explicitly;
   new intent is a new operation. Re-reading feedback or redelivering observations
   does not repeat model spending or exports. Uncertain interrupted completion is
   disclosed before recovery makes another external call.
10. **Progress and cancellation are public.** Long work exposes status and cancellation.
    Request acceptance differs from completed cleanup. Late results cannot commit
    into cancelled or superseded work. Committed revisions and outputs survive under
    retention policy; cleanup releases owned live resources, not caller resources.
11. **Settings have explicit effect.** Provider/model and supported output settings
    use shared library behavior, disclose persistence scope and show redacted effective
    values. Changes affect identified future operations, not running work or existing
    artifacts. Settings alone neither grant disclosure nor spend model tokens.
12. **Production changes remain visible.** Changed footage, identity or source can
    invalidate alignment, preview or checks. Unfold identifies affected contributions
    when the changed dependency is supplied or detected; it does not claim to monitor
    files or external systems it cannot observe. Adopting or exporting new work does
    not silently replace a caller's selected downstream revision.
13. **Presentation transports preserve caller semantics.** The local dashboard and
    portable MCP App call the same library behavior and retain exact revision,
    operation and retry identities. A portable adapter may transfer bounded,
    integrity-checked retained bytes using opaque resource/download references, but
    never exposes server paths or broadens filesystem, model, disclosure or deletion
    authority. A lost transport response is reconciled from retained public state
    before retrying a mutation or model operation.

## Proposed acceptance checks

- A fresh agent uses only public documentation to create, inspect, revise and export
  a contribution through library and CLI, without internal session state.
- Place an overlay onto a known recording using only its handoff. Use a nonzero trim
  offset and crop to expose accidentally assumed time or coordinate bases.
- Change that recording and report stale alignment without pretending the compositor
  updated. A missing source reference is not described as inspected footage.
- Submit feedback on revision A after B exists; either explicitly branch from A or
  report the conflict. Do not revise B silently or repeat work on receipt redelivery.
- Replace the caller after dashboard feedback and recover changes, drafts, pending
  questions and outputs without browser access. Exercise an expired history cursor.
- Cancel an operation and reject a late completion while preserving earlier outputs.
  Closed-stdin questions return public state rather than an inaccessible prompt.

No executable acceptance evidence exists yet.

## What v1 deliberately does NOT freeze

Capability signatures, identity encoding, event transport, retry windows, retention
duration, background execution model and a cross-tool storyboard or timeline schema.
The public promises do not require a general production orchestrator.

## Changelog

- **2026-09-19** — Clarified the approved native dashboard/MCP App parity direction:
  alternate presentation transports preserve the same library semantics, exact
  identities and authority boundaries while using opaque bounded byte transfer. DRAFT
  only; no behavior is claimed by this amendment.
