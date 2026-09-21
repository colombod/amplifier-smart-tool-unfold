"""Agent-result navigation preserves an exact draft and retained shared review state."""

import asyncio
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("playwright")
from mcp import Client
from mcp_fixtures import seed_media_library
from playwright.async_api import async_playwright, expect

from unfold.mcp import create_server

ROOT = Path(__file__).parents[1]


def test_agent_result_navigation_saves_old_draft_and_restores_view(tmp_path):
    async def run():
        library, _, revisions, artifacts = seed_media_library(tmp_path)
        old_revision, new_revision = revisions[-1], revisions[0]
        other_text = "Existing draft on the other revision"
        library.save_draft(new_revision, other_text, sequence=1)
        script = subprocess.run(
            [
                str(ROOT / "mcp-app" / "node_modules" / ".bin" / "esbuild"),
                str(ROOT / "mcp-app" / "test-host.js"),
                "--bundle",
                "--format=iife",
                "--log-level=error",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        async with Client(create_server(library)) as client, async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page(viewport={"width": 1000, "height": 1000})

            async def call(params):
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
            await page.evaluate(
                "([html,result])=>mountUnfold(html,result)",
                [
                    files("unfold").joinpath("resources/mcp_app.html").read_text(),
                    initial.model_dump(by_alias=True, exclude_none=True),
                ],
            )
            frame = page.frame_locator("#app")
            await expect(frame.locator("#feedbackTarget")).to_contain_text(old_revision[:8])
            await frame.locator("#feedbackToggle").click()
            text = "Keep this exact unfinished draft on its viewed revision"
            await frame.locator("#feedback").fill(text)
            result = await client.call_tool("unfold_inspect", {"identity": new_revision})
            await page.evaluate(
                "result=>window.unfoldBridge.sendToolResult(result)",
                result.model_dump(by_alias=True, exclude_none=True),
            )
            await expect(frame.locator("#feedbackTarget")).to_contain_text(new_revision[:8])
            await expect(frame.locator("#feedback")).to_have_value(other_text)
            drafts = {draft["revision_id"]: draft for draft in library.review_state()["drafts"]}
            assert drafts[old_revision]["text"] == text
            assert drafts[new_revision]["text"] == other_text
            await frame.locator("#scrub").fill("2")
            await frame.locator("#scrub").dispatch_event("input")
            for _ in range(50):
                views = library.review_state()["views"]
                if views and views[0]["revision_id"] == new_revision and views[0]["at"] == 2:
                    break
                await page.wait_for_timeout(100)
            view = library.review_state()["views"][0]
            assert view["revision_id"] == new_revision
            assert view["artifact_id"] == artifacts[0]
            assert view["at"] == 2
            await browser.close()

    asyncio.run(run())
