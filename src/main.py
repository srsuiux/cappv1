import argparse
import asyncio
import sys

from src.config import load_config
from src.pipeline import run, setup_logging


def main() -> None:
    if sys.argv[1:2] == ["--session"]:
        from src.tui.session import main as session_main

        sys.exit(session_main(sys.argv[2:]))

    parser = argparse.ArgumentParser(description="Generate PPTX alt-text using a vision LLM (OpenRouter, OpenAI, Anthropic, or local Ollama)")
    parser.add_argument("--resume", action="store_true", help="only resume in_progress files")
    args = parser.parse_args()

    config = load_config()
    setup_logging(config.logs_dir)

    asyncio.run(run(config, resume_only=args.resume))


if __name__ == "__main__":
    main()
