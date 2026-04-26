from __future__ import annotations

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from figma2hugo.figma_reader.service import FigmaExtractionService


def test_extraction_service_rejects_flat_roots_without_grouping_frames() -> None:
    root_node = {
        "id": "0:1",
        "name": "Page 1",
        "type": "CANVAS",
        "visible": True,
        "children": [
            {
                "id": f"vector-{index}",
                "name": f"Vector {index}",
                "type": "VECTOR",
                "visible": True,
            }
            for index in range(300)
        ],
    }

    service = FigmaExtractionService()

    with pytest.raises(RuntimeError) as exc_info:
        service._validate_root_structure(root_node)

    message = str(exc_info.value)
    assert "too flat for structured extraction" in message
    assert "grouping frames or sections" in message
