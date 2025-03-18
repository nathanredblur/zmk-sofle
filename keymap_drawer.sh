#!/bin/bash

# Define file paths as variables
CONFIG_DIR="./config"
KEYMAP_DRAWER_CONFIG="./keymap_drawer.config.yaml"
KEYMAP_FILE="${CONFIG_DIR}/eyelash_sofle.keymap"
OUTPUT_DIR="./keymap-drawer"
YAML_OUTPUT="${OUTPUT_DIR}/eyelash_sofle.yaml"
JSON_CONFIG="${CONFIG_DIR}/eyelash_sofle.json"
SVG_OUTPUT="${OUTPUT_DIR}/eyelash_sofle.svg"

# Create output directory if it doesn't exist
mkdir -p "${OUTPUT_DIR}"

# Step 1: Parse the keymap file
keymap -c "${KEYMAP_DRAWER_CONFIG}" parse -z "${KEYMAP_FILE}" > "${YAML_OUTPUT}"

# Check if the parse command succeeded
if [ $? -ne 0 ]; then
    echo "Error: Failed to parse keymap file"
    exit 1
fi

# Step 2: Draw the keymap
keymap -c "${KEYMAP_DRAWER_CONFIG}" draw "${YAML_OUTPUT}" -j "${JSON_CONFIG}" > "${SVG_OUTPUT}"

# Check if the draw command succeeded
if [ $? -ne 0 ]; then
    echo "Error: Failed to draw keymap"
    exit 1
fi

echo "Keymap successfully generated at ${SVG_OUTPUT}"