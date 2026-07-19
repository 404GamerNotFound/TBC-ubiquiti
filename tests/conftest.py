"""Stub tbc_camera_api so this plugin's tests run standalone (no TBC-camera-manager checkout needed).

module.py imports ManualRtspCameraModule from tbc_camera_api at module scope
- inside the real TBC process that facade is installed by
camera_modules/packages.py before a plugin is ever imported, but a plugin's
own standalone test run never goes through that loader, so this fake stands
in for it. ManualRtspCameraModule.probe() below reimplements the real
app/tbc/manual_rtsp/module.py logic (validate_manual_stream_uri +
probe_rtsp_stream, both from app/tbc/camera_modules/streams.py) so tests
that exercise real probing behavior, not just imports, still get correct
results. probe_rtsp_stream is looked up dynamically on the fake `streams`
submodule (not bound to a local name) so tests can monkeypatch
`tbc_camera_api.streams.probe_rtsp_stream` the same way the real plugin
loader's tests monkeypatch `app.tbc.manual_rtsp.module.probe_rtsp_stream`.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit


def _install_fake_tbc_camera_api() -> None:
    if "tbc_camera_api" in sys.modules:
        return

    class _FakeCameraCapability(str, Enum):
        LIVE = "live"
        RECORDING = "recording"
        DETECTIONS = "detections"
        CHANNELS = "channels"
        ARCHIVE = "archive"
        CONTROL = "control"
        FIRMWARE = "firmware"

    class _FakeCameraModule:
        key = ""
        label = ""
        description = ""
        default_onvif_port = 8000
        default_http_port = 80
        default_rtsp_port = 554
        supports_manual_stream_uri = False
        requires_manual_stream_uri = False
        requires_credentials = True
        capabilities: frozenset = frozenset()
        identifier_label = None

        def supports(self, capability):
            return capability in self.capabilities

        def detection_definitions(self):
            return ()

        async def probe(self, camera):
            raise NotImplementedError

    @dataclass
    class _FakeCameraSnapshot:
        status: str
        message: str
        manufacturer: str | None = None
        model: str | None = None
        firmware: str | None = None
        serial: str | None = None
        stream_uri: str | None = None
        detections: list = field(default_factory=list)
        channels: list = field(default_factory=list)
        metrics: dict = field(default_factory=dict)

    def _validate_manual_stream_uri(value):
        uri = str(value or "").strip()
        if not uri or any(character in uri for character in ("\r", "\n", "\x00")):
            raise ValueError("A valid RTSP/RTSPS URL is required")
        parsed = urlsplit(uri)
        if parsed.scheme.lower() not in {"rtsp", "rtsps"} or not parsed.hostname:
            raise ValueError("The stream URL must start with rtsp:// or rtsps:// and contain a host")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("The RTSP/RTSPS URL contains an invalid port") from exc
        return uri

    def _probe_rtsp_stream(stream_uri, timeout_seconds=8):
        raise NotImplementedError

    streams_module = types.ModuleType("tbc_camera_api.streams")
    streams_module.validate_manual_stream_uri = _validate_manual_stream_uri
    streams_module.probe_rtsp_stream = _probe_rtsp_stream

    class _FakeManualRtspCameraModule(_FakeCameraModule):
        supports_manual_stream_uri = True
        requires_manual_stream_uri = True
        requires_credentials = False
        capabilities = frozenset({_FakeCameraCapability.LIVE})

        def __init__(self, *, manufacturer, model_hint, setup_hint):
            self.manufacturer_name = manufacturer
            self.model_hint = model_hint
            self.setup_hint = setup_hint

        async def probe(self, camera):
            raw_uri = str(camera.get("manual_stream_uri") or "")
            try:
                stream_uri = streams_module.validate_manual_stream_uri(raw_uri)
            except ValueError as exc:
                return _FakeCameraSnapshot(
                    status="error",
                    message=f"{exc} | {self.setup_hint}",
                    manufacturer=self.manufacturer_name,
                    model=self.model_hint,
                )
            probe_status, probe_message = await asyncio.to_thread(streams_module.probe_rtsp_stream, stream_uri)
            status = "warn" if probe_status == "warning" else probe_status
            return _FakeCameraSnapshot(
                status=status,
                message=f"{probe_message} | {self.setup_hint}",
                manufacturer=self.manufacturer_name,
                model=self.model_hint,
                stream_uri=stream_uri,
            )

    api = types.ModuleType("tbc_camera_api")
    api.CameraCapability = _FakeCameraCapability
    api.CameraModule = _FakeCameraModule
    api.CameraSnapshot = _FakeCameraSnapshot
    api.ManualRtspCameraModule = _FakeManualRtspCameraModule
    api.streams = streams_module
    sys.modules["tbc_camera_api"] = api
    sys.modules["tbc_camera_api.streams"] = streams_module


_install_fake_tbc_camera_api()

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_MANIFEST = json.loads((_PLUGIN_DIR / "manifest.json").read_text(encoding="utf-8"))
_PACKAGE_NAME = _MANIFEST["key"]

# The plugin directory has no valid Python package name of its own (repo names
# like "TBC-ubiquiti" contain a hyphen), so TBC's real loader
# (app/tbc/camera_modules/packages.py:load_plugin_module) never imports it by
# path either - it registers a synthetic module name via
# importlib.util.spec_from_file_location and lets the plugin's relative
# imports resolve against that. Tests need the same trick to import module.py
# outside of TBC itself.
if _PACKAGE_NAME not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        _PACKAGE_NAME,
        _PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(_PLUGIN_DIR)],
    )
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_PACKAGE_NAME] = _module
    _spec.loader.exec_module(_module)
