#!/usr/bin/env bash
#
# 建立攜手之戒關卡的 Docker image.
#
# 用法:
#   ./docker/build.sh
#
# 遵循 Google Shell Style Guide.

set -o errexit
set -o nounset
set -o pipefail

# 解析 repo 根目錄 (script 相對路徑), 避免呼叫者要先 cd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly REPO_ROOT

readonly IMAGE_TAG="${IMAGE_TAG:-ring-of-hands:local}"

main() {
  echo "[build.sh] 以 ${REPO_ROOT} 為 build context, 建立 image ${IMAGE_TAG}."
  docker build \
    --tag "${IMAGE_TAG}" \
    --file "${SCRIPT_DIR}/Dockerfile" \
    "${REPO_ROOT}"
  echo "[build.sh] image ${IMAGE_TAG} 建立完成."
}

main "$@"
