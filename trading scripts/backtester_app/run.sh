#!/usr/bin/env bash
set -e

# Change directory to app root
cd "$(dirname "$0")"

echo "========================================================="
echo "  AlphaDCA - Multi-Market Investment Backtester"
echo "  US & Indian Equities, Indices, ETFs & Gold"
echo "========================================================="

# Activate conda environment mt
if command -v conda &> /dev/null; then
    eval "$(conda shell.bash hook)"
    conda activate mt
    echo "✓ Conda environment 'mt' activated."
else
    echo "⚠️  Conda command not found. Using default python environment."
fi

# Check requirements
python -c "import fastapi, uvicorn, yfinance, scipy, pandas" 2>/dev/null || {
    echo "Instal missing dependencies..."
    exit
}

echo "Starting server on http://127.0.0.1:8000 ..."
echo "Press Ctrl+C to stop."
exec uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
