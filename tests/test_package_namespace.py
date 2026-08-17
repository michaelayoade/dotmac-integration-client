"""The distribution owns one collision-free import namespace."""

from __future__ import annotations

import tomllib
from pathlib import Path

import dotmac_integration_client

REPO = Path(__file__).resolve().parents[1]


def test_distribution_and_runtime_versions_match() -> None:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["poetry"]["version"] == dotmac_integration_client.__version__


def test_the_distribution_owns_only_the_client_import_package() -> None:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["poetry"]["packages"] == [
        {"include": "dotmac_integration_client", "from": "src"}
    ]
    assert (REPO / "src" / "dotmac_integration_client" / "http.py").is_file()
    assert not (REPO / "src" / "dotmac_integration").exists()
