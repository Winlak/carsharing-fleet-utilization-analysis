import re
from pathlib import Path


def test_chart_map_links_resolve_inside_repository():
    root = Path(__file__).resolve().parents[1]
    report = root / 'outputs/chart_map.md'
    links = re.findall(r'\]\(([^)]+)\)', report.read_text())
    assert len(links) >= 2
    for href in links:
        target = (report.parent / href.split('#')[0]).resolve()
        assert root in target.parents
        assert target.is_file(), href
