import { App } from "@modelcontextprotocol/ext-apps";

const app = new App({ name: "Unfold review", version: "0.1.0" });
const MAX_VIEW_BYTES = 32 * 1024 * 1024;
let connected = false;
let hostContext = {};
const objectUrls = new Map();
const mediaEntries = new Map();
let tornDown = false;

// App iframes can have an opaque sandbox origin where WebCrypto is unavailable.
// Keep verification in the client rather than silently trusting assembled chunks.
function sha256(bytes) {
  const words = [];
  const length = bytes.length;
  for (let index = 0; index < length; index++)
    words[index >> 2] = (words[index >> 2] || 0) | (bytes[index] << (24 - (index % 4) * 8));
  words[length >> 2] = (words[length >> 2] || 0) | (0x80 << (24 - (length % 4) * 8));
  words[(((length + 8) >> 6) + 1) * 16 - 1] = length * 8;
  const hash = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ];
  const constants = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];
  for (let offset = 0; offset < words.length; offset += 16) {
    const schedule = Array.from({ length: 64 }, (_, index) => words[offset + index] || 0);
    for (let index = 16; index < 64; index++) {
      const a = schedule[index - 15], b = schedule[index - 2];
      const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3);
      const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10);
      schedule[index] = (schedule[index - 16] + s0 + schedule[index - 7] + s1) | 0;
    }
    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index++) {
      const s1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
      const choice = (e & f) ^ (~e & g);
      const t1 = (h + s1 + choice + constants[index] + schedule[index]) | 0;
      const s0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
      const majority = (a & b) ^ (a & c) ^ (b & c);
      [h, g, f, e, d, c, b, a] = [g, f, e, (d + t1) | 0, c, b, a, (t1 + s0 + majority) | 0];
    }
    for (let index = 0; index < 8; index++) hash[index] = (hash[index] + [a, b, c, d, e, f, g, h][index]) | 0;
  }
  return hash.map((value) => (value >>> 0).toString(16).padStart(8, "0")).join("");
}

function resultData(result) {
  const text = result.content?.find((item) => item.type === "text")?.text || "{}";
  let data;
  try {
    data = result.structuredContent || JSON.parse(text);
  } catch {
    throw Error(text);
  }
  if (result.isError || data.error)
    {
      const error = Error(
      data.error?.message ||
        data.result?.error?.message ||
        "Unfold could not complete this request.",
      );
      error.definitive = true;
      throw error;
    }
  return data.result ?? data;
}

async function tool(name, arguments_ = {}) {
  if (!connected) throw Error("The MCP host has not connected yet.");
  return resultData(
    await app.callServerTool({ name: `unfold_${name}`, arguments: arguments_ }),
  );
}

function mergeContext(delta = {}) {
  hostContext = {
    ...hostContext,
    ...delta,
    styles: {
      ...hostContext.styles,
      ...delta.styles,
      variables: {
        ...hostContext.styles?.variables,
        ...delta.styles?.variables,
      },
    },
  };
  const mode =
    hostContext.theme === "dark" || hostContext.theme === "light"
      ? hostContext.theme
      : "light";
  document.documentElement.dataset.hostTheme = mode;
}

function opaque(path) {
  const url = new URL(path, "https://unfold.invalid");
  const parts = url.pathname.split("/").filter(Boolean);
  if (parts.length === 3 && parts[0] === "pack-preview" && /^\d+$/.test(parts[2]))
    return { kind: "pack-preview", id: parts[1], index: Number(parts[2]) };
  if (parts.length !== 2 || !["media", "asset", "download"].includes(parts[0]))
    throw Error("This view can only retrieve a retained Unfold item.");
  return { kind: parts[0], id: parts[1], index: null };
}

async function resourceUrl(path) {
  const { kind, id, index } = opaque(path);
  const cached = objectUrls.get(path);
  if (cached?.url && !cached.stale) return cached.url;
  if (cached?.pending) return cached.pending;
  if (!app.getHostCapabilities()?.serverResources)
    throw Error(
      "This host does not support MCP resource reads, so it cannot display this retained item.",
    );
  const entry = { path, refs: 0, stale: false, pending: null };
  entry.pending = (async () => {
    const info = await tool("transfer_info", { kind, identity: id, index });
    if (info.size > MAX_VIEW_BYTES)
      throw Error(
        `This retained item is ${Math.ceil(info.size / 1024 / 1024)} MiB and exceeds this App's ${MAX_VIEW_BYTES / 1024 / 1024} MiB view limit. Use the public export operation to save it.`,
      );
    const chunks = [];
    for (let offset = 0; offset < info.size; offset += info.chunk_bytes) {
      if (tornDown) throw Error("The App disconnected before media finished loading.");
      const response = await app.readServerResource({
        uri:
          kind === "pack-preview"
            ? `unfold://pack-preview/${encodeURIComponent(id)}/${index}/${offset}`
            : `unfold://${kind}/${encodeURIComponent(id)}/${offset}`,
      });
      const blob = response.contents.find((item) => typeof item.blob === "string")?.blob;
      if (blob === undefined)
        throw Error("The retained-item resource did not return binary data.");
      const bytes = Uint8Array.from(atob(blob), (value) => value.charCodeAt(0));
      if (bytes.length !== Math.min(info.chunk_bytes, info.size - offset))
        throw Error("The retained-item resource returned an incomplete chunk.");
      chunks.push(bytes);
    }
    const assembled = new Uint8Array(await new Blob(chunks).arrayBuffer());
    if (sha256(assembled) !== info.sha256)
      throw Error("Retained item integrity changed while it was transferred.");
    const url = URL.createObjectURL(new Blob(chunks, { type: info.mime_type }));
    if (objectUrls.get(path) !== entry || entry.stale || tornDown) {
      URL.revokeObjectURL(url);
      throw Error("Retained item changed before its media load completed.");
    }
    entry.url = url;
    entry.sha256 = info.sha256;
    mediaEntries.set(url, entry);
    return url;
  })();
  objectUrls.set(path, entry);
  try {
    return await entry.pending;
  } finally {
    entry.pending = null;
    if (!entry.url && objectUrls.get(path) === entry) objectUrls.delete(path);
  }
}

async function upload(file, params) {
  const opened = await tool("begin_upload", {
    name: file.name,
    kind: params.kind,
    role: params.role || null,
    size: file.size,
  });
  for (let offset = 0; offset < file.size; offset += opened.chunk_bytes) {
    const bytes = new Uint8Array(
      await file.slice(offset, offset + opened.chunk_bytes).arrayBuffer(),
    );
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    await tool("append_upload", {
      upload_id: opened.id,
      offset,
      data: btoa(binary),
    });
  }
  return tool("finish_upload", { upload_id: opened.id });
}

async function save(path, name) {
  const url = await resourceUrl(path);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
}

const capability = {
  "/state": ["review_state"],
  "/view": ["save_review_view"],
  "/draft": ["save_draft"],
  "/refine": ["submit_refinement"],
  "/feedback": ["feedback"],
  "/cancel": [
    "cancel_job",
    (body) => ({ job_id: body.job_id, request_id: body.request_id || null }),
  ],
  "/rename": [
    "rename",
    (body) => ({ identity: body.id, name: body.name, request_id: body.request_id || null }),
  ],
  "/import": ["import_upload", (body) => body],
  "/prepare": ["prepare_download", (body) => body],
};

window.unfoldTransport = {
  sharedView: true,
  async api(path, body) {
    if (path === "/call") {
      const name = body.capability.replaceAll("-", "_");
      return tool(name, body.arguments);
    }
    const entry = capability[path];
    if (!entry)
      throw Error(`The MCP dashboard transport does not support ${path}.`);
    const [name, map] = entry;
    const result = await tool(name, map ? map(body || {}) : body || {});
    if (path === "/state") this.onState?.(result);
    return result;
  },
  mediaUrl: resourceUrl,
  retainMedia(url) {
    const entry = mediaEntries.get(url);
    if (entry) entry.refs += 1;
  },
  releaseMedia(url) {
    const entry = mediaEntries.get(url);
    if (!entry) {
      URL.revokeObjectURL(url);
      return;
    }
    entry.refs = Math.max(0, entry.refs - 1);
    if (entry.stale && entry.refs === 0) {
      mediaEntries.delete(url);
      URL.revokeObjectURL(url);
    }
  },
  onState(next) {
    const valid = new Map();
    for (const artifact of next.outputs || [])
      valid.set(
        `/media/${artifact.id}`,
        artifact.integrity === "intact" ? artifact.sha256 : null,
      );
    for (const asset of next.assets || [])
      valid.set(`/asset/${asset.id}`, asset.integrity === "intact" ? asset.sha256 : null);
    for (const [path, item] of objectUrls) {
      if (!path.startsWith("/media/") && !path.startsWith("/asset/")) continue;
      if (item.pending) continue;
      if (valid.get(path) !== item.sha256) {
        item.stale = true;
        objectUrls.delete(path);
        window.unfoldInvalidateMedia?.(path);
        if (item.url && item.refs === 0) {
          mediaEntries.delete(item.url);
          URL.revokeObjectURL(item.url);
        }
      }
    }
  },
  publishContext(value) {
    if (!connected || tornDown) return;
    app.updateModelContext({ structuredContent: value }).catch(() => {});
  },
  upload,
  save,
};

app.onhostcontextchanged = (delta) => mergeContext(delta);
app.ontoolresult = async (result) => {
  if (!connected || tornDown) return;
  try {
    window.unfoldOnToolResult?.(resultData(result));
  } catch {
    // The normal controller shows only errors that apply to its current selection.
  }
};
app.onteardown = async () => {
  tornDown = true;
  window.unfoldTeardown?.();
  for (const { url } of objectUrls.values()) if (url) URL.revokeObjectURL(url);
  objectUrls.clear();
  mediaEntries.clear();
  return {};
};

await app.connect();
connected = true;
mergeContext(app.getHostContext());
await import("../src/unfold/resources/dashboard.js");