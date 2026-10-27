"""The integration's protocol and renderer are copies of the LX-D02 package's.

The copies live in custom_components/lxd02 because Home Assistant can't install
the package. When the LX-D02 project is checked out next to this one (or
LXD02_PACKAGE points at its src/lxd02), check that they haven't drifted apart.
"""
import filecmp
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
COMPONENT = ROOT / "custom_components" / "lxd02"
PACKAGE = Path(os.environ.get("LXD02_PACKAGE", ROOT.parent / "LX-D02" / "src" / "lxd02"))
SHARED = ["protocol.py", "receipt.py", "markdown.py"]

pytestmark = pytest.mark.skipif(not PACKAGE.is_dir(), reason=f"LX-D02 package not found at {PACKAGE}")


@pytest.mark.parametrize("name", SHARED)
def test_module_is_a_copy_of_the_package(name) -> None:
    assert (COMPONENT / name).read_bytes() == (PACKAGE / name).read_bytes(), \
        f"copy {PACKAGE / name} into {COMPONENT}"


def test_assets_are_a_copy_of_the_package() -> None:
    cmp = filecmp.dircmp(PACKAGE / "assets", COMPONENT / "assets")
    assert not (cmp.left_only or cmp.right_only or cmp.diff_files)
