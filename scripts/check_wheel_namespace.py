#!/usr/bin/env python3
"""Refuse a wheel that installs the retired colliding import package."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

EXPECTED = "dotmac_integration_client"
RETIRED = "dotmac_integration"


def package_roots(wheel: Path) -> frozenset[str]:
    with zipfile.ZipFile(wheel) as archive:
        return frozenset(
            name.split("/", 1)[0]
            for name in archive.namelist()
            if "/" in name and ".dist-info" not in name and ".data" not in name
        )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_wheel_namespace.py WHEEL")
    wheel = Path(sys.argv[1])
    roots = package_roots(wheel)
    if roots != frozenset({EXPECTED}) or RETIRED in roots:
        raise SystemExit(
            f"{wheel.name} installs package roots {sorted(roots)!r}; "
            f"expected only {EXPECTED!r}"
        )
    print(f"{wheel.name} owns only {EXPECTED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
