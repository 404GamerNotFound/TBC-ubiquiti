import asyncio
import json
from pathlib import Path

from ubiquiti.module import UbiquitiCameraModule
from tbc_camera_api import CameraCapability

_PLUGIN_DIR = Path(__file__).resolve().parent.parent


def _manifest() -> dict:
    return json.loads((_PLUGIN_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_capabilities_match_module_class():
    manifest = _manifest()
    manifest_capabilities = {CameraCapability(value) for value in manifest["capabilities"]}
    assert manifest_capabilities == UbiquitiCameraModule.capabilities
    assert manifest_capabilities == {CameraCapability.LIVE}


def test_manifest_key_and_ports_match_manual_rtsp_defaults():
    manifest = _manifest()
    module = UbiquitiCameraModule()
    assert manifest["key"] == "ubiquiti"
    assert module.requires_manual_stream_uri is True
    assert module.requires_credentials is False


def test_probe_rejects_invalid_manual_stream_uri():
    module = UbiquitiCameraModule()
    snapshot = asyncio.run(module.probe({"manual_stream_uri": "not-a-valid-uri"}))
    assert snapshot.status == "error"
    assert "UniFi Protect" in snapshot.message


def test_probe_accepts_rtsps_uri_shape(monkeypatch):
    from app.tbc.manual_rtsp import module as manual_rtsp_module

    monkeypatch.setattr(
        manual_rtsp_module, "probe_rtsp_stream", lambda uri, **kwargs: ("ok", "RTSP-Stream erreichbar")
    )
    module = UbiquitiCameraModule()
    snapshot = asyncio.run(module.probe({"manual_stream_uri": "rtsps://example.invalid:7447/live/stream"}))
    assert snapshot.status == "ok"
    assert snapshot.stream_uri == "rtsps://example.invalid:7447/live/stream"
