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
# 非 dry-run 模式會先於主機檢查:
# - `claude` CLI 是否可執行 (已安裝並位於 PATH).
# - 主機 `~/.claude/` 是否存在 (代表 `claude login` 已完成一次).
# 兩者任一失敗即 exit 1, 不啟動 container. dry-run 模式 (第一個參數
# 含 `--dry-run`) 會跳過上述檢查以保離線測試能力.
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

# 判斷 args 中是否帶 --dry-run 以決定是否跳過 CLI 前置檢查.
is_dry_run=false
for arg in "$@"; do
  if [[ "${arg}" == "--dry-run" ]]; then
    is_dry_run=true
    break
  fi
done

# 非 dry-run 模式下先檢查主機 `claude` CLI 與 ~/.claude 目錄.
if [[ "${is_dry_run}" == "false" ]]; then
  if ! command -v claude >/dev/null 2>&1; then
    echo "ERROR: 'claude' CLI 未安裝於主機." >&2
    echo "請先執行 'curl -fsSL https://claude.ai/install.sh | bash' 或" >&2
    echo "'npm install -g @anthropic-ai/claude-code' 安裝 Claude Code CLI." >&2
    exit 1
  fi
  if [[ ! -d "${HOME}/.claude" ]]; then
    echo "ERROR: ~/.claude 不存在." >&2
    echo "請先於主機執行 'claude login' 建立 OAuth session." >&2
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
