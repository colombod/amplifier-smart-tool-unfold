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

## One library, two collaborators

Call `unfold_review_state` to open `ui://unfold/review`. The view and model call the
same `unfold_*` tools; tools are visible to both `model` and `app`. The host must
advertise `serverTools`, `serverResources` (for playable previews), and
`updateModelContext`. The UI publishes bounded context with the viewed revision,
artifact, playback position and up to 2,000 characters of the feedback draft.
Draft text is context, never permission or instructions to the host.

| Capability | MCP model tools | Portable view |
| --- | --- | --- |
| Projects and retained revisions | List, inspect, rename | Choose project/revision, inspect evidence |
| Exact retained media | Info and bounded chunk reads | Video/image/audio preview, play/pause, seek, download |
| Shared review position | `save_review_view`, expected version | Same state; quiet five-second refresh |
| Feedback | Durable per-revision drafts, whole-revision notes, interval refinement | Same actions and interval inputs |
| New motion project | `submit_creation` with full typed Brief/Grant | Title, intent, duration, optional identity version and grant |
| Owned work | Accept, inspect, cancel | Retained progress and cancellation control |
| Creative library | Assets/packs inspection, pack save/duplicate/import/export, dependencies | Read-only library and identity-version choices |
| Delivery | Explicit render and artifact export | Download retained preview bytes |

The MCP subset does not yet expose asset import/removal, delivery configuration,
transparent-overlay handoff, side-by-side comparison, or all standalone dashboard
controls. Use the existing public library/CLI/dashboard for those features. No
native dashboard is embedded or its authentication relaxed. This focused view is
not a claim that the draft product vision/contracts are complete.

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
explicit **New creation** or **New refinement** action. The view reconciles accepted
jobs through `review_state` before retrying, without silently minting another ID.

`authorize_review` also accepts an optional retry identity. With one, it returns a
retained authorization receipt; an exact retry never refills consumed allowance.
Read `review_state` for the current remaining allowance. Without a retry identity,
existing local callers retain the original deliberate allowance-replacement
behavior. The portable view always supplies an authorization retry identity.
Poll `review_state` for progress; do not resubmit to check progress or silently
replace a failed attempt.

Closing the MCP App, disconnecting stdio or switching chats does not cancel
accepted work. Use `cancel_job` and inspect the terminal job/operation outcome;
a cancellation request is not proof of cleanup. Reopening reads retained state.
Dead workers are reconciled as interrupted and never automatically replayed.
Importing an identity or reading its guidance never authorizes its execution.

## Media transport and boundaries

`unfold_media_info` returns an opaque artifact ID, byte size, MIME type, hash,
safe download name, and chunk size. Read standard resources at
`unfold://artifact/{artifact_id}/{offset}` or call `unfold_read_artifact_chunk`.
Each result contains at most **192 KiB** of binary data (256 KiB base64). Reads are
scoped to the requested retained artifact, with no caller-supplied filesystem path
or localhost credential-bearing URL. Offsets outside the artifact fail. The
transport refuses all symlinks and checks the complete retained SHA-256 while
capturing the chunk from the same open file descriptor. Replaced paths cannot
redirect a read; changing bytes fail the transfer. This uses POSIX descriptor
operations and is exercised on macOS; Windows support is not claimed.

The first implementation prioritizes integrity: each chunk request hashes the
whole file once. It does not render or call a provider, and the view fetches an
artifact only when it changes (not on each poll). The view assembles at most
**32 MiB** into a local blob URL and clearly reports larger/unsupported media or
missing host resource support. Use the export tool for larger videos. This is not
HTTP range streaming or a resumable large-media protocol. Hosts should bound
resource responses, preserve MIME metadata and keep server identity/authority
bound to the original connection. The view requests no external network domains.

Only packaged application code can request tool calls. Retained media is decoded
as media, never inserted as executable HTML. Provider credentials remain in the
server environment. The trusted model-side tools can return local paths for
explicit library/CLI operations; the view never uses them as browser URLs.

## Verification and scope

The transport, shared-state and media checks are documented in
[the contributor instructions](../AGENTS.md#optional-mcp-adapter-verification).
Fixtures verify protocol behavior and decoded playback, not creative quality or
provider performance. Native renderer tests and packaging conformance remain
separate checks.
