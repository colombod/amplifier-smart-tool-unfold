"""Optional loopback review adapter. Only encoded media reaches the browser."""

import json
import mimetypes
import secrets
import threading
import zipfile
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from .models import UnfoldError
from .operations import invoke
from .store import digest, uid


def media_type(path):
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if mime.startswith(("image/", "audio/", "video/", "font/")) and mime != "image/svg+xml":
        return mime
    return "application/octet-stream"


class Dashboard:
    def __init__(self, library, port=0):
        self.library = library
        self.token = secrets.token_urlsafe(32)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # Do not log viewer credentials.

            def allowed(self):
                cookies = SimpleCookie()
                try:
                    cookies.load(self.headers.get("Cookie", ""))
                    return secrets.compare_digest(cookies["unfold"].value, owner.token)
                except (KeyError, ValueError):
                    return False

            def respond(self, status, body, content_type="application/json", extra=None):
                if not isinstance(body, bytes):
                    body = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; object-src 'none'",
                )
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def valid_host(self):
                return self.headers.get("Host") == f"127.0.0.1:{owner.server.server_port}"

            def do_GET(self):
                if not self.valid_host():
                    return self.respond(403, {"error": "Invalid host"})
                parsed = urlparse(self.path)
                token = parse_qs(parsed.query).get("token", [""])[0]
                if parsed.path == "/" and token and secrets.compare_digest(token, owner.token):
                    return self.respond(
                        303,
                        b"",
                        extra={
                            "Location": "/",
                            "Set-Cookie": f"unfold={owner.token}; HttpOnly; SameSite=Strict; Path=/",
                        },
                    )
                if not self.allowed():
                    return self.respond(
                        403, {"error": "Open the dashboard URL returned by Unfold."}
                    )
                try:
                    if parsed.path == "/":
                        return self.respond(
                            200,
                            files("unfold").joinpath("resources/dashboard.html").read_bytes(),
                            "text/html; charset=utf-8",
                        )
                    if parsed.path in ("/dashboard.css", "/dashboard.js", "/theme.js"):
                        name = parsed.path.removeprefix("/")
                        return self.respond(
                            200,
                            files("unfold").joinpath("resources/" + name).read_bytes(),
                            "text/css" if name.endswith(".css") else "text/javascript",
                        )
                    if parsed.path == "/state":
                        return self.respond(
                            200,
                            library.review_state(),
                        )
                    if parsed.path.startswith("/asset/"):
                        asset = library.asset(parsed.path.removeprefix("/asset/"))
                        if asset["integrity"] != "intact":
                            raise UnfoldError("MATERIAL_CHANGED", "Asset changed or missing.")
                        safe = media_type(asset["path"])
                        return self.respond(200, Path(asset["path"]).read_bytes(), safe)
                    if parsed.path.startswith("/download/"):
                        item = library.store.get(parsed.path.removeprefix("/download/"), "download")
                        if digest(item["path"]) != item["sha256"]:
                            raise UnfoldError(
                                "MATERIAL_CHANGED", "Prepared export changed; prepare it again."
                            )
                        return self.respond(
                            200, Path(item["path"]).read_bytes(), "application/octet-stream"
                        )
                    if parsed.path.startswith("/pack-preview/"):
                        upload_id, index = parsed.path.removeprefix("/pack-preview/").split("/")
                        item = library.store.get(upload_id, "upload")
                        checked = library.inspect_pack(item["path"])
                        a = checked["manifest"]["assets"][int(index)]
                        with zipfile.ZipFile(item["path"]) as archive:
                            raw = archive.read(a["file"])
                        mime = media_type(a["file"])
                        return self.respond(200, raw, mime)
                    if parsed.path.startswith("/media/"):
                        artifact = library.artifact(parsed.path.removeprefix("/media/"))
                        if artifact["integrity"] != "intact":
                            raise UnfoldError(
                                "MATERIAL_CHANGED", "Saved output changed or is missing."
                            )
                        data = Path(artifact["path"]).read_bytes()
                        headers = {"Accept-Ranges": "bytes"}
                        if "download" in parse_qs(parsed.query):
                            headers["Content-Disposition"] = (
                                "attachment; filename*=UTF-8''" + quote(artifact["download_name"])
                            )
                        status = 200
                        if self.headers.get("Range"):
                            import re

                            match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers["Range"])
                            if not match:
                                return self.respond(416, b"")
                            start = int(match[1])
                            end = min(int(match[2]) if match[2] else len(data) - 1, len(data) - 1)
                            if start > end:
                                return self.respond(416, b"")
                            headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
                            data, status = data[start : end + 1], 206
                        return self.respond(
                            status,
                            data,
                            "video/quicktime" if artifact.get("format") == "mov" else "video/mp4",
                            headers,
                        )
                    return self.respond(404, {"error": "Not found"})
                except (UnfoldError, ValueError, OSError, IndexError, KeyError) as exc:
                    return self.respond(
                        400, {"error": exc.as_dict() if isinstance(exc, UnfoldError) else str(exc)}
                    )

            def do_POST(self):
                origin = f"http://127.0.0.1:{owner.server.server_port}"
                if (
                    not self.valid_host()
                    or not self.allowed()
                    or self.headers.get("Origin") != origin
                ):
                    return self.respond(403, {"error": "Invalid viewer origin"})
                try:
                    count = int(self.headers.get("Content-Length", "0"))
                    parsed = urlparse(self.path)
                    if parsed.path == "/upload":
                        if not 0 < count <= 256 * 1024 * 1024:
                            return self.respond(413, {"error": "Select a file up to 256 MiB."})
                        query = parse_qs(parsed.query)
                        upload_id = uid()
                        name = Path(query.get("name", ["asset.bin"])[0]).name
                        suffix = Path(name).suffix
                        if len(suffix) > 12 or not suffix.replace(".", "").isalnum():
                            suffix = ".bin"
                        path = library.store.workspace(upload_id) / ("upload" + suffix)
                        with path.open("wb") as stream:
                            remaining = count
                            while remaining:
                                block = self.rfile.read(min(1024 * 1024, remaining))
                                if not block:
                                    raise ValueError("Upload interrupted.")
                                stream.write(block)
                                remaining -= len(block)
                        if query.get("kind") == ["pack"]:
                            checked = library.inspect_pack(path)
                            library.store.put(
                                "upload",
                                {
                                    "id": upload_id,
                                    "kind": "upload",
                                    "path": str(path),
                                    "sha256": checked["sha256"],
                                },
                            )
                            return self.respond(200, {**checked, "upload_id": upload_id})
                        try:
                            asset = library.import_asset(
                                path, name=Path(name).stem, role=query.get("role", ["image"])[0]
                            )
                        finally:
                            path.unlink(missing_ok=True)
                        return self.respond(200, asset)
                    if not 0 < count <= 100000:
                        return self.respond(413, {"error": "Invalid request size"})
                    data = json.loads(self.rfile.read(count))
                    if self.path == "/import":
                        item = library.store.get(data["upload_id"], "upload")
                        result = library.import_pack(item["path"], item["sha256"])
                    elif self.path == "/call":
                        if data["capability"] not in {
                            "update-asset",
                            "save-pack",
                            "duplicate-pack",
                            "dependencies",
                            "remove",
                            "mutation-status",
                            "retain-mutation-intent",
                            "acknowledge-mutation-intent",
                            "record-draft-conflict",
                            "retain-feedback-intent",
                            "acknowledge-feedback-intent",
                            "retain-refinement-intent",
                            "acknowledge-refinement-intent",
                            "configure-delivery",
                            "render-delivery",
                        }:
                            raise ValueError("Capability is not available from the dashboard.")
                        result = invoke(library, data["capability"], data["arguments"])
                    elif self.path == "/prepare":
                        identity = uid()
                        path = library.store.workspace(identity) / "export.zip"
                        if data["kind"] == "pack":
                            result = library.export_pack(data["id"], path, data.get("request_id"))
                        elif data["kind"] == "handoff":
                            result = library.export_handoff(
                                data["id"], path, data.get("request_id")
                            )
                        else:
                            raise ValueError("Unknown export kind.")
                        library.store.put(
                            "download",
                            {
                                "id": identity,
                                "kind": "download",
                                "path": str(path),
                                "sha256": result["sha256"],
                            },
                        )
                        result = {
                            "id": identity,
                            "name": "Unfold.zip",
                            "manifest": result["manifest"],
                        }
                    elif self.path == "/feedback":
                        result = library.feedback(**data)
                    elif self.path == "/draft":
                        result = library.save_draft(**data)
                    elif self.path == "/view":
                        result = library.save_review_view(**data)
                    elif self.path == "/refine":
                        result = library.submit_refinement(**data)
                    elif self.path == "/cancel":
                        result = library.cancel_refinement(**data)
                    elif self.path == "/rename":
                        result = library.rename(data["id"], data["name"], data.get("request_id"))
                    else:
                        return self.respond(404, {"error": "Not found"})
                    return self.respond(200, result)
                except (ValueError, KeyError, TypeError, OSError, UnfoldError) as exc:
                    return self.respond(400, {"error": str(exc)})

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/?token={self.token}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
