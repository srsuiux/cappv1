#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "No .venv found — creating one and installing dependencies..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
else
    source .venv/bin/activate
    python -c "import rich, prompt_toolkit" 2>/dev/null || pip install -q -r requirements.txt
fi

python -m src.main "$@"
