import { App } from "@modelcontextprotocol/ext-apps";
const app = new App({ name: "Unfold review", version: "0.1.0" });
const $ = (id) => document.getElementById(id),
  id = () =>
    Array.from(crypto.getRandomValues(new Uint8Array(16)), (x) =>
      x.toString(16).padStart(2, "0"),
    ).join("");
let connected = false,
  state,
  revisionId,
  renderedRevisionId,
  artifactId,
  mediaUrl,
  mediaKey,
  viewVersion = 0,
  refreshPromise,
  busy = false,
  draftTimer,
  pollTimer,
  applyingView = false,
  draftSequence = Date.now(),
  renderedDraftSequence = -1,
  draftDirty = false,
  intentResult;
const pending = { create: null, refine: null };
const notice = (message, error = false) => {
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
};
function decode(result) {
  let data;
  const text = result.content?.find((c) => c.type === "text")?.text || "{}";
  try {
    data = result.structuredContent || JSON.parse(text);
  } catch {
    const error = Error(text);
    error.toolResponse = Boolean(result.isError);
    throw error;
  }
  if (result.isError || data.error) {
    const error = Error(
      data.error?.message ||
        data.result?.error?.message ||
        data.result?.error ||
        "The tool could not complete this request.",
    );
    error.toolResponse = true;
    throw error;
  }
  return data.result ?? data;
}
async function call(name, args = {}) {
  if (!connected) throw Error("The host has not connected yet.");
  return decode(
    await app.callServerTool({ name: "unfold_" + name, arguments: args }),
  );
}
function style(context) {
  if (context?.theme) {
    document.documentElement.dataset.theme = context.theme;
    document.documentElement.style.colorScheme = context.theme;
  }
  for (const [key, value] of Object.entries(context?.styles?.variables || {}))
    if (key.startsWith("--") && typeof value === "string")
      document.documentElement.style.setProperty(key, value);
}
function option(select, value, text) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = text;
  select.append(node);
}
function revision() {
  return state?.revisions.find((r) => r.id === revisionId);
}
function context() {
  if (!connected) return;
  app
    .updateModelContext({
      structuredContent: {
        revision_id: revisionId || null,
        artifact_id: artifactId || null,
        playback_seconds: Number($("scrub").value),
        playing: !$("video").paused,
        feedback_draft: $("draft").value.slice(0, 2000),
        feedback_draft_truncated: $("draft").value.length > 2000,
        draft_is_authority: false,
        pending_requests: Object.fromEntries(
          Object.entries(pending)
            .filter(([, value]) => value)
            .map(([kind, value]) => [
              kind,
              {
                request_id: value.payload.request_id,
                status: value.result?.status || "unconfirmed",
              },
            ]),
        ),
      },
    })
    .catch(() => {});
}
async function action(fn, message = "Saved.") {
  if (busy) return;
  busy = true;
  const controls = [...document.querySelectorAll("button, input, select")];
  for (const control of controls) control.disabled = true;
  notice("Working…");
  try {
    await fn();
    await refresh();
    notice(message);
  } catch (error) {
    try {
      await refresh();
    } catch {}
    notice(error.message, true);
  } finally {
    for (const control of controls) control.disabled = false;
    busy = false;
    requestControls();
  }
}
function numeric(name, min, max) {
  const value = Number($(name).value);
  if (!Number.isFinite(value) || value < min || value > max)
    throw Error(`${name} must be between ${min} and ${max}.`);
  return value;
}
function limit(name, min, max) {
  const value = numeric(name, min, max);
  if (!Number.isInteger(value)) throw Error(`${name} must be a whole number.`);
  return value;
}
function grant() {
  if (!$("model").value.trim())
    throw Error("Choose a vision-capable model ID in Generation grant.");
  if (!$("disclosure").checked)
    throw Error(
      "Generation requires explicit context and sampled-frame disclosure.",
    );
  return {
    provider: $("provider").value,
    model: $("model").value.trim(),
    allow_context: true,
    allow_frames: true,
    vision: true,
    max_model_calls: limit("calls", 1, 24),
    max_tool_calls: limit("tools", 1, 60),
    max_renders: limit("renders", 1, 5),
    max_frames: limit("frames", 1, 40),
    max_seconds: limit("seconds", 30, 1800),
  };
}
function target() {
  const at = numeric("at", 0, revision()?.brief.duration || 60),
    end =
      $("end").value === ""
        ? null
        : numeric("end", at, revision()?.brief.duration || 60);
  return { revision_id: revisionId, text: $("draft").value, at, end };
}
async function saveDraft() {
  clearTimeout(draftTimer);
  if (!revisionId) return;
  const args = { ...target(), sequence: ++draftSequence };
  const saved = await call("save_draft", args);
  draftSequence = Math.max(draftSequence, saved.sequence);
  if (
    saved.text !== args.text ||
    saved.at !== args.at ||
    saved.end !== args.end
  )
    throw Error(
      "A newer draft was saved elsewhere. Review it before saving another edit.",
    );
  if (
    revisionId === args.revision_id &&
    $("draft").value === args.text &&
    Number($("at").value) === args.at
  ) {
    draftDirty = false;
    renderedDraftSequence = saved.sequence;
  }
  context();
}
async function saveView() {
  if (!revisionId || applyingView) return;
  const view = await call("save_review_view", {
    revision_id: revisionId,
    artifact_id: artifactId || null,
    at: Number($("scrub").value),
    playing: !$("video").paused,
    expected_version: viewVersion,
  });
  viewVersion = view.version;
  context();
}
function clearMedia(message) {
  mediaKey = null;
  $("video").pause();
  $("video").removeAttribute("src");
  $("image").removeAttribute("src");
  $("download").hidden = true;
  $("download").removeAttribute("href");
  $("download").removeAttribute("download");
  if (mediaUrl) URL.revokeObjectURL(mediaUrl);
  mediaUrl = null;
  $("video").hidden = true;
  $("image").hidden = true;
  if (message) $("media-status").textContent = message;
}
async function media(identity) {
  if (!identity) {
    clearMedia();
    $("media-status").textContent =
      "No retained preview is available for this revision.";
    return;
  }
  const key = identity;
  if (mediaKey === key) return;
  clearMedia();
  mediaKey = key;
  $("media-status").textContent = "Loading retained media…";
  try {
    const info = await call("media_info", { artifact_id: identity });
    if (mediaKey !== key) return;
    if (info.size > 32 * 1024 * 1024)
      throw Error(
        "This preview exceeds the 32 MiB view limit. Use the export tool to save the intact media.",
      );
    if (!app.getHostCapabilities()?.serverResources)
      throw Error(
        "This host does not support MCP resource reads. The retained media is still available through Unfold export.",
      );
    const chunks = [];
    for (let offset = 0; offset < info.size; offset += info.chunk_bytes) {
      const resource = await app.readServerResource({
        uri: `unfold://artifact/${encodeURIComponent(identity)}/${offset}`,
      });
      const blob = resource.contents.find(
        (c) => typeof c.blob === "string",
      )?.blob;
      if (blob === undefined)
        throw Error("The media resource did not return binary data.");
      const bytes = Uint8Array.from(atob(blob), (c) => c.charCodeAt(0));
      if (bytes.length !== Math.min(info.chunk_bytes, info.size - offset))
        throw Error("The media resource returned an incomplete chunk.");
      chunks.push(bytes);
      if (mediaKey !== key) return;
    }
    if (mediaKey !== key) return;
    const url = URL.createObjectURL(new Blob(chunks, { type: info.mime_type }));
    if (mediaKey !== key) {
      URL.revokeObjectURL(url);
      return;
    }
    mediaUrl = url;
    $("video").pause();
    $("video").hidden = info.mime_type.startsWith("image/");
    $("image").hidden = !$("video").hidden;
    if ($("video").hidden) $("image").src = url;
    else $("video").src = url;
    $("download").href = url;
    $("download").download = info.name;
    $("download").textContent = "Download " + info.name;
    $("download").hidden = false;
    $("media-status").textContent =
      `${info.mime_type.split("/")[1].toUpperCase()} · ${(info.size / 1024).toFixed(0)} KiB · Retained preview`;
  } catch (error) {
    if (mediaKey !== key) return;
    clearMedia("No retained preview is available for this revision.");
    throw error;
  }
}
async function chooseRevision(identity, persist = false) {
  if (revisionId && revisionId !== identity && persist) {
    clearTimeout(draftTimer);
    await saveDraft();
    if (draftDirty)
      throw Error(
        "Your latest typing is still in this draft. Finish editing before switching revisions.",
      );
  }
  const changed = renderedRevisionId !== identity;
  revisionId = identity;
  renderedRevisionId = identity;
  const value = revision();
  if (!value) return;
  $("review").hidden = false;
  $("projects").value = value.project_id;
  $("revisions").replaceChildren();
  const project = state.projects.find((p) => p.id === value.project_id);
  for (const r of state.revisions.filter(
    (r) => r.project_id === value.project_id,
  ))
    option(
      $("revisions"),
      r.id,
      `Revision ${project.revisions.indexOf(r.id) + 1}${r.id === project.current_revision ? " · Current" : ""}`,
    );
  $("revisions").value = identity;
  $("identity").textContent = identity;
  $("limits").textContent =
    `${value.source_integrity === "intact" ? "Retained source intact" : "Source changed or missing; evidence may be stale"}. Preview and feedback use this exact revision.`;
  const draft = state.drafts.find((d) => d.revision_id === identity);
  if (
    changed ||
    (!draftDirty && (draft?.sequence ?? -1) > renderedDraftSequence)
  ) {
    clearTimeout(draftTimer);
    $("draft").value = draft?.text || "";
    $("at").value = draft?.at || 0;
    $("end").value = draft?.end ?? "";
    renderedDraftSequence = draft?.sequence ?? -1;
    draftSequence = Math.max(draftSequence, renderedDraftSequence);
    draftDirty = false;
  }
  if (changed) {
    $("scrub").value = 0;
    artifactId = value.resolved_artifacts?.[0]?.id;
  }
  if (!value.resolved_artifacts?.some((a) => a.id === artifactId))
    artifactId = value.resolved_artifacts?.[0]?.id;
  $("artifacts").replaceChildren();
  for (const artifact of value.resolved_artifacts || [])
    option(
      $("artifacts"),
      artifact.id,
      artifact.name + " · " + artifact.integrity,
    );
  $("artifacts").value = artifactId || "";
  $("scrub").max = value.brief?.duration || 60;
  $("details").textContent = JSON.stringify(
    {
      brief: value.brief,
      checks: value.checks,
      draft: state.drafts.find((d) => d.revision_id === identity),
      notes: state.events.filter(
        (e) => e.subject === identity && e.kind === "feedback_submitted",
      ),
    },
    null,
    2,
  );
  await media(artifactId);
  if (persist) await saveView();
  context();
}
function jobs() {
  const root = $("jobs");
  root.replaceChildren();
  root.hidden = !state.jobs.length;
  for (const job of state.jobs) {
    const row = document.createElement("div");
    row.className = "job";
    const label = document.createElement("span");
    label.textContent = `${job.mode === "create" ? "Creation" : "Refinement"} · ${job.status}${job.error ? " · " + job.error : ""}`;
    row.append(label);
    if (["queued", "running", "cancelling"].includes(job.status)) {
      const button = document.createElement("button");
      button.textContent = "Cancel";
      button.onclick = () =>
        action(
          () => call("cancel_job", { job_id: job.id }),
          "Cancellation requested; check the job status.",
        );
      row.append(button);
    }
    root.append(row);
  }
}
function refresh() {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    state = await call("review_state");
    reconcileRequests(state);
    $("projects").replaceChildren();
    for (const project of state.projects)
      option($("projects"), project.id, project.name);
    jobs();
    const chosen = $("identity-version").value;
    $("identity-version").replaceChildren();
    option($("identity-version"), "", "None");
    for (const pack of state.packs)
      for (const version of pack.versions || [pack.current_version])
        option(
          $("identity-version"),
          version,
          `${pack.name} · ${version.slice(0, 8)}`,
        );
    $("identity-version").value = chosen;
    $("library").textContent = JSON.stringify(
      {
        packs: state.packs,
        assets: state.assets.map((a) => ({
          id: a.id,
          name: a.name,
          role: a.role,
          integrity: a.integrity,
        })),
      },
      null,
      2,
    );
    const view = state.views?.find((v) =>
      state.revisions.some((r) => r.id === v.revision_id),
    );
    if (!revisionId)
      revisionId = view?.revision_id || state.projects[0]?.current_revision;
    if (revisionId) await chooseRevision(revisionId);
    if (view && view.version > viewVersion) {
      applyingView = true;
      try {
        if (view.revision_id !== revisionId) {
          await saveDraft();
          await chooseRevision(view.revision_id);
        }
        viewVersion = view.version;
        if (view.artifact_id && view.artifact_id !== artifactId) {
          artifactId = view.artifact_id;
          $("artifacts").value = artifactId;
          await media(artifactId);
        }
        $("scrub").value = view.at;
        $("position").textContent = Number(view.at).toFixed(2) + "s";
        if (!$("video").hidden) {
          $("video").currentTime = view.at;
          if (view.playing)
            await $("video")
              .play()
              .catch(() => notice("Playback needs a click in this browser."));
          else $("video").pause();
        }
      } finally {
        applyingView = false;
      }
    }
  })().finally(() => (refreshPromise = null));
  return refreshPromise;
}
$("refresh").onclick = () => action(refresh, "Up to date.");
$("projects").onchange = () =>
  action(
    () =>
      chooseRevision(
        state.projects.find((p) => p.id === $("projects").value)
          .current_revision,
        true,
      ),
    "Review position saved.",
  );
$("revisions").onchange = () =>
  action(
    () => chooseRevision($("revisions").value, true),
    "Review position saved.",
  );
$("artifacts").onchange = () =>
  action(async () => {
    artifactId = $("artifacts").value;
    await media(artifactId);
    await saveView();
  }, "Preview selected.");
$("play").onclick = () =>
  action(async () => {
    if ($("video").hidden) throw Error("Choose playable media first.");
    if ($("video").paused) await $("video").play();
    else $("video").pause();
    await saveView();
  }, "Playback updated.");
$("video").onerror = $("image").onerror = () => {
  notice(
    "This browser could not decode this retained media. Download it or use a compatible player.",
    true,
  );
};
$("video").onplay = $("video").onpause = () => {
  $("play").textContent = $("video").paused ? "Play" : "Pause";
};
$("video").onended = () => {
  if (!applyingView) saveView().catch((e) => notice(e.message, true));
};
$("video").ontimeupdate = () => {
  $("scrub").value = $("video").currentTime;
  $("position").textContent = $("video").currentTime.toFixed(2) + "s";
  $("play").textContent = $("video").paused ? "Play" : "Pause";
};
$("scrub").onchange = () =>
  action(async () => {
    $("video").currentTime = Number($("scrub").value);
    $("at").value = $("scrub").value;
    await saveView();
  }, "Review position saved.");
$("draft").oninput = () => {
  draftDirty = true;
  clearTimeout(draftTimer);
  draftTimer = setTimeout(
    () =>
      saveDraft()
        .then(() => notice("Draft saved; no work started."))
        .catch((e) => notice(e.message, true)),
    600,
  );
};
$("at").onchange = $("end").onchange = () =>
  action(saveDraft, "Draft interval saved.");
$("note").onclick = () =>
  action(
    () => call("feedback", { revision_id: revisionId, text: $("draft").value }),
    "Note recorded without generation.",
  );
function immutable(value) {
  if (value && typeof value === "object") {
    for (const child of Object.values(value)) immutable(child);
    Object.freeze(value);
  }
  return value;
}
function requestControls() {
  for (const kind of ["create", "refine"]) {
    const value = pending[kind];
    $(kind).textContent = value
      ? value.result
        ? `Check ${kind === "create" ? "creation" : "refinement"}`
        : `Check or retry ${kind === "create" ? "creation" : "refinement"}`
      : kind === "create"
        ? "Create with grant"
        : "Refine interval with grant";
    $(kind + "-new").hidden = !value;
    $(kind + "-pending").hidden = !value;
    if (value)
      $(kind + "-pending").textContent = value.result
        ? `Request ${value.result.status}. Later typing is a separate draft; choose New to submit it.`
        : "This request keeps its original text and grant. Check or retry uses the same identity; later typing is not submitted.";
  }
}
function reconcileRequests(snapshot) {
  for (const value of Object.values(pending)) {
    if (!value) continue;
    const job = snapshot.jobs.find(
      (job) => job.id === value.payload.request_id,
    );
    if (job) {
      value.result = job;
      value.uncertain = false;
    }
  }
  requestControls();
}
function outcome(value) {
  if (["failed", "interrupted", "cancelled"].includes(value.result?.status))
    throw Error(
      `The retained request is ${value.result.status}. It was not replayed. Choose New only for a separately authorized attempt.`,
    );
  return value.result;
}
async function sendRequest(kind, build) {
  // Capture ALL content and authority before the first await. Form edits made
  // while a response is pending never mutate the accepted request or a retry.
  const value = (pending[kind] ||= build());
  requestControls();
  context();
  if (value.attempted) {
    try {
      reconcileRequests(await call("review_state"));
    } catch {}
    if (value.result) return outcome(value);
  }
  value.attempted = true;
  try {
    if (value.authorization && !value.authorized) {
      await call("authorize_review", value.authorization);
      value.authorized = true;
    }
    value.result = await call(
      kind === "create" ? "submit_creation" : "submit_refinement",
      value.payload,
    );
    value.uncertain = false;
    return outcome(value);
  } catch (error) {
    value.rejected = Boolean(error.toolResponse);
    value.uncertain = !value.rejected;
    try {
      reconcileRequests(await call("review_state"));
    } catch {}
    if (value.result) return outcome(value);
    throw Error(
      value.uncertain
        ? "The response is uncertain. Check or retry reuses the original request and grant; it never submits your later edits."
        : `${error.message} The original request is retained; choose New to use revised input.`,
    );
  } finally {
    requestControls();
    context();
  }
}
async function newRequest(kind) {
  const value = pending[kind];
  if (value) {
    reconcileRequests(await call("review_state"));
    if (!value.result && !value.rejected)
      throw Error(
        "The previous request is still unconfirmed. Check or retry it before starting separate work.",
      );
  }
  pending[kind] = null;
  requestControls();
  context();
}
$("refine").onclick = () =>
  action(
    () =>
      sendRequest("refine", () => ({
        payload: immutable({
          ...target(),
          request_id: id(),
          identity_version: $("identity-version").value || null,
        }),
        authorization: immutable({
          project_id: revision().project_id,
          grant: grant(),
          refinements: 1,
          request_id: id(),
        }),
      })),
    "Refinement request confirmed. Progress remains available while you chat.",
  );
$("create").onclick = () =>
  action(
    () =>
      sendRequest("create", () => ({
        payload: immutable({
          brief: {
            title: $("title").value,
            intent: $("intent").value,
            duration: numeric("duration", 5, 60),
            identity_version: $("identity-version").value || null,
          },
          grant: grant(),
          request_id: id(),
        }),
      })),
    "Creation request confirmed. Keep chatting while owned work runs.",
  );
$("refine-new").onclick = () =>
  action(
    () => newRequest("refine"),
    "Ready for a new refinement. Your current draft is unchanged.",
  );
$("create-new").onclick = () =>
  action(
    () => newRequest("create"),
    "Ready for a new creation. Your current draft is unchanged.",
  );
app.onhostcontextchanged = style;
app.ontoolresult = async (result) => {
  intentResult = result;
  if (connected)
    try {
      const value = decode(result);
      const picked = value.kind === "revision" ? value.id : value.revision_id;
      if (picked && revisionId && picked !== revisionId) {
        clearTimeout(draftTimer);
        await saveDraft();
        if (draftDirty)
          throw Error(
            "Your latest typing is still in this draft. Finish editing before switching revisions.",
          );
      }
      await refresh();
      if (picked && picked !== revisionId) await chooseRevision(picked, true);
    } catch (e) {
      notice(e.message, true);
    }
};
app.onteardown = async () => {
  clearInterval(pollTimer);
  clearTimeout(draftTimer);
  if (mediaUrl) URL.revokeObjectURL(mediaUrl);
  return {};
};
try {
  await app.connect();
  connected = true;
  style(app.getHostContext());
  await refresh();
  notice("Ready to review retained work.");
  if (intentResult) {
    const value = decode(intentResult);
    if (value.kind === "revision" || value.revision_id) {
      await chooseRevision(value.revision_id || value.id, true);
    }
  }
  pollTimer = setInterval(() => {
    if (!busy && !document.hidden)
      refresh().catch((e) => notice(e.message, true));
  }, 5000);
} catch (error) {
  notice(error.message, true);
}
