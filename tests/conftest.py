from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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
