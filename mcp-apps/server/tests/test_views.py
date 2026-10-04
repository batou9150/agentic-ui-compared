"""The built views must be self-contained: no external scripts, styles or fetches.

Needs `make mcp-apps-views`; skipped locally when the views are not built,
required in CI.
"""

import os
import re

import pytest
from mcp_apps_server.server import DEFAULT_VIEWS_DIR, VIEW_FILES

built = all((DEFAULT_VIEWS_DIR / f).exists() for f in VIEW_FILES.values())
pytestmark = pytest.mark.skipif(
    not built and not os.environ.get("CI"),
    reason="views not built (make mcp-apps-views)",
)

EXTERNAL = re.compile(
    r"""<(script|link|img|iframe)\b[^>]*\b(src|href)=["']?(https?:)?//""", re.I
)


@pytest.mark.parametrize("name", sorted(VIEW_FILES.values()))
def test_view_is_self_contained(name: str) -> None:
    html = (DEFAULT_VIEWS_DIR / name).read_text()
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "<script" in html
    assert not EXTERNAL.search(html), "external resource found"
    assert 'type="module" src=' not in html  # inlined by vite-plugin-singlefile
