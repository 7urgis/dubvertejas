#!/usr/bin/env bash
# setup.sh - Initial environment setup for Dubvertejas
set -e

echo "=== Setting up Dubvertejas ==="

# Check system packages
command -v ffmpeg >/dev/null 2>&1 || { echo >&2 "Error: ffmpeg is not installed. Run: sudo apt install ffmpeg"; exit 1; }
command -v mkvmerge >/dev/null 2>&1 || { echo >&2 "Error: mkvmerge is not installed. Run: sudo apt install mkvtoolnix"; exit 1; }

mkdir -p tools models/dbz_actor data/translations data/datasets output temp media

# Setup Applio if missing
if [ ! -d "tools/Applio" ]; then
    echo "Cloning Applio RVC engine..."
    git clone https://github.com/IAHispano/Applio.git tools/Applio
fi

# Setup Applio virtual environment
if [ ! -d "tools/Applio/.venv" ]; then
    echo "Setting up Python 3.11 virtual environment for Applio..."
    cd tools/Applio
    if command -v uv >/dev/null 2>&1; then
        uv venv --python 3.11 .venv
        uv pip install -r requirements.txt
        uv pip install edge-tts faster-whisper librosa soundfile
    else
        python3 -m venv .venv
        .venv/bin/pip install --upgrade pip
        .venv/bin/pip install -r requirements.txt
        .venv/bin/pip install edge-tts faster-whisper librosa soundfile
    fi
    .venv/bin/python core.py prerequisites
    cd ../..
fi

echo "=== Dubvertejas setup is ready! ==="
