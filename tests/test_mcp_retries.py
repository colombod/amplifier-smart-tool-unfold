"""The native Apply control reuses its existing allowance and exact retry identity."""

import asyncio
import os
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("playwright")
from mcp import Client
from mcp_fixtures import seed_media_library
from playwright.async_api import async_playwright, expect

from unfold import Grant
from unfold.mcp import create_server

ROOT = Path(__file__).parents[1]


def test_lost_apply_response_retries_exact_request_without_reauthorizing(tmp_path, monkeypatch):
    async def run():
        library, project, revisions, _ = seed_media_library(tmp_path)
        library.authorize_review(
            project,
            Grant(
                provider="openai",
                model="fixture",
                allow_context=True,
                allow_frames=True,
                vision=True,
            ),
        )
        monkeypatch.setattr(library.backend, "require", lambda: None)
        launches = []

        def launch(identity):
            launches.append(identity)
            job = library.store.get(identity)
            job["pid"] = os.getpid()
            library.store.put("review_job", job)
            return job

        monkeypatch.setattr(library, "_launch_review_job", launch)
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
        lost, calls = False, []
        async with (
            Client(create_server(library, allow_models=True)) as client,
            async_playwright() as pw,
        ):
            browser = await pw.chromium.launch()
            page = await browser.new_page(viewport={"width": 1180, "height": 900})

            async def call(params):
                nonlocal lost
                calls.append(params)
                result = await client.call_tool(params["name"], params.get("arguments", {}))
                if params["name"] == "unfold_submit_refinement" and not lost:
                    lost = True
                    raise RuntimeError("fixture response lost after acceptance")
                return result.model_dump(by_alias=True, exclude_none=True)

            async def read(params):
                return (await client.read_resource(params["uri"])).model_dump(
                    by_alias=True, exclude_none=True
                )

            await page.expose_function("hostCall", call)
            await page.expose_function("hostRead", read)
            await page.goto("about:blank")
            await page.add_script_tag(content=script)
            initial = await client.call_tool("unfold_review_state", {})
            html = files("unfold").joinpath("resources/mcp_app.html").read_text()
            await page.evaluate(
                "([html,result])=>mountUnfold(html,result)",
                [html, initial.model_dump(by_alias=True, exclude_none=True)],
            )
            frame = page.frame_locator("#app")
            await expect(frame.locator("#players video")).to_be_visible()
            await frame.locator("#feedbackToggle").click()
            await frame.locator("#feedback").fill("Original bounded feedback")
            await frame.locator("#apply").click()
            await expect(frame.locator("#notice")).to_contain_text("response lost")
            await frame.locator("#feedback").fill("Later typing is a distinct draft")
            await frame.locator("#apply").click()
            await expect(frame.locator("#notice")).to_contain_text("Feedback accepted")
            submitted = [
                call["arguments"] for call in calls if call["name"] == "unfold_submit_refinement"
            ]
            assert len(submitted) == 2
            assert submitted[0] == submitted[1]
            assert submitted[0]["text"] == "Original bounded feedback"
            assert len(launches) == 1
            assert not any(call["name"] == "unfold_authorize_review" for call in calls)
            assert library.review_state()["authorities"][0]["remaining"] == 0
            await browser.close()

    asyncio.run(run())


def test_lost_comment_receipt_reopens_and_replays_the_durable_exact_intent(tmp_path):
    async def run():
        library, _, _, _ = seed_media_library(tmp_path)
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
        lost = False
        async with Client(create_server(library)) as client, async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page(viewport={"width": 1180, "height": 900})

            async def call(params):
                nonlocal lost
                result = await client.call_tool(params["name"], params.get("arguments", {}))
                if params["name"] == "unfold_feedback" and not lost:
                    lost = True
                    raise RuntimeError("fixture feedback receipt lost after acceptance")
                return result.model_dump(by_alias=True, exclude_none=True)

            async def read(params):
                return (await client.read_resource(params["uri"])).model_dump(
                    by_alias=True, exclude_none=True
                )

            async def mount():
                initial = await client.call_tool("unfold_review_state", {})
                await page.evaluate(
                    "([html,result])=>mountUnfold(html,result)",
                    [
                        files("unfold").joinpath("resources/mcp_app.html").read_text(),
                        initial.model_dump(by_alias=True, exclude_none=True),
                    ],
                )
                return page.frame_locator("#app")

            await page.expose_function("hostCall", call)
            await page.expose_function("hostRead", read)
            await page.goto("about:blank")
            await page.add_script_tag(content=script)
            frame = await mount()
            await frame.locator("#feedbackToggle").click()
            await frame.locator("#feedback").fill("One durable note")
            await frame.locator("#note").click()
            await expect(frame.locator("#notice")).to_contain_text("feedback receipt lost")
            assert len(library.store.list("feedback")) == 1

            frame = await mount()
            await expect(frame.locator("#draftStatus")).to_contain_text("Pending comment retained")
            await frame.locator("#feedbackToggle").click()
            await frame.locator("#note").click()
            await expect(frame.locator("#notice")).to_contain_text("Comment retained")
            assert len(library.store.list("feedback")) == 1
            assert library.review_state()["feedback_intents"][0]["acknowledged_at"]
            # A deliberate second action with the same visible text uses a fresh
            # request identity; receipt recovery is never text-based deduplication.
            await frame.locator("#feedback").fill("One durable note, revised")
            await frame.locator("#feedback").fill("One durable note")
            await frame.locator("#note").click()
            for _ in range(30):
                if len(library.store.list("feedback")) == 2:
                    break
                await page.wait_for_timeout(100)
            assert len(library.store.list("feedback")) == 2
            await browser.close()

    asyncio.run(run())
