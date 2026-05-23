#!/usr/bin/env bash
# Integration test for hippius-skill CLI.
# Creates a bucket, uploads a file, downloads it, verifies content, and cleans up.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Config
BUCKET_NAME="itest-$(date +%s)-$$"
TEST_FILE="$(mktemp /tmp/hippius-itest-upload-XXXXXX.txt)"
DOWNLOAD_FILE="$(mktemp /tmp/hippius-itest-download-XXXXXX.txt)"
REMOTE_PATH="test/hello.txt"

cleanup() {
    local exit_code=$?
    echo "--- Cleaning up ---"

    # Delete remote file if bucket exists locally
    if hippius-skill config list-buckets 2>/dev/null | grep -qx "${BUCKET_NAME}"; then
        echo "Deleting remote file ${REMOTE_PATH}..."
        hippius-skill delete "${BUCKET_NAME}" "${REMOTE_PATH}" || true

        echo "Removing bucket '${BUCKET_NAME}' from local config..."
        hippius-skill config remove-bucket "${BUCKET_NAME}" || true
    fi

    # Remove temp files
    rm -f "${TEST_FILE}" "${DOWNLOAD_FILE}"

    if [[ $exit_code -eq 0 ]]; then
        echo "=== Integration test PASSED ==="
    else
        echo "=== Integration test FAILED (exit code: $exit_code) ==="
    fi
    exit $exit_code
}
trap cleanup EXIT

echo "=== Hippius Skill Integration Test ==="
echo "Bucket: ${BUCKET_NAME}"
echo ""

# Generate test content
dd if=/dev/urandom bs=1K count=16 2>/dev/null | base64 > "${TEST_FILE}"
ORIGINAL_SHA=$(sha256sum "${TEST_FILE}" | awk '{print $1}')
echo "Test file: ${TEST_FILE} ($(wc -c < "${TEST_FILE}") bytes, sha256=${ORIGINAL_SHA})"
echo ""

# Step 1: Create bucket
echo "--- Step 1: Create bucket ---"
hippius-skill config add-bucket "${BUCKET_NAME}"
echo ""

# Step 2: Upload file
echo "--- Step 2: Upload file ---"
hippius-skill upload "${BUCKET_NAME}" "${TEST_FILE}" "${REMOTE_PATH}"
echo ""

# Step 3: List files to confirm
echo "--- Step 3: List files ---"
hippius-skill list "${BUCKET_NAME}" --prefix "test/"
echo ""

# Step 4: Download file
echo "--- Step 4: Download file ---"
hippius-skill download "${BUCKET_NAME}" "${REMOTE_PATH}" "${DOWNLOAD_FILE}"
echo ""

# Step 5: Verify content
echo "--- Step 5: Verify content ---"
DOWNLOAD_SHA=$(sha256sum "${DOWNLOAD_FILE}" | awk '{print $1}')
if [[ "${ORIGINAL_SHA}" != "${DOWNLOAD_SHA}" ]]; then
    echo "ERROR: SHA-256 mismatch!"
    echo "  Original: ${ORIGINAL_SHA}"
    echo "  Download: ${DOWNLOAD_SHA}"
    exit 1
fi
echo "SHA-256 match: ${ORIGINAL_SHA}"
echo ""

echo "All steps completed successfully."
