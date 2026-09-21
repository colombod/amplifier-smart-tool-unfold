import os
from pathlib import Path

import pytest
from PIL import Image

from unfold.backend import Backend, geometry
from unfold.models import Element, Scene


def vector(**kwargs):
    return Element(
        id="v",
        kind="path",
        x=0,
        y=0,
        width=1280,
        height=720,
        points=[(200, 500), (300, 300)],
        color="#b59aff",
        opacity=1,
        arrow_end=True,
        **kwargs,
    )


def test_geometry_is_numeric_svg_and_rejects_invalid_vectors():
    shape = geometry(vector())
    assert "M 200.0 500.0 L 300.0 300.0" in shape
    assert 'class="head"' in shape
    for points in ([(0, 0)], [(0, 0), (0, 0)], [(0, 0), (float("nan"), 5)], [(0, 0), (1300, 20)]):
        data = vector().model_dump()
        data["points"] = points
        with pytest.raises(ValueError):
            Element.model_validate(data)
    with pytest.raises(ValueError):
        vector(closed=True)


def test_draw_progress_cannot_target_a_text_box():
    with pytest.raises(ValueError, match="Drawing progress"):
        Scene(
            title="Wrong target",
            duration=5,
            explanation="invalid",
            elements=[Element(id="label", kind="text", x=0, y=0, width=100, height=50, text="v")],
            tweens=[dict(target="label", at=0, duration=1, draw=1)],
        )


def test_camera_timing_and_circular_arc():
    arc = Element(id="arc", kind="arc", x=0, y=0, width=204, height=204,
                  start_angle=0, sweep_angle=90, stroke_width=4)
    assert 'A 100.0 100.0 0 0 1' in geometry(arc)
    with pytest.raises(ValueError):
        Element.model_validate({**arc.model_dump(), "sweep_angle": 360})
    with pytest.raises(ValueError, match="Camera moves"):
        Scene(title="Invalid camera", duration=5, explanation="Overlap",
              elements=[arc], tweens=[dict(target="arc", at=0, draw=1)],
              camera=[dict(at=0, duration=3, center_x=100, center_y=100, zoom=2),
                      dict(at=2, duration=1, center_x=200, center_y=200, zoom=1)])


@pytest.mark.skipif(not os.environ.get("UNFOLD_TEST_BACKEND"), reason="Needs renderer")
def test_encoded_camera_centers_world_and_preserves_circle(tmp_path):
    backend = Backend(os.environ["UNFOLD_TEST_BACKEND"])
    scene = Scene(title="Camera test", duration=5, explanation="Zoom then pull back",
                  elements=[Element(id="ring", kind="arc", x=200, y=200,
                                    width=204, height=204, stroke_width=4,
                                    start_angle=0, sweep_angle=270,
                                    color="#f0c76e", opacity=1)],
                  tweens=[dict(target="ring", at=0, opacity=1)],
                  camera=[dict(at=0, duration=0, center_x=302, center_y=302, zoom=2),
                          dict(at=1, duration=1, center_x=640, center_y=360, zoom=1)])
    source = tmp_path / "source"
    backend.author(scene, source)
    backend.render(source, tmp_path / "camera.mp4")
    frames = backend.frames(tmp_path / "camera.mp4", [0.5, 3], tmp_path / "frames")
    close, wide = [Image.open(f["path"]).convert("RGB") for f in frames]
    def gold(image, x, y):
        return max(abs(a-b) for a,b in zip(image.getpixel((x,y)), (240,199,110))) < 40
    assert gold(close, 840, 360)  # rightmost radius at 2x
    assert gold(close, 640, 560)  # same vertical radius: no ellipse
    assert gold(wide, 402, 302)   # original world coordinates after pullback
    assert gold(wide, 302, 402)


@pytest.mark.skipif(not os.environ.get("UNFOLD_TEST_BACKEND"), reason="Needs renderer")
def test_partial_arc_reveals_only_the_completed_stroke(tmp_path):
    backend = Backend(os.environ["UNFOLD_TEST_BACKEND"])
    scene = Scene(title="Progressive arc", duration=5, explanation="Half at t=2",
                  stroke_animation="svg",
                  elements=[Element(id="arc", kind="arc", x=200, y=200, width=404,
                                    height=404, stroke_width=4, start_angle=0,
                                    sweep_angle=180, color="#f0c76e", opacity=1, draw=0,
                                    glow_tip=True)],
                  tweens=[dict(target="arc", at=1, duration=2, draw=1, ease="none")])
    source = tmp_path / "source"
    backend.author(scene, source)
    backend.render(source, tmp_path / "video.mp4")
    frame = backend.frames(tmp_path / "video.mp4", [2], tmp_path / "frames")[0]
    image = Image.open(frame["path"]).convert("RGB")
    # At halfway, the 45-degree point is drawn; 135 degrees is still background.
    assert sum(image.getpixel((543, 543))) > 250
    assert sum(image.getpixel((261, 543))) < 100
    # The bright tip is attached to the exact 90-degree endpoint at halfway.
    assert min(image.getpixel((402, 602))) > 200


@pytest.mark.skipif(
    not os.environ.get("UNFOLD_TEST_BACKEND"),
    reason="Requires explicit pinned renderer installation",
)
def test_encoded_vector_draw_and_rigid_translation(tmp_path):
    backend = Backend(os.environ["UNFOLD_TEST_BACKEND"])
    u = vector().model_copy(
        update={"id": "u", "points": [(200, 500), (500, 400)], "color": "#f0c76e", "draw": 0}
    )
    scene = Scene(
        title="Geometric renderer test",
        duration=5,
        explanation="Vector v translates by (300,-100), u draws.",
        elements=[
            u,
            vector(),
            Element(
                id="point",
                kind="circle",
                x=800,
                y=250,
                width=60,
                height=60,
                opacity=1,
                fill="#f0c76e",
                color="#f0c76e",
                fill_opacity=1,
            ),
        ],
        tweens=[
            dict(target="u", at=0, duration=1, draw=1, ease="none"),
            dict(target="v", at=1, duration=1, x=300, y=-100, ease="none"),
        ],
    )
    source = tmp_path / "source"
    backend.author(scene, source)
    metadata = backend.render(source, tmp_path / "video.mp4")
    frames = backend.frames(tmp_path / "video.mp4", [0.1, 2.5], tmp_path / "frames")
    before, after = [Image.open(Path(f["path"])).convert("RGB") for f in frames]

    def near(pixel, expected):
        return max(abs(a - b) for a, b in zip(pixel, expected)) < 35

    assert near(before.getpixel((250, 400)), (181, 154, 255))
    assert near(after.getpixel((550, 300)), (181, 154, 255))
    assert near(after.getpixel((250, 400)), (8, 19, 31))
    assert near(before.getpixel((350, 450)), (8, 19, 31))
    assert near(after.getpixel((350, 450)), (240, 199, 110))
    assert near(after.getpixel((830, 280)), (240, 199, 110))
    assert metadata["duration"] == 5


def orbital(**kwargs):
    return Element(id="orbit", kind="path", x=300, y=100, width=440, height=440,
                   closed=True, opacity=1, color="#ffffff",
                   orbit=dict(center=[220,220], radius=180, angles=[0,80,190,270],
                              marker_radius=5), **kwargs)


def test_orbit_validation_and_static_geometry():
    e = orbital()
    assert geometry(e).count('class="orbit-marker"') == 4
    for update in [dict(points=[(0,0),(10,10),(0,10)]), dict(closed=False),
                   dict(kind="circle"), dict(orbit=dict(center=[20,20],radius=180,
                                                      angles=[0,90,180]))]:
        with pytest.raises(ValueError):
            Element.model_validate({**e.model_dump(), **update})
    for tweens in [[dict(target="orbit", at=0, orbit_angles=[0,90,180])],
                   [dict(target="orbit", at=0, duration=2, orbit_angles=[0,90,180,270]),
                    dict(target="orbit", at=1, duration=2, orbit_angles=[45,135,225,315])]]:
        with pytest.raises(ValueError):
            Scene(title="Invalid", duration=5, explanation="Invalid orbit",
                  elements=[e], tweens=tweens)
    with pytest.raises(ValueError, match="orbit path"):
        Scene(title="Invalid", duration=5, explanation="Invalid target", elements=[vector()],
              tweens=[dict(target="v", at=0, orbit_angles=[0,90,180])])


@pytest.mark.skipif(not os.environ.get("UNFOLD_TEST_BACKEND"), reason="Needs renderer")
def test_encoded_independent_orbit_corners_and_outline(tmp_path):
    import math
    backend = Backend(os.environ["UNFOLD_TEST_BACKEND"])
    scene = Scene(title="Orbit test", duration=5, background="#000000",
                  explanation="Independent corners follow arcs, outline follows corners",
                  elements=[orbital()], stroke_animation="svg",
                  tweens=[dict(target="orbit", at=0, duration=4,
                               orbit_angles=[90,130,240,350], ease="none"),
                          dict(target="orbit", at=4, duration=1, marker_opacity=0)])
    source = tmp_path / "source"
    backend.author(scene, source)
    backend.render(source, tmp_path / "orbit.mp4")
    frames = backend.frames(tmp_path / "orbit.mp4", [1,2,3], tmp_path / "frames")
    for t, f in zip([1,2,3], frames):
        image = Image.open(f['path']).convert('RGB')
        pts = []
        for start, end in zip([0,80,190,270], [90,130,240,350]):
            angle = math.radians(start+(end-start)*t/4)
            x,y = 520+180*math.cos(angle),320+180*math.sin(angle)
            pts.append((x,y))
            # Radius and marker location at intermediate time, not endpoint-only checks.
            assert max(sum(image.getpixel((round(x)+dx,round(y)+dy)))
                       for dx in range(-2,3) for dy in range(-2,3)) > 600
        # Connected segment midpoints are rendered too.
        for a,b in zip(pts,pts[1:]+pts[:1]):
            x,y = round((a[0]+b[0])/2),round((a[1]+b[1])/2)
            assert max(sum(image.getpixel((x+dx,y+dy)))
                       for dx in range(-2,3) for dy in range(-2,3)) > 450
    # Re-open stored source: orbit data survives the same model validation as retained work.
    import json
    assert Scene.model_validate(json.loads((source/'scene.json').read_text())) == scene
