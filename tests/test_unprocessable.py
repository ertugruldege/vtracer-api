import io
import multiprocessing
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from converter_worker import convert_in_child  # noqa: E402


def png(mode, color, size=(64, 64)):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, "PNG")
    return buf.getvalue()


def run_worker(image_bytes, options=None):
    parent, child = multiprocessing.Pipe(duplex=False)
    convert_in_child(child, image_bytes, options or {})
    return parent.recv()


def test_worker_reports_a_vtracer_panic_instead_of_dying_silently():
    status, payload = run_worker(png("RGBA", (0, 0, 0, 0)))

    assert status == "unprocessable"
    assert "index out of bounds" in payload


def test_worker_still_converts_a_normal_image():
    status, payload = run_worker(png("RGB", (255, 0, 0)))

    assert status == "ok"
    assert payload.lstrip().startswith("<?xml") or "<svg" in payload


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import main

    return TestClient(main.app)


def test_api_answers_422_for_a_blank_transparent_image(client):
    response = client.post(
        "/api/convert",
        files={"image": ("blank.png", png("RGBA", (0, 0, 0, 0)), "image/png")},
    )

    assert response.status_code == 422
    assert "cannot be traced" in response.json()["detail"]


def test_api_still_converts_a_normal_image(client):
    response = client.post(
        "/api/convert",
        files={"image": ("red.png", png("RGB", (255, 0, 0)), "image/png")},
    )

    assert response.status_code == 200
    assert b"<svg" in response.content
