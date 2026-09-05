from __future__ import annotations

import sys


def main() -> None:
    argv = sys.argv[1:]
    if argv and any(arg.startswith("-") for arg in argv) and argv[0] not in {"--gui", "-g"}:
        from ipk2ipkg.cli import main as cli_main

        raise SystemExit(cli_main())
    from ipk2ipkg.gui import run_gui

    run_gui()


if __name__ == "__main__":
    main()
