#!/bin/bash

CONFIG_DIR="./config"
KEYMAP_DRAWER_CONFIG="./keymap_drawer.config.yaml"
KEYMAP_FILE="${CONFIG_DIR}/eyelash_sofle.keymap"
OUTPUT_DIR="./keymap-drawer"
YAML_OUTPUT="${OUTPUT_DIR}/eyelash_sofle.yaml"
JSON_CONFIG="${CONFIG_DIR}/eyelash_sofle.json"
SVG_OUTPUT="${OUTPUT_DIR}/eyelash_sofle.svg"

# Pick the available runner: prefer a local `keymap` binary, fallback to `uvx`.
if command -v keymap >/dev/null 2>&1; then
    KEYMAP_CMD=(keymap)
elif command -v uvx >/dev/null 2>&1; then
    KEYMAP_CMD=(uvx --from keymap-drawer keymap)
else
    echo "Error: neither 'keymap' nor 'uvx' is installed."
    echo "Install with one of:"
    echo "  pipx install keymap-drawer"
    echo "  pip install keymap-drawer"
    echo "  brew install uv   # then this script can use uvx"
    exit 1
fi

mkdir -p "${OUTPUT_DIR}"

"${KEYMAP_CMD[@]}" -c "${KEYMAP_DRAWER_CONFIG}" parse -z "${KEYMAP_FILE}" > "${YAML_OUTPUT}"
if [ $? -ne 0 ]; then
    echo "Error: Failed to parse keymap file"
    exit 1
fi

"${KEYMAP_CMD[@]}" -c "${KEYMAP_DRAWER_CONFIG}" draw "${YAML_OUTPUT}" -j "${JSON_CONFIG}" > "${SVG_OUTPUT}"
if [ $? -ne 0 ]; then
    echo "Error: Failed to draw keymap"
    exit 1
fi

# Inject a rich legend (icons + colors + key-anatomy diagram) into the SVG.
# We can't use keymap-drawer's footer_text for this because <text> can't contain
# <use> icon references in SVG.
python3 ./generate_legend.py "${SVG_OUTPUT}"

echo "Keymap successfully generated at ${SVG_OUTPUT}"