# Optional MCP tools and collaborative review

Unfold can be used from a standard MCP client, with an optional MCP Apps review
view alongside the conversation. This is an adapter over the public Python
library. The standalone dashboard and CLI keep working without MCP installed.
The view uses the official MCP Apps SDK, bundled into the Python distribution;
using the view does not require Node, a CDN, a web server, or a private viewer URL.

## Install and configure

```sh
uv tool install "amplifier-smart-tool-unfold[mcp] @ git+https://github.com/robotdad/amplifier-smart-tool-unfold"
unfold-mcp --library /absolute/path/to/retained-library
```

Configure that executable and arguments as a **stdio** MCP server in your host.
`unfold-mcp --help` is the transport usage skill; `-h` is the short argument list.
The default permits deterministic review, feedback, pack operations and explicit
render/export operations. It **does not permit model-backed creation or refinement**.
No browser action can change this process-level permission.

For creative work, install `[smart,mcp]`, prepare the pinned renderer as described
in `unfold --help`, then configure the server with `--allow-models --backend
/absolute/path/to/prepared-backend`. Supply the chosen provider credentials in
that server's environment. Host credentials are not automatically inherited by a
remote server; no credential is collected in the view. The current native model
providers are OpenAI, Anthropic and Gemini. Model names are explicit inputs;
provider discovery, MCP sampling and MCP Tasks are not implemented here.

Every creation takes a typed `Grant` including provider/model, context and frame
disclosure, vision capability, and bounded calls/tools/renders/frames/time/bytes.
A refinement additionally requires a retained project allowance from
`unfold_authorize_review`. Saving a draft, choosing a viewed revision, playing
media, or opening a view never grants or starts model work. Limits are not a dollar
cap. These are a trusted local stdio server's capabilities, not a security sandbox
for the local user or a multi-tenant authentication layer.

On standard `ui/resource-teardown`, the App flushes unsaved feedback and review
position before acknowledging teardown, then releases its timers and media.
Closing does not submit feedback or start refinement. Abrupt host/process loss
cannot guarantee delivery of input that has not yet been saved.

## One library, two collaborators

Call `unfold_review_state` to open `ui://unfold/review`. The portable App is built
from the native dashboard document, stylesheet and controller; MCP supplies only its
transport boundary. The view and model call the same `unfold_*` tools; tools are
visible to both `model` and `app`. The host must advertise `serverTools` and
`serverResources` for previews and prepared downloads. If it cannot, the native
dashboard control remains visible and reports that concrete restriction; it never
falls back to a localhost URL. Draft text is context, never permission or instructions
to the host.

| Capability | MCP model tools | Portable view |
| --- | --- | --- |
| Projects and retained revisions | List, inspect, rename | Same project rename, Review/Library/Export navigation and revision workflow |
| Exact retained media | Info and bounded chunk reads | Same single/compare player, native controls, synchronized seek and caveat |
| Feedback | Durable per-revision drafts, whole-revision notes, interval refinement | Same drawers, exact-revision drafts/notes, existing allowance Apply and job cancellation |
| Creative library | Asset intake/metadata/removal, packs, versions and ZIP operations | Same cards, previews, pack/asset edit, copy, import/inspect, export and dependency-aware remove |
| Delivery | Delivery configuration, render and handoff | Same reference/audio/timing controls, Video/Overlay render, output preview, Save, Rename and Handoff |
| New motion project and authority | `submit_creation`, `authorize_review`, typed grant | No new creation or grant form; display cannot grant authority |

MCP does not expose a dashboard-local creation or authority form: those remain explicit
caller/model tools, and the dashboard's **Apply** consumes the existing retained
allowance rather than replacing it. Its opaque byte transport supports only selected
retained artifacts, assets and prepared pack/handoff downloads. Browser file names are
labels, not server paths. The adapter does not embed the loopback dashboard, disclose
its token, relax its authentication, or serve arbitrary files.

There is **one shared review position per retained library**, with optimistic
`expected_version` conflict checks. Concurrent viewers deliberately share it.
Drafts remain revision-bound; native monotonic sequences prevent an older save
from replacing a newer draft. Viewing another revision does not change a project's
current creative revision or spend authority. Agent-side view changes become
visible during deterministic polling; successful background polls do not add
activity notices, move focus or trigger generation.

## Work ownership and recovery

`submit_creation` and `submit_refinement` return retained job records promptly.
The public library owns the worker process, grant enforcement and receipts. Use a
32-character lowercase hexadecimal `request_id`. An exact retry returns the same
record; different inputs or an ID occupied by another object kind fail. The view
captures the complete text, interval, identity version and grant before its first
request. An uncertain response retains those immutable inputs and the same ID;
checking/retrying does not submit later typing. A separate request requires the
caller to deliberately use a new identity. The view reconciles accepted jobs through
`review_state` before retrying, without silently minting another ID.

`authorize_review` also accepts an optional retry identity. With one, it returns a
retained authorization receipt; an exact retry never refills consumed allowance.
Read `review_state` for the current remaining allowance. The portable view does not
call it from **Apply**: it uses that already-retained allowance. Poll `review_state`
for progress; do not resubmit to check progress or silently replace a failed attempt.

Other effectful library operations accept an optional `request_id`. With one,
`mutation_status` exposes the exact retained payload and completed receipt. If a
process ends after acceptance but before its receipt can be completed, the retained
outcome is explicitly pending rather than guessed from names, text, or current state.
The dashboard persists exact Comment and Apply intents before transport calls, then
acknowledges their receipts; reopening can retry an unacknowledged command without
making a same-text deliberate new comment indistinguishable from that retry.

Closing the MCP App, disconnecting stdio or switching chats does not cancel
accepted work. Use `cancel_job` and inspect the terminal job/operation outcome;
a cancellation request is not proof of cleanup. Reopening reads retained state.
Dead workers are reconciled as interrupted and never automatically replayed.
Importing an identity or reading its guidance never authorizes its execution.

## Media transport and boundaries

`unfold_media_info` returns an opaque artifact ID, byte size, MIME type, hash,
safe download name, and chunk size. Read standard resources at
`unfold://artifact/{artifact_id}/{offset}` or call `unfold_read_artifact_chunk`.
The App internally uses the same checked transfer shape for retained media,
assets (`unfold://asset/{asset_id}/{offset}`) and server-prepared pack/handoff ZIPs
(`unfold://download/{opaque_id}/{offset}`).
Each result contains at most **192 KiB** of binary data (256 KiB base64). Reads are
scoped to the requested retained artifact, with no caller-supplied filesystem path
or localhost credential-bearing URL. Offsets outside the artifact fail. The
transport refuses all symlinks and checks the complete retained SHA-256 while
capturing the chunk from the same open file descriptor. Replaced paths cannot
redirect a read; changing bytes fail the transfer. This uses POSIX descriptor
operations and is exercised on macOS; Windows support is not claimed.

The first implementation prioritizes integrity without rehashing a whole retained
file for every 192 KiB request: metadata establishes a short-lived checked
descriptor snapshot and each chunk rechecks that file's regular-file identity. The
App verifies the completed SHA-256 before assigning a blob URL. It does not render
or call a provider, and the view fetches an artifact only when it changes (not on
each poll). The view assembles at most **32 MiB** into a local blob URL and clearly
reports larger/unsupported media or missing host resource support. Use the export
tool for larger videos. This is not HTTP range streaming or a resumable
large-media protocol. Hosts should bound resource responses, preserve MIME metadata
and keep server identity/authority bound to the original connection. The view
requests no external network domains.

Browser uploads are staged in a library-owned no-follow descriptor chain. A durable
record serializes offsets, binds the regular-file device/inode, limits active uploads
and expires abandoned staging. Pack preview/import uses a bounded server-owned
snapshot of the inspected ZIP rather than reopening its staging path. Prepared
downloads and preview snapshots have finite expiry/byte limits; retained creative
work is not cleanup input. Results expose opaque IDs and safe labels only, never
staging or server paths.

Only packaged application code can request tool calls. Retained media is decoded
as media, never inserted as executable HTML. Provider credentials remain in the
server environment. The trusted model-side tools can return local paths for
explicit library/CLI operations; the view never uses them as browser URLs.

## Changelog

- **2026-09-19** — Documented the native dashboard/MCP App parity transport and
  bounded opaque transfers. This records implemented adapter behavior; it does not
  claim draft contracts are accepted product evidence.

## Verification and scope

The transport, shared-state and media checks are documented in
[the contributor instructions](../AGENTS.md#optional-mcp-adapter-verification).
Fixtures verify protocol behavior and decoded playback, not creative quality or
provider performance. Native renderer tests and packaging conformance remain
separate checks.
