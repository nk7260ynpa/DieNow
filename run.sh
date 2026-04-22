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
# 非 dry-run 模式會先於主機檢查 `.env` 是否包含有值的
# CLAUDE_CODE_OAUTH_TOKEN 或 ANTHROPIC_API_KEY. 缺失即 exit 1,
# 不啟動 container. dry-run 模式 (第一個參數含 `--dry-run`) 會
# 跳過上述檢查以保離線測試能力.
#
# 容器內已自帶 Claude Code CLI (Dockerfile 層安裝), 認證靠 env_file
# 注入的 OAuth token; 因此主機不再需要安裝 claude 或執行 claude login
# (2026-04-18 起, 原 Keychain-based 方案無法跨容器).
#
# 遵循 Google Shell Style Guide.

set -o errexit
set -o nounset
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly COMPOSE_FILE="${SCRIPT_DIR}/docker/docker-compose.yaml"
readonly ENV_FILE="${SCRIPT_DIR}/.env"

# 確保 logs/ 目錄存在, 避免 compose 掛載時建立為 root-owned 目錄.
mkdir -p "${SCRIPT_DIR}/logs"

# 判斷 args 中是否帶 --dry-run 以決定是否跳過認證前置檢查.
is_dry_run=false
for arg in "$@"; do
  if [[ "${arg}" == "--dry-run" ]]; then
    is_dry_run=true
    break
  fi
done

# 非 dry-run 模式下檢查 `.env` 是否包含有值的 OAuth token 或 API key.
# (僅在主機預先攔截, 若使用者直接呼叫容器仍會由 scenario_runner
# 再做一次驗證.)
if [[ "${is_dry_run}" == "false" ]]; then
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: ${ENV_FILE} 不存在." >&2
    echo "請複製 .env.example 為 .env 並填入 CLAUDE_CODE_OAUTH_TOKEN." >&2
    echo "token 由主機執行 'claude setup-token' 取得." >&2
    exit 1
  fi
  # 擷取非註解的變數值; 支援 KEY=value 與 KEY="value" / KEY='value'.
  oauth_token="$(
    sed -n 's/^[[:space:]]*CLAUDE_CODE_OAUTH_TOKEN[[:space:]]*=[[:space:]]*\(.*\)$/\1/p' \
      "${ENV_FILE}" | head -n 1 | tr -d '"' | tr -d "'" | xargs || true
  )"
  api_key="$(
    sed -n 's/^[[:space:]]*ANTHROPIC_API_KEY[[:space:]]*=[[:space:]]*\(.*\)$/\1/p' \
      "${ENV_FILE}" | head -n 1 | tr -d '"' | tr -d "'" | xargs || true
  )"
  if [[ -z "${oauth_token}" && -z "${api_key}" ]]; then
    echo "ERROR: .env 缺少 CLAUDE_CODE_OAUTH_TOKEN (或 ANTHROPIC_API_KEY)." >&2
    echo "請於主機執行 'claude setup-token' 產生 long-lived OAuth token," >&2
    echo "並寫入 ${ENV_FILE}:" >&2
    echo "  CLAUDE_CODE_OAUTH_TOKEN=<token>" >&2
    exit 1
  fi
fi

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
