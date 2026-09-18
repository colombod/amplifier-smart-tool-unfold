"""Lost acknowledgments never duplicate work, refill grants, or retarget later typing."""

import asyncio
import os
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


@pytest.mark.parametrize(
    "kind,loss_stage,reconcile_available",
    [
        ("create", "submit", False),
        ("refine", "submit", False),
        ("refine", "authorize", False),
        ("create", "submit", True),
        ("refine", "submit", True),
    ],
)
def test_lost_response_reuses_exact_intent_and_preserves_later_typing(
    tmp_path, monkeypatch, kind, loss_stage, reconcile_available
):
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
        library, project, revisions, _ = seed_media_library(tmp_path)
        launches = []
        monkeypatch.setattr(library.backend, "require", lambda: None)

        def launch(identity):
            launches.append(identity)
            job = library.store.get(identity)
            job["pid"] = os.getpid()  # Retained fixture job; no worker or provider is started.
            library.store.put("review_job", job)
            return job

        monkeypatch.setattr(library, "_launch_review_job", launch)
        started, release = asyncio.Event(), asyncio.Event()
        calls, lost, offline = [], False, False
        submit = "unfold_submit_creation" if kind == "create" else "unfold_submit_refinement"
        lose_name = submit if loss_stage == "submit" else "unfold_authorize_review"
        paused_name = submit if kind == "create" else "unfold_authorize_review"
        async with (
            Client(create_server(library, allow_models=True)) as client,
            async_playwright() as pw,
        ):
            browser = await pw.chromium.launch()
            page = await browser.new_page(viewport={"width": 1000, "height": 1350})

            async def call(params):
                nonlocal lost, offline
                name = params["name"]
                calls.append(params)
                if name == "unfold_review_state" and offline:
                    raise RuntimeError("Fixture temporary transport outage")
                result = await client.call_tool(name, params.get("arguments", {}))
                if name == paused_name and not started.is_set():
                    started.set()
                    await release.wait()
                if name == lose_name and not lost:
                    lost = True
                    offline = not reconcile_available
                    raise RuntimeError("Fixture response lost after acceptance")
                if name == submit:
                    offline = False
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
            html = (ROOT / "src/unfold/resources/mcp_app.html").read_text()
            await page.evaluate(
                "([html,result])=>mountUnfold(html,result)",
                [html, initial.model_dump(by_alias=True, exclude_none=True)],
            )
            frame = page.frame_locator("#app")
            await expect(frame.locator("#notice")).to_have_text("Ready to review retained work.")
            await frame.locator("#grant summary").click()
            await frame.locator("#model").fill("fixture-vision-model")
            await frame.locator("#disclosure").check()
            field = frame.locator("#intent" if kind == "create" else "#draft")
            if kind == "create":
                await frame.locator("#new summary").click()
                await frame.locator("#title").fill("Original creation")
            await field.fill("Original content")
            await frame.locator("#" + kind).click()
            await asyncio.wait_for(started.wait(), 5)
            # Textareas stay editable during the network wait. The click snapshot
            # must remain immutable, including refinement's delayed authorization.
            await field.fill("Later typing remains a draft")
            release.set()
            await expect(frame.locator("#" + kind + "-pending")).to_contain_text(
                "Request queued" if reconcile_available else "keeps its original text"
            )
            await expect(frame.locator("#" + kind)).to_be_enabled()
            assert await field.input_value() == "Later typing remains a draft"
            await frame.locator("#" + kind).click()
            await expect(frame.locator("#" + kind + "-pending")).to_contain_text("Request queued")
            assert await field.input_value() == "Later typing remains a draft"
            submissions = [c["arguments"] for c in calls if c["name"] == submit]
            expected_submits = 2 if loss_stage == "submit" and not reconcile_available else 1
            assert len(submissions) == expected_submits
            assert len({c["request_id"] for c in submissions}) == 1
            assert all(c == submissions[0] for c in submissions)
            original = submissions[0]
            assert (
                original["brief"]["intent"] if kind == "create" else original["text"]
            ) == "Original content"
            assert len(launches) == 1
            if kind == "refine":
                grants = [c["arguments"] for c in calls if c["name"] == "unfold_authorize_review"]
                assert len(grants) == (2 if loss_stage == "authorize" else 1)
                assert len({c["request_id"] for c in grants}) == 1
                assert library.review_state()["authorities"][0]["remaining"] == 0
                assert len([e for e in library.observe() if e["kind"] == "review_authorized"]) == 1
            # Clicking again is a check, even after the form was edited; no new intent.
            await frame.locator("#" + kind).click()
            await expect(frame.locator("#" + kind)).to_be_enabled()
            assert len([c for c in calls if c["name"] == submit]) == expected_submits
            assert len(launches) == 1
            # A separate request requires the explicit New action.
            old = library.store.get(launches[0])
            old["status"] = "completed"
            library.store.put("review_job", old)
            await frame.locator("#" + kind + "-new").click()
            await expect(frame.locator("#" + kind + "-pending")).to_be_hidden()
            assert await field.input_value() == "Later typing remains a draft"
            await frame.locator("#" + kind).click()
            await expect(frame.locator("#" + kind + "-pending")).to_contain_text("Request queued")
            assert len(launches) == 2 and launches[0] != launches[1]
            latest = [c["arguments"] for c in calls if c["name"] == submit][-1]
            assert (
                latest["brief"]["intent"] if kind == "create" else latest["text"]
            ) == "Later typing remains a draft"
            await browser.close()

    asyncio.run(run())
