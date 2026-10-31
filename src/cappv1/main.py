import argparse
import asyncio
import sys
from dataclasses import replace

from cappv1.version import VERSION

USAGE = """cappv1 - alt text for PowerPoint and Word files

Usage
  cappv1                    open cappv1 (everything else happens inside it)
  cappv1 --web [--port N] [--no-open]
                            the same thing in your browser, until Ctrl+C
  cappv1 --batch [--resume] [--force]
                            no prompt, for scripts: process input/ and show the log
  cappv1 --version

Inside cappv1, type / to see the commands:
  /run  /files  /models  /doctor  /status  /open  /clean  /help  /exit
"""


def batch(argv: list[str]) -> int:
    from cappv1 import doctor
    from cappv1.config import load_config
    from cappv1.pipeline import discover_candidates, run, setup_logging

    parser = argparse.ArgumentParser(prog="cappv1 --batch")
    parser.add_argument("--resume", action="store_true", help="only resume in_progress files")
    parser.add_argument("--force", action="store_true", help="redo everything and replace alt text the author already wrote")
    args = parser.parse_args(argv)

    if doctor.main(["--quick"]):
        print("\nNot ready to run yet - open cappv1 and type /doctor to see what to fix")
        return 1
    config = load_config()
    if not discover_candidates(config):
        print(f"\nNo .pptx or .docx files in {config.input_dir} yet - add one, then run: cappv1 --batch")
        return 0
    if args.force:
        config = replace(config, overwrite_existing=True)
    setup_logging(config.logs_dir)
    asyncio.run(run(config, resume_only=args.resume, force=args.force))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    first = argv[0] if argv else ""

    if first == "":
        if sys.stdin.isatty() and sys.stdout.isatty():
            from cappv1.tui.session import main as session_main

            return session_main([])
        print(USAGE)
        return 0
    if first == "--web":
        from cappv1.web.server import serve_cli

        return serve_cli(argv[1:])
    if first == "--batch":
        return batch(argv[1:])
    if first in ("--version", "-V"):
        print(VERSION)
        return 0
    if first in ("-h", "--help"):
        print(USAGE)
        return 0
    print(f"Unknown command: {first}\n\ncappv1 has one command. Type cappv1 to open it; everything else")
    print("(/run, /doctor, /models, /clean ...) is typed inside.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
