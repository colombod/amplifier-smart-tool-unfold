# Review dashboard contract — v1 (DRAFT)

**Who builds against this:** People reviewing animations and managing their creative
library, calling agents and authors of Unfold presentation adapters.

## What it looks like

```text
Headless creation → open that revision → play/scrub/compare
Person selects a scene or interval → submits feedback → identified receipt
Authorized refinement → new revision available → caller observes what changed
Person selects an identity or export → the same library-owned behavior
```

Right: a comment remains attached to the scene and revision the person reviewed.
Wrong: background regeneration changes the displayed work beneath an unfinished
comment and applies it to a different moment.

## Core (the teeth)

1. **The dashboard is optional to use and built into the intended product.** Callers
   can select it, use their own UI or work headlessly. Its capabilities come from
   the library. Opening existing work does not require regeneration, conversation
   replay or model credentials. A full timeline editor is not a prerequisite.
2. **Presentation has an explicit lifecycle.** Selecting the dashboard with service
   authority can start or reuse its service without asking again for every revision.
   Opening a browser and taking focus follow separately supplied scope, which may
   be granted together. The initial service is local and access-controlled; ordinary
   generation does not expose it to a network. Optional presentation failure leaves
   artifacts and public controls usable with the limitation reported.
3. **The visible revision is identified.** Previews, playback, comparisons, comments,
   checks and export target the shown revision. Earlier versions remain accessible
   under retention policy. A storyboard, approximate draft, authored-timeline preview
   and encoded output are distinguished. The UI exposes relevant preview limits
   and failed/missing media rather than treating a blank canvas as success.
4. **Review accommodates motion.** People can play, pause and scrub the supported
   sequence, inspect relevant frames and hear included audio. Where footage is used
   as reference, contextual preview identifies it and makes delivery inclusion clear.
   Comparing approaches or revisions preserves the relevant comparison context;
   equal timestamps are not falsely described as equivalent beats after retiming.
5. **Feedback is targeted and durable.** Whole-composition feedback is supported;
   finer scene, interval and element targeting is exposed only at supported precision.
   Each target retains its revision and time basis. Saved drafts are visibly
   unsubmitted. Submission has an identified receipt before acceptance is shown.
   Stale or ambiguous targets produce an explicit resolution, not silent retargeting.
6. **Internal intelligence can handle submitted feedback.** Within existing authority,
   Unfold may interpret a submitted comment as a question, explanation request or
   refinement without a separate caller round trip. Otherwise it exposes the pending
   need. Draft saving, viewing and event redelivery never initiate model work.
   Comments, responses, operations and resulting revisions are connected through
   public state so a returning caller knows what happened.
7. **Updates preserve the person's work.** New revisions become available without
   discarding unfinished typing, saved drafts, selection or review position. The
   UI distinguishes unsaved input, accepted feedback, running work and completion.
   The person can continue reviewing while permitted work runs; selecting the new
   revision is distinct from receiving a notification about it.
8. **People and agents share observations.** Submitted feedback, answered questions,
   selections, adopted source changes and output references are retrievable through
   the same public boundary. Callers can attach review notes for the person as well.
   Annotations remain separate from composition content and exported media unless
   explicitly incorporated by an edit. Recording an action does not promise to wake
   the caller or notify another application.
9. **Creative-library management is part of participation.** People can browse,
   organize, rename, preview, reopen, duplicate, import/export and deliberately remove
   supported work and identities, with the dependency behavior of the
   [creative-library contract](creative-library.v1.md). Project identity selection
   names a version. ZIP import and shared updates do not silently replace selections.
10. **Settings and export use shared semantics.** Provider/model and supported output
    settings are redacted, scoped and library-owned. Changing a setting neither spends
    tokens nor mutates running work. Export delivers the selected identified revision
    and declared format; downloading an existing export requires no model. Rendering
    a new output is distinguishable from retrieving an existing file. Unsubmitted
    feedback is never implicitly applied by export.
11. **Closing, stopping and retaining are different.** Closing a tab disconnects the
    viewer, not necessarily the service or operation. Public stop/cancel behavior
    reports actual cleanup of owned live resources and preserves retained work.
    Stale viewer submissions cannot bypass a stopped or superseded operation.
    Later continuation reopens retained work explicitly within current authority.
12. **Composition content has no dashboard authority.** Generated or imported content
    remains isolated from credentials, library control APIs and unrelated projects.
    A simulated button inside an animation is not a user instruction to Unfold.
    Render errors and blocked resources are not human selections or approval.
13. **The portable MCP App is the dashboard over another transport, not a second
    product surface.** It starts from the same native document, styles and presentation
    controller as the loopback dashboard. At equivalent inner viewport, selection,
    retained library and theme, it exposes the same layout, controls, labels,
    responsive behavior and library-owned workflow: project rename; Review, Library
    and Export navigation; single/compare review; drafts, notes, jobs and cancellation;
    packs, assets, delivery and retained outputs. The transport boundary may report a
    concrete host capability failure (for example, unavailable MCP resource reads);
    it must not silently replace the interaction with a reduced page, a placeholder or
    a new authority/grant form. Creation and authorization remain callable public
    operations, not dashboard controls, and displaying work never grants authority.
14. **Portable bytes remain scoped and explicit.** The MCP presentation transfers only
    bounded, integrity-checked retained artifacts, assets, inspected pack previews and
    prepared downloads through opaque references. Browser filenames are labels, never
    server paths. It does not expose a loopback URL, arbitrary filesystem reads,
    symlink redirects or a relaxed dashboard authentication policy. A documented view
    size limit is a presentation limitation, not a claim about every host.

## Proposed acceptance checks

- Open a headless result directly in the dashboard with the same revision, assets
  and checks; repeat with no model credentials and no original caller session.
- Play/scrub a real animation and review included sound. Compare the contextual
  preview with the actual separate overlay/combined-video export selected.
- Save a draft, submit targeted feedback and receive a new revision while typing
  another comment. Preserve position and input, and retrieve the outcomes from CLI.
- Send a caller note into the review workspace and retrieve a user reply. Confirm
  annotations do not appear in exported frames or cause work when merely read.
- Exercise a stale comment after retiming, a failed save, repeated submission and
  reconnect with missing event history. Pending needs remain visible.
- Manage identity versions and ZIP exchange through UI and library with matching
  effects. Verify dependency-aware removal and exact-revision export.
- Render the same populated deterministic library through the native dashboard and an
  independent official AppBridge at desktop and narrow viewport under Light, Dark and
  System/partial host-context updates. Compare native DOM/control inventory, computed
  palette, geometry and pinned-media screenshots. Exercise each visible library,
  delivery and output operation through the shared public state and byte checks.
- Exercise an MCP host without the required resource capability and a retained item
  above the documented view limit. Each must identify the actual blocked operation
  while preserving selection/drafts and without supplying a localhost fallback.
- Stop owned resources without deleting retained work or stopping unrelated host
  services; reject stale submissions and reopen deliberately.

No UI or executable acceptance evidence exists yet. Screenshots, HTTP success and
rendered thumbnails alone do not establish these interaction promises.

## What v1 deliberately does NOT freeze

Framework, layout, annotation mechanism, visual element selector scheme, polling
versus events, player implementation and service process model. Support for remote
collaborative editing or a complete nonlinear editor is not implied.

## Changelog

- **2026-09-19** — Added the approved exact native dashboard/MCP App parity direction:
  one canonical presentation and controller with a small transport boundary, full
  existing dashboard workflow, no display-originated authority, and bounded opaque
  portable byte transfer. This is a DRAFT direction update, not a lock or an
  implementation acceptance claim.
