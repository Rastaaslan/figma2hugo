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
                        "name": "callout",
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


def test_layout_analyzer_unwraps_single_frame_wrapper_chain_into_inner_sections() -> None:
    root_node = {
        "id": "1:2",
        "name": "Imported Landing Page",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": -1121, "y": -4033, "width": 1920, "height": 7423},
        "children": [
            {
                "id": "1:389",
                "name": "Clip path group",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": -1225.7, "y": -4201.0, "width": 2302.6, "height": 7590.6},
                "children": [
                    {
                        "id": "1:4",
                        "name": "Page",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -1225.7, "y": -4201.0, "width": 2302.6, "height": 7590.6},
                        "children": [
                            {
                                "id": "1:6",
                                "name": "Vector",
                                "type": "VECTOR",
                                "visible": True,
                                "absoluteBoundingBox": {"x": -1121.0, "y": -4033.0, "width": 1920.0, "height": 7422.6},
                            },
                            {
                                "id": "1:7",
                                "name": "legal-footer",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": -1120.0, "y": 3292.0, "width": 1919.2, "height": 96.1},
                                "children": [],
                            },
                            {
                                "id": "1:10",
                                "name": "contact-panel",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": -1174.0, "y": -71.0, "width": 2109.6, "height": 3448.8},
                                "children": [],
                            },
                            {
                                "id": "1:109",
                                "name": "feature-strip",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": -1076.0, "y": -1578.8, "width": 1869.0, "height": 1450.3},
                                "children": [],
                            },
                            {
                                "id": "1:236",
                                "name": "hero-panel",
                                "type": "GROUP",
                                "visible": True,
                                "absoluteBoundingBox": {"x": -1225.7, "y": -4201.0, "width": 2302.6, "height": 2685.1},
                                "children": [],
                            },
                        ],
                    }
                ],
            }
        ],
    }

    sections = LayoutAnalyzer().identify_sections(root_node)

    assert [section.id for section in sections] == ["1:236", "1:109", "1:10", "1:7"]
    contact_section = next(section for section in sections if section.id == "1:10")
    assert [node["id"] for node in contact_section.extra_nodes] == ["1:6"]


def test_layout_analyzer_ignores_outer_root_orphans_when_inner_page_is_promoted() -> None:
    root_node = {
        "id": "0:1",
        "name": "Selection",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 2200, "height": 2600},
        "children": [
            {
                "id": "page",
                "name": "page",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": 100, "y": 100, "width": 1920, "height": 2200},
                "children": [
                    {
                        "id": "hero",
                        "name": "Hero",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 100, "y": 100, "width": 1920, "height": 700},
                        "children": [],
                    },
                    {
                        "id": "content",
                        "name": "Content",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 100, "y": 900, "width": 1920, "height": 900},
                        "children": [],
                    },
                    {
                        "id": "hero-accent",
                        "name": "Vector",
                        "type": "VECTOR",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 40, "y": 40, "width": 260, "height": 260},
                    },
                ],
            },
            {
                "id": "debug-note",
                "name": "J’ai un soucis de Footer",
                "type": "TEXT",
                "visible": True,
                "characters": "J’ai un soucis de Footer",
                "absoluteBoundingBox": {"x": 120, "y": 2350, "width": 1200, "height": 140},
            },
        ],
    }

    sections = LayoutAnalyzer().identify_sections(root_node)

    assert [section.id for section in sections] == ["hero", "content"]
    assert [node["id"] for node in sections[0].extra_nodes] == ["hero-accent"]
    assert [node["id"] for node in sections[1].extra_nodes] == []


def test_layout_analyzer_prefers_named_page_child_over_sibling_notes() -> None:
    root_node = {
        "id": "0:1",
        "name": "Selection",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 2200, "height": 2600},
        "children": [
            {
                "id": "3:964",
                "name": "page",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": 100, "y": 100, "width": 1920, "height": 2200},
                "children": [
                    {
                        "id": "hero",
                        "name": "section-hero",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 100, "y": 100, "width": 1920, "height": 700},
                        "children": [],
                    },
                    {
                        "id": "content",
                        "name": "section-content",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 100, "y": 900, "width": 1920, "height": 900},
                        "children": [],
                    },
                    {
                        "id": "footer",
                        "name": "footer",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 100, "y": 1900, "width": 1920, "height": 300},
                        "children": [],
                    },
                ],
            },
            {
                "id": "2019:28",
                "name": "Frame 2",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 2400, "width": 1600, "height": 180},
                "children": [
                    {
                        "id": "2019:29",
                        "name": "J’ai pas touché le header",
                        "type": "TEXT",
                        "visible": True,
                        "characters": "J’ai pas touché le header",
                        "absoluteBoundingBox": {"x": 140, "y": 2420, "width": 1200, "height": 120},
                    }
                ],
            },
            {
                "id": "2019:26",
                "name": "Frame 1",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": 120, "y": 2200, "width": 1600, "height": 180},
                "children": [
                    {
                        "id": "2019:27",
                        "name": "J’ai un soucis de Footer",
                        "type": "TEXT",
                        "visible": True,
                        "characters": "J’ai un soucis de Footer",
                        "absoluteBoundingBox": {"x": 140, "y": 2220, "width": 1200, "height": 120},
                    }
                ],
            },
        ],
    }

    sections = LayoutAnalyzer().identify_sections(root_node)

    assert [section.id for section in sections] == ["hero", "content", "footer"]


def test_layout_analyzer_keeps_multiple_real_page_sections_at_root() -> None:
    root_node = {
        "id": "3:964",
        "name": "maquette-accueil-1920",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": -684, "y": -2207, "width": 1920, "height": 3931},
        "children": [
            {
                "id": "2004:2",
                "name": "section-hero",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": -684, "y": -2207, "width": 1920, "height": 650},
                "children": [
                    {
                        "id": "hero-content",
                        "name": "hero-content",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -620, "y": -2100, "width": 900, "height": 300},
                        "children": [],
                    }
                ],
            },
            {
                "id": "6:1100",
                "name": "section-accompagnement",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": -684, "y": -1557, "width": 1920, "height": 794},
                "children": [
                    {
                        "id": "9:1156",
                        "name": "accompagnement-main",
                        "type": "FRAME",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -684, "y": -1557, "width": 1920, "height": 446},
                        "children": [],
                    },
                    {
                        "id": "9:1165",
                        "name": "bandeau-droite-accompagnement",
                        "type": "FRAME",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -684, "y": -1111, "width": 1920, "height": 298},
                        "children": [],
                    },
                ],
            },
            {
                "id": "6:1103",
                "name": "section-embedded",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": -683, "y": -763, "width": 1918, "height": 652},
                "children": [
                    {
                        "id": "logo-embedded",
                        "name": "logo-embedded",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -380, "y": -720, "width": 280, "height": 170},
                        "children": [],
                    },
                    {
                        "id": "section-embedded-infos",
                        "name": "section-embedded-infos",
                        "type": "FRAME",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -540, "y": -540, "width": 1620, "height": 390},
                        "children": [],
                    },
                ],
            },
            {
                "id": "9:1178",
                "name": "bandeau-gauche-content",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": -684, "y": -111, "width": 1920, "height": 216},
                "children": [
                    {
                        "id": "image-idees",
                        "name": "image-idees",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -600, "y": -80, "width": 180, "height": 140},
                        "children": [],
                    },
                    {
                        "id": "image-expertise",
                        "name": "image-expertise",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 300, "y": -80, "width": 180, "height": 140},
                        "children": [],
                    },
                    {
                        "id": "image-aventure",
                        "name": "image-aventure",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": 1200, "y": -80, "width": 180, "height": 140},
                        "children": [],
                    },
                ],
            },
            {
                "id": "9:1183",
                "name": "section-contact",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": -683, "y": 105, "width": 1918, "height": 909},
                "children": [
                    {
                        "id": "section-contact-moi",
                        "name": "section-contact-moi",
                        "type": "FRAME",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -683, "y": 105, "width": 1918, "height": 909},
                        "children": [],
                    }
                ],
            },
            {
                "id": "9:1220",
                "name": "footer",
                "type": "FRAME",
                "visible": True,
                "absoluteBoundingBox": {"x": -683, "y": 1014, "width": 1918, "height": 710},
                "children": [
                    {
                        "id": "bandeau-image-contact-demandes",
                        "name": "bandeau-image-contact-demandes",
                        "type": "FRAME",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -683, "y": 1014, "width": 1918, "height": 710},
                        "children": [],
                    }
                ],
            },
        ],
    }

    sections = LayoutAnalyzer().identify_sections(root_node)

    assert [section.id for section in sections] == [
        "2004:2",
        "6:1100",
        "6:1103",
        "9:1178",
        "9:1183",
        "9:1220",
    ]


def test_layout_analyzer_keeps_vector_only_roots_as_single_visual_section() -> None:
    root_node = {
        "id": "12:990",
        "name": "Exports one page 1",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": -5416, "y": -4699, "width": 1920, "height": 7422.64},
        "children": [
            {
                "id": "12:991",
                "name": "Fond",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": -5472.4, "y": -4705.3, "width": 2256.6, "height": 7434.6},
                "children": [
                    {
                        "id": "12:992",
                        "name": "Rectangle",
                        "type": "RECTANGLE",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -5472.4, "y": 1529.8, "width": 1996.8, "height": 1123.2},
                    }
                ],
            },
            {
                "id": "12:1067",
                "name": "Décors",
                "type": "GROUP",
                "visible": True,
                "absoluteBoundingBox": {"x": -5518.7, "y": -4859.8, "width": 2172.6, "height": 6732.8},
                "children": [
                    {
                        "id": "12:1068",
                        "name": "Group",
                        "type": "GROUP",
                        "visible": True,
                        "absoluteBoundingBox": {"x": -4267.2, "y": 889.6, "width": 921.1, "height": 983.4},
                        "children": [],
                    }
                ],
            },
        ],
    }

    sections = LayoutAnalyzer().identify_sections(root_node)

    assert [section.id for section in sections] == ["12:990"]
