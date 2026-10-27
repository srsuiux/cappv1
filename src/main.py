import argparse
import asyncio
import sys
from dataclasses import replace

from src.config import load_config
from src.pipeline import run, setup_logging


def main() -> None:
    if sys.argv[1:2] == ["--session"]:
        from src.tui.session import main as session_main

        sys.exit(session_main(sys.argv[2:]))

    if sys.argv[1:2] == ["--web"]:
        from src.web.server import serve_cli

        sys.exit(serve_cli(sys.argv[2:]))

    parser = argparse.ArgumentParser(description="Generate PPTX alt-text using a vision LLM (OpenRouter, OpenAI, Anthropic, or local Ollama)")
    parser.add_argument("--resume", action="store_true", help="only resume in_progress files")
    parser.add_argument("--force", action="store_true", help="redo everything and replace alt text the author already wrote")
    args = parser.parse_args()

    config = load_config()
    if args.force:
        config = replace(config, overwrite_existing=True)
    setup_logging(config.logs_dir)

    asyncio.run(run(config, resume_only=args.resume, force=args.force))


if __name__ == "__main__":
    main()
