"""Opaque MCP staging is confined, serialized, and never returns server paths."""

import asyncio
import base64

import pytest

pytest.importorskip("mcp")
from mcp import Client

from unfold import Unfold
from unfold.mcp import create_server


def test_mcp_upload_rejects_symlink_replacement_and_preserves_outside_file(tmp_path):
    async def run():
        library = Unfold(tmp_path / "library")
        outside = tmp_path / "outside"
        outside.write_bytes(b"private")
        async with Client(create_server(library)) as client:
            opened = await client.call_tool(
                "unfold_begin_upload",
                {"name": "mint.png", "kind": "asset", "role": "image", "size": 1},
            )
            upload_id = opened.structured_content["id"]
            record = library.store.get(upload_id, "mcp_upload")
            staged = library.store.root / record["relative_path"]
            staged.unlink()
            staged.symlink_to(outside)
            append = await client.call_tool(
                "unfold_append_upload",
                {
                    "upload_id": upload_id,
                    "offset": 0,
                    "data": base64.b64encode(b"X").decode(),
                },
            )
            assert append.is_error
            assert append.structured_content["error"]["code"] == "MATERIAL_CHANGED"
            assert outside.read_bytes() == b"private"

    asyncio.run(run())


def test_mcp_upload_serializes_same_offset_retry_and_preserves_png_metadata(tmp_path):
    async def run():
        library = Unfold(tmp_path / "library")
        async with (
            Client(create_server(library)) as first,
            Client(create_server(library)) as second,
        ):
            opened = await first.call_tool(
                "unfold_begin_upload",
                {"name": "mint.png", "kind": "asset", "role": "image", "size": 1},
            )
            upload_id = opened.structured_content["id"]
            payload = {
                "upload_id": upload_id,
                "offset": 0,
                "data": base64.b64encode(b"x").decode(),
            }
            one, two = await asyncio.gather(
                first.call_tool("unfold_append_upload", payload),
                second.call_tool("unfold_append_upload", payload),
            )
            assert not one.is_error and not two.is_error
            finished = await first.call_tool("unfold_finish_upload", {"upload_id": upload_id})
            assert not finished.is_error
            asset = library.asset(finished.structured_content["id"])
            assert asset["bytes"] == 1
            assert asset["suffix"] == ".png"
            assert asset["mime"] == "image/png"
            assert "path" not in finished.structured_content
            assert "relative_path" not in finished.structured_content

    asyncio.run(run())


def test_mcp_finish_recovers_a_crash_after_asset_effect_without_duplicate_import(
    tmp_path, monkeypatch
):
    async def run():
        library = Unfold(tmp_path / "library")
        original = library.import_staged_asset
        interrupted = True

        def crash_after_effect(*args, **kwargs):
            nonlocal interrupted
            result = original(*args, **kwargs)
            if interrupted:
                interrupted = False
                from unfold import UnfoldError

                raise UnfoldError("INTERRUPTED", "Fixture stopped after durable promotion.")
            return result

        monkeypatch.setattr(library, "import_staged_asset", crash_after_effect)
        async with Client(create_server(library)) as client:
            opened = await client.call_tool(
                "unfold_begin_upload",
                {"name": "once.png", "kind": "asset", "role": "image", "size": 1},
            )
            upload_id = opened.structured_content["id"]
            await client.call_tool(
                "unfold_append_upload",
                {
                    "upload_id": upload_id,
                    "offset": 0,
                    "data": base64.b64encode(b"x").decode(),
                },
            )
            first = await client.call_tool("unfold_finish_upload", {"upload_id": upload_id})
            assert first.is_error
            pending = library.store.get(upload_id, "mcp_upload")
            assert pending["status"] == "finishing"
            assert len(library.store.list("asset")) == 1
            retry = await client.call_tool("unfold_finish_upload", {"upload_id": upload_id})
            assert not retry.is_error, retry.content
            assert retry.structured_content["id"] == pending["result_id"]
            assert len(library.store.list("asset")) == 1
            assert library.store.get(upload_id, "mcp_upload")["status"] == "finished"

    asyncio.run(run())
