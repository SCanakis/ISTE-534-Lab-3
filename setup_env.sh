#!/usr/bin/env bash
# Sets up the Python environment for the Lab 3 ETL scripts.
# Usage: ./setup.sh
set -euo pipefail

cd "$(dirname "$0")"

# 1. Install uv if it's missing
if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# 2. Create the virtual environment
if [ ! -d .venv ]; then
    uv venv --python 3.12
fi

# 3. Install the libraries
uv pip install -r requirements.txt

# 4. Create .env for the MySQL password (never committed)
if [ ! -f .env ]; then
    cp .env.example .env
    echo
    echo "Created .env -- open it and set PASSWORD to your MySQL password."
fi

echo
echo "Setup done. Run a script with:  uv run <script>.py"