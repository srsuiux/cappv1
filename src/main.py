import argparse
import asyncio

from src.config import load_config
from src.pipeline import run, setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PPTX alt-text using a vision LLM via OpenRouter")
    parser.add_argument("--resume", action="store_true", help="only resume in_progress files")
    args = parser.parse_args()

    config = load_config()
    setup_logging(config.logs_dir)

    asyncio.run(run(config, resume_only=args.resume))


if __name__ == "__main__":
    main()
