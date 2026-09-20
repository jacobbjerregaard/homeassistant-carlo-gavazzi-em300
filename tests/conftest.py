"""Test bootstrap for the Carlo Gavazzi EM300 integration.

The integration package imports Home Assistant at import time, so it cannot be
loaded in a plain unit-test environment. The protocol handling under ``api``
is however free of Home Assistant, and is the part most worth testing.

To exercise it in isolation the ``api`` directory is registered as a standalone
namespace package named ``em300_api``, so tests can do::

    from em300_api.utils import decode_registers

without pulling in Home Assistant.
"""

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_DIR = _REPO_ROOT / "custom_components" / "carlo_gavazzi_em300" / "api"

# Make ``custom_components`` importable for the Home Assistant tests.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _register_namespace_package(name: str, path: Path) -> None:
    """Expose ``path`` as an importable namespace package called ``name``."""
    if name in sys.modules:
        return
    spec = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
    spec.submodule_search_locations = [str(path)]
    sys.modules[name] = importlib.util.module_from_spec(spec)


_register_namespace_package("em300_api", _API_DIR)


# tests/integration needs Home Assistant + pytest-homeassistant-custom-component.
# When those aren't installed (the pure-logic venv) skip collecting that
# directory so the rest of the suite still runs.
#
# find_spec plus the documented hook rather than a try/except import and the
# ``collect_ignore`` magic global: both of those look like dead code to static
# analysis, since nothing in this file reads either name.
_HAS_HOMEASSISTANT = (
    importlib.util.find_spec("pytest_homeassistant_custom_component") is not None
)


def pytest_ignore_collect(collection_path, config):
    """Skip tests/integration when Home Assistant isn't installed."""
    if _HAS_HOMEASSISTANT:
        return None
    if "integration" in collection_path.parts:
        return True
    return None
