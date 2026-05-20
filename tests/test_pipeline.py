from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from tests import generator_support as _generator_support

from figma2hugo.pipeline import fetcher as pipeline_fetcher
from figma2hugo.pipeline import runner as pipeline_runner
from figma2hugo.pipeline.fetcher import fetch_raw_node_from_figma, parse_figma_pipeline_url
from figma2hugo.pipeline.generator.css_geometry import (
    compute_page_geometry,
    compute_section_geometry,
)
from figma2hugo.pipeline.html_renderer import render_static_css
from figma2hugo.pipeline.hugo_renderer import _asset_filename
from figma2hugo.pipeline.models import CoordinateSpace, NodeKind
from figma2hugo.pipeline.normalizer import normalize_document
from figma2hugo.pipeline.options import PipelineRenderMode
from figma2hugo.pipeline.orchestrator import Pipeline
from figma2hugo.pipeline.responsive import ResponsiveDecision, build_responsive_manifest
from figma2hugo.pipeline.responsive_identity import unique_breakpoint_render_name
from figma2hugo.pipeline.runner import (
    build_pipeline_from_raw_files,
    build_pipeline_hugo_site_from_raw_files,
)
from figma2hugo.pipeline.visual_smoke import parse_widths, run_pipeline_visual_smoke

_ = _generator_support.ROOT
FIGMA_URL = "https://www.figma.com/design/AbCdEf1234567890/Test-Page?node-id=3-964"


def test_pipeline_remote_assets_without_suffix_use_image_extension() -> None:
    assert _asset_filename(
        "https://figma-alpha-api.s3.us-west-2.amazonaws.com/images/hash"
    ).endswith(".png")
    assert _asset_filename("https://assets.example.test/hero.jpg?token=abc").endswith(".jpg")
    assert _asset_filename("local-cache-key").endswith(".bin")


def test_pipeline_css_geometry_snaps_known_board_and_section_width() -> None:
    page = {"width": 1917, "height": 520}
    section = {"bounds": {"x": 0, "y": 0, "width": 1925, "height": 520}}

    page_geometry = compute_page_geometry(page, [section])
    section_geometry = compute_section_geometry(
        section,
        page_width=page_geometry.width,
        page_origin_x=page_geometry.origin_x,
        page_origin_y=page_geometry.origin_y,
    )

    assert page_geometry.width == 1920
    assert page_geometry.origin_x == 0
    assert section_geometry.left == 0
    assert section_geometry.width == 1920


def test_pipeline_css_geometry_clamps_centered_oversized_sections_to_board() -> None:
    page = {"width": 402, "height": 900}
    section = {"bounds": {"x": -201, "y": 100, "width": 804, "height": 300}}

    page_geometry = compute_page_geometry(page, [section], prefer_declared_width=True)
    section_geometry = compute_section_geometry(
        section,
        page_width=page_geometry.width,
        page_origin_x=page_geometry.origin_x,
        page_origin_y=page_geometry.origin_y,
    )

    assert page_geometry.width == 402
    assert section_geometry.left == 0
    assert section_geometry.width == 402


def test_pipeline_responsive_identity_replaces_breakpoint_suffixes() -> None:
    used_names = {"asset-image-card-w834"}

    assert (
        unique_breakpoint_render_name(
            "asset-image-card-w834",
            suffix="w402",
            used_names=used_names,
        )
        == "asset-image-card-w402"
    )
    assert "asset-image-card-w834-w402" not in used_names


def test_pipeline_normalizer_owns_page_coordinate_space_and_snaps_sections() -> None:
    document = normalize_document(
        {
            "id": "page",
            "name": "page-mentions-legales-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 12, "y": 40, "width": 1917, "height": 900},
            "children": [
                {
                    "id": "hero",
                    "name": "section-hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 10, "y": 40, "width": 1924, "height": 320},
                    "children": [
                        {
                            "id": "title",
                            "name": "titre-h1-mentions-legales",
                            "type": "TEXT",
                            "characters": "Title - Mentions legales",
                            "absoluteBoundingBox": {
                                "x": 120,
                                "y": 120,
                                "width": 500,
                                "height": 80,
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert document.page.coordinate_space is CoordinateSpace.PAGE
    assert document.page.page_bounds.x == 0
    assert document.page.page_bounds.width == 1920
    assert document.sections[0].kind is NodeKind.SECTION
    assert document.sections[0].page_bounds.x == 0
    assert document.sections[0].page_bounds.width == 1920
    assert document.sections[0].children[0].payload["characters"] == "Title - Mentions legales"


def test_pipeline_normalizer_accepts_domain_agnostic_regions() -> None:
    document = normalize_document(
        {
            "id": "page",
            "name": "page-dashboard-1440",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 900},
            "children": [
                {
                    "id": "main",
                    "name": "region-dashboard-main",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 80, "width": 1440, "height": 700},
                    "children": [
                        {
                            "id": "title",
                            "name": "titre-h1-dashboard",
                            "type": "TEXT",
                            "characters": "Dashboard",
                            "absoluteBoundingBox": {
                                "x": 40,
                                "y": 120,
                                "width": 300,
                                "height": 48,
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert [section.name for section in document.sections] == ["region-dashboard-main"]
    assert document.sections[0].kind is NodeKind.SECTION
    assert document.sections[0].page_bounds.width == 1440


def test_pipeline_normalizer_snaps_top_level_container_sections() -> None:
    document = normalize_document(
        {
            "id": "page",
            "name": "page-cases-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 900},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-droite-cas-clients",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": -10, "y": 200, "width": 854, "height": 240},
                    "children": [
                        {
                            "id": "title",
                            "name": "titre-bandeau",
                            "type": "TEXT",
                            "characters": "Cas clients",
                            "absoluteBoundingBox": {
                                "x": 120,
                                "y": 230,
                                "width": 220,
                                "height": 40,
                            },
                        }
                    ],
                }
            ],
        }
    )

    section = document.sections[0]

    assert section.kind is NodeKind.CONTAINER
    assert section.page_bounds.x == 0
    assert section.page_bounds.width == 834
    assert section.children[0].page_bounds.x == 120


def test_pipeline_normalizer_promotes_nested_content_section_from_empty_wrapper() -> None:
    document = normalize_document(
        {
            "id": "page",
            "name": "page-wrapper-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 700},
            "children": [
                {
                    "id": "wrapper",
                    "name": "section-wrapper",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 300},
                    "children": [
                        {
                            "id": "inner",
                            "name": "section-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 120,
                                "width": 402,
                                "height": 200,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h2-content",
                                    "type": "TEXT",
                                    "characters": "Nested content",
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 140,
                                        "width": 260,
                                        "height": 40,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    assert [section.name for section in document.sections] == ["section-content"]
    assert document.sections[0].page_bounds.y == 120


def test_pipeline_normalizer_keeps_wrapper_with_renderable_siblings() -> None:
    document = normalize_document(
        {
            "id": "page",
            "name": "page-wrapper-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 700},
            "children": [
                {
                    "id": "wrapper",
                    "name": "section-wrapper",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 420},
                    "children": [
                        {
                            "id": "header",
                            "name": "content-header",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 120,
                                "width": 402,
                                "height": 80,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h2-wrapper",
                                    "type": "TEXT",
                                    "characters": "Wrapper heading",
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 140,
                                        "width": 260,
                                        "height": 40,
                                    },
                                }
                            ],
                        },
                        {
                            "id": "inner",
                            "name": "section-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 210,
                                "width": 402,
                                "height": 200,
                            },
                            "children": [
                                {
                                    "id": "body",
                                    "name": "texte-content",
                                    "type": "TEXT",
                                    "characters": "Nested content",
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 230,
                                        "width": 260,
                                        "height": 40,
                                    },
                                }
                            ],
                        },
                        {
                            "id": "cta",
                            "name": "button-wrapper",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 140,
                                "y": 440,
                                "width": 120,
                                "height": 32,
                            },
                            "children": [
                                {
                                    "id": "cta-label",
                                    "name": "texte-button-wrapper",
                                    "type": "TEXT",
                                    "characters": "Call to action",
                                    "absoluteBoundingBox": {
                                        "x": 150,
                                        "y": 448,
                                        "width": 100,
                                        "height": 16,
                                    },
                                }
                            ],
                        },
                    ],
                }
            ],
        }
    )

    assert [section.name for section in document.sections] == ["section-wrapper"]
    assert [child.name for child in document.sections[0].children] == [
        "content-header",
        "section-content",
        "button-wrapper",
    ]


def test_pipeline_normalizer_keeps_wrapper_when_promoted_section_overhangs() -> None:
    document = normalize_document(
        {
            "id": "page",
            "name": "page-wrapper-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 700},
            "children": [
                {
                    "id": "wrapper",
                    "name": "section-wrapper",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 160, "width": 402, "height": 260},
                    "children": [
                        {
                            "id": "inner",
                            "name": "section-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 140,
                                "width": 402,
                                "height": 220,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h2-content",
                                    "type": "TEXT",
                                    "characters": "Overhanging content",
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 170,
                                        "width": 260,
                                        "height": 40,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    assert [section.name for section in document.sections] == ["section-wrapper"]
    assert document.sections[0].page_bounds.y == 160


def test_pipeline_normalizer_keeps_semantic_hero_wrapper() -> None:
    document = normalize_document(
        {
            "id": "page",
            "name": "page-hero-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
            "children": [
                {
                    "id": "hero",
                    "name": "section-hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                    "children": [
                        {
                            "id": "hero-content",
                            "name": "section-hero-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 120,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h1-hero",
                                    "type": "TEXT",
                                    "characters": "Hero title",
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 40,
                                        "width": 260,
                                        "height": 40,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    assert [section.name for section in document.sections] == ["section-hero"]


def test_pipeline_responsive_manifest_aligns_promoted_nested_sections() -> None:
    desktop = normalize_document(
        {
            "id": "page-1920",
            "name": "page-promoted-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 800},
            "children": [
                {
                    "id": "wrapper-1920",
                    "name": "section-wrapper",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 1920, "height": 300},
                    "children": [
                        {
                            "id": "content-1920",
                            "name": "section-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 120,
                                "width": 1920,
                                "height": 200,
                            },
                            "children": [
                                {
                                    "id": "title-1920",
                                    "name": "titre-h2-content",
                                    "type": "TEXT",
                                    "characters": "Same content",
                                    "absoluteBoundingBox": {
                                        "x": 200,
                                        "y": 140,
                                        "width": 400,
                                        "height": 40,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    mobile = normalize_document(
        {
            "id": "page-402",
            "name": "page-promoted-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 700},
            "children": [
                {
                    "id": "content-402",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 200},
                    "children": [
                        {
                            "id": "title-402",
                            "name": "titre-h2-content",
                            "type": "TEXT",
                            "characters": "Same content",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 120,
                                "width": 260,
                                "height": 40,
                            },
                        }
                    ],
                },
                {
                    "id": "wrapper-402",
                    "name": "section-wrapper",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 200},
                    "children": [],
                },
            ],
        }
    )

    manifest = build_responsive_manifest([desktop, mobile])

    assert [node_family.key for node_family in manifest.node_families] == [
        "section:section-content"
    ]
    assert manifest.issues == ()


def test_pipeline_responsive_manifest_uses_generic_structure_aliases() -> None:
    desktop = normalize_document(
        {
            "id": "page-1920",
            "name": "page-prestation-3-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 700},
            "children": [
                {
                    "id": "hero-1920",
                    "name": "section-hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 200},
                    "children": [
                        {
                            "id": "title-1920",
                            "name": "titre-h1-hero",
                            "type": "TEXT",
                            "characters": "Same title",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 40,
                                "width": 400,
                                "height": 40,
                            },
                        }
                    ],
                },
                {
                    "id": "cta-1920",
                    "name": "bandeau-gauche",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 300, "width": 1920, "height": 120},
                    "children": [
                        {
                            "id": "cta-text-1920",
                            "name": "texte-cta",
                            "type": "TEXT",
                            "characters": "Same CTA",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 320,
                                "width": 400,
                                "height": 40,
                            },
                        }
                    ],
                },
            ],
        }
    )
    mobile = normalize_document(
        {
            "id": "page-402",
            "name": "page-prestation-3-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 700},
            "children": [
                {
                    "id": "hero-402",
                    "name": "section-hero-main",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 200},
                    "children": [
                        {
                            "id": "title-402",
                            "name": "titre-h1-hero",
                            "type": "TEXT",
                            "characters": "Same title",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 40,
                                "width": 300,
                                "height": 40,
                            },
                        }
                    ],
                },
                {
                    "id": "cta-402",
                    "name": "bandeau-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 300, "width": 402, "height": 120},
                    "children": [
                        {
                            "id": "cta-text-402",
                            "name": "texte-cta",
                            "type": "TEXT",
                            "characters": "Same CTA",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 320,
                                "width": 300,
                                "height": 40,
                            },
                        }
                    ],
                },
            ],
        }
    )

    manifest = build_responsive_manifest([desktop, mobile])

    assert [node_family.key for node_family in manifest.node_families] == [
        "container:bandeau",
        "section:section-hero",
    ]
    assert manifest.issues == ()


def test_pipeline_responsive_manifest_strips_generic_content_suffixes() -> None:
    desktop = normalize_document(
        {
            "id": "page-1920",
            "name": "page-service-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 500},
            "children": [
                {
                    "id": "io-1920",
                    "name": "section-input-output-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 240},
                    "children": [
                        {
                            "id": "copy-1920",
                            "name": "texte-io",
                            "type": "TEXT",
                            "characters": "Inputs et outputs",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 40,
                                "width": 400,
                                "height": 40,
                            },
                        }
                    ],
                }
            ],
        }
    )
    mobile = normalize_document(
        {
            "id": "page-402",
            "name": "page-service-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 500},
            "children": [
                {
                    "id": "io-402",
                    "name": "section-input-output",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 240},
                    "children": [
                        {
                            "id": "copy-402",
                            "name": "texte-io",
                            "type": "TEXT",
                            "characters": "Inputs et outputs",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 40,
                                "width": 300,
                                "height": 40,
                            },
                        }
                    ],
                }
            ],
        }
    )

    manifest = build_responsive_manifest([desktop, mobile])

    assert [node_family.key for node_family in manifest.node_families] == [
        "section:section-input-output"
    ]
    assert manifest.issues == ()


def test_pipeline_responsive_manifest_merges_complementary_content_equivalents() -> None:
    desktop = normalize_document(
        {
            "id": "page-1920",
            "name": "page-service-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 500},
            "children": [
                {
                    "id": "service-1920",
                    "name": "section-service-detail",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 260},
                    "children": [
                        {
                            "id": "goal-1920",
                            "name": "texte-goal",
                            "type": "TEXT",
                            "characters": "Objectif commun",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 40,
                                "width": 400,
                                "height": 40,
                            },
                        },
                        {
                            "id": "copy-1920",
                            "name": "texte-copy",
                            "type": "TEXT",
                            "characters": "Description partagee",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 100,
                                "width": 400,
                                "height": 40,
                            },
                        },
                    ],
                }
            ],
        }
    )
    mobile = normalize_document(
        {
            "id": "page-402",
            "name": "page-service-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 500},
            "children": [
                {
                    "id": "service-402",
                    "name": "section-service-mobile",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 260},
                    "children": [
                        {
                            "id": "title-402",
                            "name": "titre-service",
                            "type": "TEXT",
                            "characters": "Titre mobile",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 20,
                                "width": 300,
                                "height": 40,
                            },
                        },
                        {
                            "id": "goal-402",
                            "name": "texte-goal",
                            "type": "TEXT",
                            "characters": "Objectif commun",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 80,
                                "width": 300,
                                "height": 40,
                            },
                        },
                        {
                            "id": "copy-402",
                            "name": "texte-copy",
                            "type": "TEXT",
                            "characters": "Description partagee",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 140,
                                "width": 300,
                                "height": 40,
                            },
                        },
                    ],
                }
            ],
        }
    )

    manifest = build_responsive_manifest([desktop, mobile])

    assert [issue.code for issue in manifest.issues] == ["content-conflict"]
    assert manifest.issues[0].key == "section:section-service-detail"
    assert manifest.issues[0].present_widths == (402, 1920)


def test_pipeline_responsive_manifest_keeps_footer_breakpoint_variants() -> None:
    desktop = normalize_document(
        {
            "id": "page-1920",
            "name": "page-footer-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 500},
            "children": [
                {
                    "id": "footer-1920",
                    "name": "footer-desktop",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 420, "width": 1920, "height": 80},
                    "children": [
                        {
                            "id": "copy-1920",
                            "name": "texte-footer",
                            "type": "TEXT",
                            "characters": "Tous droits reserves",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 440,
                                "width": 400,
                                "height": 40,
                            },
                        }
                    ],
                }
            ],
        }
    )
    mobile = normalize_document(
        {
            "id": "page-402",
            "name": "page-footer-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 500},
            "children": [
                {
                    "id": "footer-402",
                    "name": "footer-mobile",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 420, "width": 402, "height": 80},
                    "children": [
                        {
                            "id": "copy-402",
                            "name": "texte-footer",
                            "type": "TEXT",
                            "characters": "Tous droits reserves",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 440,
                                "width": 300,
                                "height": 40,
                            },
                        }
                    ],
                }
            ],
        }
    )

    manifest = build_responsive_manifest([desktop, mobile])

    assert [issue.key for issue in manifest.issues] == [
        "section:footer-desktop",
        "section:footer-mobile",
    ]


def test_pipeline_responsive_manifest_marks_content_changes_as_variants() -> None:
    desktop = normalize_document(
        {
            "id": "page-1920",
            "name": "page-prestation-3-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 800},
            "children": [
                {
                    "id": "faq-1920",
                    "name": "section-faq",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 300},
                    "children": [
                        {
                            "id": "question-1920",
                            "name": "titre-question",
                            "type": "TEXT",
                            "characters": "Question desktop",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 40,
                                "width": 600,
                                "height": 40,
                            },
                        }
                    ],
                }
            ],
        }
    )
    mobile = normalize_document(
        {
            "id": "page-402",
            "name": "page-prestation-3-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 900},
            "children": [
                {
                    "id": "faq-402",
                    "name": "section-faq",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 380},
                    "children": [
                        {
                            "id": "question-402",
                            "name": "titre-question",
                            "type": "TEXT",
                            "characters": "Question mobile",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 40,
                                "width": 360,
                                "height": 80,
                            },
                        }
                    ],
                }
            ],
        }
    )

    manifest = build_responsive_manifest([desktop, mobile])

    assert manifest.family == "page-prestation-3"
    assert manifest.base_width == 1920
    assert manifest.breakpoints == (402,)
    assert manifest.node_families[0].decision is ResponsiveDecision.BREAKPOINT_VARIANT
    assert manifest.issues[0].code == "content-conflict"
    assert manifest.issues[0].present_widths == (402, 1920)
    assert manifest.issues[0].missing_widths == ()
    assert manifest.issues[0].signature_count == 2
    assert manifest.issues[0].difference_kind == "content-delta"
    assert manifest.issues[0].node_role == "faq"
    assert manifest.issues[0].contract_rule == "stable-responsive-content"
    assert manifest.issues[0].contract_action == "align-copy-or-declare-intentional-variant"
    assert manifest.issues[0].contract_risk == "responsive-content-drift"


def test_pipeline_responsive_manifest_classifies_order_only_content_variants() -> None:
    desktop = normalize_document(
        {
            "id": "page-1920",
            "name": "page-prestation-3-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 800},
            "children": [
                {
                    "id": "cases-1920",
                    "name": "section-card-list",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 300},
                    "children": [
                        {
                            "id": "case-a-1920",
                            "name": "case-a",
                            "type": "TEXT",
                            "characters": "Alpha",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 40,
                                "width": 300,
                                "height": 40,
                            },
                        },
                        {
                            "id": "case-b-1920",
                            "name": "case-b",
                            "type": "TEXT",
                            "characters": "Beta",
                            "absoluteBoundingBox": {
                                "x": 440,
                                "y": 40,
                                "width": 300,
                                "height": 40,
                            },
                        },
                    ],
                }
            ],
        }
    )
    mobile = normalize_document(
        {
            "id": "page-402",
            "name": "page-prestation-3-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 900},
            "children": [
                {
                    "id": "cases-402",
                    "name": "section-card-list",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 380},
                    "children": [
                        {
                            "id": "case-b-402",
                            "name": "case-b",
                            "type": "TEXT",
                            "characters": "Beta",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 40,
                                "width": 360,
                                "height": 40,
                            },
                        },
                        {
                            "id": "case-a-402",
                            "name": "case-a",
                            "type": "TEXT",
                            "characters": "Alpha",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 100,
                                "width": 360,
                                "height": 40,
                            },
                        },
                    ],
                }
            ],
        }
    )

    manifest = build_responsive_manifest([desktop, mobile])

    assert manifest.issues[0].code == "content-conflict"
    assert manifest.issues[0].difference_kind == "same-content-different-order"
    assert manifest.issues[0].node_role == "collection"
    assert manifest.issues[0].contract_rule == "stable-collection-order"
    assert manifest.issues[0].contract_action == "normalize-order-or-declare-carousel-variant"


def test_pipeline_responsive_manifest_uses_visual_order_for_content_signatures() -> None:
    desktop = normalize_document(
        {
            "id": "page-1920",
            "name": "page-content-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 800},
            "children": [
                {
                    "id": "content-1920",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 260},
                    "children": [
                        {
                            "id": "title-1920",
                            "name": "title",
                            "type": "TEXT",
                            "characters": "Alpha",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 40,
                                "width": 300,
                                "height": 40,
                            },
                        },
                        {
                            "id": "body-1920",
                            "name": "body",
                            "type": "TEXT",
                            "characters": "Beta",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 100,
                                "width": 300,
                                "height": 40,
                            },
                        },
                    ],
                }
            ],
        }
    )
    mobile = normalize_document(
        {
            "id": "page-402",
            "name": "page-content-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 800},
            "children": [
                {
                    "id": "content-402",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 260},
                    "children": [
                        {
                            "id": "body-402",
                            "name": "body",
                            "type": "TEXT",
                            "characters": "Beta",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 100,
                                "width": 360,
                                "height": 40,
                            },
                        },
                        {
                            "id": "title-402",
                            "name": "title",
                            "type": "TEXT",
                            "characters": "Alpha",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 40,
                                "width": 360,
                                "height": 40,
                            },
                        },
                    ],
                }
            ],
        }
    )

    manifest = build_responsive_manifest([desktop, mobile])

    assert manifest.node_families[0].decision is ResponsiveDecision.SHARED
    assert manifest.issues == ()


def test_pipeline_responsive_manifest_ignores_text_flow_whitespace_changes() -> None:
    desktop = normalize_document(
        {
            "id": "page-1920",
            "name": "page-prestation-3-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 800},
            "children": [
                {
                    "id": "cta-1920",
                    "name": "section-cta",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 300},
                    "children": [
                        {
                            "id": "title-1920",
                            "name": "titre-cta",
                            "type": "TEXT",
                            "characters": "Faites decoller vos projets",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 40,
                                "width": 600,
                                "height": 40,
                            },
                        }
                    ],
                }
            ],
        }
    )
    mobile = normalize_document(
        {
            "id": "page-402",
            "name": "page-prestation-3-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 900},
            "children": [
                {
                    "id": "cta-402",
                    "name": "section-cta",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 380},
                    "children": [
                        {
                            "id": "title-402",
                            "name": "titre-cta",
                            "type": "TEXT",
                            "characters": "Faites decoller\nvos projets",
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 40,
                                "width": 360,
                                "height": 80,
                            },
                        }
                    ],
                }
            ],
        }
    )

    manifest = build_responsive_manifest([desktop, mobile])

    assert manifest.node_families[0].decision is ResponsiveDecision.SHARED
    assert manifest.issues == ()


def test_pipeline_responsive_manifest_reports_missing_breakpoint_widths() -> None:
    desktop = normalize_document(
        {
            "id": "page-1920",
            "name": "page-prestation-3-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 800},
            "children": [
                {
                    "id": "only-desktop",
                    "name": "section-desktop-only",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 200},
                    "children": [
                        {
                            "id": "title-1920",
                            "name": "titre-h2-desktop-only",
                            "type": "TEXT",
                            "characters": "Desktop only",
                            "absoluteBoundingBox": {
                                "x": 100,
                                "y": 40,
                                "width": 400,
                                "height": 40,
                            },
                        }
                    ],
                }
            ],
        }
    )
    mobile = normalize_document(
        {
            "id": "page-402",
            "name": "page-prestation-3-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 900},
            "children": [],
        }
    )

    manifest = build_responsive_manifest([desktop, mobile])

    assert manifest.issues[0].code == "breakpoint-only"
    assert manifest.issues[0].present_widths == (1920,)
    assert manifest.issues[0].missing_widths == (402,)
    assert manifest.issues[0].signature_count == 1
    assert manifest.issues[0].difference_kind == "missing-breakpoint-node"
    assert manifest.issues[0].contract_rule == "stable-breakpoint-presence"
    assert manifest.issues[0].contract_action == "add-missing-node-or-declare-breakpoint-only"


def test_pipeline_responsive_manifest_rejects_duplicate_widths_in_same_family() -> None:
    first = normalize_document(
        {
            "id": "page-402-a",
            "name": "page-prestation-3-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 800},
            "children": [],
        }
    )
    second = normalize_document(
        {
            "id": "page-402-b",
            "name": "page-prestation-3-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 900},
            "children": [],
        }
    )

    with pytest.raises(ValueError, match="duplicate widths"):
        build_responsive_manifest([first, second])


def test_pipeline_orchestrator_does_not_use_removed_canonical_flow() -> None:
    pipeline = Pipeline()
    plan = pipeline.render_plan(
        {
            "id": "page",
            "name": "page-test-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 600},
            "children": [
                {
                    "id": "contact",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 200, "width": 402, "height": 300},
                    "children": [],
                }
            ],
        }
    )

    assert plan.width == 402
    assert plan.sections[0].layout_mode == "flow"


def test_pipeline_render_plan_orders_sections_by_vertical_position() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-section-order-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 600},
            "children": [
                {
                    "id": "footer",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 500, "width": 402, "height": 80},
                },
                {
                    "id": "hero",
                    "name": "section-hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                },
                {
                    "id": "content",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 160, "width": 402, "height": 250},
                },
            ],
        }
    )

    assert [section.name for section in plan.sections] == [
        "section-hero",
        "section-content",
        "footer",
    ]


def test_pipeline_render_plan_preserves_small_text_overhang_from_figma() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 600},
            "children": [
                {
                    "id": "footer",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 552, "width": 402, "height": 48},
                    "children": [
                        {
                            "id": "footer-text",
                            "name": "footer-text",
                            "type": "TEXT",
                            "characters": "Footer text",
                            "absoluteBoundingBox": {"x": 5, "y": 552, "width": 401, "height": 48},
                        }
                    ],
                }
            ],
        }
    )

    footer_text = plan.sections[0].nodes[0]

    assert footer_text.text == "Footer text"
    assert footer_text.bounds.x == 5
    assert footer_text.bounds.width == 401
    assert footer_text.bounds.right == 406


def test_pipeline_render_plan_preserves_centered_text_frame_overhang() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-contact-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 600},
            "children": [
                {
                    "id": "contact",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 120, "width": 402, "height": 220},
                    "children": [
                        {
                            "id": "contact-coords",
                            "name": "contact-coords",
                            "type": "TEXT",
                            "characters": "Mes coordonnees\n07.81.51.40.29\nbastien@example.com",
                            "style": {"textAlignHorizontal": "CENTER", "fontSize": 14},
                            "absoluteBoundingBox": {
                                "x": -29,
                                "y": 160,
                                "width": 460,
                                "height": 54,
                            },
                        }
                    ],
                }
            ],
        }
    )

    contact_text = plan.sections[0].nodes[0]

    assert contact_text.text.startswith("Mes coordonnees")
    assert contact_text.bounds.x == pytest.approx(-29)
    assert contact_text.bounds.width == pytest.approx(460)
    assert contact_text.bounds.right == pytest.approx(431)
    assert "content-text-contained-to-rail" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_diagnostics_flags_large_vertical_gap_between_sections() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-gap-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 1000},
            "children": [
                {
                    "id": "hero",
                    "name": "section-hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 100},
                },
                {
                    "id": "contact",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 500, "width": 402, "height": 200},
                },
            ],
        }
    )

    issue = _first_issue(plan, "large-vertical-gap")
    assert issue.related_node_id == "hero"
    assert issue.severity.value == "info"
    assert issue.metrics["gap"] == 400
    assert issue.metrics["gapRatio"] == 4.167
    assert issue.metrics["gapKind"] == "large-empty-space"
    assert issue.metrics["previousSectionName"] == "section-hero"
    assert issue.metrics["nextSectionName"] == "section-contact"
    assert issue.metrics["previousSectionRole"] == "hero"
    assert issue.metrics["nextSectionRole"] == "content"


def test_pipeline_expands_page_height_for_sections_below_declared_page() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 600},
            "children": [
                {
                    "id": "footer",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 520, "width": 402, "height": 200},
                }
            ],
        }
    )

    assert plan.height == pytest.approx(720)
    assert "section-after-page-bottom" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_expands_contact_section_content_before_clipping_diagnostics() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-contact-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 600},
            "children": [
                {
                    "id": "contact",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 200},
                    "children": [
                        {
                            "id": "form-text",
                            "name": "texte-formulaire",
                            "type": "TEXT",
                            "characters": "Message",
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 280,
                                "width": 300,
                                "height": 80,
                            },
                        }
                    ],
                }
            ],
        }
    )

    issue_codes = [issue.code for issue in plan.diagnostics]
    assert "section-content-clipped" not in issue_codes

    contact = plan.sections[0]
    assert contact.bounds.height == pytest.approx(272)
    assert plan.height == pytest.approx(600)

    issue = _first_issue(plan, "section-expanded-for-semantic-content")
    assert issue.node_id == "contact"
    assert issue.severity.value == "info"
    assert issue.metrics["contentBottom"] == 360
    assert issue.metrics["afterHeight"] == 272


def test_pipeline_diagnostics_ignore_structure_only_overflow_wrappers() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-wrapper-overflow-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 700},
            "children": [
                {
                    "id": "section",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 300},
                    "children": [
                        {
                            "id": "wide-wrapper",
                            "name": "layout-wrapper",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": -80,
                                "y": 120,
                                "width": 560,
                                "height": 260,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-content",
                                    "type": "TEXT",
                                    "characters": "Visible inside board",
                                    "absoluteBoundingBox": {
                                        "x": 24,
                                        "y": 140,
                                        "width": 240,
                                        "height": 40,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    assert "node-out-of-section-horizontal" not in [issue.code for issue in plan.diagnostics]
    assert "section-content-clipped" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_diagnostics_ignore_edge_decorative_asset_overflow() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-edge-decor-diagnostics-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 420},
            "children": [
                {
                    "id": "section",
                    "name": "section-callout",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 180},
                    "children": [
                        {
                            "id": "decor",
                            "name": "image-droite-callout",
                            "type": "RECTANGLE",
                            "pipelineImageUrl": "https://images.example/decor.png",
                            "absoluteBoundingBox": {
                                "x": 360,
                                "y": 235,
                                "width": 42,
                                "height": 72,
                            },
                        },
                    ],
                }
            ],
        }
    )

    issue_codes = [issue.code for issue in plan.diagnostics]

    assert "section-expanded-for-semantic-content" not in issue_codes
    assert "section-content-clipped" not in issue_codes


def test_pipeline_diagnostics_flags_overlapping_sections() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-overlap-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 700},
            "children": [
                {
                    "id": "first",
                    "name": "section-first",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 300},
                },
                {
                    "id": "second",
                    "name": "section-second",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 250, "width": 402, "height": 200},
                },
            ],
        }
    )

    issue = _first_issue(plan, "section-overlap")
    assert issue.node_id == "second"
    assert issue.related_node_id == "first"
    assert issue.metrics["overlap"] == 50


def test_pipeline_diagnostics_use_text_line_height_for_overlap_detection() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-text-overlap-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
            "children": [
                {
                    "id": "content",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 300},
                    "children": [
                        {
                            "id": "title",
                            "name": "titre-h3-content",
                            "type": "TEXT",
                            "characters": "H3 - Content",
                            "style": {"fontSize": 24, "lineHeightPx": 24},
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 80,
                                "width": 320,
                                "height": 70,
                            },
                        },
                        {
                            "id": "body",
                            "name": "texte-content",
                            "type": "TEXT",
                            "characters": "Body text",
                            "style": {"fontSize": 12, "lineHeightPx": 16},
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 132,
                                "width": 320,
                                "height": 40,
                            },
                        },
                    ],
                }
            ],
        }
    )

    assert "content-overlap" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_diagnostics_use_estimated_text_width_for_centered_label_overlap() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-label-overlap-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "content",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                    "children": [
                        {
                            "id": "label-1",
                            "name": "label-one",
                            "type": "TEXT",
                            "characters": "Idees",
                            "style": {
                                "fontSize": 12,
                                "lineHeightPx": 12,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 120,
                                "y": 40,
                                "width": 100,
                                "height": 16,
                            },
                        },
                        {
                            "id": "label-2",
                            "name": "label-two",
                            "type": "TEXT",
                            "characters": "Expertise",
                            "style": {
                                "fontSize": 12,
                                "lineHeightPx": 12,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 190,
                                "y": 40,
                                "width": 100,
                                "height": 16,
                            },
                        },
                    ],
                }
            ],
        }
    )

    assert "content-overlap" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_ignores_empty_section_frames_before_overlap_analysis() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-empty-section-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 700},
            "children": [
                {
                    "id": "content",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 200},
                    "children": [
                        {
                            "id": "title",
                            "name": "titre-h2-content",
                            "type": "TEXT",
                            "characters": "Visible content",
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 120,
                                "width": 250,
                                "height": 40,
                            },
                        }
                    ],
                },
                {
                    "id": "empty",
                    "name": "section-empty",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 200},
                    "children": [
                        {
                            "id": "empty-child",
                            "name": "section-empty-child",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 100,
                                "width": 402,
                                "height": 200,
                            },
                        }
                    ],
                },
            ],
        }
    )

    assert [section.name for section in plan.sections] == ["section-content"]
    assert "section-overlap" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_renders_section_solid_fills_as_section_styles() -> None:
    payload = {
        "id": "page",
        "name": "page-section-fill-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 300},
        "children": [
            {
                "id": "hero",
                "name": "section-hero",
                "type": "FRAME",
                "fills": [
                    {
                        "type": "SOLID",
                        "color": {
                            "r": 0,
                            "g": 0.10980392247438431,
                            "b": 0.3490196168422699,
                            "a": 1,
                        },
                    }
                ],
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                "children": [
                    {
                        "id": "title",
                        "name": "titre-h1-hero",
                        "type": "TEXT",
                        "characters": "White title",
                        "absoluteBoundingBox": {
                            "x": 20,
                            "y": 30,
                            "width": 200,
                            "height": 40,
                        },
                    }
                ],
            }
        ],
    }

    pipeline = Pipeline()
    plan = pipeline.render_plan(payload)
    html = pipeline.render_static_html(payload)

    assert plan.sections[0].style["background-color"] == "rgb(0, 28, 89)"
    assert "background-color:rgb(0, 28, 89)" in html


def test_pipeline_predefined_text_names_keep_font_color() -> None:
    payload = {
        "id": "page",
        "name": "page-text-colors-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 260},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 220},
                "children": [
                    {
                        "id": "title",
                        "name": "titre-h1-hero",
                        "type": "TEXT",
                        "characters": "Titre",
                        "fills": [
                            {
                                "type": "SOLID",
                                "color": {"r": 0, "g": 0.1, "b": 0.35, "a": 1},
                            }
                        ],
                        "absoluteBoundingBox": {"x": 24, "y": 24, "width": 140, "height": 24},
                    },
                    {
                        "id": "body",
                        "name": "texte-hero",
                        "type": "TEXT",
                        "characters": "Texte",
                        "fills": [
                            {
                                "type": "SOLID",
                                "color": {"r": 1, "g": 0.2, "b": 0, "a": 1},
                            }
                        ],
                        "absoluteBoundingBox": {"x": 24, "y": 56, "width": 140, "height": 24},
                    },
                    {
                        "id": "label",
                        "name": "label-service",
                        "type": "TEXT",
                        "characters": "Label",
                        "fills": [
                            {
                                "type": "SOLID",
                                "color": {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1},
                            }
                        ],
                        "absoluteBoundingBox": {"x": 24, "y": 88, "width": 140, "height": 24},
                    },
                    {
                        "id": "link-label",
                        "name": "link-label-card",
                        "type": "TEXT",
                        "characters": "Lien",
                        "fills": [
                            {
                                "type": "SOLID",
                                "color": {"r": 0.2, "g": 0.4, "b": 0.6, "a": 1},
                            }
                        ],
                        "absoluteBoundingBox": {"x": 24, "y": 120, "width": 140, "height": 24},
                    },
                    {
                        "id": "placeholder",
                        "name": "placeholder-email",
                        "type": "TEXT",
                        "characters": "Email",
                        "fills": [
                            {
                                "type": "SOLID",
                                "color": {"r": 0.4, "g": 0.2, "b": 0.1, "a": 1},
                            }
                        ],
                        "absoluteBoundingBox": {"x": 24, "y": 152, "width": 140, "height": 24},
                    },
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    expected = {
        "titre-h1-hero": "rgb(0, 26, 89)",
        "texte-hero": "rgb(255, 51, 0)",
        "label-service": "rgb(26, 51, 76)",
        "link-label-card": "rgb(51, 102, 153)",
        "placeholder-email": "rgb(102, 51, 26)",
    }

    for name, color in expected.items():
        node = next(node for node in plan.sections[0].nodes if node.name == name)
        assert node.style["color"] == color
        assert f"color:{color}" in html


def test_pipeline_text_style_override_uniform_fills_keep_font_color() -> None:
    payload = {
        "id": "page",
        "name": "page-text-override-color-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                "children": [
                    {
                        "id": "title",
                        "name": "titre-h2-style",
                        "type": "TEXT",
                        "characters": "Titre style",
                        "style": {"fontFamily": "Inter", "fontSize": 20},
                        "characterStyleOverrides": [1] * len("Titre style"),
                        "styleOverrideTable": {
                            "1": {
                                "fills": [
                                    {
                                        "type": "SOLID",
                                        "color": {"r": 1, "g": 0.2, "b": 0, "a": 1},
                                    }
                                ]
                            }
                        },
                        "absoluteBoundingBox": {"x": 24, "y": 32, "width": 180, "height": 28},
                    }
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    title = plan.sections[0].nodes[0]

    assert title.style["color"] == "rgb(255, 51, 0)"
    assert "color:rgb(255, 51, 0)" in html


def test_pipeline_text_style_override_mixed_fills_use_dominant_font_color() -> None:
    payload = {
        "id": "page",
        "name": "page-text-mixed-color-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                "children": [
                    {
                        "id": "title",
                        "name": "titre-h2-style",
                        "type": "TEXT",
                        "characters": "ABBB",
                        "style": {"fontFamily": "Inter", "fontSize": 20},
                        "characterStyleOverrides": [1, 2, 2, 2],
                        "styleOverrideTable": {
                            "1": {
                                "fills": [
                                    {
                                        "type": "SOLID",
                                        "color": {"r": 1, "g": 0.2, "b": 0, "a": 1},
                                    }
                                ]
                            },
                            "2": {
                                "fills": [
                                    {
                                        "type": "SOLID",
                                        "color": {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1},
                                    }
                                ]
                            },
                        },
                        "absoluteBoundingBox": {"x": 24, "y": 32, "width": 180, "height": 28},
                    }
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    title = plan.sections[0].nodes[0]

    assert title.style["color"] == "rgb(26, 51, 76)"
    assert "color:rgb(26, 51, 76)" in html


def test_pipeline_text_style_overrides_render_inline_runs() -> None:
    payload = {
        "id": "page",
        "name": "page-text-runs-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                "children": [
                    {
                        "id": "title",
                        "name": "titre-h2-style",
                        "type": "TEXT",
                        "characters": "ABBB",
                        "style": {"fontFamily": "Inter", "fontSize": 20},
                        "characterStyleOverrides": [1, 2, 2, 2],
                        "styleOverrideTable": {
                            "1": {
                                "fontWeight": 700,
                                "italic": True,
                                "textDecoration": "UNDERLINE",
                                "fills": [
                                    {
                                        "type": "SOLID",
                                        "color": {"r": 1, "g": 0.2, "b": 0, "a": 1},
                                    }
                                ],
                            },
                            "2": {
                                "fontWeight": 400,
                                "fills": [
                                    {
                                        "type": "SOLID",
                                        "color": {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1},
                                    }
                                ],
                            },
                        },
                        "absoluteBoundingBox": {"x": 24, "y": 32, "width": 180, "height": 28},
                    }
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    title = plan.sections[0].nodes[0]

    assert [run.text for run in title.text_runs] == ["A", "BBB"]
    assert title.text_runs[0].style["color"] == "rgb(255, 51, 0)"
    assert title.text_runs[0].style["font-style"] == "italic"
    assert title.text_runs[0].style["text-decoration"] == "underline"
    assert title.text_runs[1].style["color"] == "rgb(26, 51, 76)"
    assert '<span class="pipeline-text-content">' in html
    assert "text-decoration:underline" in html
    assert ">A</span>" in html
    assert ">BBB</span>" in html


def test_pipeline_text_normalizes_figma_unicode_line_separators() -> None:
    payload = {
        "id": "page",
        "name": "page-line-separator-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
        "children": [
            {
                "id": "section",
                "name": "section-hero",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                "children": [
                    {
                        "id": "title",
                        "name": "titre-h1-hero",
                        "type": "TEXT",
                        "characters": "Ensemble,faisons decoller\u2028vos innovations !",
                        "style": {"fontFamily": "Inter", "fontSize": 20},
                        "absoluteBoundingBox": {"x": 32, "y": 0, "width": 338, "height": 74},
                    }
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    title = plan.sections[0].nodes[0]

    assert title.text == "Ensemble,faisons decoller\nvos innovations !"
    assert "\u2028" not in html
    assert "Ensemble,faisons decoller\nvos innovations !" in html


def test_pipeline_text_renders_figma_unordered_line_markers() -> None:
    payload = {
        "id": "page",
        "name": "page-list-lines-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 260},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 220},
                "children": [
                    {
                        "id": "copy",
                        "name": "texte-infos",
                        "type": "TEXT",
                        "characters": "Intro\n\nPremier point\nSecond point\nOutro",
                        "lineTypes": [
                            "NONE",
                            "NONE",
                            "UNORDERED",
                            "UNORDERED",
                            "NONE",
                        ],
                        "lineIndentations": [0, 0, 1, 1, 0],
                        "style": {
                            "fontFamily": "Inter",
                            "fontSize": 12,
                            "lineHeightPx": 14,
                            "textAlignHorizontal": "LEFT",
                        },
                        "absoluteBoundingBox": {
                            "x": 24,
                            "y": 24,
                            "width": 220,
                            "height": 120,
                        },
                    }
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    copy_node = plan.sections[0].nodes[0]

    assert copy_node.attributes["textLines"][2] == {
        "text": "Premier point",
        "type": "unordered",
        "indent": 1,
    }
    assert 'class="pipeline-text-content pipeline-list-text"' in html
    assert html.count('class="pipeline-list-line" data-list-type="unordered"') == 2
    assert '.pipeline-list-line[data-list-type="unordered"]::before' in html


def test_pipeline_text_fill_override_table_keeps_font_color() -> None:
    payload = {
        "id": "page",
        "name": "page-text-fill-override-color-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                "children": [
                    {
                        "id": "title",
                        "name": "titre-h2-style",
                        "type": "TEXT",
                        "characters": "Titre",
                        "style": {"fontFamily": "Inter", "fontSize": 20},
                        "characterStyleOverrides": [7] * len("Titre"),
                        "styleOverrideTable": {"7": {"fontSize": 20}},
                        "fillOverrideTable": {
                            "7": {
                                "fills": [
                                    {
                                        "type": "SOLID",
                                        "color": {"r": 0.2, "g": 0.4, "b": 0.6, "a": 1},
                                    }
                                ]
                            }
                        },
                        "absoluteBoundingBox": {"x": 24, "y": 32, "width": 180, "height": 28},
                    }
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    title = plan.sections[0].nodes[0]

    assert title.style["color"] == "rgb(51, 102, 153)"
    assert "color:rgb(51, 102, 153)" in html


def test_pipeline_render_plan_treats_full_band_nodes_as_background() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-background-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 700},
            "children": [
                {
                    "id": "hero",
                    "name": "section-hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 650},
                    "children": [
                        {
                            "id": "band",
                            "name": "bandeau-full-hero",
                            "type": "FRAME",
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "color": {"r": 0, "g": 0.1098, "b": 0.349, "a": 1},
                                }
                            ],
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 1920,
                                "height": 942,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h1-hero",
                                    "type": "TEXT",
                                    "characters": "Hero",
                                    "absoluteBoundingBox": {
                                        "x": 120,
                                        "y": 120,
                                        "width": 400,
                                        "height": 80,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    band = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert band.name == "bandeau-full-hero"
    assert band.layer == "background"
    assert band.bounds.height == pytest.approx(650)
    assert "background-overflow-contained" in issue_codes
    assert "section-content-clipped" not in issue_codes


def test_pipeline_semantic_adjustments_snap_bandeau_background_to_section_edges() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-snap-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "section",
                    "name": "bandeau-cta",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 20, "width": 402, "height": 100},
                    "children": [
                        _raw_box("bg", "bg-bandeau-cta", 28, 22, 374, 96),
                        {
                            "id": "title",
                            "name": "titre-bandeau",
                            "type": "TEXT",
                            "characters": "Bandeau",
                            "absoluteBoundingBox": {
                                "x": 80,
                                "y": 50,
                                "width": 180,
                                "height": 30,
                            },
                        },
                    ],
                }
            ],
        }
    )

    background = _find_node(plan.sections[0].nodes[0], "bg-bandeau-cta")

    assert background.bounds.x == pytest.approx(28)
    assert background.bounds.y == pytest.approx(22)
    assert background.bounds.width == pytest.approx(374)
    assert background.bounds.height == pytest.approx(96)
    assert "band-background-snapped-to-section" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_do_not_shrink_slightly_larger_bandeau_background() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-snap-large-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "section",
                    "name": "bandeau-cta",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 20, "width": 402, "height": 100},
                    "children": [
                        _raw_box("bg", "bg-bandeau-cta", 0, 19, 402, 103),
                        {
                            "id": "title",
                            "name": "titre-bandeau",
                            "type": "TEXT",
                            "characters": "Bandeau",
                            "absoluteBoundingBox": {
                                "x": 80,
                                "y": 50,
                                "width": 180,
                                "height": 30,
                            },
                        },
                    ],
                }
            ],
        }
    )

    background = _find_node(plan.sections[0].nodes[0], "bg-bandeau-cta")

    assert background.bounds.x == pytest.approx(0)
    assert background.bounds.y == pytest.approx(19)
    assert background.bounds.width == pytest.approx(402)
    assert background.bounds.height == pytest.approx(103)


def test_pipeline_semantic_adjustments_preserve_band_background_gap_for_edge_decor() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-edge-decor-gap-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 320},
            "children": [
                {
                    "id": "section",
                    "name": "bandeau-droite-accompagnement",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 40, "width": 834, "height": 207},
                    "children": [
                        _raw_box("bg", "bg-embedded-bandeau", 32, 40, 802, 207),
                        _raw_box("decor", "image-montgolfiere", 8, 46, 82, 154),
                        {
                            "id": "title",
                            "name": "titre-bandeau",
                            "type": "TEXT",
                            "characters": "Titre du bandeau",
                            "absoluteBoundingBox": {
                                "x": 190,
                                "y": 80,
                                "width": 220,
                                "height": 40,
                            },
                        },
                    ],
                }
            ],
        }
    )

    background = _find_node(plan.sections[0].nodes[0], "bg-embedded-bandeau")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert background.bounds.x == pytest.approx(32)
    assert background.bounds.width == pytest.approx(802)
    assert "band-background-snapped-to-section" not in issue_codes


def test_pipeline_semantic_adjustments_preserve_large_authored_band_background_gap() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-authored-gap-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 240},
            "children": [
                {
                    "id": "section",
                    "name": "bandeau-principe",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 40, "width": 834, "height": 121},
                    "children": [
                        _raw_box("bg", "bg-bandeau-principe", 0, 40, 752, 121),
                        {
                            "id": "label",
                            "name": "texte-bandeau-principe",
                            "type": "TEXT",
                            "characters": "Notre expertise",
                            "absoluteBoundingBox": {
                                "x": 300,
                                "y": 90,
                                "width": 160,
                                "height": 20,
                            },
                        },
                    ],
                }
            ],
        }
    )

    background = _find_node(plan.sections[0].nodes[0], "bg-bandeau-principe")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert background.bounds.x == pytest.approx(0)
    assert background.bounds.width == pytest.approx(752)
    assert "band-background-snapped-to-section" not in issue_codes


def test_pipeline_semantic_adjustments_expand_band_columns_past_structure_wrapper() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-wrapper-columns-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 320},
            "children": [
                {
                    "id": "section",
                    "name": "bandeau-droite-accompagnement",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 40, "width": 834, "height": 207},
                    "children": [
                        _raw_box("bg", "bg-embedded-bandeau", 32, 40, 802, 207),
                        _raw_box("decor", "image-montgolfiere", 8, 46, 82, 154),
                        {
                            "id": "content",
                            "name": "section-accompagnement-cta-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 186,
                                "y": 40,
                                "width": 462,
                                "height": 207,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h4-accueil-decoller-projets",
                                    "type": "TEXT",
                                    "characters": (
                                        "Faites decoller vos projets grace\n"
                                        "a notre accompagnement sur-mesure"
                                    ),
                                    "style": {
                                        "fontFamily": "Inter",
                                        "fontSize": 20,
                                        "lineHeightPx": 20,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 186,
                                        "y": 70,
                                        "width": 179,
                                        "height": 146,
                                    },
                                },
                                {
                                    "id": "copy",
                                    "name": "texte-accomp",
                                    "type": "TEXT",
                                    "characters": (
                                        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                                        "Vestibulum quis consequat lacus, sed tristique augue. "
                                        "Donec efficitur, sapien vitae cursus dictum, arcu velit."
                                    ),
                                    "style": {
                                        "fontFamily": "Inter",
                                        "fontSize": 14,
                                        "lineHeightPx": 14,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 421,
                                        "y": 42,
                                        "width": 226,
                                        "height": 199,
                                    },
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    )

    title = _find_section_node(plan.sections[0], "titre-h4-accueil-decoller-projets")
    copy_text = _find_section_node(plan.sections[0], "texte-accomp")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert title.bounds.width == pytest.approx(179)
    assert copy_text.bounds.width == pytest.approx(226)
    assert copy_text.bounds.x == pytest.approx(421)
    assert "band-text-column-visual-gap-expanded" not in issue_codes


def test_pipeline_semantic_adjustments_separate_desktop_band_text_visual_columns() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-visual-gap-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 320},
            "children": [
                {
                    "id": "section",
                    "name": "bandeau-feature",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 40, "width": 1920, "height": 218},
                    "children": [
                        _raw_box("bg", "bg-bandeau", 0, 40, 1920, 218),
                        {
                            "id": "title",
                            "name": "titre-h4-feature",
                            "type": "TEXT",
                            "characters": (
                                "Faites decoller vos projets grace\n"
                                "a notre accompagnement sur-mesure"
                            ),
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 38,
                                "lineHeightPx": 42,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 428.5,
                                "y": 105,
                                "width": 536,
                                "height": 84,
                            },
                        },
                        {
                            "id": "copy",
                            "name": "texte-feature",
                            "type": "TEXT",
                            "characters": (
                                "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                                "Vestibulum quis consequat lacus, sed tristique augue."
                            ),
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 24,
                                "lineHeightPx": 25,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 964.5,
                                "y": 40,
                                "width": 527,
                                "height": 218,
                            },
                        },
                    ],
                }
            ],
        }
    )

    title = _find_section_node(plan.sections[0], "titre-h4-feature")
    copy_text = _find_section_node(plan.sections[0], "texte-feature")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert title.bounds.x == pytest.approx(428.5)
    assert title.bounds.width == pytest.approx(536)
    assert copy_text.bounds.x == pytest.approx(964.5)
    assert copy_text.bounds.width == pytest.approx(527)
    assert "band-heading-text-column-rebalanced" not in issue_codes


def test_pipeline_semantic_adjustments_keeps_wrapping_band_text_columns() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-wrapping-text-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 320},
            "children": [
                {
                    "id": "section",
                    "name": "bandeau-feature",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 40, "width": 1920, "height": 218},
                    "children": [
                        _raw_box("bg", "bg-bandeau", 0, 40, 1920, 218),
                        {
                            "id": "title",
                            "name": "titre-h4-feature",
                            "type": "TEXT",
                            "characters": (
                                "Projets tutores, parce que notre metier c'est aussi "
                                "de transmettre notre savoir faire"
                            ),
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 32,
                                "lineHeightPx": 42,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 487,
                                "y": 40,
                                "width": 369,
                                "height": 218,
                            },
                        },
                        {
                            "id": "copy",
                            "name": "texte-feature",
                            "type": "TEXT",
                            "characters": (
                                "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                                "Vestibulum quis consequat lacus, sed tristique augue."
                            ),
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 24,
                                "lineHeightPx": 25,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 886,
                                "y": 40,
                                "width": 567,
                                "height": 218,
                            },
                        },
                    ],
                }
            ],
        }
    )

    copy_text = _find_section_node(plan.sections[0], "texte-feature")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert copy_text.bounds.x == pytest.approx(886)
    assert "band-text-column-visual-gap-expanded" not in issue_codes


def test_pipeline_semantic_adjustments_preserves_explicit_band_heading_column() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-heading-balance-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 320},
            "children": [
                {
                    "id": "section",
                    "name": "bandeau-droite-accompagnement",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 40, "width": 1920, "height": 218},
                    "children": [
                        _raw_box("bg", "bg-embedded-bandeau", 31, 40, 1889, 215),
                        {
                            "id": "content",
                            "name": "section-accompagnement-cta-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 442,
                                "y": 75,
                                "width": 1036,
                                "height": 174,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h4-accueil-decoller-projets",
                                    "type": "TEXT",
                                    "characters": (
                                        "Faites decoller vos projets grace\n"
                                        "a notre accompagnement sur-mesure"
                                    ),
                                    "style": {
                                        "fontFamily": "Inter",
                                        "fontSize": 32,
                                        "lineHeightPx": 42,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 442,
                                        "y": 81,
                                        "width": 477,
                                        "height": 168,
                                    },
                                },
                                {
                                    "id": "copy",
                                    "name": "texte-accomp",
                                    "type": "TEXT",
                                    "characters": (
                                        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                                        "Vestibulum quis consequat lacus, sed tristique augue. "
                                        "Donec efficitur, sapien vitae cursus dictum, arcu velit "
                                        "feugiat risus, a mollis ipsum sem at libero."
                                    ),
                                    "style": {
                                        "fontFamily": "Inter",
                                        "fontSize": 20,
                                        "lineHeightPx": 20,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 935,
                                        "y": 75,
                                        "width": 543,
                                        "height": 160,
                                    },
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    )

    title = _find_section_node(plan.sections[0], "titre-h4-accueil-decoller-projets")
    copy_text = _find_section_node(plan.sections[0], "texte-accomp")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert title.bounds.width == pytest.approx(477)
    assert copy_text.bounds.width == pytest.approx(543)
    assert title.bounds.right + 16 <= copy_text.bounds.x
    assert "band-heading-text-column-rebalanced" not in issue_codes


def test_pipeline_semantic_adjustments_preserve_nested_band_background_height() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-background-padding-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 980},
            "children": [
                {
                    "id": "section",
                    "name": "bandeau-droite-accompagnement",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 765, "width": 402, "height": 174},
                    "children": [
                        {
                            "id": "content",
                            "name": "section-accompagnement-cta-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": -46,
                                "y": 765,
                                "width": 448,
                                "height": 161.5,
                            },
                            "children": [
                                _raw_box("bg", "bg-embedded-bandeau", -46, 765, 448, 161.5),
                                {
                                    "id": "title",
                                    "name": "titre-h4-accueil-decoller-projets",
                                    "type": "TEXT",
                                    "characters": "Faites decoller vos projets",
                                    "style": {
                                        "fontFamily": "Inter",
                                        "fontSize": 14,
                                        "lineHeightPx": 12,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 106.5,
                                        "y": 780.5,
                                        "width": 189,
                                        "height": 48,
                                    },
                                },
                                {
                                    "id": "copy",
                                    "name": "texte-accomp",
                                    "type": "TEXT",
                                    "characters": (
                                        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                                        "Vestibulum quis consequat lacus, sed tristique augue. "
                                        "Donec efficitur, sapien vitae cursus dictum."
                                    ),
                                    "style": {
                                        "fontFamily": "Inter",
                                        "fontSize": 11,
                                        "lineHeightPx": 11,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 63,
                                        "y": 838.5,
                                        "width": 276,
                                        "height": 88,
                                    },
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    )

    background = _find_section_node(plan.sections[0], "bg-embedded-bandeau")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert background.bounds.height == pytest.approx(161.5)
    assert "band-background-padded-to-content" not in issue_codes


def test_pipeline_content_rails_separate_overlapping_text_columns() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-overlapping-columns-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 500},
            "children": [
                {
                    "id": "section",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 500},
                    "children": [
                        {
                            "id": "left",
                            "name": "texte-left",
                            "type": "TEXT",
                            "characters": "Left column",
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 16,
                                "lineHeightPx": 18,
                            },
                            "absoluteBoundingBox": {
                                "x": 171,
                                "y": 100,
                                "width": 260,
                                "height": 80,
                            },
                        },
                        {
                            "id": "right",
                            "name": "texte-right",
                            "type": "TEXT",
                            "characters": "Right column",
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 16,
                                "lineHeightPx": 18,
                            },
                            "absoluteBoundingBox": {
                                "x": 403,
                                "y": 100,
                                "width": 260,
                                "height": 120,
                            },
                        },
                    ],
                }
            ],
        }
    )

    left = _find_section_node(plan.sections[0], "texte-left")
    right = _find_section_node(plan.sections[0], "texte-right")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert left.bounds.x == pytest.approx(171)
    assert left.bounds.width == pytest.approx(260)
    assert right.bounds.x == pytest.approx(403)
    assert right.bounds.width == pytest.approx(260)
    assert "content-text-row-contained-to-rail" not in issue_codes


def test_pipeline_diagnostics_flags_horizontal_section_overflow() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-overflow-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 500},
            "children": [
                {
                    "id": "wide",
                    "name": "section-wide",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 450, "height": 200},
                }
            ],
        }
    )

    issue = _first_issue(plan, "section-outside-page-right")
    assert issue.node_id == "wide"
    assert issue.metrics["right"] == 450


def test_pipeline_diagnostics_allow_minor_horizontal_section_bleed() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-minor-bleed-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 500},
            "children": [
                {
                    "id": "bleed",
                    "name": "bandeau-droite-accompagnement",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": -10, "y": 100, "width": 854, "height": 200},
                }
            ],
        }
    )

    issue_codes = [issue.code for issue in plan.diagnostics]

    assert "section-outside-page-left" not in issue_codes
    assert "section-outside-page-right" not in issue_codes


def test_pipeline_expands_section_for_original_outlying_content() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-section-content-overflow-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 320},
            "children": [
                {
                    "id": "first",
                    "name": "section-first",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 80, "width": 402, "height": 100},
                    "children": [
                        {
                            "id": "body",
                            "name": "texte-body",
                            "type": "TEXT",
                            "characters": "Content that sits below the source section.",
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 150,
                                "width": 260,
                                "height": 50,
                            },
                        }
                    ],
                },
                {
                    "id": "second",
                    "name": "section-second",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 180, "width": 402, "height": 80},
                    "children": [
                        {
                            "id": "next-body",
                            "name": "texte-next",
                            "type": "TEXT",
                            "characters": "Next section",
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 200,
                                "width": 260,
                                "height": 30,
                            },
                        }
                    ],
                },
            ],
        }
    )

    first, second = plan.sections

    assert first.bounds.height == pytest.approx(132)
    assert first.bounds.bottom == pytest.approx(212)
    assert second.bounds.y == pytest.approx(212)
    assert "section-expanded-for-semantic-content" in [issue.code for issue in plan.diagnostics]
    assert "section-content-clipped" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_exports_render_plan_and_minimal_html_without_removed_templates() -> None:
    pipeline = Pipeline()
    payload = {
        "id": "page",
        "name": "page-export-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
        "children": [
            {
                "id": "hero",
                "name": "section-hero",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 200},
                "children": [
                    {
                        "id": "title",
                        "name": "titre-h1-export",
                        "type": "TEXT",
                        "characters": "Title - <Export>",
                        "style": {
                            "fontFamily": "Inter",
                            "fontSize": 32,
                            "fontWeight": 700,
                            "letterSpacing": -0.5,
                        },
                        "fills": [
                            {
                                "type": "SOLID",
                                "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                            }
                        ],
                        "absoluteBoundingBox": {"x": 20, "y": 40, "width": 240, "height": 50},
                    },
                    {
                        "id": "image",
                        "name": "image-export",
                        "type": "RECTANGLE",
                        "pipelineImageUrl": "https://images.example/export.png",
                        "absoluteBoundingBox": {"x": 20, "y": 100, "width": 120, "height": 90},
                    },
                ],
            }
        ],
    }

    plan_payload = pipeline.render_plan_payload(payload)
    html = pipeline.render_static_html(payload)

    assert plan_payload["page"]["width"] == 402
    assert plan_payload["sections"][0]["nodes"][0]["text"] == "Title - <Export>"
    assert plan_payload["sections"][0]["nodes"][0]["style"]["font-size"] == "32px"
    assert plan_payload["sections"][0]["nodes"][0]["style"]["letter-spacing"] == "-0.5px"
    assert (
        plan_payload["sections"][0]["nodes"][1]["assetUrl"] == "https://images.example/export.png"
    )
    assert 'class="pipeline-page"' in html
    assert "Title - &lt;Export&gt;" in html
    assert '<img class="pipeline-img" src="https://images.example/export.png"' in html
    assert "font-family:'Inter','Segoe UI',Arial,sans-serif" in html


def test_pipeline_image_assets_trust_exported_asset_opacity() -> None:
    payload = {
        "id": "page",
        "name": "page-image-opacity-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 240},
        "children": [
            {
                "id": "section",
                "name": "section-media",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 200},
                "children": [
                    {
                        "id": "image",
                        "name": "image-portrait",
                        "type": "RECTANGLE",
                        "opacity": 0.42,
                        "pipelineImageUrl": "https://images.example/portrait.png",
                        "absoluteBoundingBox": {"x": 20, "y": 40, "width": 160, "height": 100},
                    }
                ],
            }
        ],
    }

    pipeline = Pipeline()
    plan = pipeline.render_plan(payload)
    plan_payload = pipeline.render_plan_payload(payload)
    html = pipeline.render_static_html(payload)
    image = plan.sections[0].nodes[0]

    assert image.asset_url == "https://images.example/portrait.png"
    assert "opacity" not in image.style
    assert "opacity" not in plan_payload["sections"][0]["nodes"][0]["style"]
    assert "opacity:0.42" not in html


def test_pipeline_image_assets_do_not_reapply_image_fill_opacity() -> None:
    payload = {
        "id": "page",
        "name": "page-image-fill-opacity-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 240},
        "children": [
            {
                "id": "section",
                "name": "section-media",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 200},
                "children": [
                    {
                        "id": "image",
                        "name": "image-portrait",
                        "type": "RECTANGLE",
                        "opacity": 0.5,
                        "pipelineImageRef": "image-ref",
                        "pipelineImageUrl": "https://images.example/portrait.png",
                        "fills": [
                            {
                                "type": "IMAGE",
                                "imageRef": "image-ref",
                                "opacity": 0.25,
                            }
                        ],
                        "absoluteBoundingBox": {"x": 20, "y": 40, "width": 160, "height": 100},
                    }
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    image = plan.sections[0].nodes[0]

    assert "opacity" not in image.style
    assert "opacity:0.125" not in html


def test_pipeline_render_plan_drops_href_metadata_text_nodes() -> None:
    payload = _raw_link_card_payload()
    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)

    card = plan.sections[0].nodes[0]
    assert card.component == "link-card"
    assert card.attributes["href"] == "https://example.com/cas"
    assert card.attributes["target"] == "_blank"
    assert [_node.name for _node in card.children] == ["case-card-01-link"]
    assert "content-overlap" not in [issue.code for issue in plan.diagnostics]
    assert '<a class="pipeline-node pipeline-layer-content pipeline-link-card"' in html
    assert 'href="https://example.com/cas"' in html
    assert "https://example.com/cas</" not in html


def test_pipeline_render_plan_reads_hidden_href_metadata_text_nodes() -> None:
    payload = _raw_link_card_payload()
    card = payload["children"][0]["children"][0]  # type: ignore[index]
    href = next(child for child in card["children"] if child["id"] == "href")  # type: ignore[index]
    href["visible"] = False

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    card_plan = plan.sections[0].nodes[0]

    assert card_plan.component == "link-card"
    assert card_plan.attributes["href"] == "https://example.com/cas"
    assert [_node.name for _node in card_plan.children] == ["case-card-01-link"]
    assert 'href="https://example.com/cas"' in html
    assert "https://example.com/cas</" not in html


def test_pipeline_background_suffix_is_independent_from_component_typology() -> None:
    payload = _raw_link_card_payload()
    card = payload["children"][0]["children"][0]  # type: ignore[index]
    card["children"].insert(  # type: ignore[index]
        0,
        _raw_box("card-bg", "case-card-01-bg", 24, 24, 180, 160),
    )

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    card_plan = plan.sections[0].nodes[0]
    background = _find_node(card_plan, "case-card-01-bg")

    assert card_plan.component == "link-card"
    assert background.component == ""
    assert background.layer == "background"
    assert background.style["background-color"] == "rgb(0, 26, 89)"
    assert 'data-node-name="case-card-01-bg" data-kind="asset"' in html
    assert "pipeline-layer-background" in html


def test_pipeline_foreground_name_creates_front_layer() -> None:
    payload = _raw_link_card_payload()
    card = payload["children"][0]["children"][0]  # type: ignore[index]
    card["children"].extend(  # type: ignore[index]
        [
            _raw_box("card-decor", "decor-card-shape", 24, 24, 180, 160),
            _raw_box("card-foreground", "foreground-card-shine", 24, 24, 180, 160),
        ]
    )

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    card_plan = plan.sections[0].nodes[0]
    decor = _find_node(card_plan, "decor-card-shape")
    foreground = _find_node(card_plan, "foreground-card-shine")

    assert decor.layer == "decorative"
    assert foreground.layer == "foreground"
    assert int(foreground.style["z-index"]) > int(decor.style["z-index"])
    assert "pipeline-layer-foreground" in html


def test_pipeline_hugo_site_propagates_link_card_href_between_breakpoints() -> None:
    desktop_payload = _raw_link_card_payload()
    desktop_payload["name"] = "page-link-card-1920"
    desktop_payload["absoluteBoundingBox"]["width"] = 1920
    desktop_payload["children"][0]["absoluteBoundingBox"]["width"] = 1920

    mobile_payload = copy.deepcopy(_raw_link_card_payload())
    mobile_payload["name"] = "page-link-card-402"
    mobile_card = mobile_payload["children"][0]["children"][0]
    mobile_card["children"] = [
        child for child in mobile_card["children"] if not str(child["name"]).startswith("href-")
    ]

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-link-propagation-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        desktop_raw = temp_path / "desktop.raw.json"
        mobile_raw = temp_path / "mobile.raw.json"
        desktop_raw.write_text(
            _generator_support.json.dumps(desktop_payload),
            encoding="utf-8",
        )
        mobile_raw.write_text(
            _generator_support.json.dumps(mobile_payload),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files(
            [desktop_raw, mobile_raw], temp_path / "site-pipeline"
        )

        responsive_data = _generator_support.json.loads(
            (
                temp_path
                / "site-pipeline"
                / "data"
                / "pipeline"
                / "responsive"
                / "page-link-card.json"
            ).read_text(
                encoding="utf-8",
            )
        )

    hrefs_by_width: dict[int, list[str]] = {}
    for variant in responsive_data["variants"]:
        hrefs_by_width[int(variant["width"])] = [
            node["attributes"]["href"]
            for node in _json_nodes_by_component(variant["page"], "link-card")
        ]

    assert hrefs_by_width[1920] == ["https://example.com/cas"]
    assert hrefs_by_width[402] == ["https://example.com/cas"]


def test_pipeline_render_plan_outputs_semantic_accordion_controls() -> None:
    payload = _raw_accordion_payload()
    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)

    accordion = plan.sections[0].nodes[0]
    item = accordion.children[0]
    trigger = item.children[0]
    panel = item.children[1]

    assert accordion.component == "accordion"
    assert item.component == "accordion-item"
    assert item.attributes == {"open": "open"}
    assert trigger.component == "accordion-trigger"
    assert panel.component == "accordion-panel"
    assert '<details class="pipeline-node pipeline-layer-content pipeline-accordion-item"' in html
    assert " open>" in html
    assert (
        '<summary class="pipeline-node pipeline-layer-content pipeline-accordion-trigger"' in html
    )


def test_pipeline_render_plan_collapses_nested_duplicate_accordion_trigger() -> None:
    payload = _raw_accordion_payload()
    trigger = payload["children"][0]["children"][0]["children"][0]["children"][0]
    trigger["children"] = [
        {
            "id": "nested-trigger",
            "name": "accordion-trigger-1",
            "type": "FRAME",
            "absoluteBoundingBox": trigger["absoluteBoundingBox"],
            "fills": [
                {
                    "type": "SOLID",
                    "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                }
            ],
            "children": trigger["children"],
        }
    ]

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    trigger_plan = plan.sections[0].nodes[0].children[0].children[0]

    assert trigger_plan.component == "accordion-trigger"
    assert [child.component for child in trigger_plan.children] == [""]
    assert trigger_plan.style["background-color"] == "rgb(0, 26, 76)"
    assert html.count("<summary") == 1


def test_pipeline_render_plan_outputs_semantic_carousel_controls() -> None:
    payload = _raw_carousel_payload()
    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)

    carousel = plan.sections[0].nodes[0]
    stage = _find_node(carousel, "carousel-stage-gallery")
    nav = _find_node(carousel, "carousel-thumbs-gallery")
    slide_1 = _find_node(carousel, "carousel-slide-1-active")
    slide_2 = _find_node(carousel, "carousel-slide-2")
    thumb_1 = _find_node(carousel, "carousel-thumb-1")

    assert carousel.component == "carousel"
    assert stage.component == "carousel-stage"
    assert nav.component == "carousel-nav"
    assert slide_1.component == "carousel-slide"
    assert slide_1.attributes == {"key": "1", "default": "true"}
    assert slide_2.component == "carousel-slide"
    assert slide_2.attributes == {"key": "2"}
    assert thumb_1.component == "carousel-thumb"
    assert thumb_1.attributes == {"key": "1", "default": "true"}
    assert 'data-carousel="true"' in html
    assert 'data-carousel-stage="true"' in html
    assert 'data-carousel-slide="1" data-carousel-default="true"' in html
    assert 'data-carousel-slide="2" hidden aria-hidden="true"' in html
    assert '<button class="pipeline-node pipeline-layer-content pipeline-carousel-thumb"' in html
    assert "content-overlap" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_render_plan_detects_semantic_contact_form_controls() -> None:
    plan = Pipeline().render_plan(_raw_contact_form_payload())

    form = plan.sections[0].nodes[0]
    name_field = _find_node(form, "input-nom-prenom-required")
    email = _find_node(form, "input-mail-required")
    subject = _find_node(form, "input-select-demande-required")
    message = _find_node(form, "input-message-required")
    submit = _find_node(form, "action-contact")

    assert form.component == "form"
    assert form.attributes == {"method": "post"}
    assert name_field.attributes["name"] == "nom-et-prenom"
    assert email.component == "field"
    assert email.attributes["type"] == "email"
    assert email.attributes["placeholder"] == "Votre email"
    assert email.attributes["required"] == "required"
    assert subject.component == "select"
    assert subject.attributes["placeholder"] == "Choisissez le sujet de votre demande"
    assert message.component == "textarea"
    assert message.attributes["placeholder"] == "Votre message"
    assert submit.component == "submit"
    assert submit.attributes["label"] == "Envoyer"


def test_pipeline_select_control_uses_closed_visual_bounds_not_option_list() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-select-options-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "section",
                    "name": "section-formulaire",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 140},
                    "children": [
                        {
                            "id": "form",
                            "name": "formulaire-contact",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 80,
                                "y": 20,
                                "width": 240,
                                "height": 100,
                            },
                            "children": [
                                {
                                    "id": "select",
                                    "name": "input-select-demande-required",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 100,
                                        "y": 40,
                                        "width": 200,
                                        "height": 90,
                                    },
                                    "children": [
                                        {
                                            "id": "select-bg",
                                            "name": "zone-demande",
                                            "type": "RECTANGLE",
                                            "pipelineImageUrl": "https://example.com/select.png",
                                            "absoluteBoundingBox": {
                                                "x": 100,
                                                "y": 40,
                                                "width": 200,
                                                "height": 28,
                                            },
                                        },
                                        {
                                            "id": "option",
                                            "name": "option-demande-audit",
                                            "type": "TEXT",
                                            "characters": "audit|Audit",
                                            "absoluteBoundingBox": {
                                                "x": 100,
                                                "y": 110,
                                                "width": 120,
                                                "height": 16,
                                            },
                                        },
                                        {
                                            "id": "selected",
                                            "name": "option-choix-demande-selected",
                                            "type": "TEXT",
                                            "characters": "choisir|Choisissez le sujet",
                                            "absoluteBoundingBox": {
                                                "x": 108,
                                                "y": 46,
                                                "width": 160,
                                                "height": 16,
                                            },
                                        },
                                    ],
                                },
                                {
                                    "id": "message",
                                    "name": "input-message-required",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 100,
                                        "y": 76,
                                        "width": 200,
                                        "height": 50,
                                    },
                                    "children": [
                                        {
                                            "id": "message-bg",
                                            "name": "zone-message",
                                            "type": "RECTANGLE",
                                            "absoluteBoundingBox": {
                                                "x": 100,
                                                "y": 76,
                                                "width": 200,
                                                "height": 50,
                                            },
                                        },
                                        {
                                            "id": "message-label",
                                            "name": "placeholder-message",
                                            "type": "TEXT",
                                            "characters": "Votre message",
                                            "absoluteBoundingBox": {
                                                "x": 108,
                                                "y": 84,
                                                "width": 120,
                                                "height": 16,
                                            },
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    form = plan.sections[0].nodes[0]
    select = _find_node(form, "input-select-demande-required")
    message = _find_node(form, "input-message-required")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert select.component == "select"
    assert select.bounds.height == pytest.approx(28)
    assert select.children == ()
    assert select.attributes["options"] == [{"value": "audit", "label": "Audit"}]
    assert select.style["background-image"] == 'url("https://example.com/select.png")'
    assert message.bounds.y > select.bounds.bottom
    assert "content-overlap" not in issue_codes


def test_pipeline_form_controls_keep_frame_bounds_when_visual_matches_field() -> None:
    plan = Pipeline(render_mode="strict").render_plan(
        {
            "id": "page",
            "name": "page-form-frame-bounds-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
            "children": [
                {
                    "id": "section",
                    "name": "section-formulaire",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 140},
                    "children": [
                        {
                            "id": "form",
                            "name": "formulaire-contact",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 80,
                                "y": 20,
                                "width": 240,
                                "height": 100,
                            },
                            "children": [
                                {
                                    "id": "select",
                                    "name": "input-select-demande-required",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 100,
                                        "y": 40,
                                        "width": 125,
                                        "height": 17,
                                    },
                                    "children": [
                                        _raw_box("select-bg", "zone-demande", 100, 41, 126, 16),
                                        {
                                            "id": "selected",
                                            "name": "option-choix-demande-selected",
                                            "type": "TEXT",
                                            "characters": "Choisissez le sujet",
                                            "absoluteBoundingBox": {
                                                "x": 100,
                                                "y": 41,
                                                "width": 124,
                                                "height": 16,
                                            },
                                        },
                                    ],
                                },
                                {
                                    "id": "message",
                                    "name": "input-message-required",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 100,
                                        "y": 67,
                                        "width": 125,
                                        "height": 33,
                                    },
                                    "children": [
                                        _raw_box(
                                            "message-bg",
                                            "zone-message",
                                            99.875,
                                            67,
                                            125.75,
                                            33.856,
                                        ),
                                        {
                                            "id": "message-label",
                                            "name": "placeholder-message",
                                            "type": "TEXT",
                                            "characters": "Votre message",
                                            "absoluteBoundingBox": {
                                                "x": 100,
                                                "y": 67,
                                                "width": 125,
                                                "height": 33,
                                            },
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    form = plan.sections[0].nodes[0]
    select = _find_node(form, "input-select-demande-required")
    message = _find_node(form, "input-message-required")

    assert select.bounds.x == pytest.approx(100)
    assert select.bounds.width == pytest.approx(125)
    assert select.bounds.height == pytest.approx(17)
    assert message.bounds.x == pytest.approx(100)
    assert message.bounds.width == pytest.approx(125)
    assert message.bounds.height == pytest.approx(33)
    assert message.bounds.y - select.bounds.bottom == pytest.approx(10)


def test_pipeline_textarea_control_translates_centered_figma_placeholder() -> None:
    payload = _raw_contact_form_payload()
    form_children = payload["children"][0]["children"][0]["children"]  # type: ignore[index]
    message_label = form_children[3]["children"][0]  # type: ignore[index]
    message_label["style"] = {  # type: ignore[index]
        "fontFamily": "Inter",
        "fontSize": 10,
        "lineHeightPx": 5,
        "textAlignHorizontal": "CENTER",
        "textAlignVertical": "CENTER",
    }

    plan = Pipeline().render_plan(payload)
    form = plan.sections[0].nodes[0]
    message = _find_node(form, "input-message-required")

    assert message.component == "textarea"
    assert message.style["display"] == "block"
    assert message.style["line-height"] == "10px"
    assert message.style["padding-top"] == f"{((message.bounds.height - 10) / 2):g}px"
    assert "padding-bottom" not in message.style


def test_pipeline_semantic_form_controls_keep_label_text_style() -> None:
    payload = _raw_contact_form_payload()
    form_children = payload["children"][0]["children"][0]["children"]  # type: ignore[index]
    name_label = form_children[0]["children"][0]  # type: ignore[index]
    submit_label = form_children[4]["children"][0]  # type: ignore[index]
    name_label["style"] = {  # type: ignore[index]
        "fontFamily": "Inter",
        "fontSize": 3,
        "lineHeightPx": 4,
        "fontWeight": 500,
        "textAlignHorizontal": "LEFT",
    }
    submit_label["style"] = {  # type: ignore[index]
        "fontFamily": "Inter",
        "fontSize": 5,
        "lineHeightPx": 6,
        "fontWeight": 700,
        "textAlignHorizontal": "CENTER",
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    form = plan.sections[0].nodes[0]
    name_field = _find_node(form, "input-nom-prenom-required")
    submit = _find_node(form, "action-contact")

    assert name_field.style["font-size"] == "3px"
    assert name_field.style["line-height"] == f"{name_field.bounds.height:g}px"
    assert name_field.style["font-weight"] == "500"
    assert name_field.style["text-align"] == "left"
    assert submit.style["font-size"] == "5px"
    assert submit.style["line-height"] == "6px"
    assert submit.style["font-weight"] == "700"
    assert submit.style["text-align"] == "center"
    assert "font-size:3px" in html
    assert "font-size:5px" in html


def test_pipeline_predefined_form_controls_keep_label_font_color() -> None:
    payload = _raw_contact_form_payload()
    form_children = payload["children"][0]["children"][0]["children"]  # type: ignore[index]
    name_label = form_children[0]["children"][0]  # type: ignore[index]
    submit_label = form_children[4]["children"][0]  # type: ignore[index]
    name_label["fills"] = [  # type: ignore[index]
        {
            "type": "SOLID",
            "color": {"r": 1, "g": 0.2, "b": 0, "a": 1},
        }
    ]
    submit_label["fills"] = [  # type: ignore[index]
        {
            "type": "SOLID",
            "color": {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1},
        }
    ]

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    form = plan.sections[0].nodes[0]
    name_field = _find_node(form, "input-nom-prenom-required")
    submit = _find_node(form, "action-contact")

    assert name_field.component == "field"
    assert name_field.style["color"] == "rgb(255, 51, 0)"
    assert submit.component == "submit"
    assert submit.style["color"] == "rgb(26, 51, 76)"
    assert "color:rgb(255, 51, 0)" in html
    assert "color:rgb(26, 51, 76)" in html


def test_pipeline_submit_control_accepts_suffix_background_name() -> None:
    payload = {
        "id": "page",
        "name": "page-button-style-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                "children": [
                    {
                        "id": "button",
                        "name": "button-envoyer",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 140,
                            "y": 48,
                            "width": 120,
                            "height": 32,
                        },
                        "children": [
                            _raw_box("button-bg", "button-envoyer-bg", 140, 48, 120, 32),
                            {
                                "id": "button-label",
                                "name": "texte-button-envoyer",
                                "type": "TEXT",
                                "characters": "Envoyer",
                                "absoluteBoundingBox": {
                                    "x": 170,
                                    "y": 56,
                                    "width": 60,
                                    "height": 16,
                                },
                            },
                        ],
                    }
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    button = plan.sections[0].nodes[0]

    assert button.component == "submit"
    assert button.children == ()
    assert button.style["background-color"] == "rgb(0, 26, 89)"
    assert "background-color:rgb(0, 26, 89)" in html
    assert ">Envoyer</button>" in html


def test_pipeline_semantic_adjustments_scale_tiny_mobile_form_controls() -> None:
    payload = _raw_tiny_contact_form_payload()

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    form = plan.sections[0].nodes[0]
    name_field = _find_node(form, "input-nom-prenom-required")
    message = _find_node(form, "input-message-required")
    submit = _find_node(form, "button-envoyer")

    assert name_field.bounds.height == pytest.approx(10)
    assert message.bounds.height == pytest.approx(20)
    assert submit.bounds.height == pytest.approx(8)
    assert name_field.style["font-size"] == "3px"
    assert submit.style["font-size"] == "4px"
    assert form.bounds.width == pytest.approx(120)
    assert plan.sections[0].bounds.height == pytest.approx(150)
    assert plan.height == 160
    assert "form-controls-expanded" not in [issue.code for issue in plan.diagnostics]
    assert "section-expanded-for-semantic-content" not in [issue.code for issue in plan.diagnostics]
    assert "page-height-expanded-for-semantic-content" not in [
        issue.code for issue in plan.diagnostics
    ]
    assert "font-size:3px" in html
    assert "font-size:4px" in html


def test_pipeline_semantic_form_scaling_keeps_even_vertical_gaps() -> None:
    plan = Pipeline().render_plan(_raw_tiny_contact_form_payload())
    html = Pipeline().render_static_html(_raw_tiny_contact_form_payload())
    form_plan = plan.sections[0].nodes[0]
    name_field = _find_node(form_plan, "input-nom-prenom-required")
    email = _find_node(form_plan, "input-mail-required")
    select = _find_node(form_plan, "input-select-demande-required")
    message = _find_node(form_plan, "input-message-required")
    field_gap = email.bounds.y - name_field.bounds.bottom
    message_gap = message.bounds.y - select.bounds.bottom

    assert select.bounds.height == pytest.approx(10)
    assert message.bounds.height == pytest.approx(20)
    assert message_gap == pytest.approx(field_gap)
    assert select.style["height"] == "10px"
    assert message.style["height"] == "20px"
    assert ".pipeline-form-control { padding: 0;" in html
    assert "form-controls-expanded" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_form_scaling_keeps_authored_mobile_form_size() -> None:
    def field(
        node_id: str, name: str, label: str, *, y: float, height: float = 17
    ) -> dict[str, object]:
        return {
            "id": node_id,
            "name": name,
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 138.5, "y": y, "width": 125, "height": height},
            "children": [
                _raw_box(f"{node_id}-bg", f"zone-{node_id}", 138.5, y, 125, height),
                {
                    "id": f"{node_id}-label",
                    "name": f"placeholder-{node_id}",
                    "type": "TEXT",
                    "characters": label,
                    "style": {"fontFamily": "Inter", "fontSize": 8, "lineHeightPx": 8.3},
                    "absoluteBoundingBox": {"x": 138.5, "y": y, "width": 125, "height": height},
                },
            ],
        }

    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-authored-mobile-form-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 320},
            "children": [
                {
                    "id": "footer",
                    "name": "footer-mobile",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 270},
                    "children": [
                        {
                            "id": "form-section",
                            "name": "section-formulaire",
                            "type": "FRAME",
                            "absoluteBoundingBox": {"x": 0, "y": 1, "width": 402, "height": 224},
                            "children": [
                                _raw_box("form-section-bg", "bg-formulaire", 0, 0, 402, 228),
                                {
                                    "id": "form",
                                    "name": "formulaire-contact-post",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 126.75,
                                        "y": 22.25,
                                        "width": 148.5,
                                        "height": 181.5,
                                    },
                                    "children": [
                                        _raw_box(
                                            "form-bg",
                                            "bg-contact-formulaire",
                                            126,
                                            22.2,
                                            149.9,
                                            180.7,
                                        ),
                                        field(
                                            "input-name", "input-nom-prenom-required", "Nom", y=31.6
                                        ),
                                        field("input-company", "input-societe", "Societe", y=58.6),
                                        field(
                                            "input-subject",
                                            "input-select-demande-required",
                                            "Choisir",
                                            y=112.6,
                                            height=16,
                                        ),
                                        field(
                                            "input-message",
                                            "input-message-required",
                                            "Message",
                                            y=139.6,
                                            height=33,
                                        ),
                                        {
                                            "id": "button",
                                            "name": "button-envoyer",
                                            "type": "FRAME",
                                            "absoluteBoundingBox": {
                                                "x": 176.3,
                                                "y": 182.6,
                                                "width": 49.4,
                                                "height": 11.7,
                                            },
                                            "children": [
                                                _raw_box(
                                                    "button-bg",
                                                    "bg-button-envoyer",
                                                    176.3,
                                                    182.6,
                                                    49.4,
                                                    11.7,
                                                ),
                                                {
                                                    "id": "button-label",
                                                    "name": "texte-button-envoyer",
                                                    "type": "TEXT",
                                                    "characters": "Envoyer",
                                                    "style": {
                                                        "fontFamily": "Inter",
                                                        "fontSize": 8,
                                                        "lineHeightPx": 8.3,
                                                    },
                                                    "absoluteBoundingBox": {
                                                        "x": 183,
                                                        "y": 181.4,
                                                        "width": 36,
                                                        "height": 14,
                                                    },
                                                },
                                            ],
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    form = _find_node(plan.sections[0].nodes[0], "formulaire-contact-post")
    name_field = _find_node(form, "input-nom-prenom-required")
    submit = _find_node(form, "button-envoyer")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert form.bounds.width == pytest.approx(148.5)
    assert name_field.bounds.height == pytest.approx(17)
    assert name_field.style["font-size"] == "8px"
    assert submit.bounds.height == pytest.approx(11.7)
    assert "form-controls-expanded" not in issue_codes


def test_pipeline_semantic_form_scaling_regularizes_parallel_field_row() -> None:
    def field(
        node_id: str,
        name: str,
        label: str,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> dict[str, object]:
        return {
            "id": node_id,
            "name": name,
            "type": "FRAME",
            "absoluteBoundingBox": {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            },
            "children": [
                _raw_box(f"{node_id}-bg", f"zone-{node_id}", x, y, width, height),
                {
                    "id": f"{node_id}-label",
                    "name": f"placeholder-{node_id}",
                    "type": "TEXT",
                    "characters": label,
                    "style": {"fontSize": 3, "lineHeightPx": 4},
                    "absoluteBoundingBox": {
                        "x": x + 2,
                        "y": y + 3,
                        "width": width - 4,
                        "height": 4,
                    },
                },
            ],
        }

    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-contact-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 190},
            "children": [
                {
                    "id": "contact",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
                    "children": [
                        {
                            "id": "form",
                            "name": "formulaire-contact-post",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 190,
                                "y": 40,
                                "width": 120,
                                "height": 130,
                            },
                            "children": [
                                _raw_box("form-bg", "bg-contact-formulaire", 214, 44, 96, 116),
                                field(
                                    "input-name",
                                    "input-nom-prenom-required",
                                    "Nom",
                                    x=220,
                                    y=50,
                                    width=76,
                                    height=10,
                                ),
                                field(
                                    "input-company",
                                    "input-societe",
                                    "Societe",
                                    x=220,
                                    y=65,
                                    width=76,
                                    height=10,
                                ),
                                field(
                                    "input-phone",
                                    "input-telephone-required",
                                    "Telephone",
                                    x=220,
                                    y=79.85,
                                    width=37,
                                    height=10.2,
                                ),
                                field(
                                    "input-email",
                                    "input-mail-required",
                                    "Email",
                                    x=259,
                                    y=80,
                                    width=37,
                                    height=10,
                                ),
                                field(
                                    "input-subject",
                                    "input-select-demande-required",
                                    "Choisissez",
                                    x=220,
                                    y=95,
                                    width=76,
                                    height=10,
                                ),
                                field(
                                    "input-message",
                                    "input-message-required",
                                    "Message",
                                    x=220,
                                    y=110,
                                    width=76,
                                    height=20,
                                ),
                                {
                                    "id": "button-submit",
                                    "name": "button-envoyer",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 242,
                                        "y": 140,
                                        "width": 32,
                                        "height": 8,
                                    },
                                    "children": [
                                        _raw_box(
                                            "button-submit-bg",
                                            "bg-button-envoyer",
                                            242,
                                            140,
                                            32,
                                            8,
                                        )
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    form_plan = plan.sections[0].nodes[0]
    phone = _find_node(form_plan, "input-telephone-required")
    email = _find_node(form_plan, "input-mail-required")
    select = _find_node(form_plan, "input-select-demande-required")

    assert phone.bounds.y == pytest.approx(79.85)
    assert email.bounds.y == pytest.approx(80)
    assert phone.bounds.height == pytest.approx(10.2)
    assert email.bounds.height == pytest.approx(10)
    assert phone.bounds.x == pytest.approx(220)
    assert email.bounds.right == pytest.approx(296)
    assert select.bounds.y - email.bounds.bottom == pytest.approx(5)


def test_pipeline_semantic_form_regularizes_unscaled_parallel_field_row() -> None:
    def field(
        node_id: str,
        name: str,
        label: str,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> dict[str, object]:
        return {
            "id": node_id,
            "name": name,
            "type": "FRAME",
            "absoluteBoundingBox": {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            },
            "children": [
                _raw_box(f"{node_id}-bg", f"zone-{node_id}", x, y, width, height),
                {
                    "id": f"{node_id}-label",
                    "name": f"placeholder-{node_id}",
                    "type": "TEXT",
                    "characters": label,
                    "style": {"fontSize": 16, "lineHeightPx": 20},
                    "absoluteBoundingBox": {
                        "x": x + 12,
                        "y": y + 15,
                        "width": width - 24,
                        "height": 20,
                    },
                },
            ],
        }

    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-contact-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 760},
            "children": [
                {
                    "id": "contact",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 720},
                    "children": [
                        {
                            "id": "form",
                            "name": "formulaire-contact-post",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 1200,
                                "y": 160,
                                "width": 460,
                                "height": 390,
                            },
                            "children": [
                                _raw_box("form-bg", "bg-contact-formulaire", 1200, 160, 460, 390),
                                field(
                                    "input-name",
                                    "input-nom-prenom-required",
                                    "Nom",
                                    x=1258,
                                    y=200,
                                    width=364,
                                    height=49,
                                ),
                                field(
                                    "input-company",
                                    "input-societe",
                                    "Societe",
                                    x=1258,
                                    y=270,
                                    width=364,
                                    height=49,
                                ),
                                field(
                                    "input-phone",
                                    "input-telephone-required",
                                    "Telephone",
                                    x=1256.5,
                                    y=340,
                                    width=173,
                                    height=48,
                                ),
                                field(
                                    "input-email",
                                    "input-mail-required",
                                    "Email",
                                    x=1447.5,
                                    y=340,
                                    width=176,
                                    height=48,
                                ),
                                field(
                                    "input-subject",
                                    "input-select-demande-required",
                                    "Sujet",
                                    x=1258,
                                    y=409,
                                    width=364,
                                    height=49,
                                ),
                                field(
                                    "input-message",
                                    "input-message-required",
                                    "Message",
                                    x=1258,
                                    y=479,
                                    width=364,
                                    height=98,
                                ),
                            ],
                        }
                    ],
                }
            ],
        }
    )

    form_plan = plan.sections[0].nodes[0]
    name = _find_node(form_plan, "input-nom-prenom-required")
    company = _find_node(form_plan, "input-societe")
    phone = _find_node(form_plan, "input-telephone-required")
    email = _find_node(form_plan, "input-mail-required")
    select = _find_node(form_plan, "input-select-demande-required")
    message = _find_node(form_plan, "input-message-required")
    field_gap = company.bounds.y - name.bounds.bottom

    assert phone.bounds.y == pytest.approx(email.bounds.y)
    assert phone.bounds.height == pytest.approx(email.bounds.height)
    assert phone.bounds.x == pytest.approx(1256.5)
    assert email.bounds.right == pytest.approx(1623.5)
    assert phone.bounds.y - company.bounds.bottom == pytest.approx(field_gap)
    assert select.bounds.y - phone.bounds.bottom == pytest.approx(field_gap)
    assert message.bounds.y - select.bounds.bottom == pytest.approx(field_gap)


def test_pipeline_semantic_adjustments_raise_compact_tablet_form_placeholder_text() -> None:
    def field(node_id: str, name: str, label: str, *, y: float) -> dict[str, object]:
        return {
            "id": node_id,
            "name": name,
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 312, "y": y, "width": 205, "height": 23},
            "children": [
                _raw_box(f"{node_id}-bg", f"zone-{node_id}", 312, y, 205, 23),
                {
                    "id": f"{node_id}-label",
                    "name": f"placeholder-{node_id}",
                    "type": "TEXT",
                    "characters": label,
                    "style": {
                        "fontFamily": "Inter",
                        "fontSize": 8,
                        "lineHeightPx": 4,
                    },
                    "absoluteBoundingBox": {"x": 312, "y": y, "width": 205, "height": 23},
                },
            ],
        }

    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-contact-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 360},
            "children": [
                {
                    "id": "footer",
                    "name": "footer-tablette",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 340},
                    "children": [
                        {
                            "id": "form",
                            "name": "formulaire-contact-post",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 280,
                                "y": 40,
                                "width": 274,
                                "height": 250,
                            },
                            "children": [
                                _raw_box("form-bg", "bg-contact-formulaire", 280, 40, 274, 250),
                                field(
                                    "input-name",
                                    "input-nom-prenom-required",
                                    "Nom et Prenom",
                                    y=72,
                                ),
                                field(
                                    "input-subject",
                                    "input-select-demande-required",
                                    "choisir|Choisissez le sujet de votre demande",
                                    y=112,
                                ),
                                field(
                                    "input-message",
                                    "input-message-required",
                                    "Votre message",
                                    y=152,
                                ),
                                {
                                    "id": "button-submit",
                                    "name": "button-envoyer",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 370,
                                        "y": 200,
                                        "width": 95,
                                        "height": 19,
                                    },
                                    "children": [
                                        _raw_box(
                                            "button-submit-bg",
                                            "bg-button-envoyer",
                                            370,
                                            200,
                                            95,
                                            19,
                                        ),
                                        {
                                            "id": "button-submit-label",
                                            "name": "texte-button-envoyer",
                                            "type": "TEXT",
                                            "characters": "Envoyer",
                                            "style": {"fontFamily": "Inter", "fontSize": 16},
                                            "absoluteBoundingBox": {
                                                "x": 387,
                                                "y": 200,
                                                "width": 61,
                                                "height": 19,
                                            },
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    form_plan = plan.sections[0].nodes[0]
    name = _find_node(form_plan, "input-nom-prenom-required")
    select = _find_node(form_plan, "input-select-demande-required")
    message = _find_node(form_plan, "input-message-required")
    submit = _find_node(form_plan, "button-envoyer")

    assert name.style["font-size"] == "8px"
    assert select.style["font-size"] == "8px"
    assert message.style["font-size"] == "8px"
    assert submit.style["font-size"] == "16px"


def test_pipeline_unscaled_form_background_does_not_stretch_to_form_bottom() -> None:
    payload = {
        "id": "page",
        "name": "page-contact-1920",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 760},
        "children": [
            {
                "id": "contact",
                "name": "section-contact",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 720},
                "children": [
                    {
                        "id": "form",
                        "name": "formulaire-contact-post",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 960,
                            "y": 120,
                            "width": 480,
                            "height": 360,
                        },
                        "children": [
                            _raw_box("form-bg", "bg-contact-formulaire", 1000, 150, 400, 260),
                            _raw_box("name-bg", "zone-nom", 1040, 180, 320, 48),
                            {
                                "id": "name",
                                "name": "input-nom-prenom-required",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 1040,
                                    "y": 180,
                                    "width": 320,
                                    "height": 48,
                                },
                                "children": [
                                    {
                                        "id": "name-label",
                                        "name": "placeholder-nom",
                                        "type": "TEXT",
                                        "characters": "Nom",
                                        "style": {"fontFamily": "Inter", "fontSize": 16},
                                        "absoluteBoundingBox": {
                                            "x": 1040,
                                            "y": 180,
                                            "width": 320,
                                            "height": 48,
                                        },
                                    }
                                ],
                            },
                            {
                                "id": "button",
                                "name": "button-envoyer",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 1130,
                                    "y": 340,
                                    "width": 140,
                                    "height": 34,
                                },
                                "children": [
                                    _raw_box("button-bg", "bg-button-envoyer", 1130, 340, 140, 34)
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }

    form = Pipeline().render_plan(payload).sections[0].nodes[0]
    background = _find_node(form, "bg-contact-formulaire")

    assert background.bounds.y == pytest.approx(150)
    assert background.bounds.height == pytest.approx(260)


def test_pipeline_semantic_adjustments_stretch_broad_wrapper_background_after_form_scale() -> None:
    payload = copy.deepcopy(_raw_tiny_contact_form_payload())
    form = payload["children"][0]["children"][0]  # type: ignore[index]
    payload["children"] = [  # type: ignore[index]
        {
            "id": "footer",
            "name": "footer-mobile",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
            "children": [
                {
                    "id": "form-section",
                    "name": "section-formulaire",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                    "children": [
                        _raw_box("form-section-bg", "bg-formulaire", 0, 0, 402, 110),
                        form,
                    ],
                }
            ],
        }
    ]

    plan = Pipeline().render_plan(payload)
    wrapper = plan.sections[0].nodes[0]
    form_plan = _find_node(wrapper, "formulaire-contact-post")
    background = _find_node(wrapper, "bg-formulaire")

    assert form_plan.bounds.bottom > 110
    assert background.bounds.bottom == pytest.approx(110)
    assert wrapper.bounds.bottom == pytest.approx(120)


def test_pipeline_semantic_adjustments_preserve_mobile_gap_between_form_and_footer() -> None:
    payload = copy.deepcopy(_raw_tiny_contact_form_payload())
    form = payload["children"][0]["children"][0]  # type: ignore[index]
    payload["children"] = [  # type: ignore[index]
        {
            "id": "footer",
            "name": "footer-mobile",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 190},
            "children": [
                {
                    "id": "form-section",
                    "name": "section-formulaire",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                    "children": [
                        _raw_box("form-section-bg", "bg-formulaire", 0, 0, 402, 110),
                        form,
                    ],
                },
                {
                    "id": "footer-strip",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 120, "width": 402, "height": 45},
                    "children": [
                        _raw_box("footer-bg", "bg-footer", 0, 120, 402, 45),
                        {
                            "id": "footer-text",
                            "name": "footer-text",
                            "type": "TEXT",
                            "characters": "2025 - 2026 Tous droits reserves",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 124,
                                "width": 402,
                                "height": 16,
                            },
                        },
                    ],
                },
            ],
        }
    ]

    plan = Pipeline().render_plan(payload)
    form_section = plan.sections[0].nodes[0]
    footer = plan.sections[0].nodes[1]
    form_plan = _find_node(form_section, "formulaire-contact-post")
    background = _find_node(form_section, "bg-formulaire")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert background.bounds.bottom == pytest.approx(110)
    assert form_section.bounds.bottom == pytest.approx(120)
    assert footer.bounds.y == pytest.approx(120)
    assert footer.bounds.y - form_plan.bounds.bottom < 0
    assert "footer-strip-stacked-after-content" not in issue_codes


def test_pipeline_semantic_adjustments_extend_form_background_into_footer_gap() -> None:
    payload = copy.deepcopy(_raw_tiny_contact_form_payload())
    form = payload["children"][0]["children"][0]  # type: ignore[index]
    payload["children"] = [  # type: ignore[index]
        {
            "id": "footer",
            "name": "footer-mobile",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 220},
            "children": [
                {
                    "id": "form-section",
                    "name": "section-formulaire",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 140},
                    "children": [
                        _raw_box("form-section-bg", "bg-formulaire", 0, 0, 402, 110),
                        {
                            "id": "contact-illu",
                            "name": "contact-illu",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 180,
                                "height": 110,
                            },
                            "children": [
                                _raw_box(
                                    "decor-fond-logo-contact",
                                    "decor-fond-logo-contact",
                                    0,
                                    0,
                                    180,
                                    110,
                                ),
                            ],
                        },
                        form,
                    ],
                },
                {
                    "id": "footer-strip",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 140, "width": 402, "height": 45},
                    "children": [
                        _raw_box("footer-bg", "bg-footer", 0, 140, 402, 45),
                        {
                            "id": "footer-text",
                            "name": "footer-text",
                            "type": "TEXT",
                            "characters": "2025 - 2026 Tous droits reserves",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 144,
                                "width": 402,
                                "height": 16,
                            },
                        },
                    ],
                },
            ],
        }
    ]

    plan = Pipeline().render_plan(payload)
    form_section = plan.sections[0].nodes[0]
    footer = plan.sections[0].nodes[1]
    form_plan = _find_node(form_section, "formulaire-contact-post")
    background = _find_node(form_section, "bg-formulaire")
    decor = _find_node(form_section, "decor-fond-logo-contact")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert background.bounds.bottom == pytest.approx(110)
    assert decor.bounds.height == pytest.approx(110)
    assert form_section.bounds.bottom == pytest.approx(140)
    assert footer.bounds.y == pytest.approx(140)
    assert footer.bounds.y - form_plan.bounds.bottom < 0
    assert form_plan.bounds.y > background.bounds.y
    assert "footer-strip-stacked-after-content" not in issue_codes


def test_pipeline_semantic_adjustments_center_scaled_mobile_form_controls() -> None:
    plan = Pipeline().render_plan(_raw_tiny_contact_form_payload())
    form = plan.sections[0].nodes[0]
    min_left = plan.sections[0].bounds.x + 12
    max_right = plan.sections[0].bounds.right - 12
    left_padding = form.bounds.x - min_left
    right_padding = max_right - form.bounds.right

    assert left_padding == pytest.approx(178)
    assert right_padding == pytest.approx(80)
    assert "form-controls-expanded" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_form_adjustment_is_independent_from_contact_name() -> None:
    payload = copy.deepcopy(_raw_tiny_contact_form_payload())
    payload["name"] = "page-newsletter-402"
    section = payload["children"][0]  # type: ignore[index]
    section["id"] = "newsletter"  # type: ignore[index]
    section["name"] = "section-newsletter"  # type: ignore[index]
    form = section["children"][0]  # type: ignore[index]
    form["name"] = "formulaire-newsletter-post"  # type: ignore[index]
    form["children"][0]["name"] = "bg-newsletter-formulaire"  # type: ignore[index]

    plan = Pipeline().render_plan(payload)
    form_plan = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert "contact" not in plan.sections[0].name
    assert form_plan.component == "form"
    assert form_plan.bounds.width == pytest.approx(120)
    assert "form-controls-expanded" not in issue_codes


def test_pipeline_contact_section_direct_field_does_not_trigger_form_layout() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-contact-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "contact",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
                    "children": [
                        _raw_tiny_field(
                            "input-email",
                            "input-mail-required",
                            "Email",
                            y=40,
                        )
                    ],
                }
            ],
        }
    )

    field = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert field.component == "field"
    assert field.bounds.width == pytest.approx(76)
    assert "form-controls-expanded" not in issue_codes


def test_pipeline_contact_section_zone_name_does_not_trigger_form_layout() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-contact-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "contact",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
                    "children": [
                        {
                            "id": "zone-message",
                            "name": "zone-message",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 40,
                                "y": 40,
                                "width": 180,
                                "height": 60,
                            },
                            "children": [
                                _raw_box("zone-message-bg", "zone-message-bg", 40, 40, 180, 60)
                            ],
                        }
                    ],
                }
            ],
        }
    )

    zone = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert zone.name == "zone-message"
    assert zone.component == ""
    assert "form-controls-expanded" not in issue_codes


def test_pipeline_semantic_adjustments_preserve_mobile_heading_touching_section_top() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-heading-padding-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
            "children": [
                {
                    "id": "hero",
                    "name": "section-hero-main",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 122},
                    "children": [
                        _raw_box("hero-bg", "bg-hero", 0, 0, 402, 122),
                        {
                            "id": "hero-content",
                            "name": "section-hero-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 32,
                                "y": 0,
                                "width": 338,
                                "height": 110,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h1-hero",
                                    "type": "TEXT",
                                    "characters": "Nom de la prestation",
                                    "style": {"fontSize": 20, "lineHeightPx": 15},
                                    "absoluteBoundingBox": {
                                        "x": 32,
                                        "y": 0,
                                        "width": 338,
                                        "height": 74,
                                    },
                                },
                                {
                                    "id": "subtitle",
                                    "name": "titre-h3-hero",
                                    "type": "TEXT",
                                    "characters": "Titre H2 lisible",
                                    "style": {"fontSize": 12, "lineHeightPx": 12},
                                    "absoluteBoundingBox": {
                                        "x": 65,
                                        "y": 74,
                                        "width": 272,
                                        "height": 36,
                                    },
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    )

    bg = next(node for node in plan.sections[0].nodes if node.name == "bg-hero")
    hero_content = next(
        node for node in plan.sections[0].nodes if node.name == "section-hero-content"
    )
    title = _find_node(hero_content, "titre-h1-hero")
    subtitle = _find_node(hero_content, "titre-h3-hero")

    assert bg.bounds.y == pytest.approx(0)
    assert hero_content.bounds.y == pytest.approx(0)
    assert title.bounds.y == pytest.approx(0)
    assert subtitle.bounds.y == pytest.approx(74)


def test_pipeline_strict_mode_keeps_raw_heading_geometry_and_metrics() -> None:
    payload = {
        "id": "page",
        "name": "page-heading-padding-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
        "children": [
            {
                "id": "hero",
                "name": "section-hero-main",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 122},
                "children": [
                    _raw_box("hero-bg", "bg-hero", 0, 0, 402, 122),
                    {
                        "id": "hero-content",
                        "name": "section-hero-content",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 32,
                            "y": 0,
                            "width": 338,
                            "height": 110,
                        },
                        "children": [
                            {
                                "id": "title",
                                "name": "titre-h1-hero",
                                "type": "TEXT",
                                "characters": "Nom de la prestation",
                                "style": {"fontSize": 20, "lineHeightPx": 15},
                                "absoluteBoundingBox": {
                                    "x": 32,
                                    "y": 0,
                                    "width": 338,
                                    "height": 74,
                                },
                            }
                        ],
                    },
                ],
            }
        ],
    }

    usable = Pipeline().render_plan(copy.deepcopy(payload))
    strict = Pipeline(render_mode=PipelineRenderMode.STRICT).render_plan(copy.deepcopy(payload))

    usable_content = next(
        node for node in usable.sections[0].nodes if node.name == "section-hero-content"
    )
    strict_content = next(
        node for node in strict.sections[0].nodes if node.name == "section-hero-content"
    )
    usable_title = _find_node(usable_content, "titre-h1-hero")
    strict_title = _find_node(strict_content, "titre-h1-hero")

    assert strict_content.bounds.y == pytest.approx(0)
    assert strict_title.bounds.y == pytest.approx(0)
    assert strict_title.style["line-height"] == "15px"
    assert usable_content.bounds.y == pytest.approx(0)
    assert usable_title.bounds.y == pytest.approx(0)
    assert usable_title.style["line-height"] == "15px"


def test_pipeline_static_css_loads_plan_fonts_without_debug_fallbacks() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-fonts-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
            "children": [
                {
                    "id": "section",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 100},
                    "children": [
                        {
                            "id": "text",
                            "name": "texte-content",
                            "type": "TEXT",
                            "characters": "Texte lisible",
                            "style": {"fontFamily": "Inter", "fontSize": 16},
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 24,
                                "width": 240,
                                "height": 24,
                            },
                        }
                    ],
                }
            ],
        }
    )

    css = render_static_css(plan)

    assert css.startswith("@import url('https://fonts.googleapis.com")
    assert "family=Inter" in css
    assert "font-family: 'Inter', 'Segoe UI', Arial, sans-serif" in css
    assert ".pipeline-form-control::placeholder { color: currentColor; opacity: 1; }" in css
    assert ".pipeline-select-control {" in css
    assert "appearance: none;" in css
    assert "text-align-last: center;" in css
    assert ".pipeline-select-arrow::before {" in css
    assert ".pipeline-layer-asset > .pipeline-img," in css
    assert ".pipeline-layer-decorative > .pipeline-img {" in css
    assert ".pipeline-layer-background > .pipeline-img {" in css
    assert "object-fit: fill;" in css
    assert "width: calc(100% + 12px);" in css
    assert "transform: translateX(-6px);" in css
    assert ".pipeline-layer-decorative { z-index: 1; }" in css
    assert (
        ".pipeline-accordion-item:not([open]) { overflow: hidden; height: auto !important; }" in css
    )
    assert ".pipeline-layer-decorative { z-index: 1; opacity:" not in css
    assert "outline: 1px" not in css
    assert "rgba(6, 29, 79, 0.08)" not in css


def test_pipeline_explicit_multiline_text_still_counts_wrapped_lines() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-wrapped-explicit-lines-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 220},
            "children": [
                {
                    "id": "section",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 140},
                    "children": [
                        {
                            "id": "group",
                            "name": "section-content-group",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 40,
                                "y": 20,
                                "width": 180,
                                "height": 80,
                            },
                            "children": [
                                {
                                    "id": "heading",
                                    "name": "titre-h4-long",
                                    "type": "TEXT",
                                    "characters": "Premiere ligne\nSeconde ligne beaucoup trop longue",
                                    "style": {"fontSize": 12, "lineHeightPx": 12},
                                    "absoluteBoundingBox": {
                                        "x": 40,
                                        "y": 20,
                                        "width": 110,
                                        "height": 24,
                                    },
                                },
                                {
                                    "id": "body",
                                    "name": "texte-suite",
                                    "type": "TEXT",
                                    "characters": "Texte suivant",
                                    "style": {"fontSize": 10, "lineHeightPx": 10},
                                    "absoluteBoundingBox": {
                                        "x": 40,
                                        "y": 48,
                                        "width": 110,
                                        "height": 12,
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    section = plan.sections[0]
    heading = next(node for node in section.nodes if node.name == "titre-h4-long")
    body = next(node for node in section.nodes if node.name == "texte-suite")

    assert heading.bounds.height == pytest.approx(24)
    assert body.bounds.y == pytest.approx(48)
    assert "text-sibling-shifted-for-intrinsic-height" not in [
        issue.code for issue in plan.diagnostics
    ]


def test_pipeline_submit_control_keeps_visual_background_child() -> None:
    payload = {
        "id": "page",
        "name": "page-button-style-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                "children": [
                    {
                        "id": "button",
                        "name": "button-envoyer",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 140,
                            "y": 48,
                            "width": 120,
                            "height": 32,
                        },
                        "children": [
                            {
                                "id": "button-bg",
                                "name": "bg-button-envoyer",
                                "type": "RECTANGLE",
                                "pipelineImageUrl": "https://example.com/button.png",
                                "absoluteBoundingBox": {
                                    "x": 140,
                                    "y": 48,
                                    "width": 120,
                                    "height": 32,
                                },
                            },
                            {
                                "id": "button-label",
                                "name": "texte-button-envoyer",
                                "type": "TEXT",
                                "characters": "Envoyer",
                                "style": {"fontFamily": "Inter", "fontSize": 12},
                                "absoluteBoundingBox": {
                                    "x": 170,
                                    "y": 56,
                                    "width": 60,
                                    "height": 16,
                                },
                            },
                        ],
                    }
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    button = plan.sections[0].nodes[0]

    assert button.component == "submit"
    assert button.style["background-image"] == 'url("https://example.com/button.png")'
    assert button.style["background-color"] == "transparent"
    assert button.style["background-size"] == "100% 100%"
    assert 'background-image:url("https://example.com/button.png")' in html


def test_pipeline_submit_control_uses_larger_visual_background_bounds() -> None:
    payload = {
        "id": "page",
        "name": "page-button-style-834",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 180},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 140},
                "children": [
                    {
                        "id": "button",
                        "name": "button-envoyer",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 386,
                            "y": 72,
                            "width": 62,
                            "height": 15,
                        },
                        "children": [
                            {
                                "id": "button-bg",
                                "name": "bg-button-envoyer",
                                "type": "RECTANGLE",
                                "pipelineImageUrl": "https://example.com/button-wide.png",
                                "absoluteBoundingBox": {
                                    "x": 370,
                                    "y": 66,
                                    "width": 95,
                                    "height": 19,
                                },
                            },
                            {
                                "id": "button-label",
                                "name": "texte-button-envoyer",
                                "type": "TEXT",
                                "characters": "Envoyer",
                                "style": {"fontFamily": "Inter", "fontSize": 16},
                                "absoluteBoundingBox": {
                                    "x": 386,
                                    "y": 66,
                                    "width": 62,
                                    "height": 19,
                                },
                            },
                        ],
                    }
                ],
            }
        ],
    }

    button = Pipeline().render_plan(payload).sections[0].nodes[0]

    assert button.component == "submit"
    assert button.bounds.x == pytest.approx(370)
    assert button.bounds.y == pytest.approx(66)
    assert button.bounds.width == pytest.approx(95)
    assert button.bounds.height == pytest.approx(19)


def test_pipeline_submit_control_uses_inner_visual_when_frame_is_too_wide() -> None:
    payload = {
        "id": "page",
        "name": "page-button-wide-frame-834",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 180},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 140},
                "children": [
                    {
                        "id": "button",
                        "name": "button-cta",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 200,
                            "y": 72,
                            "width": 432,
                            "height": 17,
                        },
                        "children": [
                            {
                                "id": "button-bg",
                                "name": "bg-button-cta",
                                "type": "RECTANGLE",
                                "pipelineImageUrl": "https://example.com/cta.png",
                                "absoluteBoundingBox": {
                                    "x": 200,
                                    "y": 72,
                                    "width": 95,
                                    "height": 18,
                                },
                            },
                            {
                                "id": "button-label",
                                "name": "texte-button-cta",
                                "type": "TEXT",
                                "characters": "CTA",
                                "style": {"fontFamily": "Inter", "fontSize": 16},
                                "absoluteBoundingBox": {
                                    "x": 204,
                                    "y": 73,
                                    "width": 86,
                                    "height": 14,
                                },
                            },
                        ],
                    }
                ],
            }
        ],
    }

    button = Pipeline().render_plan(payload).sections[0].nodes[0]

    assert button.component == "submit"
    assert button.bounds.x == pytest.approx(200)
    assert button.bounds.y == pytest.approx(72)
    assert button.bounds.width == pytest.approx(95)
    assert button.bounds.height == pytest.approx(18)


def test_pipeline_submit_control_uses_wider_shorter_visual_background_bounds() -> None:
    payload = {
        "id": "page",
        "name": "page-button-style-834",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 180},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 140},
                "children": [
                    {
                        "id": "button",
                        "name": "button-labo-embedded",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 86,
                            "y": 48,
                            "width": 61,
                            "height": 40,
                        },
                        "children": [
                            {
                                "id": "button-bg",
                                "name": "bg-button-le-labo",
                                "type": "RECTANGLE",
                                "pipelineImageUrl": "https://example.com/labo-button.png",
                                "absoluteBoundingBox": {
                                    "x": 71,
                                    "y": 71,
                                    "width": 91,
                                    "height": 17,
                                },
                            },
                            {
                                "id": "button-label",
                                "name": "texte-button-le-labo",
                                "type": "TEXT",
                                "characters": "Le Labo",
                                "style": {"fontFamily": "Inter", "fontSize": 16},
                                "absoluteBoundingBox": {
                                    "x": 80,
                                    "y": 71,
                                    "width": 73,
                                    "height": 17,
                                },
                            },
                        ],
                    }
                ],
            }
        ],
    }

    button = Pipeline().render_plan(payload).sections[0].nodes[0]

    assert button.component == "submit"
    assert button.bounds.x == pytest.approx(71)
    assert button.bounds.y == pytest.approx(71)
    assert button.bounds.width == pytest.approx(91)
    assert button.bounds.height == pytest.approx(17)


def test_pipeline_control_visual_image_keeps_transparent_background_over_fill() -> None:
    payload = {
        "id": "page",
        "name": "page-button-transparent-bg-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                "children": [
                    {
                        "id": "button",
                        "name": "button-envoyer",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 140,
                            "y": 48,
                            "width": 120,
                            "height": 32,
                        },
                        "children": [
                            {
                                "id": "button-bg",
                                "name": "bg-button-envoyer",
                                "type": "RECTANGLE",
                                "pipelineImageUrl": "https://example.com/button.png",
                                "fills": [
                                    {
                                        "type": "SOLID",
                                        "color": {"r": 1, "g": 0, "b": 0},
                                    }
                                ],
                                "absoluteBoundingBox": {
                                    "x": 140,
                                    "y": 48,
                                    "width": 120,
                                    "height": 32,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }

    button = Pipeline().render_plan(payload).sections[0].nodes[0]

    assert button.style["background-image"] == 'url("https://example.com/button.png")'
    assert button.style["background-color"] == "transparent"


def test_pipeline_body_typography_keeps_tighter_figma_spacing_than_headings() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-typography-ratio-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
            "children": [
                {
                    "id": "section",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                    "children": [
                        {
                            "id": "heading",
                            "name": "titre-h2-content",
                            "type": "TEXT",
                            "characters": "Titre",
                            "style": {"fontSize": 20, "lineHeightPx": 15},
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 24,
                                "width": 160,
                                "height": 24,
                            },
                        },
                        {
                            "id": "body",
                            "name": "texte-content",
                            "type": "TEXT",
                            "characters": "Paragraphe assez court.",
                            "style": {"fontSize": 10, "lineHeightPx": 8},
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 60,
                                "width": 220,
                                "height": 20,
                            },
                        },
                    ],
                }
            ],
        }
    )

    heading = next(node for node in plan.sections[0].nodes if node.name == "titre-h2-content")
    body = next(node for node in plan.sections[0].nodes if node.name == "texte-content")

    assert heading.style["line-height"] == "15px"
    assert body.style["line-height"] == "8px"


def test_pipeline_semantic_adjustments_aligns_stacked_title_to_body_column() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-stacked-text-column-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 420},
            "children": [
                {
                    "id": "section",
                    "name": "section-editorial",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 360},
                    "children": [
                        {
                            "id": "title",
                            "name": "titre-h4-editorial",
                            "type": "TEXT",
                            "characters": "Parler de la passion\nUn titre assez grand",
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 11,
                                "lineHeightPx": 14,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 2,
                                "y": 16,
                                "width": 398,
                                "height": 28,
                            },
                        },
                        {
                            "id": "body",
                            "name": "texte-editorial",
                            "type": "TEXT",
                            "characters": (
                                "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                                "Vestibulum quis consequat lacus, sed tristique augue."
                            ),
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 11,
                                "lineHeightPx": 14,
                                "textAlignHorizontal": "LEFT",
                            },
                            "absoluteBoundingBox": {
                                "x": 63,
                                "y": 58,
                                "width": 276,
                                "height": 120,
                            },
                        },
                    ],
                }
            ],
        }
    )

    heading = _find_section_node(plan.sections[0], "titre-h4-editorial")
    body = _find_section_node(plan.sections[0], "texte-editorial")
    assert heading.bounds.x == pytest.approx(2)
    assert heading.bounds.width == pytest.approx(398)
    assert body.bounds.x == pytest.approx(63)
    assert body.bounds.width == pytest.approx(276)
    assert heading.style["text-align"] == "center"
    assert "stacked-text-column-aligned" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_preserves_intentional_body_inset() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-stacked-text-column-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 420},
            "children": [
                {
                    "id": "section",
                    "name": "section-editorial",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 360},
                    "children": [
                        {
                            "id": "title",
                            "name": "titre-h4-editorial",
                            "type": "TEXT",
                            "characters": "Parler de la passion\nUn titre assez grand",
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 24,
                                "lineHeightPx": 28,
                                "textAlignHorizontal": "LEFT",
                            },
                            "absoluteBoundingBox": {
                                "x": 600,
                                "y": 40,
                                "width": 570,
                                "height": 58,
                            },
                        },
                        {
                            "id": "body",
                            "name": "texte-editorial",
                            "type": "TEXT",
                            "characters": (
                                "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                                "Vestibulum quis consequat lacus, sed tristique augue. "
                                "Donec efficitur, sapien vitae cursus dictum."
                            ),
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 20,
                                "lineHeightPx": 22,
                                "textAlignHorizontal": "LEFT",
                            },
                            "absoluteBoundingBox": {
                                "x": 616,
                                "y": 104,
                                "width": 538,
                                "height": 140,
                            },
                        },
                    ],
                }
            ],
        }
    )

    heading = _find_section_node(plan.sections[0], "titre-h4-editorial")
    body = _find_section_node(plan.sections[0], "texte-editorial")

    assert heading.bounds.x == pytest.approx(600)
    assert heading.bounds.width == pytest.approx(570)
    assert body.bounds.x - heading.bounds.x == pytest.approx(16)
    assert all(issue.code != "stacked-text-column-aligned" for issue in plan.diagnostics)


def test_pipeline_semantic_adjustments_does_not_expand_stacked_title_to_body_width() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-stacked-text-column-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 420},
            "children": [
                {
                    "id": "section",
                    "name": "section-editorial",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 360},
                    "children": [
                        {
                            "id": "title",
                            "name": "titre-h4-editorial",
                            "type": "TEXT",
                            "characters": "H3 - Informations générales",
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 28,
                                "lineHeightPx": 28,
                                "textAlignHorizontal": "LEFT",
                            },
                            "absoluteBoundingBox": {
                                "x": 475,
                                "y": 40,
                                "width": 360,
                                "height": 48,
                            },
                        },
                        {
                            "id": "body",
                            "name": "texte-editorial",
                            "type": "TEXT",
                            "characters": (
                                "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                                "Vestibulum quis consequat lacus, sed tristique augue. "
                                "Donec efficitur, sapien vitae cursus dictum. "
                                "Curabitur vitae cursus risus."
                            ),
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 20,
                                "lineHeightPx": 22,
                                "textAlignHorizontal": "LEFT",
                            },
                            "absoluteBoundingBox": {
                                "x": 451,
                                "y": 104,
                                "width": 1018,
                                "height": 160,
                            },
                        },
                    ],
                }
            ],
        }
    )

    heading = _find_section_node(plan.sections[0], "titre-h4-editorial")
    body = _find_section_node(plan.sections[0], "texte-editorial")

    assert heading.bounds.x == pytest.approx(475)
    assert heading.bounds.width == pytest.approx(360)
    assert body.bounds.x == pytest.approx(451)
    assert "stacked-text-column-aligned" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_centers_stacked_title_on_centered_body() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-centered-stacked-title-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 620},
            "children": [
                {
                    "id": "section",
                    "name": "section-embedded",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 560},
                    "children": [
                        {
                            "id": "group",
                            "name": "embedded-infos-decouvre",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 391,
                                "y": 120,
                                "width": 568,
                                "height": 420,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h2-decouvrez-bureau",
                                    "type": "TEXT",
                                    "characters": "Decouvrez\nle bureau d'etude",
                                    "style": {
                                        "fontFamily": "Inter",
                                        "fontSize": 32,
                                        "fontWeight": 700,
                                        "lineHeightPx": 42,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 442,
                                        "y": 120,
                                        "width": 568,
                                        "height": 84,
                                    },
                                },
                                {
                                    "id": "body",
                                    "name": "texte-decouvrez-bureau",
                                    "type": "TEXT",
                                    "characters": (
                                        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                                        "Vestibulum quis consequat lacus, sed tristique augue. "
                                        "Donec efficitur, sapien vitae cursus dictum, arcu velit."
                                    ),
                                    "style": {
                                        "fontFamily": "Inter",
                                        "fontSize": 20,
                                        "lineHeightPx": 20,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 445,
                                        "y": 227,
                                        "width": 462,
                                        "height": 240,
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    title = _find_section_node(plan.sections[0], "titre-h2-decouvrez-bureau")
    body = _find_section_node(plan.sections[0], "texte-decouvrez-bureau")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert title.bounds.x == pytest.approx(442)
    assert title.bounds.width == pytest.approx(568)
    assert body.bounds.x == pytest.approx(445)
    assert body.bounds.width == pytest.approx(462)
    assert "stacked-centered-heading-aligned" not in issue_codes


def test_pipeline_semantic_adjustments_aligns_nested_right_text_column() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-stacked-text-column-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 620},
            "children": [
                {
                    "id": "section",
                    "name": "section-editorial",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 560},
                    "children": [
                        {
                            "id": "card",
                            "name": "card-v-editorial",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 880,
                                "y": 80,
                                "width": 622,
                                "height": 420,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h4-editorial",
                                    "type": "TEXT",
                                    "characters": "Parler de la passion\nUn titre assez grand",
                                    "style": {
                                        "fontFamily": "Inter",
                                        "fontSize": 24,
                                        "lineHeightPx": 32,
                                        "textAlignHorizontal": "RIGHT",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 880,
                                        "y": 80,
                                        "width": 622,
                                        "height": 64,
                                    },
                                },
                                {
                                    "id": "body",
                                    "name": "texte-editorial",
                                    "type": "TEXT",
                                    "characters": (
                                        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                                        "Vestibulum quis consequat lacus, sed tristique augue."
                                    ),
                                    "style": {
                                        "fontFamily": "Inter",
                                        "fontSize": 20,
                                        "lineHeightPx": 24,
                                        "textAlignHorizontal": "RIGHT",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 904,
                                        "y": 144,
                                        "width": 574,
                                        "height": 220,
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    card = plan.sections[0].nodes[0]
    heading = _find_node(card, "titre-h4-editorial")
    body = _find_node(card, "texte-editorial")

    assert heading.bounds.x == pytest.approx(880)
    assert heading.bounds.width == pytest.approx(622)
    assert body.bounds.x == pytest.approx(904)
    assert body.bounds.width == pytest.approx(574)
    assert "stacked-text-column-aligned" not in [issue.code for issue in plan.diagnostics]
    assert heading.style["text-align"] == "right"


def test_pipeline_composites_gradient_colors_with_node_opacity() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-gradient-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
            "children": [
                {
                    "id": "section",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 100},
                    "children": [
                        {
                            "id": "decor",
                            "name": "decor-gradient",
                            "type": "RECTANGLE",
                            "opacity": 0.5,
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 120,
                                "height": 80,
                            },
                            "fills": [
                                {
                                    "type": "GRADIENT_LINEAR",
                                    "gradientStops": [
                                        {
                                            "position": 0,
                                            "color": {"r": 1, "g": 0, "b": 0, "a": 1},
                                        },
                                        {
                                            "position": 1,
                                            "color": {"r": 0, "g": 0, "b": 1, "a": 1},
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    decor = plan.sections[0].nodes[0]

    assert decor.style["background-color"] == "rgba(128, 0, 128, 0.5)"
    assert "opacity" not in decor.style


def test_pipeline_semantic_adjustments_shift_bottom_anchored_footer_strip() -> None:
    payload = _raw_tiny_contact_form_payload()
    section = payload["children"][0]
    children = section["children"]
    assert isinstance(children, list)
    children.extend(
        [
            _raw_box("footer-bg", "bg-footer", 0, 140, 402, 10),
            {
                "id": "footer-text",
                "name": "footer-text",
                "type": "TEXT",
                "characters": "Copyright",
                "style": {"fontFamily": "Inter", "fontSize": 4, "lineHeightPx": 5},
                "absoluteBoundingBox": {"x": 120, "y": 142, "width": 80, "height": 5},
            },
        ]
    )

    plan = Pipeline().render_plan(payload)
    form = _find_node(plan.sections[0].nodes[0], "formulaire-contact-post")
    footer_bg = next(node for node in plan.sections[0].nodes if node.name == "bg-footer")
    footer_text = next(node for node in plan.sections[0].nodes if node.name == "footer-text")

    assert footer_bg.bounds.y == pytest.approx(140)
    assert footer_text.bounds.y == pytest.approx(142)
    assert footer_bg.bounds.y < form.bounds.bottom
    assert footer_text.bounds.y < form.bounds.bottom
    assert footer_bg.bounds.bottom <= plan.sections[0].bounds.bottom
    assert "section-bottom-anchored-content-shifted" not in [
        issue.code for issue in plan.diagnostics
    ]


def test_pipeline_semantic_adjustments_expand_tiny_footer_legal_text() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-legal-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "footer",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                    "children": [
                        {
                            "id": "footer-text",
                            "name": "footer-text",
                            "type": "TEXT",
                            "characters": "Copyright 2026 Example",
                            "style": {"fontSize": 2, "lineHeightPx": 3},
                            "absoluteBoundingBox": {
                                "x": 120,
                                "y": 100,
                                "width": 120,
                                "height": 5,
                            },
                        }
                    ],
                }
            ],
        }
    )

    footer_text = plan.sections[0].nodes[0]

    assert footer_text.bounds.x == pytest.approx(5)
    assert footer_text.bounds.width == pytest.approx(392)
    assert footer_text.bounds.height == pytest.approx(24)
    assert footer_text.style["font-size"] == "8px"
    assert footer_text.style["line-height"] == "12px"
    assert footer_text.style["text-align"] == "center"
    assert footer_text.style["display"] == "flex"
    assert footer_text.style["align-items"] == "center"
    assert footer_text.style["justify-content"] == "center"
    assert "footer-text-expanded-for-readability" in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_expand_tablet_footer_height() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-legal-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 120},
            "children": [
                {
                    "id": "footer",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 60, "width": 834, "height": 30},
                    "children": [
                        _raw_box("bg-footer", "bg-footer", 0, 60, 834, 30),
                        {
                            "id": "footer-text",
                            "name": "footer-text",
                            "type": "TEXT",
                            "characters": "2025 - 2026 Tous droits reserves Copyright Example",
                            "style": {"fontSize": 8, "lineHeightPx": 12},
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 60,
                                "width": 834,
                                "height": 30,
                            },
                        },
                    ],
                }
            ],
        }
    )

    footer = plan.sections[0]
    footer_bg = next(node for node in footer.nodes if node.name == "bg-footer")
    footer_text = next(node for node in footer.nodes if node.name == "footer-text")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert footer.bounds.height >= 44
    assert footer_bg.bounds.height == pytest.approx(footer.bounds.height)
    assert footer_text.bounds.height >= 36
    assert footer_text.style["display"] == "flex"
    assert "tiny-footer" not in issue_codes
    assert "footer-text-expanded-for-readability" in issue_codes


def test_pipeline_semantic_adjustments_contain_desktop_footer_legal_text() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-legal-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 200},
            "children": [
                {
                    "id": "footer",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 1920, "height": 75},
                    "children": [
                        {
                            "id": "footer-text",
                            "name": "footer-text",
                            "type": "TEXT",
                            "characters": "2025 - 2026 Tous droits reserves Copyright Example",
                            "style": {"fontSize": 20, "lineHeightPx": 25},
                            "absoluteBoundingBox": {
                                "x": -14,
                                "y": 100,
                                "width": 1933,
                                "height": 75,
                            },
                        }
                    ],
                }
            ],
        }
    )

    footer_text = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert footer_text.bounds.x == pytest.approx(0)
    assert footer_text.bounds.width == pytest.approx(1920)
    assert "node-out-of-section-horizontal" not in issue_codes


def test_pipeline_footer_legal_text_is_contained_to_viewport_when_footer_bleeds() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-legal-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 200},
            "children": [
                {
                    "id": "footer",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {
                        "x": -7,
                        "y": 100,
                        "width": 1933,
                        "height": 75,
                    },
                    "children": [
                        {
                            "id": "footer-text",
                            "name": "footer-text",
                            "type": "TEXT",
                            "characters": "2025 - 2026 Tous droits reserves Copyright Example",
                            "style": {"fontSize": 20, "lineHeightPx": 25},
                            "absoluteBoundingBox": {
                                "x": -7,
                                "y": 100,
                                "width": 1933,
                                "height": 75,
                            },
                        }
                    ],
                }
            ],
        }
    )

    footer_text = plan.sections[0].nodes[0]

    assert footer_text.bounds.x == pytest.approx(0)
    assert footer_text.bounds.width == pytest.approx(1920)


def test_pipeline_footer_text_name_without_legal_copy_does_not_expand() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-label-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "footer",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                    "children": [
                        {
                            "id": "footer-text",
                            "name": "footer-text",
                            "type": "TEXT",
                            "characters": "Footer text",
                            "style": {"fontSize": 2, "lineHeightPx": 3},
                            "absoluteBoundingBox": {
                                "x": 120,
                                "y": 100,
                                "width": 120,
                                "height": 5,
                            },
                        }
                    ],
                }
            ],
        }
    )

    footer_text = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert footer_text.bounds.x == pytest.approx(120)
    assert footer_text.bounds.width == pytest.approx(120)
    assert footer_text.style["font-size"] == "2px"
    assert "footer-text-expanded-for-readability" not in issue_codes


def test_pipeline_footer_legal_text_is_vertically_centered_even_when_sized() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-centered-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 80},
            "children": [
                {
                    "id": "footer",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 48},
                    "children": [
                        {
                            "id": "footer-copy",
                            "name": "footer-copy",
                            "type": "TEXT",
                            "characters": "2025 - 2026 Tous droits réservés © Example",
                            "style": {"fontSize": 8, "lineHeightPx": 12},
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 48,
                            },
                        }
                    ],
                }
            ],
        }
    )

    footer_text = plan.sections[0].nodes[0]

    assert footer_text.bounds.x == pytest.approx(0)
    assert footer_text.bounds.height == pytest.approx(48)
    assert footer_text.style["display"] == "flex"
    assert footer_text.style["align-items"] == "center"
    assert footer_text.style["justify-content"] == "center"


def test_pipeline_footer_legal_text_repairs_mojibake_copyright_marker() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-legal-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "footer",
                    "name": "footer",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                    "children": [
                        {
                            "id": "footer-copy",
                            "name": "texte-footer-copy",
                            "type": "TEXT",
                            "characters": "\u00c3\u0082\u00c2\u00a9 2026 Example",
                            "style": {"fontSize": 2, "lineHeightPx": 3},
                            "absoluteBoundingBox": {
                                "x": 140,
                                "y": 100,
                                "width": 80,
                                "height": 5,
                            },
                        }
                    ],
                }
            ],
        }
    )

    footer_text = plan.sections[0].nodes[0]

    assert footer_text.bounds.x == pytest.approx(5)
    assert footer_text.bounds.width == pytest.approx(392)
    assert "footer-text-expanded-for-readability" in [issue.code for issue in plan.diagnostics]


def test_pipeline_footer_strip_stacks_after_nested_footer_content() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-stack-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 360},
            "children": [
                {
                    "id": "footer-section",
                    "name": "footer-mobile",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 220},
                    "children": [
                        {
                            "id": "form-section",
                            "name": "section-formulaire",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 190,
                            },
                            "children": [
                                {
                                    "id": "form-copy",
                                    "name": "texte-form-copy",
                                    "type": "TEXT",
                                    "characters": "Message du formulaire",
                                    "absoluteBoundingBox": {
                                        "x": 40,
                                        "y": 150,
                                        "width": 220,
                                        "height": 40,
                                    },
                                }
                            ],
                        },
                        {
                            "id": "footer-strip",
                            "name": "footer",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 120,
                                "width": 402,
                                "height": 45,
                            },
                            "children": [
                                _raw_box("footer-bg", "bg-footer", 0, 120, 402, 45),
                                {
                                    "id": "footer-copy",
                                    "name": "footer-text",
                                    "type": "TEXT",
                                    "characters": (
                                        "2025 - 2026 Tous droits réservés © Embedded in Mind"
                                    ),
                                    "style": {"fontSize": 8, "lineHeightPx": 12},
                                    "absoluteBoundingBox": {
                                        "x": 0,
                                        "y": 120,
                                        "width": 402,
                                        "height": 45,
                                    },
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    )

    form_section = plan.sections[0].nodes[0]
    footer_strip = plan.sections[0].nodes[1]
    strip_gap = footer_strip.bounds.y - form_section.bounds.bottom

    assert strip_gap == pytest.approx(-70)
    assert plan.sections[0].bounds.height >= footer_strip.bounds.bottom
    assert "footer-strip-stacked-after-content" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_contain_narrow_decorative_overflow() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-decorative-overflow-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 260},
            "children": [
                {
                    "id": "visual",
                    "name": "section-visual",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 60, "width": 402, "height": 140},
                    "children": [
                        _raw_box("decor-shape", "decor-shape", -20, 40, 120, 80),
                        {
                            "id": "body",
                            "name": "texte-body",
                            "type": "TEXT",
                            "characters": "Contenu lisible",
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 90,
                                "width": 220,
                                "height": 30,
                            },
                        },
                    ],
                }
            ],
        }
    )

    decor = next(node for node in plan.sections[0].nodes if node.name == "decor-shape")

    assert decor.layer == "decorative"
    assert decor.bounds.x == pytest.approx(0)
    assert decor.bounds.y == pytest.approx(60)
    assert decor.bounds.width == pytest.approx(100)
    assert decor.bounds.height == pytest.approx(60)
    assert "decorative-overflow-contained" in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_ignore_structure_wrapper_bottom_for_section_expansion() -> (
    None
):
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-wrapper-bottom-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 360},
            "children": [
                {
                    "id": "contact",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
                    "children": [
                        {
                            "id": "contact-wrapper",
                            "name": "section-contact-moi",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 900,
                            },
                            "children": [
                                {
                                    "id": "contact-copy",
                                    "name": "texte-contact-copy",
                                    "type": "TEXT",
                                    "characters": (
                                        "Long readable text that wraps enough to require a taller "
                                        "text box."
                                    ),
                                    "style": {"fontSize": 12, "lineHeightPx": 12},
                                    "absoluteBoundingBox": {
                                        "x": 24,
                                        "y": 40,
                                        "width": 90,
                                        "height": 8,
                                    },
                                }
                            ],
                        }
                    ],
                },
                {
                    "id": "after",
                    "name": "section-after",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 180, "width": 402, "height": 120},
                    "children": [
                        {
                            "id": "after-title",
                            "name": "texte-after-title",
                            "type": "TEXT",
                            "characters": "After",
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 210,
                                "width": 120,
                                "height": 24,
                            },
                        }
                    ],
                },
            ],
        }
    )

    issue_codes = [issue.code for issue in plan.diagnostics]
    wrapper = _find_node(plan.sections[0].nodes[0], "section-contact-moi")

    assert "text-intrinsic-height-expanded" not in issue_codes
    assert "structure-wrapper-compacted-for-semantic-content" not in issue_codes
    assert wrapper.bounds.height == pytest.approx(900)
    assert plan.sections[0].bounds.height == pytest.approx(180)
    assert plan.sections[1].bounds.y == pytest.approx(180)
    assert "section-expanded-for-semantic-content" not in issue_codes


def test_pipeline_semantic_adjustments_compact_closed_accordion_space() -> None:
    payload = _raw_multi_accordion_payload()

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    faq = plan.sections[0]
    next_section = plan.sections[1]
    accordion = faq.nodes[0]
    item_1 = _find_node(accordion, "accordion-item-1-open")
    item_2 = _find_node(accordion, "accordion-item-2")
    item_3 = _find_node(accordion, "accordion-item-3")

    assert item_1.bounds.height == pytest.approx(120)
    assert item_2.bounds.height == pytest.approx(30)
    assert item_3.bounds.height == pytest.approx(30)
    assert item_3.bounds.y == pytest.approx(250)
    assert accordion.bounds.height < 260
    assert faq.bounds.height == pytest.approx(304)
    assert next_section.bounds.y == pytest.approx(faq.bounds.bottom)
    assert plan.height == 404
    assert html.count("<details") == 3
    assert html.count(" open>") == 1
    issue_codes = [issue.code for issue in plan.diagnostics]
    assert "accordion-closed-panel-space" in issue_codes
    assert "section-compacted-for-semantic-content" in issue_codes
    assert "page-height-compacted-for-semantic-content" in issue_codes


def test_pipeline_semantic_adjustments_cap_compacted_accordion_gaps() -> None:
    payload = _raw_multi_accordion_payload()
    accordion_children = payload["children"][0]["children"][0]["children"]  # type: ignore[index]
    accordion_children[1] = _raw_accordion_item(2, y=240, open_item=False)
    accordion_children[2] = _raw_accordion_item(3, y=520, open_item=False)

    plan = Pipeline().render_plan(payload)
    accordion = plan.sections[0].nodes[0]
    item_1 = _find_node(accordion, "accordion-item-1-open")
    item_2 = _find_node(accordion, "accordion-item-2")
    item_3 = _find_node(accordion, "accordion-item-3")

    assert item_2.bounds.y - item_1.bounds.bottom <= 24
    assert item_3.bounds.y - item_2.bounds.bottom <= 24


def test_pipeline_semantic_adjustments_stack_overlapping_open_accordion_items() -> None:
    payload = _raw_multi_accordion_payload()
    payload["children"][0]["children"][0]["name"] = "accordion-multi-faq"  # type: ignore[index]
    accordion_children = payload["children"][0]["children"][0]["children"]  # type: ignore[index]
    accordion_children[1] = _raw_accordion_item(2, y=140, open_item=True)
    accordion_children[2] = _raw_accordion_item(3, y=220, open_item=True)

    plan = Pipeline().render_plan(payload)
    accordion = plan.sections[0].nodes[0]
    item_1 = _find_node(accordion, "accordion-item-1-open")
    item_2 = _find_node(accordion, "accordion-item-2-open")
    item_3 = _find_node(accordion, "accordion-item-3-open")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert item_2.bounds.y >= item_1.bounds.bottom
    assert item_3.bounds.y >= item_2.bounds.bottom
    assert "section-expanded-for-semantic-content" in issue_codes
    assert "content-overlap" not in issue_codes


def test_pipeline_semantic_adjustments_single_accordion_keeps_first_open_item() -> None:
    payload = _raw_multi_accordion_payload()
    accordion_children = payload["children"][0]["children"][0]["children"]  # type: ignore[index]
    accordion_children[1] = _raw_accordion_item(2, y=200, open_item=True)
    accordion_children[2] = _raw_accordion_item(3, y=340, open_item=True)

    plan = Pipeline().render_plan(payload)
    accordion = plan.sections[0].nodes[0]
    open_items = [item for item in accordion.children if item.attributes.get("open")]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert [item.name for item in open_items] == ["accordion-item-1-open"]
    assert "accordion-single-open-state-normalized" in issue_codes


def test_pipeline_semantic_adjustments_shift_open_accordion_panel_below_trigger() -> None:
    payload = _raw_accordion_payload()
    item = payload["children"][0]["children"][0]["children"][0]  # type: ignore[index]
    panel = item["children"][1]  # type: ignore[index]
    panel["absoluteBoundingBox"]["y"] = 70  # type: ignore[index]
    answer = panel["children"][0]  # type: ignore[index]
    answer["absoluteBoundingBox"]["y"] = 80  # type: ignore[index]

    plan = Pipeline().render_plan(payload)
    accordion = plan.sections[0].nodes[0]
    item_plan = _find_node(accordion, "accordion-item-1-open")
    trigger = _find_node(item_plan, "accordion-trigger-1")
    panel_plan = _find_node(item_plan, "accordion-panel-1")

    assert panel_plan.bounds.y >= trigger.bounds.bottom
    assert "accordion-panel-shifted-for-trigger-space" in [issue.code for issue in plan.diagnostics]
    assert "content-overlap" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_shift_panel_with_overhanging_child() -> None:
    payload = _raw_accordion_payload()
    item = payload["children"][0]["children"][0]["children"][0]  # type: ignore[index]
    trigger = item["children"][0]  # type: ignore[index]
    panel = item["children"][1]  # type: ignore[index]
    trigger["absoluteBoundingBox"]["y"] = 40  # type: ignore[index]
    trigger["absoluteBoundingBox"]["height"] = 28  # type: ignore[index]
    panel["absoluteBoundingBox"]["y"] = 68  # type: ignore[index]
    answer = panel["children"][0]  # type: ignore[index]
    answer["absoluteBoundingBox"]["y"] = 65  # type: ignore[index]

    plan = Pipeline().render_plan(payload)
    item_plan = _find_node(plan.sections[0].nodes[0], "accordion-item-1-open")
    trigger_plan = _find_node(item_plan, "accordion-trigger-1")
    answer_plan = _find_node(item_plan, "texte-reponse-1")

    assert answer_plan.bounds.y >= trigger_plan.bounds.bottom
    assert "accordion-panel-shifted-for-trigger-space" in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_preserve_top_overflowing_footer_decor() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-footer-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 900},
            "children": [
                {
                    "id": "footer",
                    "name": "footer-tablette",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 400, "width": 834, "height": 380},
                    "children": [
                        {
                            "id": "decor",
                            "name": "decor-droite-contact",
                            "type": "RECTANGLE",
                            "absoluteBoundingBox": {
                                "x": 507,
                                "y": 280,
                                "width": 327,
                                "height": 200,
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    decor = plan.sections[0].nodes[0]

    assert decor.bounds.y == pytest.approx(280)
    assert decor.bounds.height == pytest.approx(200)
    assert "decorative-overflow-contained" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_keep_content_above_decorative_siblings() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-stack-order-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 320},
            "children": [
                {
                    "id": "footer",
                    "name": "footer-mobile",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 260},
                    "children": [
                        {
                            "id": "decor",
                            "name": "decor-droite-contact",
                            "type": "RECTANGLE",
                            "absoluteBoundingBox": {
                                "x": 260,
                                "y": -40,
                                "width": 142,
                                "height": 120,
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "color": {"r": 0.8, "g": 0.3, "b": 0.3, "a": 1},
                                }
                            ],
                        },
                        {
                            "id": "form",
                            "name": "section-formulaire",
                            "type": "FRAME",
                            "absoluteBoundingBox": {"x": 40, "y": 40, "width": 320, "height": 160},
                            "children": [
                                {
                                    "id": "bg",
                                    "name": "bg-formulaire",
                                    "type": "RECTANGLE",
                                    "absoluteBoundingBox": {
                                        "x": 40,
                                        "y": 40,
                                        "width": 320,
                                        "height": 160,
                                    },
                                    "fills": [
                                        {
                                            "type": "SOLID",
                                            "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                                        }
                                    ],
                                },
                                {
                                    "id": "label",
                                    "name": "texte-formulaire",
                                    "type": "TEXT",
                                    "characters": "Contact",
                                    "absoluteBoundingBox": {
                                        "x": 80,
                                        "y": 80,
                                        "width": 120,
                                        "height": 30,
                                    },
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    )

    decor = plan.sections[0].nodes[0]
    form = plan.sections[0].nodes[1]
    form_bg = _find_node(form, "bg-formulaire")
    form_label = _find_node(form, "texte-formulaire")

    assert int(form.style["z-index"]) > int(decor.style["z-index"])
    assert form_bg.style["z-index"] == "0"
    assert int(form_label.style["z-index"]) > int(form_bg.style["z-index"])


def test_pipeline_semantic_adjustments_keep_contact_label_above_decorative_shape() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-contact-footer-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 380},
            "children": [
                {
                    "id": "footer",
                    "name": "footer-tablette",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 380},
                    "children": [
                        {
                            "id": "section-formulaire",
                            "name": "section-formulaire",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 834,
                                "height": 332,
                            },
                            "children": [
                                {
                                    "id": "contact-illu-frame",
                                    "name": "contact-illu-frame",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 0,
                                        "y": 0,
                                        "width": 415,
                                        "height": 332,
                                    },
                                    "children": [
                                        {
                                            "id": "decor",
                                            "name": "decor-fond-logo-contact",
                                            "type": "RECTANGLE",
                                            "absoluteBoundingBox": {
                                                "x": 0,
                                                "y": -32,
                                                "width": 408,
                                                "height": 364,
                                            },
                                            "fills": [
                                                {
                                                    "type": "SOLID",
                                                    "color": {
                                                        "r": 0,
                                                        "g": 0.1,
                                                        "b": 0.3,
                                                        "a": 1,
                                                    },
                                                }
                                            ],
                                        },
                                        {
                                            "id": "label",
                                            "name": "label-contact",
                                            "type": "TEXT",
                                            "characters": "Contact",
                                            "absoluteBoundingBox": {
                                                "x": 0,
                                                "y": 0,
                                                "width": 374,
                                                "height": 332,
                                            },
                                        },
                                    ],
                                },
                                {
                                    "id": "form",
                                    "name": "formulaire-contact-post",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 417,
                                        "y": 50,
                                        "width": 300,
                                        "height": 240,
                                    },
                                    "children": [
                                        {
                                            "id": "field",
                                            "name": "nom",
                                            "type": "TEXT",
                                            "characters": "Nom et Prénom",
                                            "absoluteBoundingBox": {
                                                "x": 450,
                                                "y": 70,
                                                "width": 220,
                                                "height": 24,
                                            },
                                        }
                                    ],
                                },
                            ],
                        },
                        {
                            "id": "footer-strip",
                            "name": "footer",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 332,
                                "width": 834,
                                "height": 48,
                            },
                            "children": [
                                _raw_box("footer-bg", "bg-footer", 0, 332, 834, 48),
                                {
                                    "id": "footer-text",
                                    "name": "footer-text",
                                    "type": "TEXT",
                                    "characters": (
                                        "2025 - 2026 Tous droits réservés © Embedded in Mind"
                                    ),
                                    "absoluteBoundingBox": {
                                        "x": 0,
                                        "y": 335,
                                        "width": 834,
                                        "height": 20,
                                    },
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    )

    frame = _find_node(plan.sections[0].nodes[0], "contact-illu-frame")
    decor = _find_node(frame, "decor-fond-logo-contact")
    label = _find_node(frame, "label-contact")

    assert int(label.style["z-index"]) > int(decor.style["z-index"])
    assert label.bounds.y == pytest.approx(0)
    assert label.bounds.height == pytest.approx(332)


def test_pipeline_semantic_adjustments_keep_decorative_backgrounds_behind_content() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-stack-band-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 500},
            "children": [
                {
                    "id": "band",
                    "name": "section-bandeau-test",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 260},
                    "children": [
                        {
                            "id": "decor",
                            "name": "decor-accompagnement-cta",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 834,
                                "height": 260,
                            },
                            "children": [
                                {
                                    "id": "bg",
                                    "name": "bg-accompagnement-cta",
                                    "type": "RECTANGLE",
                                    "absoluteBoundingBox": {
                                        "x": 0,
                                        "y": 0,
                                        "width": 834,
                                        "height": 260,
                                    },
                                    "fills": [
                                        {
                                            "type": "SOLID",
                                            "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                                        }
                                    ],
                                },
                                {
                                    "id": "asset",
                                    "name": "image-montgolfiere",
                                    "type": "RECTANGLE",
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 20,
                                        "width": 120,
                                        "height": 180,
                                    },
                                    "fills": [
                                        {
                                            "type": "SOLID",
                                            "color": {"r": 0.5, "g": 0.5, "b": 0.9, "a": 1},
                                        }
                                    ],
                                },
                            ],
                        },
                        {
                            "id": "title",
                            "name": "titre-h4-presta-decoller-projets",
                            "type": "TEXT",
                            "characters": "Faites decoller vos projets",
                            "absoluteBoundingBox": {
                                "x": 80,
                                "y": 80,
                                "width": 300,
                                "height": 40,
                            },
                        },
                    ],
                }
            ],
        }
    )

    decor = plan.sections[0].nodes[0]
    title = plan.sections[0].nodes[1]
    bg = _find_node(decor, "bg-accompagnement-cta")

    assert decor.layer == "decorative"
    assert decor.style["z-index"] == "0"
    assert bg.style["z-index"] == "0"
    assert int(title.style["z-index"]) > int(decor.style["z-index"])


def test_pipeline_semantic_adjustments_do_not_pad_visual_bands_for_rule_only_changes() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-padding-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 420},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-cta",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 180},
                    "children": [
                        {
                            "id": "bg",
                            "name": "bg-bandeau-cta",
                            "type": "RECTANGLE",
                            "absoluteBoundingBox": {
                                "x": -20,
                                "y": 100,
                                "width": 422,
                                "height": 180,
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                                }
                            ],
                        },
                        {
                            "id": "title",
                            "name": "titre-bandeau",
                            "type": "TEXT",
                            "characters": "Titre du bandeau",
                            "absoluteBoundingBox": {
                                "x": 40,
                                "y": 130,
                                "width": 320,
                                "height": 40,
                            },
                        },
                    ],
                }
            ],
        }
    )

    band = plan.sections[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert band.bounds.height == pytest.approx(180)
    assert "section-expanded-for-semantic-content" not in issue_codes
    assert "background-overflow-contained" not in issue_codes


def test_pipeline_semantic_adjustments_do_not_pad_centered_top_heading_frame() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-centered-hero-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 240},
            "children": [
                {
                    "id": "hero",
                    "name": "section-hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 119},
                    "children": [
                        _raw_box("bg", "bg-hero", 0, 0, 402, 119),
                        {
                            "id": "title",
                            "name": "titre-h1-hero",
                            "type": "TEXT",
                            "characters": "Ensemble,faisons decoller\nvos innovations !",
                            "style": {
                                "fontSize": 20,
                                "fontWeight": 700,
                                "lineHeightPx": 15,
                                "textAlignHorizontal": "CENTER",
                                "textAlignVertical": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 32,
                                "y": 0,
                                "width": 338,
                                "height": 74,
                            },
                        },
                        {
                            "id": "subtitle",
                            "name": "titre-h3-hero",
                            "type": "TEXT",
                            "characters": "Un bureau d'etude au coeur de la vallee de l'arve.",
                            "style": {
                                "fontSize": 14,
                                "lineHeightPx": 13,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 65,
                                "y": 74,
                                "width": 272,
                                "height": 45,
                            },
                        },
                    ],
                }
            ],
        }
    )

    hero = plan.sections[0]
    title = next(node for node in hero.nodes if node.name == "titre-h1-hero")
    subtitle = next(node for node in hero.nodes if node.name == "titre-h3-hero")

    assert hero.bounds.height == pytest.approx(119)
    assert title.bounds.y == pytest.approx(0)
    assert subtitle.bounds.y == pytest.approx(74)


def test_pipeline_semantic_adjustments_keep_dense_band_text_readable() -> None:
    long_copy = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Vestibulum quis "
        "consequat lacus, sed tristique augue. Donec efficitur, sapien vitae cursus "
        "dictum, arcu velit feugiat risus, a mollis ipsum sem at libero. Donec diam "
        "nibh, hendrerit sit amet est eu, iaculis sagittis sapien. Duis lectus augue, "
        "dapibus vitae turpis vel, sollicitudin iaculis neque. Lorem ipsum dolor sit "
        "amet, consectetur adipiscing elit."
    )
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-readable-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 420},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-droite-accompagnement",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 147},
                    "children": [
                        _raw_box("bg", "bg-bandeau-accompagnement", 0, 100, 402, 147),
                        {
                            "id": "title",
                            "name": "titre-h4-accueil-decoller-projets",
                            "type": "TEXT",
                            "characters": (
                                "Faites decoller vos projets grace\n"
                                "a notre accompagnement sur-mesure"
                            ),
                            "style": {
                                "fontSize": 14,
                                "fontWeight": 700,
                                "lineHeightPx": 12,
                                "textAlignHorizontal": "CENTER",
                                "textAlignVertical": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 8,
                                "y": 112,
                                "width": 386,
                                "height": 37,
                            },
                        },
                        {
                            "id": "copy",
                            "name": "texte-accomp",
                            "type": "TEXT",
                            "characters": long_copy,
                            "style": {
                                "fontSize": 11,
                                "lineHeightPx": 9.8,
                                "textAlignHorizontal": "CENTER",
                                "textAlignVertical": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 44,
                                "y": 169,
                                "width": 314,
                                "height": 64,
                            },
                        },
                    ],
                }
            ],
        }
    )

    band = plan.sections[0]
    background = _find_node(band.nodes[0], "bg-bandeau-accompagnement")
    title_node = next(
        node for node in band.nodes if node.name == "titre-h4-accueil-decoller-projets"
    )
    copy_node = next(node for node in band.nodes if node.name == "texte-accomp")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert title_node.style["line-height"] == "12px"
    assert title_node.style["display"] == "flex"
    assert title_node.style["justify-content"] == "center"
    assert copy_node.style["line-height"] == "9.8px"
    assert copy_node.style["display"] == "flex"
    assert copy_node.style["justify-content"] == "center"
    assert copy_node.bounds.x == pytest.approx(44)
    assert copy_node.bounds.width == pytest.approx(314)
    assert copy_node.bounds.height == pytest.approx(64)
    assert copy_node.bounds.y == pytest.approx(169)
    assert band.bounds.height == pytest.approx(147)
    assert background.bounds.height == pytest.approx(band.bounds.height)
    assert "band-text-line-height-normalized" not in issue_codes
    assert "content-text-contained-to-rail" not in issue_codes
    assert "section-expanded-for-semantic-content" not in issue_codes


def test_pipeline_semantic_adjustments_contain_overwide_band_body_text_to_rail() -> None:
    long_copy = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Vestibulum quis "
        "consequat lacus, sed tristique augue. Donec efficitur, sapien vitae cursus "
        "dictum, arcu velit feugiat risus, a mollis ipsum sem at libero."
    )
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-centered-text-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 420},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-droite-accompagnement",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 174},
                    "children": [
                        _raw_box("bg", "bg-bandeau-accompagnement", -46, 100, 448, 162),
                        {
                            "id": "title",
                            "name": "titre-h4-accueil-decoller-projets",
                            "type": "TEXT",
                            "characters": (
                                "Faites decoller vos projets grace\n"
                                "a notre accompagnement sur-mesure"
                            ),
                            "style": {
                                "fontSize": 14,
                                "fontWeight": 700,
                                "lineHeightPx": 12,
                                "textAlignHorizontal": "CENTER",
                                "textAlignVertical": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 106.5,
                                "y": 116,
                                "width": 189,
                                "height": 48,
                            },
                        },
                        {
                            "id": "copy",
                            "name": "texte-accomp",
                            "type": "TEXT",
                            "characters": long_copy,
                            "style": {
                                "fontSize": 11,
                                "lineHeightPx": 10,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 44,
                                "y": 174,
                                "width": 314,
                                "height": 88,
                            },
                        },
                    ],
                }
            ],
        }
    )

    band = plan.sections[0]
    title = next(node for node in band.nodes if node.name == "titre-h4-accueil-decoller-projets")
    copy = next(node for node in band.nodes if node.name == "texte-accomp")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert title.bounds.x == pytest.approx(106.5)
    assert title.bounds.width == pytest.approx(189)
    assert title.bounds.height == pytest.approx(48)
    assert copy.bounds.x == pytest.approx(44)
    assert copy.bounds.width == pytest.approx(314)
    assert copy.bounds.height == pytest.approx(88)
    assert "content-text-contained-to-rail" not in issue_codes


@pytest.mark.parametrize(
    "page_width",
    (402, 834, 1920),
)
def test_pipeline_semantic_adjustments_preserve_single_text_box_outside_content_rail(
    page_width: int,
) -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": f"page-content-rail-{page_width}",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": page_width, "height": 180},
            "children": [
                {
                    "id": "section",
                    "name": "section-hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {
                        "x": 0,
                        "y": 0,
                        "width": page_width,
                        "height": 120,
                    },
                    "children": [
                        {
                            "id": "copy",
                            "name": "texte-hero",
                            "type": "TEXT",
                            "characters": "Texte court",
                            "style": {"fontSize": 16, "lineHeightPx": 20},
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 40,
                                "width": page_width,
                                "height": 30,
                            },
                        }
                    ],
                }
            ],
        }
    )

    text = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert text.bounds.x == pytest.approx(0)
    assert text.bounds.width == pytest.approx(page_width)
    assert "content-text-contained-to-rail" not in issue_codes


def test_pipeline_semantic_adjustments_contain_text_column_rows_to_content_rail() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-content-column-rail-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 520},
            "children": [
                {
                    "id": "section",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 500},
                    "children": [
                        {
                            "id": "content",
                            "name": "content-columns",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 60,
                                "width": 834,
                                "height": 360,
                            },
                            "children": [
                                {
                                    "id": "left",
                                    "name": "colonne-gauche",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 147,
                                        "y": 100,
                                        "width": 260,
                                        "height": 260,
                                    },
                                    "children": [
                                        {
                                            "id": "left-title",
                                            "name": "titre-colonne-gauche",
                                            "type": "TEXT",
                                            "characters": "Bastien Blochet",
                                            "style": {"fontSize": 18, "lineHeightPx": 22},
                                            "absoluteBoundingBox": {
                                                "x": 147,
                                                "y": 100,
                                                "width": 260,
                                                "height": 24,
                                            },
                                        },
                                        {
                                            "id": "left-copy",
                                            "name": "texte-colonne-gauche",
                                            "type": "TEXT",
                                            "characters": (
                                                "Lorem ipsum dolor sit amet, consectetur adipiscing "
                                                "elit. Vestibulum quis consequat lacus."
                                            ),
                                            "style": {"fontSize": 16, "lineHeightPx": 20},
                                            "absoluteBoundingBox": {
                                                "x": 147,
                                                "y": 140,
                                                "width": 260,
                                                "height": 120,
                                            },
                                        },
                                    ],
                                },
                                {
                                    "id": "right",
                                    "name": "colonne-droite",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 427,
                                        "y": 100,
                                        "width": 260,
                                        "height": 260,
                                    },
                                    "children": [
                                        {
                                            "id": "right-copy",
                                            "name": "texte-colonne-droite",
                                            "type": "TEXT",
                                            "characters": (
                                                "Donec efficitur, sapien vitae cursus dictum, arcu "
                                                "velit feugiat risus, a mollis ipsum sem."
                                            ),
                                            "style": {"fontSize": 16, "lineHeightPx": 20},
                                            "absoluteBoundingBox": {
                                                "x": 427,
                                                "y": 100,
                                                "width": 260,
                                                "height": 120,
                                            },
                                        },
                                        {
                                            "id": "right-title",
                                            "name": "titre-colonne-droite",
                                            "type": "TEXT",
                                            "characters": "Expertise",
                                            "style": {"fontSize": 18, "lineHeightPx": 22},
                                            "absoluteBoundingBox": {
                                                "x": 427,
                                                "y": 240,
                                                "width": 260,
                                                "height": 24,
                                            },
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    left = _find_section_node(plan.sections[0], "colonne-gauche")
    right = _find_section_node(plan.sections[0], "colonne-droite")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert left.bounds.x == pytest.approx(147)
    assert left.bounds.width == pytest.approx(260)
    assert right.bounds.x == pytest.approx(427)
    assert right.bounds.width == pytest.approx(260)
    assert "content-column-row-contained-to-rail" not in issue_codes


def test_pipeline_semantic_adjustments_contain_link_card_rows_to_content_rail() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-link-cards-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 260},
            "children": [
                {
                    "id": "section",
                    "name": "section-cas-clients",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 220},
                    "children": [
                        {
                            "id": "row",
                            "name": "link-row-1",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 40,
                                "width": 402,
                                "height": 80,
                            },
                            "children": [
                                {
                                    "id": "card-1",
                                    "name": "case-card-1",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 48,
                                        "y": 40,
                                        "width": 142,
                                        "height": 80,
                                    },
                                    "children": [
                                        {
                                            "id": "card-1-text",
                                            "name": "texte-projet-1",
                                            "type": "TEXT",
                                            "characters": "Projet 1",
                                            "absoluteBoundingBox": {
                                                "x": 52,
                                                "y": 60,
                                                "width": 134,
                                                "height": 24,
                                            },
                                        }
                                    ],
                                },
                                {
                                    "id": "card-2",
                                    "name": "case-card-2",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 217,
                                        "y": 40,
                                        "width": 134,
                                        "height": 80,
                                    },
                                    "children": [
                                        {
                                            "id": "card-2-text",
                                            "name": "texte-projet-2",
                                            "type": "TEXT",
                                            "characters": "Projet 2",
                                            "absoluteBoundingBox": {
                                                "x": 221,
                                                "y": 60,
                                                "width": 126,
                                                "height": 24,
                                            },
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    row = plan.sections[0].nodes[0]
    card_1 = _find_node(row, "case-card-1")
    card_2 = _find_node(row, "case-card-2")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert card_1.bounds.x == pytest.approx(48)
    assert card_2.bounds.right == pytest.approx(351)
    assert "content-component-row-contained-to-rail" not in issue_codes


def test_pipeline_semantic_adjustments_contain_compact_visual_strip_to_content_rail() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-visual-strip-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-principe",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 40, "width": 402, "height": 96},
                    "children": [
                        _raw_box("bg", "bg-bandeau-principe", 0, 40, 402, 96),
                        _raw_visual_card(
                            "card-1",
                            "card-bandeau-item-idees",
                            56,
                            54,
                            64,
                            image_offset=0,
                            label_offset=28,
                        ),
                        _raw_asset("plus", "icone-bandeau-plus", 132, 110, 10, 10),
                        _raw_visual_card("card-2", "card-bandeau-item-expertise", 153, 112, 64),
                        _raw_asset("equal", "icone-bandeau-egal", 261, 112, 9, 6),
                        _raw_visual_card(
                            "card-3",
                            "card-bandeau-item-aventure",
                            284,
                            48,
                            67,
                            image_offset=47,
                            label_offset=0,
                        ),
                    ],
                }
            ],
        }
    )

    band = plan.sections[0]
    visual_nodes = [node for node in band.nodes if node.layer not in {"background", "decorative"}]
    visual_left = min(_render_node_left(node) for node in visual_nodes)
    visual_right = max(_render_node_right(node) for node in visual_nodes)
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert visual_left == pytest.approx(56)
    assert visual_right == pytest.approx(353)
    assert "content-visual-strip-contained-to-rail" not in issue_codes


def test_pipeline_semantic_adjustments_contain_accordion_to_content_rail() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-accordion-rail-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 320},
            "children": [
                {
                    "id": "section",
                    "name": "section-faq",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 40, "y": 0, "width": 322, "height": 280},
                    "children": [
                        {
                            "id": "accordion",
                            "name": "accordion-single-faq",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 40,
                                "y": 40,
                                "width": 322,
                                "height": 120,
                            },
                            "children": [
                                {
                                    "id": "item",
                                    "name": "accordion-item-1-open",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 40,
                                        "y": 40,
                                        "width": 322,
                                        "height": 120,
                                    },
                                    "children": [
                                        {
                                            "id": "trigger",
                                            "name": "accordion-trigger-1",
                                            "type": "FRAME",
                                            "absoluteBoundingBox": {
                                                "x": 40,
                                                "y": 40,
                                                "width": 322,
                                                "height": 28,
                                            },
                                            "children": [
                                                {
                                                    "id": "question",
                                                    "name": "texte-question-1",
                                                    "type": "TEXT",
                                                    "characters": "Question",
                                                    "absoluteBoundingBox": {
                                                        "x": 47,
                                                        "y": 40,
                                                        "width": 290,
                                                        "height": 28,
                                                    },
                                                }
                                            ],
                                        },
                                        {
                                            "id": "panel",
                                            "name": "accordion-panel-1",
                                            "type": "FRAME",
                                            "absoluteBoundingBox": {
                                                "x": 40,
                                                "y": 68,
                                                "width": 322,
                                                "height": 92,
                                            },
                                            "children": [
                                                {
                                                    "id": "answer",
                                                    "name": "texte-reponse-1",
                                                    "type": "TEXT",
                                                    "characters": "Reponse",
                                                    "absoluteBoundingBox": {
                                                        "x": 40,
                                                        "y": 68,
                                                        "width": 322,
                                                        "height": 48,
                                                    },
                                                }
                                            ],
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    accordion = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert accordion.bounds.x == pytest.approx(40)
    assert accordion.bounds.width == pytest.approx(322)
    assert "content-component-contained-to-rail" not in issue_codes


def test_pipeline_semantic_adjustments_keep_off_center_band_columns() -> None:
    long_copy = " ".join(["Lorem ipsum dolor sit amet"] * 14)
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-columns-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 420},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-gauche",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 174},
                    "children": [
                        _raw_box("bg", "bg-bandeau-gauche", 0, 100, 402, 174),
                        {
                            "id": "left-copy",
                            "name": "texte-colonne-gauche",
                            "type": "TEXT",
                            "characters": long_copy,
                            "style": {
                                "fontSize": 11,
                                "lineHeightPx": 10,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 130,
                                "width": 150,
                                "height": 110,
                            },
                        },
                        {
                            "id": "right-copy",
                            "name": "texte-colonne-droite",
                            "type": "TEXT",
                            "characters": long_copy,
                            "style": {
                                "fontSize": 11,
                                "lineHeightPx": 10,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 232,
                                "y": 130,
                                "width": 150,
                                "height": 110,
                            },
                        },
                    ],
                }
            ],
        }
    )

    band = plan.sections[0]
    left = next(node for node in band.nodes if node.name == "texte-colonne-gauche")
    right = next(node for node in band.nodes if node.name == "texte-colonne-droite")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert left.bounds.x == pytest.approx(20)
    assert left.bounds.width == pytest.approx(150)
    assert right.bounds.x == pytest.approx(232)
    assert right.bounds.width == pytest.approx(150)
    assert "band-centered-text-width-expanded" not in issue_codes
    assert "content-text-row-contained-to-rail" not in issue_codes


def test_pipeline_semantic_adjustments_preserve_tablet_band_content_wrapper() -> None:
    long_copy = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Vestibulum quis "
        "consequat lacus, sed tristique augue. Donec efficitur, sapien vitae cursus "
        "dictum, arcu velit feugiat risus, a mollis ipsum sem at libero. Donec diam "
        "nibh, hendrerit sit amet est eu, iaculis sagittis sapien."
    )
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-columns-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 420},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-droite-accompagnement",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 834, "height": 207},
                    "children": [
                        _raw_box("bg", "bg-embedded-bandeau", 32, 100, 802, 207),
                        _raw_box("left-decor", "image-montgolfiere", 8, 106, 82, 154),
                        _raw_box("right-decor", "image-droite-accompagnement", 781, 270, 53, 73),
                        {
                            "id": "content",
                            "name": "section-accompagnement-cta-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 186.7,
                                "y": 101,
                                "width": 460.6,
                                "height": 199,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h4-accueil-decoller-projets",
                                    "type": "TEXT",
                                    "characters": (
                                        "Faites decoller vos projets grace\n"
                                        "a notre accompagnement sur-mesure"
                                    ),
                                    "style": {
                                        "fontSize": 20,
                                        "fontWeight": 700,
                                        "lineHeightPx": 20,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 186.7,
                                        "y": 126,
                                        "width": 179,
                                        "height": 146,
                                    },
                                },
                                {
                                    "id": "copy",
                                    "name": "texte-accomp",
                                    "type": "TEXT",
                                    "characters": long_copy,
                                    "style": {
                                        "fontSize": 14,
                                        "lineHeightPx": 14,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 421.3,
                                        "y": 101,
                                        "width": 226,
                                        "height": 199,
                                    },
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    )

    band = plan.sections[0]
    content = next(node for node in band.nodes if node.name == "section-accompagnement-cta-content")
    title = _find_node(content, "titre-h4-accueil-decoller-projets")
    copy = _find_node(content, "texte-accomp")
    background = next(node for node in band.nodes if node.name == "bg-embedded-bandeau")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert background.bounds.x == pytest.approx(32)
    assert content.bounds.width == pytest.approx(460.6)
    assert title.bounds.x == pytest.approx(186.7)
    assert title.bounds.width == pytest.approx(179)
    assert copy.bounds.x == pytest.approx(421.3)
    assert copy.bounds.x > title.bounds.right
    assert copy.bounds.width == pytest.approx(226)
    assert "band-text-column-width-expanded" not in issue_codes
    assert "band-background-snapped-to-section" not in issue_codes


def test_pipeline_semantic_adjustments_preserve_explicit_band_heading_breaks() -> None:
    payload = {
        "id": "page",
        "name": "page-band-heading-1920",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 360},
        "children": [
            {
                "id": "band",
                "name": "bandeau-droite-accompagnement",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 120, "width": 1920, "height": 218},
                "children": [
                    _raw_box("bg", "bg-accompagnement-cta", 0, 120, 1920, 218),
                    {
                        "id": "title",
                        "name": "titre-h4-presta-decoller-projets",
                        "type": "TEXT",
                        "characters": (
                            "Faites decoller vos projets grace\na notre accompagnement sur-mesure"
                        ),
                        "style": {
                            "fontSize": 32,
                            "fontWeight": 700,
                            "lineHeightPx": 42,
                            "textAlignHorizontal": "CENTER",
                        },
                        "absoluteBoundingBox": {
                            "x": 428.5,
                            "y": 185,
                            "width": 536,
                            "height": 84,
                        },
                    },
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    heading = plan.sections[0].nodes[1]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert heading.style["white-space"] == "pre"
    assert "white-space:pre" in html
    assert "band-heading-explicit-lines-preserved" in issue_codes


def test_pipeline_semantic_adjustments_keep_band_operator_assets_in_place() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-operators-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 360},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-principe",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 1920, "height": 220},
                    "children": [
                        _raw_box("bg", "bg-bandeau-principe", 0, 100, 1920, 220),
                        {
                            "id": "card",
                            "name": "card-bandeau-principe-item-idees",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 442,
                                "y": 120,
                                "width": 353,
                                "height": 170,
                            },
                            "children": [
                                {
                                    "id": "label",
                                    "name": "label-idees",
                                    "type": "TEXT",
                                    "characters": "Vos idees",
                                    "style": {
                                        "fontSize": 24,
                                        "lineHeightPx": 24,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 442,
                                        "y": 250,
                                        "width": 353,
                                        "height": 40,
                                    },
                                }
                            ],
                        },
                        _raw_asset(
                            "plus",
                            "icone-bandeau-principe-plus",
                            731,
                            170,
                            40,
                            44,
                        ),
                    ],
                }
            ],
        }
    )

    plus = _find_section_node(plan.sections[0], "icone-bandeau-principe-plus")

    assert plus.bounds.y == pytest.approx(170)
    assert plus.bounds.x == pytest.approx(731)
    assert "text-sibling-shifted-for-intrinsic-height" not in [
        issue.code for issue in plan.diagnostics if issue.node_id == "plus"
    ]


def test_pipeline_semantic_adjustments_align_icon_labels_to_visual_axis() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-icon-label-band-1920",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 360},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-principe",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 1920, "height": 220},
                    "children": [
                        _raw_box("bg", "bg-bandeau-principe", 0, 100, 1920, 220),
                        {
                            "id": "card",
                            "name": "card-bandeau-principe-item-idees",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 442,
                                "y": 120,
                                "width": 380,
                                "height": 170,
                            },
                            "children": [
                                _raw_asset("icon", "image-idees", 502, 120, 80, 120),
                                {
                                    "id": "label",
                                    "name": "label-idees",
                                    "type": "TEXT",
                                    "characters": "Vos idees",
                                    "style": {
                                        "fontSize": 24,
                                        "lineHeightPx": 24,
                                        "textAlignHorizontal": "CENTER",
                                    },
                                    "absoluteBoundingBox": {
                                        "x": 442,
                                        "y": 250,
                                        "width": 353,
                                        "height": 40,
                                    },
                                },
                            ],
                        },
                    ],
                }
            ],
        }
    )

    icon = _find_section_node(plan.sections[0], "image-idees")
    label = _find_section_node(plan.sections[0], "label-idees")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert icon.bounds.x == pytest.approx(502)
    assert icon.bounds.width == pytest.approx(80)
    assert label.bounds.x == pytest.approx(442)
    assert label.bounds.width == pytest.approx(353)
    assert "icon-label-aligned-to-visual" not in issue_codes


def test_pipeline_semantic_adjustments_allow_tablet_band_heading_wrap() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-heading-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 360},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-droite-accompagnement",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 120, "width": 834, "height": 207},
                    "children": [
                        _raw_box("bg", "bg-accompagnement-cta", 32, 120, 802, 207),
                        {
                            "id": "title",
                            "name": "titre-h4-presta-decoller-projets",
                            "type": "TEXT",
                            "characters": (
                                "Faites decoller vos projets grace\n"
                                "a notre accompagnement sur-mesure"
                            ),
                            "style": {
                                "fontSize": 20,
                                "fontWeight": 700,
                                "lineHeightPx": 20,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 98,
                                "y": 148,
                                "width": 321,
                                "height": 146,
                            },
                        },
                        {
                            "id": "copy",
                            "name": "texte-accomp",
                            "type": "TEXT",
                            "characters": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
                            "style": {
                                "fontSize": 14,
                                "lineHeightPx": 14,
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 452,
                                "y": 130,
                                "width": 321,
                                "height": 180,
                            },
                        },
                    ],
                }
            ],
        }
    )

    title = plan.sections[0].nodes[1]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert title.style["white-space"] == "pre"
    assert "band-heading-explicit-lines-preserved" in issue_codes


def test_pipeline_semantic_adjustments_preserve_tablet_heading_authored_lines() -> None:
    payload = {
        "id": "page",
        "name": "page-heading-lines-834",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 180},
        "children": [
            {
                "id": "section",
                "name": "section-labo",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 180},
                "children": [
                    {
                        "id": "subtitle",
                        "name": "titre-h4-labo",
                        "type": "TEXT",
                        "characters": (
                            "Parler de la passion de Bastien\n"
                            "Un titre assez grand pour du referencement"
                        ),
                        "style": {
                            "fontSize": 16,
                            "lineHeightPx": 20,
                            "textAlignHorizontal": "CENTER",
                        },
                        "absoluteBoundingBox": {
                            "x": 258,
                            "y": 52,
                            "width": 318,
                            "height": 36,
                        },
                    }
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    heading = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert heading.style["white-space"] == "pre"
    assert heading.bounds.height == pytest.approx(36)
    assert "white-space:pre" in html
    assert "heading-explicit-lines-preserved" in issue_codes
    assert "text-intrinsic-height-expanded" not in issue_codes


def test_pipeline_semantic_adjustments_ignore_edge_decor_assets_for_section_height() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-edge-decor-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 420},
            "children": [
                {
                    "id": "section",
                    "name": "section-callout",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 180},
                    "children": [
                        {
                            "id": "copy",
                            "name": "texte-callout",
                            "type": "TEXT",
                            "characters": "Contenu principal",
                            "absoluteBoundingBox": {
                                "x": 40,
                                "y": 150,
                                "width": 220,
                                "height": 40,
                            },
                        },
                        {
                            "id": "decor",
                            "name": "image-droite-callout",
                            "type": "RECTANGLE",
                            "pipelineImageUrl": "https://images.example/decor.png",
                            "absoluteBoundingBox": {
                                "x": 360,
                                "y": 235,
                                "width": 42,
                                "height": 72,
                            },
                        },
                    ],
                }
            ],
        }
    )

    section = plan.sections[0]

    assert section.bounds.height == pytest.approx(180)
    assert "section-expanded-for-semantic-content" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_align_band_visuals_to_section() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-bandeau-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 500},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-gauche",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 120, "width": 402, "height": 180},
                    "children": [
                        {
                            "id": "bg",
                            "name": "bg-embedded-bandeau",
                            "type": "RECTANGLE",
                            "absoluteBoundingBox": {
                                "x": -46,
                                "y": 119,
                                "width": 448,
                                "height": 181,
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    band_bg = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert band_bg.bounds.x == pytest.approx(-46)
    assert band_bg.bounds.y == pytest.approx(119)
    assert band_bg.bounds.width == pytest.approx(448)
    assert band_bg.bounds.height == pytest.approx(181)
    assert "background-overflow-contained" not in issue_codes


def test_pipeline_semantic_adjustments_align_section_spanning_visuals_by_geometry() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-region-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 500},
            "children": [
                {
                    "id": "region",
                    "name": "region-callout",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 120, "width": 402, "height": 180},
                    "children": [
                        {
                            "id": "bg",
                            "name": "bg-callout",
                            "type": "RECTANGLE",
                            "absoluteBoundingBox": {
                                "x": 8,
                                "y": 120,
                                "width": 386,
                                "height": 180,
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    region_bg = plan.sections[0].nodes[0]

    assert region_bg.bounds.x == pytest.approx(8)
    assert region_bg.bounds.y == pytest.approx(120)
    assert region_bg.bounds.width == pytest.approx(386)
    assert region_bg.bounds.height == pytest.approx(180)
    assert "band-visual-aligned-to-section" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_contain_section_spanning_background_by_geometry() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-section-bg-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 500},
            "children": [
                {
                    "id": "region",
                    "name": "region-panel",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 180},
                    "children": [
                        {
                            "id": "bg",
                            "name": "bg-panel",
                            "type": "RECTANGLE",
                            "absoluteBoundingBox": {
                                "x": -20,
                                "y": 90,
                                "width": 442,
                                "height": 210,
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    region_bg = plan.sections[0].nodes[0]

    assert region_bg.bounds.x == pytest.approx(0)
    assert region_bg.bounds.y == pytest.approx(100)
    assert region_bg.bounds.width == pytest.approx(402)
    assert region_bg.bounds.height == pytest.approx(180)
    assert "background-overflow-contained" in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_recompact_band_wrapper_after_visual_align() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-bandeau-wrapper-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
            "children": [
                {
                    "id": "band",
                    "name": "bandeau-wrapper",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 160},
                    "children": [
                        {
                            "id": "wrapper",
                            "name": "section-bandeau-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": -46,
                                "y": 100,
                                "width": 448,
                                "height": 160,
                            },
                            "children": [
                                {
                                    "id": "bg",
                                    "name": "bg-embedded-bandeau",
                                    "type": "RECTANGLE",
                                    "absoluteBoundingBox": {
                                        "x": -46,
                                        "y": 100,
                                        "width": 448,
                                        "height": 160,
                                    },
                                    "fills": [
                                        {
                                            "type": "SOLID",
                                            "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                                        }
                                    ],
                                },
                                {
                                    "id": "title",
                                    "name": "titre-bandeau",
                                    "type": "TEXT",
                                    "characters": "Title",
                                    "absoluteBoundingBox": {
                                        "x": 100,
                                        "y": 120,
                                        "width": 160,
                                        "height": 40,
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )

    wrapper = plan.sections[0].nodes[0]
    band_bg = _find_node(wrapper, "bg-embedded-bandeau")

    assert band_bg.bounds.x == pytest.approx(-46)
    assert band_bg.bounds.width == pytest.approx(448)
    assert wrapper.bounds.x == pytest.approx(-46)
    assert wrapper.bounds.width == pytest.approx(448)
    assert "node-out-of-section-horizontal" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_keep_band_text_origin_when_expanded() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-band-text-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 320},
            "children": [
                {
                    "id": "band",
                    "name": "region-cta",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 100},
                    "children": [
                        {
                            "id": "bg",
                            "name": "bg-cta",
                            "type": "RECTANGLE",
                            "absoluteBoundingBox": {"x": 0, "y": 100, "width": 402, "height": 100},
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "color": {"r": 0, "g": 0.1, "b": 0.3, "a": 1},
                                }
                            ],
                        },
                        {
                            "id": "title",
                            "name": "titre-cta",
                            "type": "TEXT",
                            "characters": "This title wraps across many compact lines in the band",
                            "absoluteBoundingBox": {"x": 24, "y": 110, "width": 110, "height": 20},
                            "style": {"fontSize": 20, "lineHeightPx": 20},
                        },
                        {
                            "id": "body",
                            "name": "texte-cta",
                            "type": "TEXT",
                            "characters": "Body",
                            "absoluteBoundingBox": {
                                "x": 220,
                                "y": 100,
                                "width": 150,
                                "height": 100,
                            },
                            "style": {
                                "fontSize": 16,
                                "lineHeightPx": 20,
                                "textAlignVertical": "CENTER",
                            },
                        },
                    ],
                }
            ],
        }
    )

    body = next(node for node in plan.sections[0].nodes if node.name == "texte-cta")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert plan.sections[0].bounds.height == pytest.approx(100)
    assert body.bounds.y == pytest.approx(100)
    assert "section-bottom-anchored-content-shifted" not in issue_codes


def test_pipeline_text_style_overrides_reduce_effective_text_metrics() -> None:
    payload = _raw_text_override_payload()

    plan = Pipeline().render_plan(payload)
    html = Pipeline().render_static_html(payload)
    title = _find_node(plan.sections[0].nodes[0], "titre-h4-infos")
    paragraph = _find_node(plan.sections[0].nodes[0], "texte-infos")

    assert title.style["font-size"] == "18px"
    assert title.style["line-height"] == "23px"
    assert title.bounds.height == pytest.approx(60)
    assert paragraph.bounds.y == pytest.approx(80)
    assert "font-size:18px" in html
    assert "line-height:23px" in html
    assert "font-size:35px" not in html


def test_pipeline_text_vertical_alignment_from_figma_style() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-vertical-text-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
            "children": [
                {
                    "id": "section",
                    "name": "section-band",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 120},
                    "children": [
                        {
                            "id": "title",
                            "name": "titre-bandeau",
                            "type": "TEXT",
                            "characters": "Titre centre verticalement",
                            "style": {
                                "fontSize": 12,
                                "lineHeightPx": 14,
                                "textAlignVertical": "CENTER",
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 24,
                                "y": 20,
                                "width": 180,
                                "height": 80,
                            },
                        }
                    ],
                }
            ],
        }
    )

    title = plan.sections[0].nodes[0]

    assert title.style["display"] == "flex"
    assert title.style["flex-direction"] == "column"
    assert title.style["justify-content"] == "center"


def test_pipeline_preserves_centered_text_box_from_figma() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-centered-expanded-text-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "section",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 150},
                    "children": [
                        {
                            "id": "title",
                            "name": "titre-h4-centered",
                            "type": "TEXT",
                            "characters": (
                                "Faites decoller vos projets grace a notre "
                                "accompagnement sur-mesure"
                            ),
                            "style": {
                                "fontSize": 14,
                                "lineHeightPx": 16,
                                "textAlignVertical": "CENTER",
                                "textAlignHorizontal": "CENTER",
                            },
                            "absoluteBoundingBox": {
                                "x": 78,
                                "y": 60,
                                "width": 150,
                                "height": 20,
                            },
                        }
                    ],
                }
            ],
        }
    )

    title = plan.sections[0].nodes[0]
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert title.bounds.height == pytest.approx(20)
    assert title.bounds.y == pytest.approx(60)
    assert "text-intrinsic-height-expanded" not in issue_codes


def test_pipeline_semantic_adjustments_preserve_text_box_without_overrides() -> None:
    payload = _raw_text_override_payload()
    title = payload["children"][0]["children"][0]["children"][0]  # type: ignore[index]
    title.pop("characterStyleOverrides")  # type: ignore[attr-defined]
    title.pop("styleOverrideTable")  # type: ignore[attr-defined]

    plan = Pipeline().render_plan(payload)
    title_plan = _find_node(plan.sections[0].nodes[0], "titre-h4-infos")
    paragraph = _find_node(plan.sections[0].nodes[0], "texte-infos")

    assert title_plan.bounds.height == pytest.approx(60)
    assert paragraph.bounds.y == pytest.approx(80)
    assert "text-intrinsic-height-expanded" not in [issue.code for issue in plan.diagnostics]
    assert "text-sibling-shifted-for-intrinsic-height" not in [
        issue.code for issue in plan.diagnostics
    ]


def test_pipeline_semantic_adjustments_preserve_wrapped_text_height() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-wrapped-text-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "hero",
                    "name": "section-hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 110},
                    "children": [
                        {
                            "id": "subtitle",
                            "name": "titre-h2-prestation",
                            "type": "TEXT",
                            "characters": (
                                "Titre H2 qui comprend le nom de la prestation "
                                "et la denomination de bureau d'etude."
                            ),
                            "style": {"fontSize": 12, "lineHeightPx": 14},
                            "absoluteBoundingBox": {
                                "x": 98,
                                "y": 72,
                                "width": 210,
                                "height": 16,
                            },
                        }
                    ],
                }
            ],
        }
    )

    subtitle = plan.sections[0].nodes[0]
    assert subtitle.bounds.height == pytest.approx(16)
    assert "text-intrinsic-height-expanded" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_expand_styled_multiline_text_runs() -> None:
    role_text = (
        "Fondateur d'Embedded in Mind \n"
        "Ingenieur systemes embarques | Expertise DevOps & Open Source"
    )
    overrides = [1 if index < role_text.index("\n") else 2 for index, _ in enumerate(role_text)]

    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-contact-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 620},
            "children": [
                {
                    "id": "section",
                    "name": "section-contact",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 460},
                    "children": [
                        {
                            "id": "role",
                            "name": "titre-h4-contact-role",
                            "type": "TEXT",
                            "characters": role_text,
                            "style": {
                                "fontFamily": "Inter",
                                "fontSize": 16,
                                "lineHeightPx": 20,
                                "textAlignHorizontal": "LEFT",
                            },
                            "characterStyleOverrides": overrides,
                            "styleOverrideTable": {
                                "1": {
                                    "fontSize": 16,
                                    "fontWeight": 700,
                                    "italic": True,
                                    "lineHeightPx": 20,
                                },
                                "2": {
                                    "fontSize": 16,
                                    "fontWeight": 400,
                                    "lineHeightPx": 20,
                                },
                            },
                            "absoluteBoundingBox": {
                                "x": 171,
                                "y": 50,
                                "width": 236.88888888888889,
                                "height": 68,
                            },
                        },
                        {
                            "id": "paragraph",
                            "name": "texte-contact-paragraph-1",
                            "type": "TEXT",
                            "characters": "Lorem ipsum dolor sit amet.",
                            "style": {"fontSize": 14, "lineHeightPx": 14},
                            "absoluteBoundingBox": {
                                "x": 171,
                                "y": 126.6875,
                                "width": 236.88888888888889,
                                "height": 48,
                            },
                        },
                    ],
                }
            ],
        }
    )

    role = _find_node(plan.sections[0].nodes[0], "titre-h4-contact-role")
    paragraph = _find_node(plan.sections[0].nodes[1], "texte-contact-paragraph-1")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert role.bounds.height == pytest.approx(68)
    assert paragraph.bounds.y == pytest.approx(126.6875)
    assert "text-intrinsic-height-expanded" not in issue_codes
    assert "text-sibling-shifted-for-intrinsic-height" not in issue_codes


def test_pipeline_semantic_adjustments_do_not_expand_comfortably_sized_body_copy() -> None:
    body_copy = " ".join(
        [
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "Vestibulum quis consequat lacus, sed tristique augue.",
            "Donec efficitur, sapien vitae cursus dictum, arcu velit feugiat risus,",
            "a mollis ipsum sem at libero.",
        ]
        * 5
    )

    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-body-copy-834",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 500},
            "children": [
                {
                    "id": "section",
                    "name": "section-content",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 834, "height": 360},
                    "children": [
                        {
                            "id": "copy",
                            "name": "texte-long",
                            "type": "TEXT",
                            "characters": body_copy,
                            "style": {"fontSize": 14, "lineHeightPx": 14},
                            "absoluteBoundingBox": {
                                "x": 190,
                                "y": 40,
                                "width": 455,
                                "height": 282,
                            },
                        }
                    ],
                }
            ],
        }
    )

    copy = plan.sections[0].nodes[0]

    assert copy.bounds.height == pytest.approx(282)
    assert "text-intrinsic-height-expanded" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_semantic_adjustments_shift_only_overlapping_text_stack() -> None:
    payload = {
        "id": "page",
        "name": "page-text-stack-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 240},
        "children": [
            {
                "id": "section",
                "name": "section-content",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
                "children": [
                    {
                        "id": "title",
                        "name": "titre-h2-stack",
                        "type": "TEXT",
                        "characters": "Un titre de bloc vraiment long qui passe sur plusieurs lignes",
                        "style": {"fontSize": 12, "lineHeightPx": 14},
                        "absoluteBoundingBox": {
                            "x": 24,
                            "y": 24,
                            "width": 120,
                            "height": 12,
                        },
                    },
                    {
                        "id": "body",
                        "name": "texte-stack",
                        "type": "TEXT",
                        "characters": "Texte suivant",
                        "style": {"fontSize": 10, "lineHeightPx": 12},
                        "absoluteBoundingBox": {
                            "x": 24,
                            "y": 44,
                            "width": 160,
                            "height": 12,
                        },
                    },
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    title = _find_node(plan.sections[0].nodes[0], "titre-h2-stack")
    body = _find_node(plan.sections[0].nodes[1], "texte-stack")
    issue_codes = [issue.code for issue in plan.diagnostics]

    assert body.bounds.y == pytest.approx(44)
    assert title.bounds.height == pytest.approx(12)
    assert "text-sibling-shifted-for-intrinsic-height" not in issue_codes


def test_pipeline_semantic_adjustments_shift_cards_after_nested_text_growth() -> None:
    payload = {
        "id": "page",
        "name": "page-card-stack-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 320},
        "children": [
            {
                "id": "section",
                "name": "section-cards",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 220},
                "children": [
                    {
                        "id": "card-1",
                        "name": "card-service-1",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 24,
                            "y": 24,
                            "width": 170,
                            "height": 46,
                        },
                        "children": [
                            {
                                "id": "card-1-title",
                                "name": "titre-h3-card-1",
                                "type": "TEXT",
                                "characters": (
                                    "Titre de carte tres long qui doit pousser la carte suivante"
                                ),
                                "style": {"fontSize": 12, "lineHeightPx": 14},
                                "absoluteBoundingBox": {
                                    "x": 32,
                                    "y": 30,
                                    "width": 92,
                                    "height": 12,
                                },
                            }
                        ],
                    },
                    {
                        "id": "card-2",
                        "name": "card-service-2",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 24,
                            "y": 76,
                            "width": 170,
                            "height": 46,
                        },
                        "children": [
                            {
                                "id": "card-2-title",
                                "name": "titre-h3-card-2",
                                "type": "TEXT",
                                "characters": "Carte suivante",
                                "style": {"fontSize": 12, "lineHeightPx": 14},
                                "absoluteBoundingBox": {
                                    "x": 32,
                                    "y": 82,
                                    "width": 120,
                                    "height": 12,
                                },
                            }
                        ],
                    },
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    card_1 = plan.sections[0].nodes[0]
    card_2 = plan.sections[0].nodes[1]

    assert card_2.bounds.y == pytest.approx(76)
    assert card_1.bounds.height == pytest.approx(46)
    assert "text-sibling-shifted-for-intrinsic-height" not in [
        issue.code for issue in plan.diagnostics
    ]


def test_pipeline_semantic_adjustments_shift_button_after_text_growth() -> None:
    payload = {
        "id": "page",
        "name": "page-button-after-text-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 240},
        "children": [
            {
                "id": "section",
                "name": "section-button-after-text",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
                "children": [
                    {
                        "id": "copy",
                        "name": "texte-decouvrez-bureau",
                        "type": "TEXT",
                        "characters": (
                            "Un paragraphe assez long pour prendre plus de hauteur que sa "
                            "boite Figma initiale et pousser le bouton."
                        ),
                        "style": {"fontSize": 11, "lineHeightPx": 12},
                        "absoluteBoundingBox": {
                            "x": 58,
                            "y": 24,
                            "width": 170,
                            "height": 24,
                        },
                    },
                    {
                        "id": "button",
                        "name": "button-labo-embedded",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 100,
                            "y": 54,
                            "width": 90,
                            "height": 20,
                        },
                        "children": [
                            {
                                "id": "button-label",
                                "name": "texte-button-decouvrir",
                                "type": "TEXT",
                                "characters": "Decouvrir",
                                "style": {"fontSize": 10, "lineHeightPx": 12},
                                "absoluteBoundingBox": {
                                    "x": 110,
                                    "y": 58,
                                    "width": 70,
                                    "height": 12,
                                },
                            }
                        ],
                    },
                    {
                        "id": "next-title",
                        "name": "titre-h2-next",
                        "type": "TEXT",
                        "characters": "Titre suivant",
                        "style": {"fontSize": 12, "lineHeightPx": 14},
                        "absoluteBoundingBox": {
                            "x": 86,
                            "y": 58,
                            "width": 120,
                            "height": 14,
                        },
                    },
                ],
            }
        ],
    }

    plan = Pipeline().render_plan(payload)
    button = plan.sections[0].nodes[1]
    next_title = plan.sections[0].nodes[2]

    assert button.component == "submit"
    assert button.bounds.y == pytest.approx(54)
    assert next_title.bounds.y == pytest.approx(58)
    assert "text-sibling-shifted-for-intrinsic-height" not in [
        issue.code for issue in plan.diagnostics
    ]


def test_pipeline_semantic_adjustments_stretch_full_section_background_after_expansion() -> None:
    plan = Pipeline().render_plan(
        {
            "id": "page",
            "name": "page-bg-expansion-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 180},
            "children": [
                {
                    "id": "hero",
                    "name": "section-hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 100},
                    "children": [
                        _raw_box("hero-bg", "bg-hero", 0, 0, 402, 100),
                        {
                            "id": "copy",
                            "name": "texte-hero",
                            "type": "TEXT",
                            "characters": " ".join(["Contenu long"] * 18),
                            "style": {"fontSize": 12, "lineHeightPx": 16},
                            "absoluteBoundingBox": {
                                "x": 32,
                                "y": 70,
                                "width": 120,
                                "height": 18,
                            },
                        },
                    ],
                }
            ],
        }
    )

    section = plan.sections[0]
    background = next(node for node in section.nodes if node.name == "bg-hero")

    assert section.bounds.height == pytest.approx(100)
    assert background.bounds.bottom == pytest.approx(100)
    assert "section-expanded-for-semantic-content" not in [issue.code for issue in plan.diagnostics]


def test_pipeline_static_renderer_outputs_semantic_contact_form_controls() -> None:
    html = Pipeline().render_static_html(_raw_contact_form_payload())

    assert '<form class="pipeline-node pipeline-layer-content"' in html
    assert 'data-component="form"' in html
    assert '<input class="pipeline-node pipeline-layer-content pipeline-form-control"' in html
    assert 'type="email"' in html
    assert 'placeholder="Votre email"' in html
    assert '<div class="pipeline-node pipeline-layer-content pipeline-select-wrapper"' in html
    assert '<select class="pipeline-form-control pipeline-select-control"' in html
    assert '<span class="pipeline-select-arrow" aria-hidden="true"></span>' in html
    assert '<option value="" style="color:#111;background-color:#fff">' in html
    assert '<option value="expertise" style="color:#111;background-color:#fff">' in html
    assert '<option value="formation" style="color:#111;background-color:#fff">' in html
    assert '<textarea class="pipeline-node pipeline-layer-content pipeline-form-control"' in html
    assert '<button class="pipeline-node pipeline-layer-content pipeline-button"' in html
    assert ">Envoyer</button>" in html


def test_pipeline_runner_writes_artifacts_without_legacy_pipeline() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "raw.json"
        raw_file.write_text(
            """
{
  "id": "page",
  "name": "page-pipeline-402",
  "type": "FRAME",
  "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
  "children": [
    {
      "id": "hero",
      "name": "section-hero",
      "type": "FRAME",
      "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 200},
      "children": [
        {
          "id": "title",
          "name": "titre-h1-pipeline",
          "type": "TEXT",
          "characters": "Pipeline only",
          "absoluteBoundingBox": {"x": 20, "y": 40, "width": 200, "height": 40}
        }
      ]
    }
  ]
}
""".strip(),
            encoding="utf-8",
        )

        result = build_pipeline_from_raw_files([raw_file], temp_path / "out")

        assert result["pipeline"] == "pipeline"
        assert (temp_path / "out" / "page-pipeline-402.render-plan.json").exists()
        assert (temp_path / "out" / "page-pipeline-402.html").exists()
        assert (temp_path / "out" / "diagnostics.json").exists()
        assert (temp_path / "out" / "site" / "index.html").exists()
        assert (temp_path / "out" / "site" / "pages" / "page-pipeline-402" / "index.html").exists()
        assert (temp_path / "out" / "site" / "assets" / "page-pipeline-402.css").exists()
        assert (temp_path / "out" / "hugo" / "hugo.toml").exists()
        assert (temp_path / "out" / "hugo" / "content" / "page-pipeline-402" / "index.md").exists()
        assert (
            temp_path / "out" / "hugo" / "data" / "pipeline" / "pages" / "page-pipeline-402.json"
        ).exists()
        assert (
            temp_path / "out" / "hugo" / "layouts" / "partials" / "pipeline" / "page.html"
        ).exists()
        assert (
            temp_path / "out" / "hugo" / "assets" / "css" / "pipeline" / "page-pipeline-402.css"
        ).exists()
        assert result["responsiveManifest"] is None
        assert result["site"]["pages"][0]["slug"] == "page-pipeline-402"
        assert result["hugo"]["pages"][0]["slug"] == "page-pipeline-402"


def test_pipeline_runner_writes_responsive_site_from_manifest() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-responsive-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        desktop_raw = temp_path / "desktop.json"
        mobile_raw = temp_path / "mobile.json"
        desktop_raw.write_text(
            """
{
  "id": "page-desktop",
  "name": "page-pipeline-1920",
  "type": "FRAME",
  "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 600},
  "children": [
    {
      "id": "hero-desktop",
      "name": "section-hero",
      "type": "FRAME",
      "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 320}
    }
  ]
}
""".strip(),
            encoding="utf-8",
        )
        mobile_raw.write_text(
            """
{
  "id": "page-mobile",
  "name": "page-pipeline-402",
  "type": "FRAME",
  "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 700},
  "children": [
    {
      "id": "hero-mobile",
      "name": "section-hero",
      "type": "FRAME",
      "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 360}
    }
  ]
}
""".strip(),
            encoding="utf-8",
        )

        result = build_pipeline_from_raw_files([desktop_raw, mobile_raw], temp_path / "out")

        responsive_html = temp_path / "out" / "site" / "pages" / "page-pipeline" / "index.html"
        responsive_css = temp_path / "out" / "site" / "assets" / "page-pipeline.responsive.css"
        assert (temp_path / "out" / "responsive-manifest.json").exists()
        assert responsive_html.exists()
        assert responsive_css.exists()
        assert result["site"]["responsivePage"]["slug"] == "page-pipeline"
        assert str(responsive_html) in result["writtenFiles"]
        assert str(responsive_css) in result["writtenFiles"]
        assert result["hugo"]["pages"][0]["slug"] == "page-pipeline"
        assert result["hugo"]["pages"][0]["responsive"] is True
        assert "pipeline-responsive-variant-1920" in responsive_html.read_text(encoding="utf-8")
        assert "pipeline-responsive-variant-402" in responsive_html.read_text(encoding="utf-8")
        css = responsive_css.read_text(encoding="utf-8")
        assert "@media (max-width: 1161px)" in css
        assert ".pipeline-responsive-variant-402 { display: block; }" in css
        hugo_content = temp_path / "out" / "hugo" / "content" / "page-pipeline" / "index.md"
        hugo_data = (
            temp_path / "out" / "hugo" / "data" / "pipeline" / "responsive" / "page-pipeline.json"
        )
        hugo_css = (
            temp_path
            / "out"
            / "hugo"
            / "assets"
            / "css"
            / "pipeline"
            / "page-pipeline.responsive.css"
        )
        assert hugo_content.exists()
        assert hugo_data.exists()
        assert hugo_css.exists()
        assert 'pipelineResponsiveKey = "page-pipeline"' in hugo_content.read_text(encoding="utf-8")
        assert (
            len(_generator_support.json.loads(hugo_data.read_text(encoding="utf-8"))["variants"])
            == 2
        )
        assert ".pipeline-responsive-variant-402 .pipeline-page" in hugo_css.read_text(
            encoding="utf-8"
        )


def test_pipeline_hugo_output_builds_when_hugo_is_available() -> None:
    if not _generator_support.HUGO_BIN:
        raise _generator_support.unittest.SkipTest("Hugo binary is not available")

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-hugo-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        desktop_raw = temp_path / "desktop.json"
        mobile_raw = temp_path / "mobile.json"
        desktop_raw.write_text(
            _raw_page_json(name="page-pipeline-1920", width=1920, height=600, section_height=320),
            encoding="utf-8",
        )
        mobile_raw.write_text(
            _raw_page_json(name="page-pipeline-402", width=402, height=700, section_height=360),
            encoding="utf-8",
        )

        build_pipeline_from_raw_files([desktop_raw, mobile_raw], temp_path / "out")
        _generator_support.subprocess.run(
            [
                _generator_support.HUGO_BIN,
                "--source",
                str(temp_path / "out" / "hugo"),
                "--destination",
                str(temp_path / "out" / "hugo-public"),
                "--quiet",
            ],
            check=True,
            capture_output=True,
            text=True,
        )


def test_pipeline_hugo_output_keeps_pipeline_inline_css_values() -> None:
    if not _generator_support.HUGO_BIN:
        raise _generator_support.unittest.SkipTest("Hugo binary is not available")

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-hugo-css-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "page-style.json"
        raw_file.write_text(
            _generator_support.json.dumps(
                {
                    "id": "page",
                    "name": "page-style-402",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
                    "children": [
                        {
                            "id": "hero",
                            "name": "section-hero",
                            "type": "FRAME",
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "color": {
                                        "r": 0,
                                        "g": 0.10980392247438431,
                                        "b": 0.3490196168422699,
                                        "a": 1,
                                    },
                                }
                            ],
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 200,
                            },
                            "children": [
                                {
                                    "id": "title",
                                    "name": "titre-h1-style",
                                    "type": "TEXT",
                                    "characters": "Hero Title",
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 40,
                                        "width": 200,
                                        "height": 40,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        build_pipeline_from_raw_files([raw_file], temp_path / "out")
        _generator_support.subprocess.run(
            [
                _generator_support.HUGO_BIN,
                "--source",
                str(temp_path / "out" / "hugo"),
                "--destination",
                str(temp_path / "out" / "hugo-public"),
                "--quiet",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        html = (temp_path / "out" / "hugo-public" / "page-style-402" / "index.html").read_text(
            encoding="utf-8"
        )

        assert "ZgotmplZ" not in html
        assert "%!" not in html
        assert "background-color:rgb(0, 28, 89)" in html
        assert ">Hero Title</div>" in html


def test_pipeline_hugo_output_renders_semantic_contact_form_controls() -> None:
    if not _generator_support.HUGO_BIN:
        raise _generator_support.unittest.SkipTest("Hugo binary is not available")

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-hugo-form-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "page-contact.json"
        raw_file.write_text(
            _generator_support.json.dumps(_raw_contact_form_payload()),
            encoding="utf-8",
        )

        build_pipeline_from_raw_files([raw_file], temp_path / "out")
        _generator_support.subprocess.run(
            [
                _generator_support.HUGO_BIN,
                "--source",
                str(temp_path / "out" / "hugo"),
                "--destination",
                str(temp_path / "out" / "hugo-public"),
                "--quiet",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        html = (temp_path / "out" / "hugo-public" / "page-contact-402" / "index.html").read_text(
            encoding="utf-8"
        )

        assert "<form " in html
        assert 'data-component="form"' in html
        assert "<input " in html
        assert 'type="email"' in html
        assert 'placeholder="Votre email"' in html
        assert "<select " in html
        assert (
            '<option value="expertise" style="color:#111;background-color:#fff;">Expertise</option>'
            in html
        )
        assert (
            '<option value="formation" style="color:#111;background-color:#fff;">Formation</option>'
            in html
        )
        assert "<textarea " in html
        assert "<button " in html
        assert ">Envoyer</button>" in html
        assert "ZgotmplZ" not in html
        assert "%!" not in html


def test_pipeline_final_hugo_site_writes_single_responsive_route() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_files = []
        for width, height, section_height in (
            (1920, 600, 320),
            (834, 700, 360),
            (402, 800, 420),
        ):
            raw_file = temp_path / f"page-pipeline-{width}.json"
            raw_file.write_text(
                _raw_page_json(
                    name=f"page-pipeline-{width}",
                    width=width,
                    height=height,
                    section_height=section_height,
                ),
                encoding="utf-8",
            )
            raw_files.append(raw_file)

        result = build_pipeline_hugo_site_from_raw_files(raw_files, temp_path / "site-pipeline")

        assert result["command"] == "build-site"
        assert Path(result["hugo"]["root"]) == temp_path / "site-pipeline"
        assert (temp_path / "site-pipeline" / "hugo.toml").exists()
        assert (temp_path / "site-pipeline" / "content" / "page-pipeline" / "index.md").exists()
        assert not (
            temp_path / "site-pipeline" / "content" / "page-pipeline-1920" / "index.md"
        ).exists()
        assert (
            temp_path / "site-pipeline" / "data" / "pipeline" / "responsive" / "page-pipeline.json"
        ).exists()
        assert (
            temp_path / "site-pipeline" / ".figma2hugo-pipeline-debug" / "diagnostics.json"
        ).exists()
        assert (
            temp_path / "site-pipeline" / ".figma2hugo-pipeline-debug" / "responsive-manifest.json"
        ).exists()
        assert [page["slug"] for page in result["hugo"]["pages"]] == ["page-pipeline"]
        assert result["responsiveManifest"] == str(
            temp_path / "site-pipeline" / ".figma2hugo-pipeline-debug" / "responsive-manifest.json"
        )
        assert [manifest["family"] for manifest in result["responsiveManifests"]] == [
            "page-pipeline"
        ]
        report = _generator_support.json.loads(
            (temp_path / "site-pipeline" / "report.json").read_text(encoding="utf-8")
        )
        assert report["pipeline"] == "pipeline"
        assert report["pageCount"] == 1
        assert report["responsive"]["issueCount"] == 0


def test_pipeline_final_hugo_site_report_includes_performance_timings() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-performance-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "page-pipeline-402.json"
        raw_file.write_text(
            _raw_page_json(
                name="page-pipeline-402",
                width=402,
                height=700,
                section_height=320,
            ),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files([raw_file], temp_path / "site-pipeline")

        report = _generator_support.json.loads(
            (temp_path / "site-pipeline" / "report.json").read_text(encoding="utf-8")
        )
        performance = report["performance"]

        expected_keys = {
            "fetchSeconds",
            "cacheReadSeconds",
            "normalizeSeconds",
            "renderPlanSeconds",
            "responsiveSeconds",
            "hugoWriteSeconds",
            "reportSeconds",
            "totalSeconds",
        }
        assert set(performance) == expected_keys
        assert all(isinstance(performance[key], int | float) for key in expected_keys)
        assert all(performance[key] >= 0 for key in expected_keys)
        assert performance["totalSeconds"] >= max(
            performance[key] for key in expected_keys if key != "totalSeconds"
        )


def test_pipeline_final_hugo_site_reuses_raw_cache(monkeypatch) -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-raw-cache-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        cache_dir = temp_path / "cache"
        calls = {"count": 0}

        def fake_fetch(figma_url: str, *, token: str | None = None):
            assert figma_url == FIGMA_URL
            assert token == "token-pipeline"
            calls["count"] += 1
            return _generator_support.json.loads(
                _raw_page_json(name="page-pipeline-402", width=402, height=400, section_height=200)
            )

        monkeypatch.setattr(pipeline_runner, "fetch_raw_node_from_figma", fake_fetch)

        first = pipeline_runner.build_pipeline_hugo_site_from_figma_urls(
            [FIGMA_URL],
            temp_path / "site-first",
            token="token-pipeline",
            cache_dir=cache_dir,
        )
        second = pipeline_runner.build_pipeline_hugo_site_from_figma_urls(
            [FIGMA_URL],
            temp_path / "site-second",
            token="token-pipeline",
            cache_dir=cache_dir,
        )

        assert calls["count"] == 1
        first_report = _generator_support.json.loads(
            Path(first["report"]).read_text(encoding="utf-8")
        )
        second_report = _generator_support.json.loads(
            Path(second["report"]).read_text(encoding="utf-8")
        )
        assert first_report["cache"]["raw"]["misses"] == 1
        assert first_report["cache"]["raw"]["writes"] == 1
        assert second_report["cache"]["raw"]["hits"] == 1
        assert second_report["performance"]["cacheReadSeconds"] >= 0


def test_pipeline_final_hugo_site_localizes_asset_urls() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-asset-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        image = temp_path / "hero.png"
        image.write_bytes(b"fake-png")
        raw_file = temp_path / "asset.raw.json"
        raw_file.write_text(
            _generator_support.json.dumps(
                {
                    "id": "page",
                    "name": "page-asset-402",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
                    "children": [
                        {
                            "id": "hero",
                            "name": "section-hero",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 300,
                            },
                            "children": [
                                {
                                    "id": "hero-image",
                                    "name": "image-hero",
                                    "type": "RECTANGLE",
                                    "imageUrl": str(image),
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 40,
                                        "width": 120,
                                        "height": 90,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files([raw_file], temp_path / "site-pipeline")

        data = _generator_support.json.loads(
            (
                temp_path / "site-pipeline" / "data" / "pipeline" / "pages" / "page-asset-402.json"
            ).read_text(encoding="utf-8")
        )
        asset_url = data["sections"][0]["nodes"][0]["assetUrl"]
        localized_asset = temp_path / "site-pipeline" / "static" / asset_url.lstrip("/")

        assert asset_url.startswith("/pipeline-assets/")
        assert localized_asset.read_bytes() == b"fake-png"


def test_pipeline_final_hugo_site_localizes_inline_style_asset_urls() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-style-asset-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        button_image = temp_path / "button.png"
        button_image.write_bytes(b"button-png")
        raw_file = temp_path / "button.raw.json"
        raw_file.write_text(
            _generator_support.json.dumps(
                {
                    "id": "page",
                    "name": "page-button-style-402",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 240},
                    "children": [
                        {
                            "id": "content",
                            "name": "section-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 180,
                            },
                            "children": [
                                {
                                    "id": "submit",
                                    "name": "button-envoyer",
                                    "type": "FRAME",
                                    "absoluteBoundingBox": {
                                        "x": 120,
                                        "y": 60,
                                        "width": 120,
                                        "height": 32,
                                    },
                                    "children": [
                                        {
                                            "id": "submit-bg",
                                            "name": "bg-button-envoyer",
                                            "type": "RECTANGLE",
                                            "imageUrl": str(button_image),
                                            "absoluteBoundingBox": {
                                                "x": 120,
                                                "y": 60,
                                                "width": 120,
                                                "height": 32,
                                            },
                                        },
                                        {
                                            "id": "submit-label",
                                            "name": "texte-button-envoyer",
                                            "type": "TEXT",
                                            "characters": "Envoyer",
                                            "absoluteBoundingBox": {
                                                "x": 150,
                                                "y": 68,
                                                "width": 60,
                                                "height": 16,
                                            },
                                        },
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files([raw_file], temp_path / "site-pipeline")

        data = _generator_support.json.loads(
            (
                temp_path
                / "site-pipeline"
                / "data"
                / "pipeline"
                / "pages"
                / "page-button-style-402.json"
            ).read_text(encoding="utf-8")
        )
        background_image = data["sections"][0]["nodes"][0]["style"]["background-image"]
        asset_url = background_image.removeprefix('url("').removesuffix('")')
        localized_asset = temp_path / "site-pipeline" / "static" / asset_url.lstrip("/")

        assert asset_url.startswith("/pipeline-assets/")
        assert localized_asset.read_bytes() == b"button-png"


def test_pipeline_final_hugo_site_reuses_remote_asset_cache(monkeypatch) -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-remote-cache-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        source = "https://assets.example.test/hero.png?token=abc"
        cache_dir = temp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / _asset_filename(source)).write_bytes(b"cached-png")
        monkeypatch.setenv("FIGMA2HUGO_PIPELINE_ASSET_CACHE", str(cache_dir))

        def fail_urlopen(*_args, **_kwargs):
            raise AssertionError("remote asset cache should avoid network downloads")

        monkeypatch.setattr(
            "figma2hugo.pipeline.hugo_renderer.urllib.request.urlopen", fail_urlopen
        )

        raw_file = temp_path / "asset.raw.json"
        raw_file.write_text(
            _generator_support.json.dumps(
                {
                    "id": "page",
                    "name": "page-asset-cache-402",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
                    "children": [
                        {
                            "id": "hero",
                            "name": "section-hero",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 300,
                            },
                            "children": [
                                {
                                    "id": "hero-image",
                                    "name": "image-hero",
                                    "type": "RECTANGLE",
                                    "imageUrl": source,
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 40,
                                        "width": 120,
                                        "height": 90,
                                    },
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files([raw_file], temp_path / "site-pipeline")

        data = _generator_support.json.loads(
            (
                temp_path
                / "site-pipeline"
                / "data"
                / "pipeline"
                / "pages"
                / "page-asset-cache-402.json"
            ).read_text(encoding="utf-8")
        )
        asset_url = data["sections"][0]["nodes"][0]["assetUrl"]
        localized_asset = temp_path / "site-pipeline" / "static" / asset_url.lstrip("/")

        assert asset_url.startswith("/pipeline-assets/")
        assert localized_asset.read_bytes() == b"cached-png"


def test_pipeline_final_hugo_site_removes_stale_pipeline_outputs() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-clean-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        old_raw = temp_path / "old.raw.json"
        old_raw.write_text(
            _raw_page_json(name="page-old-402", width=402, height=400, section_height=200),
            encoding="utf-8",
        )
        new_raw = temp_path / "new.raw.json"
        new_raw.write_text(
            _raw_page_json(name="page-new-402", width=402, height=400, section_height=200),
            encoding="utf-8",
        )
        site_dir = temp_path / "site-pipeline"
        delete_probe = site_dir / "content" / "delete-probe" / "index.md"
        delete_probe.parent.mkdir(parents=True)
        delete_probe.write_text("probe", encoding="utf-8")
        try:
            delete_probe.unlink()
            delete_probe.parent.rmdir()
        except PermissionError:
            pytest.skip("Current filesystem sandbox does not allow deletion probes.")

        build_pipeline_hugo_site_from_raw_files([old_raw], site_dir)
        assert (site_dir / "content" / "page-old-402" / "index.md").exists()
        assert (site_dir / "data" / "pipeline" / "pages" / "page-old-402.json").exists()
        (site_dir / "content" / "manual" / "index.md").parent.mkdir(parents=True)
        (site_dir / "content" / "manual" / "index.md").write_text(
            '+++\ntitle = "Manual"\n+++\n',
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files([new_raw], site_dir)

        assert not (site_dir / "content" / "page-old-402").exists()
        assert not (site_dir / "data" / "pipeline" / "pages" / "page-old-402.json").exists()
        assert (site_dir / "content" / "page-new-402" / "index.md").exists()
        assert (site_dir / "content" / "manual" / "index.md").exists()


def test_pipeline_final_hugo_site_writes_managed_files_manifest() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-manifest-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "page.raw.json"
        raw_file.write_text(
            _raw_page_json(name="page-pipeline-402", width=402, height=400, section_height=200),
            encoding="utf-8",
        )
        site_dir = temp_path / "site-pipeline"

        build_pipeline_hugo_site_from_raw_files([raw_file], site_dir)

        manifest_path = site_dir / ".figma2hugo-pipeline" / "managed-files.json"
        manifest = _generator_support.json.loads(manifest_path.read_text(encoding="utf-8"))

        assert manifest["pipeline"] == "pipeline"
        assert manifest["managedMarker"] == "figma2hugo:pipeline-managed"
        assert ".figma2hugo-pipeline/managed-files.json" in manifest["files"]
        assert "layouts/_default/baseof.html" in manifest["files"]
        assert "content/page-pipeline-402/index.md" in manifest["files"]
        assert "data/pipeline/pages/page-pipeline-402.json" in manifest["files"]
        assert "assets/css/pipeline/page-pipeline-402.css" in manifest["files"]
        assert manifest["pages"] == [
            {
                "slug": "page-pipeline-402",
                "content": "content/page-pipeline-402/index.md",
                "data": "data/pipeline/pages/page-pipeline-402.json",
                "css": "assets/css/pipeline/page-pipeline-402.css",
                "responsive": False,
            }
        ]


def test_pipeline_final_hugo_site_writes_pipeline_runtime_for_accordions_and_layout() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-runtime-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "accordion.raw.json"
        raw_file.write_text(
            _generator_support.json.dumps(_raw_multi_accordion_payload()),
            encoding="utf-8",
        )
        site_dir = temp_path / "site-pipeline"

        build_pipeline_hugo_site_from_raw_files([raw_file], site_dir)

        baseof = (site_dir / "layouts" / "_default" / "baseof.html").read_text(encoding="utf-8")
        runtime = (site_dir / "assets" / "js" / "pipeline" / "runtime.js").read_text(
            encoding="utf-8"
        )
        manifest = _generator_support.json.loads(
            (site_dir / ".figma2hugo-pipeline" / "managed-files.json").read_text(encoding="utf-8")
        )

        assert 'resources.Get "js/pipeline/runtime.js"' in baseof
        assert "closeSiblingAccordions" in runtime
        assert "normalizeInitialAccordionState" in runtime
        assert "initializeCarouselRoot" in runtime
        assert "[data-carousel='true']" in runtime
        assert "layoutPage" in runtime
        assert "contributesToLayout" in runtime
        assert "usesAccordionLayoutHeight" in runtime
        assert "pipeline-layer-decorative" in runtime
        assert "canShrinkForAccordion" not in runtime
        assert "sectionAllowsDynamicShrink" in runtime
        assert "originalBottomPadding" in runtime
        assert "\x08" not in runtime
        assert "name.split(/[^a-z0-9]+/)" in runtime
        assert "naturalHeight" in runtime
        assert "scrollHeight" not in runtime
        assert "var nextHeight = Math.max(1, cursor);" in runtime
        assert "contentBottom + bottomPadding" in runtime
        assert ": Math.max(originalHeight(section), contentBottom);" in runtime
        assert "var pageBottom = 0;" in runtime
        assert "assets/js/pipeline/runtime.js" in manifest["files"]
        assert "assets/js/pipeline" in manifest["managedZones"]


def test_pipeline_final_hugo_site_refuses_non_pipeline_scaffold_overwrite() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-protect-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "page.raw.json"
        raw_file.write_text(
            _raw_page_json(name="page-pipeline-402", width=402, height=400, section_height=200),
            encoding="utf-8",
        )
        site_dir = temp_path / "site-pipeline"
        user_baseof = site_dir / "layouts" / "_default" / "baseof.html"
        user_baseof.parent.mkdir(parents=True)
        user_baseof.write_text("<!doctype html><title>User Hugo</title>\n", encoding="utf-8")

        with pytest.raises(ValueError, match="non-pipeline Hugo scaffold"):
            build_pipeline_hugo_site_from_raw_files([raw_file], site_dir)

        assert (
            user_baseof.read_text(encoding="utf-8") == "<!doctype html><title>User Hugo</title>\n"
        )
        assert not (site_dir / "hugo.toml").exists()


def test_pipeline_final_hugo_site_expands_parent_frames_into_page_variants() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-parent-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "parent.raw.json"
        raw_file.write_text(
            _generator_support.json.dumps(
                {
                    "id": "parent",
                    "name": "page-pipeline",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 2000, "height": 1000},
                    "children": [
                        _raw_page_payload(
                            name="page-pipeline-1920",
                            width=1920,
                            height=600,
                            section_height=320,
                        ),
                        _raw_page_payload(
                            name="page-pipeline-402",
                            width=402,
                            height=800,
                            section_height=420,
                        ),
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = build_pipeline_hugo_site_from_raw_files([raw_file], temp_path / "site-pipeline")

        assert [page["slug"] for page in result["hugo"]["pages"]] == ["page-pipeline"]
        assert (temp_path / "site-pipeline" / "content" / "page-pipeline" / "index.md").exists()
        assert (
            temp_path / "site-pipeline" / "data" / "pipeline" / "responsive" / "page-pipeline.json"
        ).exists()
        assert not (
            temp_path / "site-pipeline" / "content" / "page-pipeline-1920" / "index.md"
        ).exists()


def test_pipeline_final_hugo_site_dedupes_parent_and_child_page_variants() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-parent-dedupe-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        desktop_payload = _raw_page_payload(
            name="page-pipeline-1920",
            width=1920,
            height=600,
            section_height=320,
        )
        mobile_payload = _raw_page_payload(
            name="page-pipeline-402",
            width=402,
            height=800,
            section_height=420,
        )
        parent_raw_file = temp_path / "parent.raw.json"
        parent_raw_file.write_text(
            _generator_support.json.dumps(
                {
                    "id": "parent",
                    "name": "page-pipeline",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 2000, "height": 1000},
                    "children": [desktop_payload, mobile_payload],
                }
            ),
            encoding="utf-8",
        )
        duplicate_child_raw_file = temp_path / "mobile.raw.json"
        duplicate_child_raw_file.write_text(
            _generator_support.json.dumps(copy.deepcopy(mobile_payload)),
            encoding="utf-8",
        )

        result = build_pipeline_hugo_site_from_raw_files(
            [parent_raw_file, duplicate_child_raw_file],
            temp_path / "site-pipeline",
        )

        assert [page["slug"] for page in result["hugo"]["pages"]] == ["page-pipeline"]
        assert [manifest["family"] for manifest in result["responsiveManifests"]] == [
            "page-pipeline"
        ]
        responsive_manifest = (
            temp_path / "site-pipeline" / "data" / "pipeline" / "responsive" / "page-pipeline.json"
        )
        assert responsive_manifest.exists()
        responsive_payload = _generator_support.json.loads(
            responsive_manifest.read_text(encoding="utf-8")
        )
        assert responsive_payload["manifest"]["breakpoints"] == [402]


def test_pipeline_final_hugo_site_groups_multiple_responsive_families() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-groups-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_files = []
        for family, specs in {
            "page-alpha": ((1920, 600, 320), (402, 800, 420)),
            "page-beta": ((1920, 500, 260), (402, 700, 360)),
        }.items():
            for width, height, section_height in specs:
                raw_file = temp_path / f"{family}-{width}.json"
                raw_file.write_text(
                    _raw_page_json(
                        name=f"{family}-{width}",
                        width=width,
                        height=height,
                        section_height=section_height,
                    ),
                    encoding="utf-8",
                )
                raw_files.append(raw_file)

        result = build_pipeline_hugo_site_from_raw_files(raw_files, temp_path / "site-pipeline")

        assert [page["slug"] for page in result["hugo"]["pages"]] == [
            "page-alpha",
            "page-beta",
        ]
        assert (temp_path / "site-pipeline" / "content" / "page-alpha" / "index.md").exists()
        assert (temp_path / "site-pipeline" / "content" / "page-beta" / "index.md").exists()
        assert not (
            temp_path / "site-pipeline" / "content" / "page-alpha-1920" / "index.md"
        ).exists()
        assert not (temp_path / "site-pipeline" / "content" / "page-beta-402" / "index.md").exists()
        assert (
            temp_path / "site-pipeline" / "data" / "pipeline" / "responsive" / "page-alpha.json"
        ).exists()
        assert (
            temp_path / "site-pipeline" / "data" / "pipeline" / "responsive" / "page-beta.json"
        ).exists()
        assert (
            temp_path
            / "site-pipeline"
            / ".figma2hugo-pipeline-debug"
            / "page-alpha.responsive-manifest.json"
        ).exists()
        assert (
            temp_path
            / "site-pipeline"
            / ".figma2hugo-pipeline-debug"
            / "page-beta.responsive-manifest.json"
        ).exists()
        assert result["responsiveManifest"] is None
        assert [manifest["family"] for manifest in result["responsiveManifests"]] == [
            "page-alpha",
            "page-beta",
        ]
        report = _generator_support.json.loads(
            (temp_path / "site-pipeline" / "report.json").read_text(encoding="utf-8")
        )
        assert report["pageCount"] == 2
        assert report["responsive"]["familyCount"] == 2
        assert report["responsive"]["issueCount"] == 0


def test_pipeline_final_hugo_site_keeps_singleton_pages_with_responsive_families() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-mixed-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_files = []
        for name, width, height, section_height in (
            ("page-alpha-1920", 1920, 600, 320),
            ("page-alpha-402", 402, 800, 420),
            ("page-gamma-402", 402, 700, 360),
        ):
            raw_file = temp_path / f"{name}.json"
            raw_file.write_text(
                _raw_page_json(
                    name=name,
                    width=width,
                    height=height,
                    section_height=section_height,
                ),
                encoding="utf-8",
            )
            raw_files.append(raw_file)

        result = build_pipeline_hugo_site_from_raw_files(raw_files, temp_path / "site-pipeline")

        assert [page["slug"] for page in result["hugo"]["pages"]] == [
            "page-alpha",
            "page-gamma-402",
        ]
        assert (temp_path / "site-pipeline" / "content" / "page-alpha" / "index.md").exists()
        assert (temp_path / "site-pipeline" / "content" / "page-gamma-402" / "index.md").exists()
        assert (
            temp_path / "site-pipeline" / "data" / "pipeline" / "pages" / "page-gamma-402.json"
        ).exists()
        assert (
            temp_path / "site-pipeline" / "data" / "pipeline" / "responsive" / "page-alpha.json"
        ).exists()
        assert [manifest["family"] for manifest in result["responsiveManifests"]] == ["page-alpha"]


def test_pipeline_final_hugo_site_report_lists_responsive_issue_details() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-report-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        desktop_raw = temp_path / "desktop.json"
        mobile_raw = temp_path / "mobile.json"
        desktop_raw.write_text(
            _raw_page_json_with_text(
                name="page-pipeline-1920",
                width=1920,
                height=600,
                section_name="section-content",
                section_height=320,
                text="Desktop content",
            ),
            encoding="utf-8",
        )
        mobile_raw.write_text(
            _raw_page_json_with_text(
                name="page-pipeline-402",
                width=402,
                height=700,
                section_name="section-content",
                section_height=360,
                text="Mobile content",
            ),
            encoding="utf-8",
        )

        result = build_pipeline_hugo_site_from_raw_files(
            [desktop_raw, mobile_raw], temp_path / "site-pipeline"
        )

        assert result["responsiveManifests"][0]["issues"][0]["code"] == "content-conflict"
        assert result["responsiveManifests"][0]["issueCount"] == 0
        assert result["responsiveManifests"][0]["reviewCount"] == 1
        report = _generator_support.json.loads(
            (temp_path / "site-pipeline" / "report.json").read_text(encoding="utf-8")
        )
        assert report["responsive"]["issueCount"] == 0
        assert report["responsive"]["byCode"] == {}
        assert report["responsive"]["reviewCount"] == 1
        assert report["responsive"]["reviewByCode"] == {"content-conflict": 1}
        assert report["responsive"]["families"][0]["issues"][0]["key"] == "section:section-content"
        assert report["responsive"]["families"][0]["issues"][0]["severity"] == "info"
        assert report["responsive"]["families"][0]["issues"][0]["presentWidths"] == [402, 1920]
        assert report["responsive"]["families"][0]["issues"][0]["signatureCount"] == 2
        assert report["responsive"]["families"][0]["issues"][0]["differenceKind"] == "content-delta"
        assert report["responsive"]["families"][0]["issues"][0]["nodeRole"] == "section"
        assert report["responsive"]["families"][0]["issues"][0]["contractRule"] == (
            "stable-responsive-content"
        )
        assert report["responsive"]["families"][0]["issues"][0]["contractAction"] == (
            "align-copy-or-declare-intentional-variant"
        )
        assert report["review"]["byClassification"]["accepted-info"] >= 0
        assert report["review"]["byClassification"]["actionable-review"] == 1
        assert report["review"]["byClassification"]["blocking"] == 0
        assert report["review"]["byPriority"]["P0"] == 0
        assert report["review"]["byPriority"]["P1"] == 0
        assert report["review"]["byPriority"]["P2"] == 0
        assert report["review"]["byPriority"]["P3"] >= 0
        assert report["review"]["byContractRule"] == {"stable-responsive-content": 1}
        assert report["review"]["byNodeRole"] == {"section": 1}
        responsive_group = next(
            group
            for group in report["review"]["groups"]
            if group["source"] == "responsive" and group["code"] == "content-conflict"
        )
        responsive_item = next(
            item
            for item in report["review"]["items"]
            if item["source"] == "responsive" and item["code"] == "content-conflict"
        )
        assert responsive_group["action"] == "inspect-responsive-contract"
        assert responsive_group["owner"] == "figma-contract"
        assert responsive_item["differenceKind"] == "content-delta"
        assert responsive_item["contractRisk"] == "responsive-content-drift"


def test_pipeline_final_hugo_site_accepts_declared_responsive_contract() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-contract-review-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        desktop_raw = temp_path / "desktop.json"
        mobile_raw = temp_path / "mobile.json"
        contract_file = temp_path / "responsive-contract.json"
        desktop_raw.write_text(
            _raw_page_json_with_text(
                name="page-pipeline-1920",
                width=1920,
                height=600,
                section_name="section-content",
                section_height=320,
                text="Desktop content",
            ),
            encoding="utf-8",
        )
        mobile_raw.write_text(
            _raw_page_json_with_text(
                name="page-pipeline-402",
                width=402,
                height=700,
                section_name="section-content",
                section_height=360,
                text="Mobile content",
            ),
            encoding="utf-8",
        )
        contract_file.write_text(
            _generator_support.json.dumps(
                {
                    "version": 1,
                    "responsiveContracts": [
                        {
                            "family": "page-pipeline",
                            "code": "content-conflict",
                            "key": "section:section-content",
                            "differenceKind": "content-delta",
                            "contractRule": "stable-responsive-content",
                            "presentWidths": [402, 1920],
                            "decision": "intentional-content-variant",
                            "rationale": "Desktop and mobile copy intentionally differ in Figma.",
                            "owner": "figma-contract",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files(
            [desktop_raw, mobile_raw],
            temp_path / "site-pipeline",
            responsive_contract=contract_file,
        )
        report = _generator_support.json.loads(
            (temp_path / "site-pipeline" / "report.json").read_text(encoding="utf-8")
        )

    item = next(
        item for item in report["review"]["items"] if item["classification"] == "accepted-contract"
    )
    assert report["review"]["byClassification"]["accepted-contract"] == 1
    assert report["review"]["byClassification"]["actionable-review"] == 0
    assert report["review"]["byContractDecision"] == {"intentional-content-variant": 1}
    assert report["review"]["acceptedContracts"][0]["action"] == "accept-responsive-contract"
    assert item["classification"] == "accepted-contract"
    assert item["contractDecision"] == "intentional-content-variant"
    assert item["contractRationale"] == "Desktop and mobile copy intentionally differ in Figma."
    assert report["review"]["responsiveContract"]["matchedCount"] == 1
    assert report["review"]["responsiveContract"]["unusedCount"] == 0
    assert report["review"]["responsiveContract"]["invalidCount"] == 0


def test_pipeline_accepts_project_responsive_contract_baseline() -> None:
    from figma2hugo.pipeline.review_baselines import promote_project_review_baseline

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-project-review-baseline-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        desktop_raw = temp_path / "desktop.json"
        mobile_raw = temp_path / "mobile.json"
        baseline_root = temp_path / "review-baselines"
        desktop_raw.write_text(
            _raw_page_json_with_text(
                name="page-pipeline-1920",
                width=1920,
                height=600,
                section_name="section-content",
                section_height=320,
                text="Desktop content",
            ),
            encoding="utf-8",
        )
        mobile_raw.write_text(
            _raw_page_json_with_text(
                name="page-pipeline-402",
                width=402,
                height=700,
                section_name="section-content",
                section_height=360,
                text="Mobile content",
            ),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files(
            [desktop_raw, mobile_raw], temp_path / "site-pipeline"
        )
        promoted = promote_project_review_baseline(
            temp_path / "site-pipeline",
            baseline_root,
            baseline_id="accepted-responsive",
        )
        build_pipeline_hugo_site_from_raw_files(
            [desktop_raw, mobile_raw],
            temp_path / "site-pipeline-contracted",
            responsive_contract_root=baseline_root,
        )
        report = _generator_support.json.loads(
            (temp_path / "site-pipeline-contracted" / "report.json").read_text(encoding="utf-8")
        )

    assert promoted["responsiveContractCount"] == 1
    assert report["review"]["byClassification"]["accepted-contract"] == 1
    assert report["review"]["byClassification"]["actionable-review"] == 0
    assert report["review"]["responsiveContract"]["matchedCount"] == 1
    assert report["review"]["responsiveContract"]["unusedCount"] == 0
    assert report["review"]["projectReviewBaseline"]["baselineId"] == "accepted-responsive"


def test_pipeline_final_hugo_site_report_splits_order_only_responsive_review() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-order-review-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        desktop_raw = temp_path / "desktop.json"
        mobile_raw = temp_path / "mobile.json"
        desktop_raw.write_text(
            _generator_support.json.dumps(
                {
                    "id": "page-1920",
                    "name": "page-pipeline-1920",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 600},
                    "children": [
                        {
                            "id": "content-1920",
                            "name": "section-faq",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 1920,
                                "height": 320,
                            },
                            "children": [
                                {
                                    "id": "text-a-1920",
                                    "name": "text-a",
                                    "type": "TEXT",
                                    "characters": "Alpha",
                                    "absoluteBoundingBox": {
                                        "x": 100,
                                        "y": 40,
                                        "width": 400,
                                        "height": 40,
                                    },
                                },
                                {
                                    "id": "text-b-1920",
                                    "name": "text-b",
                                    "type": "TEXT",
                                    "characters": "Beta",
                                    "absoluteBoundingBox": {
                                        "x": 100,
                                        "y": 100,
                                        "width": 400,
                                        "height": 40,
                                    },
                                },
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        mobile_raw.write_text(
            _generator_support.json.dumps(
                {
                    "id": "page-402",
                    "name": "page-pipeline-402",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 700},
                    "children": [
                        {
                            "id": "content-402",
                            "name": "section-faq",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 360,
                            },
                            "children": [
                                {
                                    "id": "text-b-402",
                                    "name": "text-b",
                                    "type": "TEXT",
                                    "characters": "Beta",
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 40,
                                        "width": 360,
                                        "height": 40,
                                    },
                                },
                                {
                                    "id": "text-a-402",
                                    "name": "text-a",
                                    "type": "TEXT",
                                    "characters": "Alpha",
                                    "absoluteBoundingBox": {
                                        "x": 20,
                                        "y": 100,
                                        "width": 360,
                                        "height": 40,
                                    },
                                },
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files(
            [desktop_raw, mobile_raw], temp_path / "site-pipeline"
        )
        report = _generator_support.json.loads(
            (temp_path / "site-pipeline" / "report.json").read_text(encoding="utf-8")
        )

    assert report["responsive"]["reviewCount"] == 1
    assert report["responsive"]["families"][0]["issues"][0]["differenceKind"] == (
        "same-content-different-order"
    )
    responsive_group = next(
        group
        for group in report["review"]["groups"]
        if group["source"] == "responsive" and group["code"] == "content-conflict"
    )
    responsive_item = next(
        item
        for item in report["review"]["items"]
        if item["source"] == "responsive" and item["code"] == "content-conflict"
    )
    assert responsive_group["action"] == "inspect-responsive-order-or-carousel"
    assert responsive_item["differenceKind"] == "same-content-different-order"


def test_pipeline_final_hugo_site_report_separates_diagnostic_review_signals() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-diagnostic-review-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "gap.json"
        raw_file.write_text(
            _generator_support.json.dumps(
                {
                    "id": "page",
                    "name": "page-gap-402",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 900},
                    "children": [
                        {
                            "id": "hero",
                            "name": "section-hero",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 100,
                            },
                        },
                        {
                            "id": "content",
                            "name": "section-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 500,
                                "width": 402,
                                "height": 100,
                            },
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files([raw_file], temp_path / "site-pipeline")
        report = _generator_support.json.loads(
            (temp_path / "site-pipeline" / "report.json").read_text(encoding="utf-8")
        )

    assert report["diagnostics"]["issueCount"] == 0
    assert report["diagnostics"]["byCode"] == {}
    assert report["diagnostics"]["reviewCount"] == 1
    assert report["diagnostics"]["reviewByCode"] == {"large-vertical-gap": 1}
    assert report["review"]["byClassification"] == {
        "accepted-info": 0,
        "actionable-review": 1,
        "blocking": 0,
    }
    assert report["review"]["byPriority"] == {"P0": 0, "P1": 0, "P2": 1, "P3": 0}
    assert report["review"]["groups"][0]["action"] == "inspect-empty-space-or-figma-intent"
    assert report["review"]["groups"][0]["owner"] == "figma-or-code"


def test_pipeline_final_hugo_site_report_marks_minor_gap_review_as_p3() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-minor-gap-review-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "minor-gap.json"
        raw_file.write_text(
            _generator_support.json.dumps(
                {
                    "id": "page",
                    "name": "page-minor-gap-402",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 500},
                    "children": [
                        {
                            "id": "hero",
                            "name": "section-hero",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 100,
                            },
                        },
                        {
                            "id": "content",
                            "name": "section-content",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 210,
                                "width": 402,
                                "height": 100,
                            },
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files([raw_file], temp_path / "site-pipeline")
        report = _generator_support.json.loads(
            (temp_path / "site-pipeline" / "report.json").read_text(encoding="utf-8")
        )

    review_item = report["review"]["items"][0]
    assert review_item["code"] == "large-vertical-gap"
    assert review_item["classification"] == "accepted-info"
    assert review_item["priority"] == "P3"
    assert review_item["action"] == "accept-near-threshold-visual-rhythm"
    assert review_item["owner"] == "visual-review"
    assert review_item["gapKind"] == "near-threshold"
    assert report["review"]["byClassification"] == {
        "accepted-info": 1,
        "actionable-review": 0,
        "blocking": 0,
    }
    assert report["review"]["byPriority"] == {"P0": 0, "P1": 0, "P2": 0, "P3": 1}


def test_pipeline_final_hugo_site_report_classifies_semantic_adjustments_as_accepted() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-final-site-accepted-review-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_file = temp_path / "contact.json"
        raw_file.write_text(
            _generator_support.json.dumps(_raw_tiny_contact_form_payload()),
            encoding="utf-8",
        )

        build_pipeline_hugo_site_from_raw_files([raw_file], temp_path / "site-pipeline")
        report = _generator_support.json.loads(
            (temp_path / "site-pipeline" / "report.json").read_text(encoding="utf-8")
        )

    assert report["diagnostics"]["issueCount"] == 0
    assert report["review"]["byClassification"]["accepted-info"] == 0
    assert report["review"]["byClassification"]["actionable-review"] == 0
    assert report["review"]["byPriority"]["P3"] == 0
    assert report["review"]["acceptedAdjustments"] == []


def test_pipeline_responsive_css_orders_media_queries_from_wide_to_narrow() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-css-order-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_files = []
        for width, height, section_height in (
            (1920, 600, 320),
            (834, 700, 360),
            (402, 800, 420),
        ):
            raw_file = temp_path / f"page-pipeline-{width}.json"
            raw_file.write_text(
                _raw_page_json(
                    name=f"page-pipeline-{width}",
                    width=width,
                    height=height,
                    section_height=section_height,
                ),
                encoding="utf-8",
            )
            raw_files.append(raw_file)

        build_pipeline_from_raw_files(raw_files, temp_path / "out")
        static_css = (
            temp_path / "out" / "site" / "assets" / "page-pipeline.responsive.css"
        ).read_text(encoding="utf-8")
        hugo_css = (
            temp_path
            / "out"
            / "hugo"
            / "assets"
            / "css"
            / "pipeline"
            / "page-pipeline.responsive.css"
        ).read_text(encoding="utf-8")

        assert static_css.index("@media (max-width: 1377px)") < static_css.index(
            "@media (max-width: 618px)"
        )
        assert hugo_css.index("@media (max-width: 1377px)") < hugo_css.index(
            "@media (max-width: 618px)"
        )


def test_pipeline_responsive_css_scales_active_variant_to_viewport_width() -> None:
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-css-scale-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        raw_files = []
        for width, height, section_height in (
            (1920, 600, 320),
            (834, 700, 360),
            (402, 800, 420),
        ):
            raw_file = temp_path / f"page-pipeline-{width}.json"
            raw_file.write_text(
                _raw_page_json(
                    name=f"page-pipeline-{width}",
                    width=width,
                    height=height,
                    section_height=section_height,
                ),
                encoding="utf-8",
            )
            raw_files.append(raw_file)

        build_pipeline_from_raw_files(raw_files, temp_path / "out")
        css_files = [
            temp_path / "out" / "site" / "assets" / "page-pipeline.responsive.css",
            temp_path
            / "out"
            / "hugo"
            / "assets"
            / "css"
            / "pipeline"
            / "page-pipeline.responsive.css",
        ]

        for css_file in css_files:
            css = css_file.read_text(encoding="utf-8")
            assert ".pipeline-responsive-variant { display: none; overflow: hidden;" in css
            assert (
                ".pipeline-responsive-variant .pipeline-page { margin: 0; overflow: visible;" in css
            )
            assert (
                ".pipeline-img { display: block; width: 100%; height: 100%; min-height: inherit;"
                in css
            )
            assert "width: calc(100% + 12px);" in css
            assert "transform: translateX(-6px);" in css
            assert "html, body { overflow-x: hidden; }" in css
            assert ".pipeline-responsive-variant-1920 .pipeline-page { width: 1920px;" in css
            assert (
                ".pipeline-responsive-variant-1920 .pipeline-page { transform: scale(calc(100vw / 1920px)); }"
            ) in css
            assert (
                ".pipeline-responsive-variant-1920 { width: 100vw; "
                "height: 31.250000vw; max-width: none; }"
            ) in css
            assert "@media (max-width: 618px)" in css
            assert (
                ".pipeline-responsive-variant-402 .pipeline-page { transform: scale(calc(100vw / 402px)); }"
            ) in css
            assert (
                ".pipeline-responsive-variant-402 { width: 100vw; "
                "height: 199.004975vw; max-width: none; }"
            ) in css
            assert "@media (max-width: 1377px)" in css
            assert (
                ".pipeline-responsive-variant-834 .pipeline-page { transform: scale(calc(100vw / 834px)); }"
            ) in css


def test_pipeline_visual_smoke_width_parser_keeps_order_and_deduplicates() -> None:
    assert parse_widths("1920, 834;402,834", default=(1440,)) == (1920, 834, 402)
    assert parse_widths("", default=(1920, 402)) == (1920, 402)

    with pytest.raises(ValueError, match="positive"):
        parse_widths("1920,0", default=(1920,))


def test_pipeline_visual_smoke_detects_image_mime_type_for_bin_assets(tmp_path: Path) -> None:
    from figma2hugo.pipeline.visual_smoke import _image_mime_type

    asset = tmp_path / "asset.bin"
    asset.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    assert _image_mime_type(asset) == "image/png"


def test_pipeline_visual_smoke_reports_screenshot_manifest(monkeypatch) -> None:
    class FakePage:
        def goto(self, *_args, **_kwargs) -> None:
            pass

        def wait_for_timeout(self, _timeout: int) -> None:
            pass

        def evaluate(self, _script: str, payload: dict[str, object]) -> dict[str, object]:
            if "slug" not in payload:
                return {}
            return {
                "issues": [],
                "metrics": {
                    "slug": payload["slug"],
                    "clientWidth": 402,
                    "scrollWidth": 402,
                },
            }

        def screenshot(self, *, path: str, full_page: bool) -> None:
            assert full_page is True
            Image.new("RGB", (4, 8), color=(255, 255, 255)).save(path)

        def close(self) -> None:
            pass

    class FakeBrowser:
        def new_page(self, **_kwargs) -> FakePage:
            return FakePage()

        def close(self) -> None:
            pass

    class FakePlaywright:
        chromium = SimpleNamespace(launch=lambda: FakeBrowser())

        def __enter__(self) -> FakePlaywright:
            return self

        def __exit__(self, *_args) -> None:
            pass

    sync_module = SimpleNamespace(sync_playwright=lambda: FakePlaywright())
    monkeypatch.setitem(sys.modules, "playwright", SimpleNamespace(sync_api=sync_module))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_module)

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-smoke-report-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        source = temp_path / "site"
        public = temp_path / "public"
        out = temp_path / "smoke"
        source.mkdir()
        public.mkdir()
        (source / "report.json").write_text(
            _generator_support.json.dumps(
                {
                    "pipeline": "pipeline",
                    "pages": [{"slug": "page-pipeline"}],
                }
            ),
            encoding="utf-8",
        )

        report = run_pipeline_visual_smoke(
            source,
            out,
            public_dir=public,
            widths=(402,),
            screenshot_widths=(402,),
        )

        report_payload = _generator_support.json.loads(
            (out / "report.json").read_text(encoding="utf-8")
        )
        assert report["issueCount"] == 0
        assert report_payload["issueCount"] == 0
        assert report_payload["errorCount"] == 0
        assert report_payload["warnCount"] == 0
        assert report_payload["screenshots"] == {
            "count": 1,
            "byPage": {"page-pipeline": 1},
            "items": [
                {
                    "slug": "page-pipeline",
                    "viewport": 402,
                    "path": "page-pipeline-402.png",
                    "fullPage": True,
                    "viewportSize": {"width": 402, "height": 874},
                    "visualReview": {
                        "slug": "page-pipeline",
                        "viewport": 402,
                        "screenshot": "page-pipeline-402.png",
                        "referenceKind": "capture",
                        "status": "capture-only",
                        "baseline": None,
                        "diff": None,
                        "pixelDiffRatio": None,
                        "sizeMismatch": False,
                    },
                }
            ],
        }
        assert report_payload["summaries"][0]["screenshot"] == "page-pipeline-402.png"
        assert report_payload["summaries"][0]["visualReview"]["status"] == "capture-only"
        assert report_payload["visualReview"]["byStatus"] == {"capture-only": 1}
        assert report_payload["visualReview"]["reviewHtml"] == "review.html"
        assert report_payload["visualReview"]["contactSheet"] == "contact-sheet.png"
        assert report_payload["artifacts"]["contactSheet"] == "contact-sheet.png"
        assert (out / "page-pipeline-402.png").exists()
        assert (out / "review.html").exists()
        assert (out / "contact-sheet.png").exists()


def test_pipeline_visual_smoke_falls_back_to_static_when_browser_is_unavailable(
    monkeypatch,
) -> None:
    from figma2hugo.pipeline import visual_smoke

    def unavailable_browser(**_kwargs: object) -> None:
        raise PermissionError("async pipe access denied")

    monkeypatch.setattr(visual_smoke, "_run_playwright_browser_smoke", unavailable_browser)

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-smoke-static-fallback-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        source = temp_path / "site"
        public = temp_path / "public"
        out = temp_path / "smoke"
        source.mkdir()
        public_page = public / "page-pipeline"
        asset_dir = public / "pipeline-assets"
        public_page.mkdir(parents=True)
        asset_dir.mkdir()
        (asset_dir / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (public_page / "index.html").write_text(
            """
            <html><body>
              <main class="pipeline-page">
                <section class="pipeline-responsive-variant">
                  <img src="/pipeline-assets/hero.png" alt="">
                  <form data-component="form"><input name="email"></form>
                  <details data-component="accordion-item"><summary>Question</summary></details>
                  <div data-carousel="true"></div>
                </section>
              </main>
            </body></html>
            """,
            encoding="utf-8",
        )
        (source / "report.json").write_text(
            _generator_support.json.dumps(
                {
                    "pipeline": "pipeline",
                    "pages": [{"slug": "page-pipeline"}],
                }
            ),
            encoding="utf-8",
        )

        report = run_pipeline_visual_smoke(
            source,
            out,
            public_dir=public,
            widths=(402,),
            screenshot_widths=(402,),
        )

        report_payload = _generator_support.json.loads(
            (out / "report.json").read_text(encoding="utf-8")
        )
        assert report["issueCount"] == 0
        assert report_payload["browser"]["engine"] == "static-fallback"
        assert report_payload["browser"]["status"] == "fallback"
        assert report_payload["browser"]["screenshotsAvailable"] is False
        assert report_payload["screenshots"]["count"] == 0
        assert report_payload["visualReview"]["count"] == 0
        assert report_payload["summaries"][0]["metrics"]["engine"] == "static-html"
        assert (out / "review.html").exists()
        assert (out / "issues.json").exists()


def test_pipeline_visual_smoke_compares_against_figma_reference_when_no_baseline(
    monkeypatch, tmp_path: Path
) -> None:
    class FakePage:
        def goto(self, *_args, **_kwargs) -> None:
            pass

        def wait_for_timeout(self, _timeout: int) -> None:
            pass

        def evaluate(self, _script: str, payload: dict[str, object]) -> dict[str, object]:
            if "slug" not in payload:
                return {}
            return {
                "issues": [],
                "metrics": {
                    "slug": payload["slug"],
                    "clientWidth": 402,
                    "scrollWidth": 402,
                },
            }

        def screenshot(self, *, path: str, full_page: bool) -> None:
            assert full_page is True
            Image.new("RGB", (402, 402), color=(255, 255, 255)).save(path)

        def close(self) -> None:
            pass

    class FakeBrowser:
        def new_page(self, **_kwargs) -> FakePage:
            return FakePage()

        def close(self) -> None:
            pass

    class FakePlaywright:
        chromium = SimpleNamespace(launch=lambda: FakeBrowser())

        def __enter__(self) -> FakePlaywright:
            return self

        def __exit__(self, *_args) -> None:
            pass

    sync_module = SimpleNamespace(sync_playwright=lambda: FakePlaywright())
    monkeypatch.setitem(sys.modules, "playwright", SimpleNamespace(sync_api=sync_module))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_module)

    from figma2hugo.pipeline import figma_references

    source_ref = tmp_path / "source-ref.png"
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(source_ref)
    monkeypatch.setattr(
        figma_references.FigmaPipelineRawClient,
        "get_node_render_urls",
        lambda self, file_key, node_ids: {"1:1": "https://images.example/ref.png"},
    )
    monkeypatch.setattr(
        figma_references,
        "_download_image_bytes",
        lambda _url: source_ref.read_bytes(),
    )

    source = tmp_path / "site"
    public = tmp_path / "public"
    out = tmp_path / "smoke"
    source.mkdir()
    public.mkdir()
    (source / "report.json").write_text(
        _generator_support.json.dumps(
            {
                "pipeline": "pipeline",
                "pages": [{"slug": "page-pipeline"}],
                "figmaReference": {
                    "version": 1,
                    "pipeline": "pipeline",
                    "enabled": True,
                    "source": "figma-render",
                    "status": "planned",
                    "count": 1,
                    "items": [
                        {
                            "slug": "page-pipeline",
                            "viewport": 402,
                            "fileName": "page-pipeline-402.png",
                            "fileKey": "FILE",
                            "nodeId": "1:1",
                            "sourceWidth": 402,
                            "sourceHeight": 402,
                            "derivedFromWidth": 402,
                            "responsive": False,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    report = run_pipeline_visual_smoke(
        source,
        out,
        public_dir=public,
        widths=(402,),
        screenshot_widths=(402,),
        token="token-pipeline",
    )

    item = report["visualReview"]["items"][0]
    assert report["visualReview"]["comparisonKind"] == "figma-reference"
    assert report["visualReview"]["figmaReference"]["preparedCount"] == 1
    assert item["status"] == "pass"
    assert item["referenceKind"] == "figma-reference"
    assert (out / "figma-reference" / "page-pipeline-402.png").exists()


def test_pipeline_visual_smoke_marks_baseline_diffs_for_review() -> None:
    from figma2hugo.pipeline.visual_smoke import _visual_review_record

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-smoke-baseline-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        out = temp_path / "smoke"
        baseline = temp_path / "baseline"
        out.mkdir()
        baseline.mkdir()
        screenshot_path = out / "page-pipeline-402.png"
        baseline_path = baseline / "page-pipeline-402.png"
        Image.new("RGB", (4, 4), color=(255, 255, 255)).save(screenshot_path)
        Image.new("RGB", (4, 4), color=(255, 255, 255)).save(baseline_path)
        with Image.open(baseline_path) as image:
            image.putpixel((0, 0), (0, 0, 0))
            image.save(baseline_path)

        record = _visual_review_record(
            screenshot_path,
            out_dir=out,
            baseline_dir=baseline,
            slug="page-pipeline",
            width=402,
            review_threshold=0.01,
            fail_threshold=0.5,
        )

        assert record["status"] == "review"
        assert record["pixelDiffRatio"] == 0.0625
        assert record["diff"] == "page-pipeline-402-diff.png"
        assert (out / "page-pipeline-402-diff.png").exists()


def test_pipeline_visual_smoke_ignores_tiny_antialias_pixel_diffs() -> None:
    from figma2hugo.pipeline.visual_smoke import _visual_review_record

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-smoke-antialias-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        out = temp_path / "smoke"
        baseline = temp_path / "baseline"
        out.mkdir()
        baseline.mkdir()
        screenshot_path = out / "page-pipeline-402.png"
        baseline_path = baseline / "page-pipeline-402.png"
        Image.new("RGB", (4, 4), color=(255, 255, 255)).save(screenshot_path)
        Image.new("RGB", (4, 4), color=(255, 255, 255)).save(baseline_path)
        with Image.open(baseline_path) as image:
            image.putpixel((0, 0), (235, 235, 235))
            image.save(baseline_path)

        record = _visual_review_record(
            screenshot_path,
            out_dir=out,
            baseline_dir=baseline,
            slug="page-pipeline",
            width=402,
            review_threshold=0.01,
            fail_threshold=0.5,
        )

        assert record["status"] == "pass"
        assert record["pixelDiffRatio"] == 0.0
        assert record["diff"] is None


def test_pipeline_visual_smoke_marks_height_only_delta_for_review() -> None:
    from figma2hugo.pipeline.visual_smoke import _visual_review_record

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-smoke-height-delta-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        out = temp_path / "smoke"
        baseline = temp_path / "baseline"
        out.mkdir()
        baseline.mkdir()
        screenshot_path = out / "page-pipeline-402.png"
        baseline_path = baseline / "page-pipeline-402.png"
        Image.new("RGB", (4, 6), color=(255, 255, 255)).save(screenshot_path)
        Image.new("RGB", (4, 4), color=(255, 255, 255)).save(baseline_path)

        record = _visual_review_record(
            screenshot_path,
            out_dir=out,
            baseline_dir=baseline,
            slug="page-pipeline",
            width=402,
            review_threshold=0.01,
            fail_threshold=0.5,
        )

        assert record["status"] == "height-delta-review"
        assert record["sizeMismatch"] is True
        assert record["sizeMismatchKind"] == "height-only"
        assert record["commonCropPixelDiffRatio"] == 0.0
        assert record["sizeDelta"] == {"width": 0, "height": 2}


def test_pipeline_source_identity_is_project_stable_but_snapshot_sensitive() -> None:
    from figma2hugo.pipeline.visual_baselines import build_source_identity

    first_raw = {"id": "1:2", "name": "Page", "characters": "Before"}
    second_raw = {"id": "1:2", "name": "Page", "characters": "After"}
    figma_url = "https://www.figma.com/design/FILEKEY/Page?node-id=1-2"

    first = build_source_identity([first_raw], figma_urls=[figma_url])
    second = build_source_identity([second_raw], figma_urls=[figma_url])

    assert first["sourceKind"] == "figma"
    assert first["projectId"] == second["projectId"]
    assert first["sourceHash"] != second["sourceHash"]
    assert first["figmaFileKeys"] == ["FILEKEY"]
    assert first["figmaNodeIds"] == ["1:2"]


def test_pipeline_visual_baseline_root_bootstraps_new_project(tmp_path: Path) -> None:
    from figma2hugo.pipeline.visual_baselines import resolve_visual_baseline

    source = tmp_path / "site"
    source.mkdir()
    (source / "report.json").write_text(
        _generator_support.json.dumps(
            {
                "pipeline": "pipeline",
                "sourceIdentity": {
                    "version": 1,
                    "pipeline": "pipeline",
                    "projectId": "figma-example",
                    "sourceHash": "abc",
                },
            }
        ),
        encoding="utf-8",
    )

    resolved = resolve_visual_baseline(
        source_dir=source,
        baseline_mode="auto",
        baseline_dir=None,
        baseline_root=tmp_path / "baselines",
    )

    assert resolved.resolved_mode == "capture"
    assert resolved.bootstrap_required is True
    assert resolved.project_id == "figma-example"


def test_pipeline_promotes_visual_baseline_snapshot() -> None:
    from figma2hugo.pipeline.visual_baselines import promote_visual_baseline

    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-baseline-promote-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        smoke = temp_path / "smoke"
        baseline_root = temp_path / "baselines"
        smoke.mkdir()
        Image.new("RGB", (4, 4), color=(255, 255, 255)).save(smoke / "page-pipeline-402.png")
        (smoke / "report.json").write_text(
            _generator_support.json.dumps(
                {
                    "pipeline": "pipeline",
                    "sourceIdentity": {
                        "version": 1,
                        "pipeline": "pipeline",
                        "projectId": "figma-example",
                        "sourceHash": "abcdef123456",
                    },
                    "screenshots": {
                        "items": [
                            {
                                "slug": "page-pipeline",
                                "viewport": 402,
                                "path": "page-pipeline-402.png",
                                "fullPage": True,
                                "viewportSize": {"width": 402, "height": 874},
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

        result = promote_visual_baseline(
            smoke,
            baseline_root,
            baseline_id="first-approved",
            label="first approved",
        )

        snapshot = baseline_root / "figma-example" / "first-approved"
        assert result["baselineDir"] == str(snapshot.resolve())
        assert (snapshot / "page-pipeline-402.png").exists()
        manifest = _generator_support.json.loads(
            (snapshot / "manifest.json").read_text(encoding="utf-8")
        )
        index = _generator_support.json.loads(
            (baseline_root / "figma-example" / "index.json").read_text(encoding="utf-8")
        )
        assert manifest["screenshotCount"] == 1
        assert manifest["screenshots"][0]["imageSize"] == {"width": 4, "height": 4}
        assert index["current"] == "first-approved"


def test_pipeline_fetcher_parses_url_and_fetches_raw_node_without_legacy_reader() -> None:
    target = parse_figma_pipeline_url("https://www.figma.com/design/file-key/Test?node-id=12-34")
    assert target.file_key == "file-key"
    assert target.node_id == "12:34"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-figma-token"] == "token-pipeline"
        if request.url.path == "/v1/files/file-key/images":
            return httpx.Response(
                200, json={"images": {"image-ref": "https://images.example/a.png"}}
            )
        assert request.url.path == "/v1/files/file-key/nodes"
        assert request.url.params["ids"] == "12:34"
        return httpx.Response(
            200,
            json={
                "nodes": {
                    "12:34": {
                        "document": {
                            "id": "12:34",
                            "name": "page-pipeline-402",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 400,
                            },
                            "children": [
                                {
                                    "id": "image",
                                    "name": "image-test",
                                    "type": "RECTANGLE",
                                    "absoluteBoundingBox": {
                                        "x": 0,
                                        "y": 0,
                                        "width": 100,
                                        "height": 100,
                                    },
                                    "fills": [{"type": "IMAGE", "imageRef": "image-ref"}],
                                }
                            ],
                        }
                    }
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        raw = fetch_raw_node_from_figma(
            target.source_url,
            token="token-pipeline",
            base_url="https://api.figma.test/v1",
            client=client,
        )

    assert raw["id"] == "12:34"
    assert raw["name"] == "page-pipeline-402"
    assert raw["children"][0]["pipelineImageUrl"] == "https://images.example/a.png"


def test_pipeline_fetcher_falls_back_to_render_urls_for_image_fill_nodes() -> None:
    target = parse_figma_pipeline_url("https://www.figma.com/design/file-key/Test?node-id=12-34")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/files/file-key/images":
            return httpx.Response(200, json={"error": True, "status": 404, "meta": {}})
        if request.url.path == "/v1/images/file-key":
            assert request.url.params["ids"] == "image"
            assert request.url.params["format"] == "png"
            return httpx.Response(
                200,
                json={"images": {"image": "https://images.example/rendered-node.png"}},
            )
        assert request.url.path == "/v1/files/file-key/nodes"
        return httpx.Response(
            200,
            json={
                "nodes": {
                    "12:34": {
                        "document": {
                            "id": "12:34",
                            "name": "page-pipeline-402",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 400,
                            },
                            "children": [
                                {
                                    "id": "image",
                                    "name": "image-test",
                                    "type": "RECTANGLE",
                                    "absoluteBoundingBox": {
                                        "x": 0,
                                        "y": 0,
                                        "width": 100,
                                        "height": 100,
                                    },
                                    "fills": [
                                        {"type": "IMAGE", "imageRef": "missing-from-file-images"}
                                    ],
                                }
                            ],
                        }
                    }
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        raw = fetch_raw_node_from_figma(
            target.source_url,
            token="token-pipeline",
            base_url="https://api.figma.test/v1",
            client=client,
        )

    assert raw["children"][0]["pipelineImageUrl"] == "https://images.example/rendered-node.png"


def test_pipeline_fetcher_retries_transient_image_endpoint_errors(monkeypatch) -> None:
    target = parse_figma_pipeline_url("https://www.figma.com/design/file-key/Test?node-id=12-34")
    image_attempts = 0
    monkeypatch.setattr(pipeline_fetcher.time, "sleep", lambda _delay: None)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal image_attempts
        if request.url.path == "/v1/files/file-key/images":
            image_attempts += 1
            if image_attempts < 3:
                return httpx.Response(
                    503,
                    headers={"Retry-After": "0"},
                    text="Service Unavailable",
                )
            return httpx.Response(
                200, json={"images": {"image-ref": "https://images.example/a.png"}}
            )
        assert request.url.path == "/v1/files/file-key/nodes"
        return httpx.Response(
            200,
            json={
                "nodes": {
                    "12:34": {
                        "document": {
                            "id": "12:34",
                            "name": "page-pipeline-402",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 400,
                            },
                            "children": [
                                {
                                    "id": "image",
                                    "name": "image-test",
                                    "type": "RECTANGLE",
                                    "absoluteBoundingBox": {
                                        "x": 0,
                                        "y": 0,
                                        "width": 100,
                                        "height": 100,
                                    },
                                    "fills": [{"type": "IMAGE", "imageRef": "image-ref"}],
                                }
                            ],
                        }
                    }
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        raw = fetch_raw_node_from_figma(
            target.source_url,
            token="token-pipeline",
            base_url="https://api.figma.test/v1",
            client=client,
        )

    assert image_attempts == 3
    assert raw["children"][0]["pipelineImageUrl"] == "https://images.example/a.png"


def test_pipeline_fetcher_uses_local_config_token(monkeypatch) -> None:
    target = parse_figma_pipeline_url("https://www.figma.com/design/file-key/Test?node-id=12-34")
    monkeypatch.delenv("FIGMA_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FIGMA_TOKEN", raising=False)
    monkeypatch.setattr(pipeline_fetcher, "get_local_figma_token", lambda: "local-token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-figma-token"] == "local-token"
        if request.url.path == "/v1/files/file-key/images":
            return httpx.Response(200, json={"images": {}})
        assert request.url.path == "/v1/files/file-key/nodes"
        return httpx.Response(
            200,
            json={
                "nodes": {
                    "12:34": {
                        "document": {
                            "id": "12:34",
                            "name": "page-pipeline-402",
                            "type": "FRAME",
                            "absoluteBoundingBox": {
                                "x": 0,
                                "y": 0,
                                "width": 402,
                                "height": 400,
                            },
                            "children": [],
                        }
                    }
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        raw = fetch_raw_node_from_figma(
            target.source_url,
            base_url="https://api.figma.test/v1",
            client=client,
        )

    assert raw["name"] == "page-pipeline-402"


def test_pipeline_runner_can_build_from_figma_urls_with_pipeline_fetcher_only(monkeypatch) -> None:
    def fake_fetch(figma_url: str, *, token: str | None = None):
        assert "node-id=12-34" in figma_url
        assert token == "token-pipeline"
        return {
            "id": "12:34",
            "name": "page-pipeline-402",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
            "children": [],
        }

    monkeypatch.setattr(pipeline_runner, "fetch_raw_node_from_figma", fake_fetch)
    with _generator_support.tempfile.TemporaryDirectory(
        dir=_generator_support.ROOT,
        prefix=".pipeline-fetch-test-",
    ) as temp_dir:
        temp_path = Path(temp_dir)
        result = pipeline_runner.build_pipeline_from_figma_urls(
            ["https://www.figma.com/design/file-key/Test?node-id=12-34"],
            temp_path / "out",
            token="token-pipeline",
        )

        assert result["command"] == "build-figma"
        assert (temp_path / "out" / "raw" / "file-key-12-34.raw.json").exists()
        assert (temp_path / "out" / "page-pipeline-402.render-plan.json").exists()
        assert (temp_path / "out" / "site" / "pages" / "page-pipeline-402" / "index.html").exists()


def test_pipeline_python_modules_do_not_import_removed_generators() -> None:
    pipeline_root = _generator_support.ROOT / "src" / "figma2hugo" / "pipeline"
    forbidden_imports = (
        "figma2hugo.generators",
        "._canonical",
        "._responsive",
        "content_extractor",
        "figma_reader",
        "workflow",
        "templates.hugo",
        "templates.shared",
    )

    for path in Path(pipeline_root).rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(forbidden in source for forbidden in forbidden_imports), path


def _first_issue(plan, code: str):
    for issue in plan.diagnostics:
        if issue.code == code:
            return issue
    raise AssertionError(
        f"Missing diagnostic {code}. Got {[issue.code for issue in plan.diagnostics]}"
    )


def _find_node(root, name: str):
    if root.name == name:
        return root
    for child in root.children:
        try:
            return _find_node(child, name)
        except AssertionError:
            pass
    raise AssertionError(f"Missing render node {name}")


def _find_section_node(section, name: str):
    for node in section.nodes:
        try:
            return _find_node(node, name)
        except AssertionError:
            pass
    raise AssertionError(f"Missing render node {name}")


def _json_nodes_by_component(root, component: str):
    matches = []
    if isinstance(root, dict):
        if root.get("component") == component:
            matches.append(root)
        for key in ("sections", "nodes", "children"):
            value = root.get(key)
            if isinstance(value, list):
                for child in value:
                    matches.extend(_json_nodes_by_component(child, component))
    return matches


def _raw_text_override_payload() -> dict[str, object]:
    title = "Parler de la passion de Bastien\nUn titre assez grand pour du referencement"
    overrides = [8 if index <= title.index("\n") else 7 for index, _ in enumerate(title)]
    return {
        "id": "page",
        "name": "page-text-1920",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 220},
        "children": [
            {
                "id": "section",
                "name": "section-histoire-embedded",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1920, "height": 180},
                "children": [
                    {
                        "id": "card",
                        "name": "card-v-infos",
                        "type": "FRAME",
                        "absoluteBoundingBox": {"x": 20, "y": 20, "width": 640, "height": 140},
                        "children": [
                            {
                                "id": "title",
                                "name": "titre-h4-infos",
                                "type": "TEXT",
                                "characters": title,
                                "style": {
                                    "fontFamily": "Inter",
                                    "fontSize": 35,
                                    "fontWeight": 700,
                                    "italic": True,
                                    "lineHeightPx": 45,
                                    "letterSpacing": -0.7,
                                    "textAlignHorizontal": "LEFT",
                                },
                                "characterStyleOverrides": overrides,
                                "styleOverrideTable": {
                                    "8": {
                                        "fontSize": 18,
                                        "lineHeightPx": 23,
                                        "letterSpacing": -0.18,
                                    },
                                    "7": {
                                        "fontSize": 17,
                                        "lineHeightPx": 22,
                                        "letterSpacing": -0.085,
                                    },
                                },
                                "absoluteBoundingBox": {
                                    "x": 40,
                                    "y": 20,
                                    "width": 620,
                                    "height": 60,
                                },
                            },
                            {
                                "id": "paragraph",
                                "name": "texte-infos",
                                "type": "TEXT",
                                "characters": "Lorem ipsum dolor sit amet.",
                                "style": {
                                    "fontFamily": "Inter",
                                    "fontSize": 12,
                                    "lineHeightPx": 15,
                                    "textAlignHorizontal": "LEFT",
                                },
                                "absoluteBoundingBox": {
                                    "x": 40,
                                    "y": 80,
                                    "width": 620,
                                    "height": 45,
                                },
                            },
                        ],
                    }
                ],
            }
        ],
    }


def _raw_contact_form_payload() -> dict[str, object]:
    return {
        "id": "page",
        "name": "page-contact-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 620},
        "children": [
            {
                "id": "contact",
                "name": "section-contact",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 520},
                "children": [
                    {
                        "id": "form",
                        "name": "formulaire-contact-post",
                        "type": "FRAME",
                        "absoluteBoundingBox": {"x": 70, "y": 96, "width": 262, "height": 316},
                        "children": [
                            _raw_field(
                                "input-name",
                                "input-nom-prenom-required",
                                "Nom et Prénom",
                                y=120,
                            ),
                            _raw_field(
                                "input-email",
                                "input-mail-required",
                                "Votre email",
                                y=168,
                            ),
                            _raw_field(
                                "input-subject",
                                "input-select-demande-required",
                                "choisir|Choisissez le sujet de votre demande",
                                y=216,
                                extra_labels=("formation", "Formation", "expertise", "Expertise"),
                            ),
                            _raw_field(
                                "input-message",
                                "input-message-required",
                                "Votre message",
                                y=264,
                                height=70,
                            ),
                            {
                                "id": "action",
                                "name": "action-contact",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 153,
                                    "y": 354,
                                    "width": 96,
                                    "height": 28,
                                },
                                "children": [
                                    {
                                        "id": "action-label",
                                        "name": "texte-button-envoyer",
                                        "type": "TEXT",
                                        "characters": "Envoyer",
                                        "absoluteBoundingBox": {
                                            "x": 168,
                                            "y": 360,
                                            "width": 66,
                                            "height": 18,
                                        },
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def _raw_tiny_contact_form_payload() -> dict[str, object]:
    return {
        "id": "page",
        "name": "page-contact-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 160},
        "children": [
            {
                "id": "contact",
                "name": "section-contact",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 150},
                "children": [
                    {
                        "id": "form",
                        "name": "formulaire-contact-post",
                        "type": "FRAME",
                        "absoluteBoundingBox": {"x": 190, "y": 40, "width": 120, "height": 108},
                        "children": [
                            _raw_box("form-bg", "bg-contact-formulaire", 214, 44, 96, 96),
                            _raw_tiny_field(
                                "input-name",
                                "input-nom-prenom-required",
                                "Nom",
                                y=50,
                            ),
                            _raw_tiny_field(
                                "input-email",
                                "input-mail-required",
                                "Email",
                                y=65,
                            ),
                            _raw_tiny_field(
                                "input-subject",
                                "input-select-demande-required",
                                "Choisissez",
                                y=80,
                            ),
                            _raw_tiny_field(
                                "input-message",
                                "input-message-required",
                                "Message",
                                y=95,
                                height=20,
                            ),
                            {
                                "id": "button-submit",
                                "name": "button-envoyer",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 242,
                                    "y": 122,
                                    "width": 32,
                                    "height": 8,
                                },
                                "children": [
                                    _raw_box(
                                        "button-submit-bg",
                                        "bg-button-envoyer",
                                        242,
                                        122,
                                        32,
                                        8,
                                    ),
                                    {
                                        "id": "button-submit-label",
                                        "name": "texte-button-envoyer",
                                        "type": "TEXT",
                                        "characters": "Envoyer",
                                        "style": {
                                            "fontFamily": "Inter",
                                            "fontSize": 4,
                                            "lineHeightPx": 5,
                                            "textAlignHorizontal": "CENTER",
                                        },
                                        "absoluteBoundingBox": {
                                            "x": 246,
                                            "y": 124,
                                            "width": 24,
                                            "height": 4,
                                        },
                                    },
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def _raw_link_card_payload() -> dict[str, object]:
    return {
        "id": "page",
        "name": "page-link-card-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 300},
        "children": [
            {
                "id": "section",
                "name": "section-cards",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 240},
                "children": [
                    {
                        "id": "card",
                        "name": "case-card-01",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 24,
                            "y": 24,
                            "width": 180,
                            "height": 160,
                        },
                        "children": [
                            {
                                "id": "label",
                                "name": "case-card-01-link",
                                "type": "TEXT",
                                "characters": "Lire le cas",
                                "absoluteBoundingBox": {
                                    "x": 40,
                                    "y": 120,
                                    "width": 120,
                                    "height": 24,
                                },
                            },
                            {
                                "id": "href",
                                "name": "href-case-card-01",
                                "type": "TEXT",
                                "characters": "https://example.com/cas",
                                "absoluteBoundingBox": {
                                    "x": 40,
                                    "y": 120,
                                    "width": 260,
                                    "height": 40,
                                },
                            },
                        ],
                    }
                ],
            }
        ],
    }


def _raw_accordion_payload() -> dict[str, object]:
    return {
        "id": "page",
        "name": "page-accordion-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 420},
        "children": [
            {
                "id": "section",
                "name": "section-faq",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 360},
                "children": [
                    {
                        "id": "accordion",
                        "name": "accordion-single-faq",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 24,
                            "y": 40,
                            "width": 354,
                            "height": 220,
                        },
                        "children": [
                            {
                                "id": "item",
                                "name": "accordion-item-1-open",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 24,
                                    "y": 40,
                                    "width": 354,
                                    "height": 180,
                                },
                                "children": [
                                    {
                                        "id": "trigger",
                                        "name": "accordion-trigger-1",
                                        "type": "FRAME",
                                        "absoluteBoundingBox": {
                                            "x": 24,
                                            "y": 40,
                                            "width": 354,
                                            "height": 52,
                                        },
                                        "children": [
                                            {
                                                "id": "question",
                                                "name": "texte-question-1",
                                                "type": "TEXT",
                                                "characters": "Question longue ?",
                                                "absoluteBoundingBox": {
                                                    "x": 40,
                                                    "y": 52,
                                                    "width": 260,
                                                    "height": 24,
                                                },
                                            }
                                        ],
                                    },
                                    {
                                        "id": "panel",
                                        "name": "accordion-panel-1",
                                        "type": "FRAME",
                                        "absoluteBoundingBox": {
                                            "x": 24,
                                            "y": 92,
                                            "width": 354,
                                            "height": 120,
                                        },
                                        "children": [
                                            {
                                                "id": "answer",
                                                "name": "texte-reponse-1",
                                                "type": "TEXT",
                                                "characters": "Réponse détaillée.",
                                                "absoluteBoundingBox": {
                                                    "x": 40,
                                                    "y": 112,
                                                    "width": 280,
                                                    "height": 50,
                                                },
                                            }
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _raw_carousel_payload() -> dict[str, object]:
    return {
        "id": "page",
        "name": "page-carousel-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 360},
        "children": [
            {
                "id": "section",
                "name": "section-gallery",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 320},
                "children": [
                    {
                        "id": "carousel",
                        "name": "carousel-gallery",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 24,
                            "y": 40,
                            "width": 354,
                            "height": 240,
                        },
                        "children": [
                            {
                                "id": "stage",
                                "name": "carousel-stage-gallery",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 24,
                                    "y": 40,
                                    "width": 354,
                                    "height": 160,
                                },
                                "children": [
                                    {
                                        "id": "slide-1",
                                        "name": "carousel-slide-1-active",
                                        "type": "FRAME",
                                        "absoluteBoundingBox": {
                                            "x": 24,
                                            "y": 40,
                                            "width": 354,
                                            "height": 160,
                                        },
                                        "children": [
                                            {
                                                "id": "slide-1-title",
                                                "name": "texte-slide-1",
                                                "type": "TEXT",
                                                "characters": "Premier cas client",
                                                "absoluteBoundingBox": {
                                                    "x": 40,
                                                    "y": 70,
                                                    "width": 180,
                                                    "height": 24,
                                                },
                                            }
                                        ],
                                    },
                                    {
                                        "id": "slide-2",
                                        "name": "carousel-slide-2",
                                        "type": "FRAME",
                                        "absoluteBoundingBox": {
                                            "x": 24,
                                            "y": 40,
                                            "width": 354,
                                            "height": 160,
                                        },
                                        "children": [
                                            {
                                                "id": "slide-2-title",
                                                "name": "texte-slide-2",
                                                "type": "TEXT",
                                                "characters": "Second cas client",
                                                "absoluteBoundingBox": {
                                                    "x": 40,
                                                    "y": 70,
                                                    "width": 180,
                                                    "height": 24,
                                                },
                                            }
                                        ],
                                    },
                                ],
                            },
                            {
                                "id": "thumbs",
                                "name": "carousel-thumbs-gallery",
                                "type": "FRAME",
                                "absoluteBoundingBox": {
                                    "x": 24,
                                    "y": 220,
                                    "width": 108,
                                    "height": 40,
                                },
                                "children": [
                                    {
                                        "id": "thumb-1",
                                        "name": "carousel-thumb-1",
                                        "type": "FRAME",
                                        "absoluteBoundingBox": {
                                            "x": 24,
                                            "y": 220,
                                            "width": 48,
                                            "height": 40,
                                        },
                                    },
                                    {
                                        "id": "thumb-2",
                                        "name": "carousel-thumb-2",
                                        "type": "FRAME",
                                        "absoluteBoundingBox": {
                                            "x": 84,
                                            "y": 220,
                                            "width": 48,
                                            "height": 40,
                                        },
                                    },
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def _raw_multi_accordion_payload() -> dict[str, object]:
    return {
        "id": "page",
        "name": "page-accordion-402",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 600},
        "children": [
            {
                "id": "section-faq",
                "name": "section-faq",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 402, "height": 400},
                "children": [
                    {
                        "id": "accordion",
                        "name": "accordion-single-faq",
                        "type": "FRAME",
                        "absoluteBoundingBox": {
                            "x": 40,
                            "y": 60,
                            "width": 322,
                            "height": 300,
                        },
                        "children": [
                            _raw_accordion_item(1, y=60, open_item=True),
                            _raw_accordion_item(2, y=200, open_item=False),
                            _raw_accordion_item(3, y=340, open_item=False),
                        ],
                    }
                ],
            },
            {
                "id": "after-faq",
                "name": "section-after-faq",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 0, "y": 400, "width": 402, "height": 100},
                "children": [
                    {
                        "id": "after-text",
                        "name": "texte-apres-faq",
                        "type": "TEXT",
                        "characters": "Apres FAQ",
                        "absoluteBoundingBox": {"x": 40, "y": 420, "width": 120, "height": 24},
                    }
                ],
            },
        ],
    }


def _raw_accordion_item(index: int, *, y: int, open_item: bool) -> dict[str, object]:
    suffix = "-open" if open_item else ""
    return {
        "id": f"item-{index}",
        "name": f"accordion-item-{index}{suffix}",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 40, "y": y, "width": 322, "height": 120},
        "children": [
            {
                "id": f"trigger-{index}",
                "name": f"accordion-trigger-{index}",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 40, "y": y, "width": 322, "height": 30},
                "children": [
                    {
                        "id": f"question-{index}",
                        "name": f"texte-question-{index}",
                        "type": "TEXT",
                        "characters": "Question longue ?",
                        "absoluteBoundingBox": {
                            "x": 52,
                            "y": y + 6,
                            "width": 240,
                            "height": 18,
                        },
                    }
                ],
            },
            {
                "id": f"panel-{index}",
                "name": f"accordion-panel-{index}",
                "type": "FRAME",
                "absoluteBoundingBox": {"x": 40, "y": y + 30, "width": 322, "height": 90},
                "children": [
                    {
                        "id": f"answer-{index}",
                        "name": f"texte-reponse-{index}",
                        "type": "TEXT",
                        "characters": "Reponse detaillee.",
                        "absoluteBoundingBox": {
                            "x": 52,
                            "y": y + 42,
                            "width": 260,
                            "height": 36,
                        },
                    }
                ],
            },
        ],
    }


def _raw_field(
    node_id: str,
    name: str,
    label: str,
    *,
    y: int,
    height: int = 34,
    extra_labels: tuple[str, ...] = (),
) -> dict[str, object]:
    children: list[dict[str, object]] = [
        {
            "id": f"{node_id}-label",
            "name": f"placeholder-{node_id}",
            "type": "TEXT",
            "characters": label,
            "absoluteBoundingBox": {
                "x": 104,
                "y": y + 8,
                "width": 190,
                "height": 18,
            },
        }
    ]
    for index, extra_label in enumerate(extra_labels, start=1):
        children.insert(
            0,
            {
                "id": f"{node_id}-option-{index}",
                "name": f"option-{node_id}-{index}",
                "type": "TEXT",
                "characters": extra_label,
                "absoluteBoundingBox": {
                    "x": 104,
                    "y": y + 8,
                    "width": 120,
                    "height": 18,
                },
            },
        )
    return {
        "id": node_id,
        "name": name,
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 94, "y": y, "width": 214, "height": height},
        "children": children,
    }


def _raw_tiny_field(
    node_id: str,
    name: str,
    label: str,
    *,
    y: int,
    height: int = 10,
) -> dict[str, object]:
    return {
        "id": node_id,
        "name": name,
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 220, "y": y, "width": 76, "height": height},
        "children": [
            _raw_box(f"{node_id}-bg", f"zone-{node_id}", 220, y, 76, height),
            {
                "id": f"{node_id}-label",
                "name": f"placeholder-{node_id}",
                "type": "TEXT",
                "characters": label,
                "style": {
                    "fontFamily": "Inter",
                    "fontSize": 3,
                    "lineHeightPx": 4,
                    "textAlignHorizontal": "LEFT",
                },
                "absoluteBoundingBox": {"x": 222, "y": y + 3, "width": 52, "height": 3},
            },
        ],
    }


def _raw_box(
    node_id: str,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> dict[str, object]:
    return {
        "id": node_id,
        "name": name,
        "type": "RECTANGLE",
        "absoluteBoundingBox": {"x": x, "y": y, "width": width, "height": height},
        "fills": [
            {
                "type": "SOLID",
                "color": {"r": 0.0, "g": 0.1, "b": 0.35, "a": 1.0},
            }
        ],
    }


def _raw_asset(
    node_id: str,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> dict[str, object]:
    node = _raw_box(node_id, name, x, y, width, height)
    node["pipelineImageUrl"] = f"https://images.example/{node_id}.png"
    return node


def _raw_visual_card(
    node_id: str,
    name: str,
    x: int,
    y: int,
    width: int,
    *,
    image_offset: int = 8,
    label_offset: int = 16,
) -> dict[str, object]:
    return {
        "id": node_id,
        "name": name,
        "type": "FRAME",
        "absoluteBoundingBox": {"x": x, "y": y, "width": width, "height": 56},
        "children": [
            _raw_asset(f"{node_id}-image", f"image-{node_id}", x + image_offset, y, 22, 32),
            {
                "id": f"{node_id}-label",
                "name": f"label-{node_id}",
                "type": "TEXT",
                "characters": "Notre expertise",
                "style": {
                    "fontSize": 8,
                    "lineHeightPx": 8,
                    "textAlignHorizontal": "CENTER",
                },
                "absoluteBoundingBox": {
                    "x": x + label_offset,
                    "y": y + 42,
                    "width": 32,
                    "height": 8,
                },
            },
        ],
    }


def _render_node_left(node) -> float:
    children_left = [_render_node_left(child) for child in node.children]
    own_left = node.bounds.x if node.text.strip() or node.asset_url else None
    return min([value for value in (own_left, *children_left) if value is not None])


def _render_node_right(node) -> float:
    children_right = [_render_node_right(child) for child in node.children]
    own_right = node.bounds.right if node.text.strip() or node.asset_url else None
    return max([value for value in (own_right, *children_right) if value is not None])


def _raw_page_json(*, name: str, width: int, height: int, section_height: int) -> str:
    return _generator_support.json.dumps(
        _raw_page_payload(
            name=name,
            width=width,
            height=height,
            section_height=section_height,
        )
    )


def _raw_page_payload(
    *, name: str, width: int, height: int, section_height: int
) -> dict[str, object]:
    return {
        "id": f"page-{width}",
        "name": name,
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": width, "height": height},
        "children": [
            {
                "id": f"hero-{width}",
                "name": "section-hero",
                "type": "FRAME",
                "absoluteBoundingBox": {
                    "x": 0,
                    "y": 0,
                    "width": width,
                    "height": section_height,
                },
            }
        ],
    }


def _raw_page_json_with_text(
    *,
    name: str,
    width: int,
    height: int,
    section_name: str,
    section_height: int,
    text: str,
) -> str:
    return _generator_support.json.dumps(
        {
            "id": f"page-{width}",
            "name": name,
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": width, "height": height},
            "children": [
                {
                    "id": f"content-{width}",
                    "name": section_name,
                    "type": "FRAME",
                    "absoluteBoundingBox": {
                        "x": 0,
                        "y": 0,
                        "width": width,
                        "height": section_height,
                    },
                    "children": [
                        {
                            "id": f"title-{width}",
                            "name": "titre-h2-content",
                            "type": "TEXT",
                            "characters": text,
                            "absoluteBoundingBox": {
                                "x": 20,
                                "y": 40,
                                "width": min(width - 40, 400),
                                "height": 40,
                            },
                        }
                    ],
                }
            ],
        }
    )
