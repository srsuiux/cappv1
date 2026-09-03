import argparse
import asyncio

from src.config import load_config
from src.pipeline import run, setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PPTX alt-text using Claude via OpenRouter")
    parser.add_argument("--file", help="process a single file from input/", default=None)
    parser.add_argument("--resume", action="store_true", help="only resume in_progress files")
    args = parser.parse_args()

    config = load_config()
    setup_logging(config.logs_dir)

    asyncio.run(run(config, only_file=args.file, resume_only=args.resume))


if __name__ == "__main__":
    main()
