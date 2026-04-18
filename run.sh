#!/usr/bin/env bash
#
# 以 Docker container 執行攜手之戒關卡或相關指令.
#
# 用法:
#   ./run.sh                  # 以預設 config 執行關卡
#   ./run.sh --dry-run        # dry-run 模式 (不呼叫真實 LLM)
#   ./run.sh pytest           # 於容器內跑測試
#   ./run.sh python -m ...    # 透傳任意指令
#
# 遵循 Google Shell Style Guide.

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly COMPOSE_FILE="${SCRIPT_DIR}/docker/docker-compose.yaml"

# 確保 logs/ 目錄存在, 避免 compose 掛載時建立為 root-owned 目錄.
mkdir -p "${SCRIPT_DIR}/logs"

# 若未提供指令, 執行預設關卡; 若第一個參數看起來像 CLI 旗標 (以 `-` 起頭),
# 則假設使用者想跑預設 CLI 入口並附加旗標 (例: `./run.sh --dry-run`).
if [[ "$#" -eq 0 ]]; then
  exec docker compose --file "${COMPOSE_FILE}" run --rm app \
    python -m ring_of_hands.cli run --config configs/default.yaml
fi

if [[ "${1#-}" != "${1}" ]]; then
  exec docker compose --file "${COMPOSE_FILE}" run --rm app \
    python -m ring_of_hands.cli run --config configs/default.yaml "$@"
fi

exec docker compose --file "${COMPOSE_FILE}" run --rm app "$@"
