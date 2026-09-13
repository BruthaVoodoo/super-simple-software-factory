"""Import current template modules without touching the operator environment.

`adw_modules/utils.py` calls dotenv's `load_dotenv()` at import time, which
would read whatever `.env` sits in the current directory. The bootstrap
patches that call for the first import only, then verifies that the loaded
package really is the current template copy — never an installed shadow.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

TEMPLATE_ADWS = (Path(__file__).resolve().parents[2]
                 / ".claude" / "skills" / "sssf" / "templates" / "adws")


def bootstrap() -> None:
    """Put the current template modules on the path and verify the import."""
    if str(TEMPLATE_ADWS) not in sys.path:
        sys.path.insert(0, str(TEMPLATE_ADWS))
    if "adw_modules" in sys.modules:
        return
    with mock.patch("dotenv.load_dotenv", return_value=False):
        import adw_modules.utils  # noqa: F401
    loaded = Path(adw_modules.utils.__file__).resolve()
    assert loaded.is_relative_to(TEMPLATE_ADWS), (
        f"imported {loaded} — not the current template copy")
