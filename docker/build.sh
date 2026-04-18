#!/usr/bin/env bash
#
# 建立攜手之戒關卡的 Docker image.
#
# 用法:
#   ./docker/build.sh
#
# 會自動帶入 APP_UID / APP_GID build-arg, 以便容器內 `app` user 與主機
# 擁有者對齊, 共享 bind-mounted ~/.claude 目錄讀權.
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
  local host_uid
  local host_gid
  host_uid="$(id -u)"
  host_gid="$(id -g)"
  echo "[build.sh] 以 ${REPO_ROOT} 為 build context, 建立 image ${IMAGE_TAG}"
  echo "[build.sh] APP_UID=${host_uid} APP_GID=${host_gid} (對齊主機使用者以共享 ~/.claude)."
  docker build \
    --tag "${IMAGE_TAG}" \
    --file "${SCRIPT_DIR}/Dockerfile" \
    --build-arg "APP_UID=${host_uid}" \
    --build-arg "APP_GID=${host_gid}" \
    "${REPO_ROOT}"
  echo "[build.sh] image ${IMAGE_TAG} 建立完成."
}

main "$@"
