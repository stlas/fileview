#!/bin/bash
# FileView - Quick Install Script
set -e

echo "=== FileView Installer ==="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is required but not installed."
    exit 1
fi

# Check pip
if ! command -v pip3 &>/dev/null && ! python3 -m pip --version &>/dev/null 2>&1; then
    echo "ERROR: pip is required. Install with: apt install python3-pip"
    exit 1
fi

# Install dependencies
echo "Installing Python dependencies..."
pip3 install --quiet flask flask-cors markdown pygments 2>/dev/null || \
python3 -m pip install --quiet flask flask-cors markdown pygments

# Create config if not exists
if [ ! -f config.json ]; then
    echo "Creating config.json from example..."
    cp config.example.json config.json
    echo ""
    echo "IMPORTANT: Edit config.json to set your allowed_paths!"
    echo "  Example: \"allowed_paths\": [\"/srv/files\", \"/home/user/docs\"]"
    echo ""
fi

echo ""
echo "Installation complete!"
echo ""
echo "Start FileView:"
echo "  python3 fileview.py"
echo ""
echo "Then open http://localhost:$(python3 -c "import json; print(json.load(open('config.json')).get('port', 8080))" 2>/dev/null || echo 8080) in your browser."
