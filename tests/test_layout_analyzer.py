from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from figma2hugo.layout_analyzer import LayoutAnalyzer


def test_layout_analyzer_keeps_small_nav_groups_as_sections() -> None:
    root_node = {
        "id": "page",
        "name": "Page",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 1800},
        "children": [
            {
                "id": "hero",
                "name": "Hero",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 0, "y": 80, "width": 1240, "height": 640},
                "children": [],
            },
            {
                "id": "nav",
                "name": "nav",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1240, "height": 40},
                "children": [
                    {
                        "id": "nav-labels",
                        "name": "nav-labels",
                        "type": "TEXT",
                        "visible": True,
                        "characters": "home about contact",
                        "absoluteBoundingBox": {"x": 40, "y": 0, "width": 300, "height": 20},
                    }
                ],
            },
        ],
    }

    sections = LayoutAnalyzer().identify_sections(root_node)

    assert [section.id for section in sections] == ["nav", "hero"]


def test_layout_analyzer_attaches_top_level_vectors_to_nearest_section() -> None:
    root_node = {
        "id": "page",
        "name": "Page",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 2400},
        "children": [
            {
                "id": "hero",
                "name": "Hero",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 0, "y": 100, "width": 1240, "height": 600},
                "children": [],
            },
            {
                "id": "footer",
                "name": "Footer",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": 0, "y": 1800, "width": 1240, "height": 400},
                "children": [],
            },
            {
                "id": "hero-accent",
                "name": "Vector",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": -120, "y": 40, "width": 300, "height": 220},
            },
            {
                "id": "footer-accent",
                "name": "Vector",
                "type": "VECTOR",
                "visible": True,
                "absoluteBoundingBox": {"x": 980, "y": 1880, "width": 260, "height": 200},
            },
        ],
    }

    sections = LayoutAnalyzer().identify_sections(root_node)

    assert [node["id"] for node in sections[0].extra_nodes] == ["hero-accent"]
    assert [node["id"] for node in sections[1].extra_nodes] == ["footer-accent"]


def test_layout_analyzer_unwraps_single_canvas_wrapper_frame_into_inner_sections() -> None:
    root_node = {
        "id": "0:1",
        "name": "Page 1",
        "type": "CANVAS",
        "visible": True,
        "absoluteBoundingBox": {"x": -721, "y": -776, "width": 1440, "height": 3507},
        "children": [
            {
                "id": "1:2",
                "name": "base",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": -721, "y": -776, "width": 1440, "height": 3507},
                "children": [
                    {
                        "id": "4:7",
                        "name": "Vector",
                        "type": "VECTOR",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 436, "y": 1138, "width": 566.83, "height": 655.64},
                    },
                    {
                        "id": "1:30",
                        "name": "nav",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -621, "y": -735, "width": 1240, "height": 34},
                        "children": [
                            {
                                "id": "nav-text",
                                "name": "Nav text",
                                "type": "TEXT",
                                "visible": True,
                                "characters": "home about services",
                                "absoluteBoundingBox": {"x": -100, "y": -735, "width": 320, "height": 20},
                            }
                        ],
                    },
                    {
                        "id": "1:10",
                        "name": "Hero",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -621, "y": -676, "width": 1240, "height": 587},
                        "children": [],
                    },
                    {
                        "id": "3:71",
                        "name": "breaker",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -721, "y": 1052, "width": 1440, "height": 465},
                        "children": [],
                    },
                ],
            }
        ],
    }

    sections = LayoutAnalyzer().identify_sections(root_node)

    assert [section.id for section in sections] == ["1:30", "1:10", "3:71"]
    assert [node["id"] for node in sections[2].extra_nodes] == ["4:7"]
