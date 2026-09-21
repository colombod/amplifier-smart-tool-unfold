import json
import os
import zipfile
from pathlib import Path

import pytest

from unfold import Unfold, UnfoldError
from unfold.store import digest, uid


@pytest.fixture
def library(tmp_path):
    return Unfold(tmp_path / "library")


def test_pack_roundtrip_and_ownership(library, tmp_path):
    original = tmp_path / "logo.png"
    original.write_bytes(b"asset fixture")
    a = library.import_asset(original, rights="redistributable")
    referenced = library.import_asset(original, mode="reference")
    pack = library.save_pack("Team", {"required": "mint", "adaptable": "pacing"}, [a["id"]])
    library.rename(a["id"], "Mark")
    assert library.asset(a["id"])["sha256"] == a["sha256"]
    with pytest.raises(UnfoldError, match="depends"):
        library.remove(a["id"])
    exported = library.export_pack(pack["current_version"], tmp_path / "team.zip")
    assert str(tmp_path) not in json.dumps(exported["manifest"])
    original.unlink()
    assert library.asset(referenced["id"])["integrity"] == "changed_or_missing"
    assert library.asset(a["id"])["integrity"] == "intact"
    fresh = Unfold(tmp_path / "fresh")
    receipt = fresh.import_pack(exported["path"])
    assert fresh.import_pack(exported["path"]) == receipt
    imported = fresh.inspect(receipt["version_id"])
    assert fresh.asset(imported["assets"][0])["name"] == "Mark"
    assert Path(fresh.asset(imported["assets"][0])["path"]).read_bytes() == b"asset fixture"
    changed = dict(exported["manifest"], name="Conflict")
    with zipfile.ZipFile(tmp_path / "conflict.zip", "w") as z:
        z.writestr("manifest.json", json.dumps(changed))
        z.writestr(changed["assets"][0]["file"], b"asset fixture")
    with pytest.raises(UnfoldError, match="different content"):
        fresh.import_pack(tmp_path / "conflict.zip")
    assert len(fresh.packs()) == 1


def test_invalid_pack_never_imports(library, tmp_path):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("something.txt", "not a pack")
    with pytest.raises(UnfoldError, match="manifest"):
        library.inspect_pack(path)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("../escaped", "no")
        z.writestr("manifest.json", "{}")
    with pytest.raises(UnfoldError, match="Unsafe"):
        library.import_pack(path)
    assert not library.assets() and not library.packs()
    assert not (tmp_path / "escaped").exists()


def seed_review(library):
    p, r = uid(), uid()
    library.store.put(
        "project",
        {"id": p, "kind": "project", "current_revision": r, "revisions": [r], "name": "Test"},
    )
    library.store.put(
        "revision", {"id": r, "kind": "revision", "project_id": p, "brief": {"duration": 10}}
    )
    return p, r


def grant():
    return {
        "provider": "gemini",
        "model": "test",
        "allow_context": True,
        "allow_frames": True,
        "vision": True,
    }


def test_review_authority_idempotency_stale_and_draft(library, monkeypatch):
    p, r = seed_review(library)
    calls = []

    class Child:
        pid = os.getpid()

        def wait(self):
            return 0

    monkeypatch.setattr(
        "unfold.review.subprocess.Popen", lambda *a, **k: calls.append(a) or Child()
    )
    library.save_draft(r, "Retained", at=2, sequence=2)
    assert library.save_draft(r, "Older", sequence=1)["text"] == "Retained"
    with pytest.raises(UnfoldError, match="authorize"):
        library.submit_refinement(r, "Change", uid())
    library.authorize_review(p, grant(), 1)
    request = uid()
    job = library.submit_refinement(r, "Change", request, at=2, end=3)
    assert library.submit_refinement(r, "Change", request, at=2, end=3)["id"] == job["id"]
    assert len(calls) == 1
    with pytest.raises(UnfoldError, match="different feedback"):
        library.submit_refinement(r, "Other", request)
    assert library.cancel_refinement(job["id"])["status"] == "cancelled"
    assert library.run_review_job(job["id"])["status"] == "cancelled"
    with pytest.raises(UnfoldError, match="allowance"):
        library.submit_refinement(r, "Again", uid())
    project = library.store.get(p)
    project["current_revision"] = uid()
    library.store.put("project", project)
    with pytest.raises(UnfoldError, match="newer revision"):
        library.submit_refinement(r, "Again", uid())
    assert library.store.get(r + "-draft")["text"] == "Retained"


def test_versions_and_omissions(library, tmp_path):
    f = tmp_path / "sound.wav"
    f.write_bytes(b"fixture")
    a = library.import_asset(f, role="audio")
    first = library.save_pack("One", {"required": "blue"}, [a["id"]])
    second = library.save_pack("One", {"required": "green"}, [], pack_id=first["id"])
    assert library.inspect(first["current_version"])["guidance"] == {"required": "blue"}
    assert second["version"]["number"] == 2
    exported = library.export_pack(first["current_version"], tmp_path / "omissions.zip")
    assert exported["manifest"]["omissions"][0]["reason"] == "unknown redistribution rights"
    assert exported["manifest"]["assets"] == []


def test_review_worker_links_result_and_target(library, monkeypatch):
    p, r = seed_review(library)
    job_id, op_id, note_id, result_id = [uid() for _ in range(4)]
    note = {
        "id": note_id,
        "kind": "feedback",
        "project_id": p,
        "revision_id": r,
        "text": "Change here",
        "status": "pending",
    }
    job = {
        "id": job_id,
        "kind": "review_job",
        "project_id": p,
        "revision_id": r,
        "text": note["text"],
        "at": 2,
        "end": 4,
        "feedback_id": note_id,
        "operation_id": op_id,
        "grant": grant(),
        "status": "queued",
    }
    library.store.put("feedback", note)
    library.store.put("review_job", job)

    def revise(base, text, g, **kwargs):
        assert kwargs["target"] == {"at": 2, "end": 4}
        assert kwargs["request_id"] == op_id
        library.store.put(
            "revision",
            {"id": result_id, "kind": "revision", "base_revision": base, "feedback": text},
        )
        return {"status": "completed", "revision_id": result_id}

    monkeypatch.setattr(library, "revise", revise)
    assert library.run_review_job(job_id)["status"] == "completed"
    assert library.inspect(note_id)["result_revision"] == result_id
    assert library.run_review_job(job_id)["status"] == "completed"


def test_removing_output_retains_source(tmp_path):
    library = Unfold(tmp_path / "lib")
    p, r = seed_review(library)
    a = uid()
    path = library.store.root / "output.mp4"
    path.write_bytes(b"video")
    revision = library.store.get(r)
    revision["artifacts"] = [a]
    library.store.put("revision", revision)
    library.store.put(
        "artifact",
        {
            "id": a,
            "kind": "artifact",
            "relative_path": "output.mp4",
            "revision_id": r,
            "sha256": digest(path),
        },
    )
    library.remove(a)
    assert library.store.get(r)["artifacts"] == []
    assert library.store.get(p)["current_revision"] == r
    assert not path.exists()


def test_failed_pack_export_does_not_publish_partial(library, tmp_path, monkeypatch):
    original = tmp_path / "a.png"
    original.write_bytes(b"bytes")
    a = library.import_asset(original, rights="redistributable")
    p = library.save_pack("Team", {}, [a["id"]])

    def fail(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(zipfile.ZipFile, "write", fail)
    with pytest.raises(OSError, match="disk failure"):
        library.export_pack(p["current_version"], tmp_path / "broken.zip")
    assert not (tmp_path / "broken.zip").exists()
    assert not list(tmp_path.glob(".unfold-*"))


def test_identity_images_are_copied_and_tampering_detected(tmp_path, monkeypatch):
    from PIL import Image

    from unfold.backend import Backend
    from unfold.models import Scene

    backend = Backend(tmp_path / "backend")
    backend.root.mkdir()
    backend.gsap.parent.mkdir(parents=True)
    backend.gsap.write_text("/* test runtime */")
    monkeypatch.setattr(backend, "require", lambda: None)
    image = tmp_path / "original.png"
    Image.new("RGBA", (20, 20), "red").save(image)
    asset_id = uid()
    scene = Scene.model_validate(
        {
            "title": "Image",
            "duration": 5,
            "explanation": "Known logo",
            "tweens": [{"target": "logo", "at": 0, "duration": 1, "opacity": 1}],
            "elements": [
                {
                    "id": "logo",
                    "kind": "image",
                    "asset_id": asset_id,
                    "x": 10,
                    "y": 10,
                    "width": 100,
                    "height": 100,
                    "opacity": 1,
                }
            ],
        }
    )
    source = tmp_path / "source"
    original_hash = backend.author(scene, source, {asset_id: image})
    image.unlink()
    assert backend.source_hash(source) == original_hash
    assert "media/" + asset_id + ".png" in (source / "index.html").read_text()
    (source / "media" / f"{asset_id}.png").write_bytes(b"changed")
    with pytest.raises(UnfoldError, match="changed"):
        backend.source_hash(source)
    with pytest.raises(UnfoldError, match="selected identity"):
        backend.author(scene, tmp_path / "unscoped", {})


def test_delivery_rejects_changed_sources_before_renderer(library, tmp_path, monkeypatch):
    p, r = seed_review(library)
    f = tmp_path / "capture.mp4"
    f.write_bytes(b"capture")
    a = library.import_asset(f, role="video", mode="reference")
    monkeypatch.setattr("unfold.delivery.media_info", lambda path: {"duration": 20, "streams": []})
    delivery = library.configure_delivery(r, a["id"], reference_start=3)
    assert delivery["reference_start"] == 3 and delivery["reference_audio"] == "excluded"
    with pytest.raises(UnfoldError, match="shorter"):
        library.configure_delivery(r, a["id"], reference_start=15)
    with pytest.raises(UnfoldError, match="depends"):
        library.remove(a["id"])
    f.write_bytes(b"changed")
    with pytest.raises(UnfoldError, match="intact"):
        library.configure_delivery(r, a["id"])
