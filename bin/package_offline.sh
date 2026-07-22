#!/bin/bash

# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# ============================================================================
# package_offline.sh - Build offline deployment package
#
# Runs on the ONLINE machine. Downloads target-architecture wheel packages
# and bundles the project into a self-contained tar.gz for air-gapped deploy.
#
# Usage:
#   ./bin/package_offline.sh [--arch=x86_64|aarch64] [--python-version=3.12]
#                            [--version=1.0.0] [--output=dist]
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Defaults
TARGET_ARCH="$(uname -m)"
PYTHON_VERSION="3.12"
VERSION="1.0.0"
OUTPUT_DIR="${ROOT_DIR}/dist"

usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --arch=ARCH             Target architecture: x86_64 or aarch64 (default: current)"
    echo "  --python-version=VER    Target Python version (default: 3.12)"
    echo "  --version=VER           Package version label (default: 1.0.0)"
    echo "  --output=DIR            Output directory (default: ./dist)"
    echo "  -h, --help              Show this help"
    exit 0
}

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --arch=*) TARGET_ARCH="${arg#*=}" ;;
        --python-version=*) PYTHON_VERSION="${arg#*=}" ;;
        --version=*) VERSION="${arg#*=}" ;;
        --output=*) OUTPUT_DIR="${arg#*=}" ;;
        -h|--help) usage ;;
        *) echo -e "${RED}Unknown option: $arg${NC}"; usage ;;
    esac
done

# Validate architecture
if [[ "$TARGET_ARCH" != "x86_64" && "$TARGET_ARCH" != "aarch64" ]]; then
    echo -e "${RED}Error: Unsupported architecture '$TARGET_ARCH'. Use x86_64 or aarch64.${NC}"
    exit 1
fi

# Build list of pip platform tags (newer packages like cryptography require manylinux_2_28+)
PIP_PLATFORMS=()
case "$TARGET_ARCH" in
    x86_64)
        PIP_PLATFORMS+=("manylinux_2_34_x86_64")
        PIP_PLATFORMS+=("manylinux_2_28_x86_64")
        PIP_PLATFORMS+=("manylinux_2_17_x86_64")
        PIP_PLATFORMS+=("manylinux2014_x86_64")
        ;;
    aarch64)
        PIP_PLATFORMS+=("manylinux_2_34_aarch64")
        PIP_PLATFORMS+=("manylinux_2_28_aarch64")
        PIP_PLATFORMS+=("manylinux_2_17_aarch64")
        PIP_PLATFORMS+=("manylinux2014_aarch64")
        ;;
esac

PKG_NAME="registry-center-${VERSION}-linux-${TARGET_ARCH}"
BUILD_DIR="${OUTPUT_DIR}/build/${PKG_NAME}"
WHEELS_DIR="${BUILD_DIR}/wheels"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} Registry Center Offline Packager${NC}"
echo -e "${GREEN}============================================${NC}"
echo "  Version:        ${VERSION}"
echo "  Target arch:    ${TARGET_ARCH}"
echo "  Python version: ${PYTHON_VERSION}"
echo "  Pip platforms:  ${PIP_PLATFORMS[*]}"
echo "  Output:         ${OUTPUT_DIR}"
echo ""

# --- Step 1: Prepare build directory ---
echo -e "${GREEN}[1/5] Preparing build directory...${NC}"
rm -rf "${OUTPUT_DIR}/build"
mkdir -p "$BUILD_DIR"

# --- Step 2: Copy project source ---
echo -e "${GREEN}[2/5] Copying project source...${NC}"

# Copy source directories
cp -r "${ROOT_DIR}/agent_registry" "${BUILD_DIR}/"
cp -r "${ROOT_DIR}/common" "${BUILD_DIR}/"
cp -r "${ROOT_DIR}/etc" "${BUILD_DIR}/"
cp -r "${ROOT_DIR}/bin" "${BUILD_DIR}/"
cp "${ROOT_DIR}/requirements.txt" "${BUILD_DIR}/"

# Remove unnecessary files from copied source
find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
rm -rf "${BUILD_DIR}/bin/package_offline.sh"

# Create empty runtime directories
mkdir -p "${BUILD_DIR}/log" "${BUILD_DIR}/run" "${BUILD_DIR}/data"

echo "  Source copied."

# --- Step 3: Download wheel packages ---
echo -e "${GREEN}[3/5] Downloading wheel packages for ${TARGET_ARCH}...${NC}"
mkdir -p "$WHEELS_DIR"

# Build --platform flags for pip download
PLATFORM_FLAGS=()
for p in "${PIP_PLATFORMS[@]}"; do
    PLATFORM_FLAGS+=("--platform" "$p")
done

# First pass: download binary wheels for target platform (all manylinux variants)
pip download \
    -r "${ROOT_DIR}/requirements.txt" \
    "${PLATFORM_FLAGS[@]}" \
    --python-version "$PYTHON_VERSION" \
    --only-binary=:all: \
    --dest "$WHEELS_DIR" \
    2>&1 | sed 's/^/  /'

# Second pass: download pure-Python packages (platform 'any')
pip download \
    -r "${ROOT_DIR}/requirements.txt" \
    --platform any \
    --python-version "$PYTHON_VERSION" \
    --only-binary=:all: \
    --dest "$WHEELS_DIR" \
    2>&1 | sed 's/^/  /' || true

# Verify wheels were downloaded
WHEEL_COUNT=$(find "$WHEELS_DIR" -name "*.whl" | wc -l)
if [ "$WHEEL_COUNT" -eq 0 ]; then
    echo -e "${RED}Error: No wheel packages downloaded. Check network and platform settings.${NC}"
    exit 1
fi
echo "  Downloaded ${WHEEL_COUNT} wheel packages."

# --- Step 4: Generate README_OFFLINE.txt ---
echo -e "${GREEN}[4/5] Generating README_OFFLINE.txt...${NC}"
cat > "${BUILD_DIR}/README_OFFLINE.txt" <<EOF
==========================================================
 Registry Center v${VERSION} - Offline Deployment Package
 Target: linux/${TARGET_ARCH} | Python ${PYTHON_VERSION}
==========================================================

Prerequisites:
  - Linux ${TARGET_ARCH}
  - Python ${PYTHON_VERSION} (pre-installed)
  - No internet connection required

Quick Start:
  1. Extract the package:
     tar -xzf ${PKG_NAME}.tar.gz

  2. Enter the directory:
     cd ${PKG_NAME}

  3. Run offline setup (creates venv, installs deps, configures):
     chmod +x bin/*.sh
     ./bin/setup_offline.sh

     To skip interactive configuration:
     ./bin/setup_offline.sh --skip-init

  4. Start the service:
     source venv/bin/activate
     ./bin/start.sh

  5. Stop the service:
     ./bin/stop.sh

Configuration (can be re-run anytime):
  ./venv/bin/python -m agent_registry.init

  Or manually edit:
  - etc/conf/server.conf       (IP, port, TLS, signing)
  - etc/conf/persistence.conf  (storage mode: file/postgresql)
  - common/config/llm_config.json (LLM API key, optional)

Systemd Service (optional, requires root):
  sudo ./bin/install_service.sh install
  sudo systemctl start registry-center

Directory Layout:
  agent_registry/   Application source code
  common/           Shared modules and config templates
  etc/conf/         Configuration files
  etc/systemd/      Systemd service templates
  bin/              Operational scripts
  wheels/           Pre-downloaded Python wheel packages
  venv/             Virtual environment (created by setup_offline.sh)
  log/              Runtime logs
  run/              Runtime PID/socket files
  data/             File-based storage data
EOF

echo "  README generated."

# --- Step 5: Create tar.gz archive ---
echo -e "${GREEN}[5/5] Creating archive...${NC}"
mkdir -p "$OUTPUT_DIR"
tar -czf "${OUTPUT_DIR}/${PKG_NAME}.tar.gz" -C "${OUTPUT_DIR}/build" "$PKG_NAME"

# Cleanup build directory
rm -rf "${OUTPUT_DIR}/build"

ARCHIVE_SIZE=$(du -h "${OUTPUT_DIR}/${PKG_NAME}.tar.gz" | cut -f1)

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} Package built successfully!${NC}"
echo -e "${GREEN}============================================${NC}"
echo "  File: ${OUTPUT_DIR}/${PKG_NAME}.tar.gz"
echo "  Size: ${ARCHIVE_SIZE}"
echo ""
echo "  Transfer this file to the offline machine, then:"
echo "    tar -xzf ${PKG_NAME}.tar.gz"
echo "    cd ${PKG_NAME}"
echo "    ./bin/setup_offline.sh"
echo "    source venv/bin/activate"
echo "    ./bin/start.sh"
echo -e "${GREEN}============================================${NC}"