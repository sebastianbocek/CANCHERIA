from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cancheria.desktop.update_service import UPDATE_ASSETS, create_update_archive  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crea un paquete de actualización de CANCHERIA")
    parser.add_argument("--payload", required=True)
    parser.add_argument("--platform", required=True, choices=sorted(UPDATE_ASSETS))
    parser.add_argument("--version", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    payload = Path(args.payload).resolve()
    output = (
        Path(args.output).resolve()
        if args.output
        else ROOT / "release" / UPDATE_ASSETS[args.platform]
    )
    archive, digest = create_update_archive(payload, output, args.version, args.platform)
    print(f"UPDATE_PACKAGE={archive}")
    print(f"SHA256={digest.upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
