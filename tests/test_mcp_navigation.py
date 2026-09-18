"""Agent-driven review navigation preserves an exact, not-yet-debounced draft."""

import asyncio
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("playwright")
from mcp import Client
from mcp_fixtures import seed_media_library
from playwright.async_api import async_playwright, expect

from unfold.mcp import create_server

ROOT = Path(__file__).parents[1]


def test_external_tool_result_preserves_unsaved_draft_on_exact_revision(tmp_path):
    node_modules = ROOT / "mcp-app" / "node_modules"
    if not node_modules.exists():
        pytest.skip("Run npm ci --prefix mcp-app for the independent AppBridge fixture.")
    script = subprocess.run(
        [
            str(node_modules / ".bin" / "esbuild"),
            str(ROOT / "mcp-app" / "test-host.js"),
            "--bundle",
            "--format=iife",
            "--log-level=error",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    async def run():
        library, _, revisions, _ = seed_media_library(tmp_path)
        old_revision, new_revision = revisions[-1], revisions[0]
        other_text = "Existing draft on the other revision"
        library.save_draft(new_revision, other_text, sequence=1)
        delay_next_read = False
        async with Client(create_server(library)) as client, async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page(viewport={"width": 1000, "height": 1350})
            errors, saves = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))

            async def call(params):
                nonlocal delay_next_read
                if params["name"] == "unfold_review_state" and delay_next_read:
                    delay_next_read = False
                    # Make a pending 600 ms draft timer fire during the external
                    # navigation's state read if the transition did not cancel it.
                    await asyncio.sleep(0.85)
                if params["name"] == "unfold_save_draft":
                    saves.append(params["arguments"])
                result = await client.call_tool(params["name"], params.get("arguments", {}))
                return result.model_dump(by_alias=True, exclude_none=True)

            async def read(params):
                result = await client.read_resource(params["uri"])
                return result.model_dump(by_alias=True, exclude_none=True)

            await page.expose_function("hostCall", call)
            await page.expose_function("hostRead", read)
            await page.goto("about:blank")
            await page.add_script_tag(content=script)
            initial = await client.call_tool("unfold_review_state", {})
            html = (ROOT / "src" / "unfold" / "resources" / "mcp_app.html").read_text()
            await page.evaluate(
                "([html,result])=>mountUnfold(html,result)",
                [html, initial.model_dump(by_alias=True, exclude_none=True)],
            )
            frame = page.frame_locator("#app")
            await expect(frame.locator("#notice")).to_have_text("Ready to review retained work.")
            await expect(frame.locator("#identity")).to_have_text(old_revision)

            result = await client.call_tool("unfold_inspect", {"identity": new_revision})
            text = "Keep this unfinished feedback attached to the revision I was reviewing"
            delay_next_read = True
            await frame.locator("#draft").fill(text)
            # Deliver an agent result immediately, before the normal autosave delay.
            await page.evaluate(
                "result=>window.unfoldBridge.sendToolResult(result)",
                result.model_dump(by_alias=True, exclude_none=True),
            )
            await expect(frame.locator("#identity")).to_have_text(new_revision)
            await expect(frame.locator("#draft")).to_have_value(other_text)
            await page.wait_for_timeout(750)

            drafts = {draft["revision_id"]: draft for draft in library.review_state()["drafts"]}
            assert drafts[old_revision]["text"] == text
            assert drafts[new_revision]["text"] == other_text
            assert saves and all(save["revision_id"] == old_revision for save in saves)
            assert not library.store.list("review_job")
            assert not library.store.list("operation")
            assert not errors, errors
            await browser.close()

    asyncio.run(run())
