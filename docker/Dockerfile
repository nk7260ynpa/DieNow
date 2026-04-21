# syntax=docker/dockerfile:1.7
# 攜手之戒關卡執行環境 Docker image.
# 以 Python 3.11-slim 為基底, 安裝 pyproject 相依與 Claude Code CLI,
# 並以非 root user 執行. 容器內的 `claude` 以環境變數
# `CLAUDE_CODE_OAUTH_TOKEN` (由 docker-compose 的 env_file 從 `.env`
# 注入; 以 `claude setup-token` 取得) 承繼 Max 訂閱身份;
# 不再以 bind mount `~/.claude` 的方式承繼 OAuth session, 因 macOS
# Keychain 儲存的 token 無法跨容器讀取.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# 使用者由 build-arg 指定, 方便與主機 ~/.claude 擁有者對齊以保有讀權.
ARG APP_UID=1001
ARG APP_GID=1001

# 安裝 Node.js (供 @anthropic-ai/claude-code 使用) 與 curl / ca-certificates.
# Node 20 採用 NodeSource 發行倉庫, 以避免 Debian bookworm 預設過舊.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Claude Code CLI (官方 npm package).
# 該 package 提供 `claude` 可執行檔, 支援 Max 訂閱 OAuth 的 `claude login`
# 與非互動 `claude -p "..." --output-format stream-json` 模式.
RUN npm install -g @anthropic-ai/claude-code \
    && claude --version

# 建立非 root 執行身份 (UID/GID 由 build-arg 控制; 預設 1001).
# 若目標 UID/GID 已存在於 base image (例如 macOS 主機的 GID 20 = staff 衝突
# Debian 13 的 staff), 直接重用, 並以 `app` 名稱建立 alias group/user.
RUN set -eux; \
    if getent group "${APP_GID}" >/dev/null; then \
        existing_group="$(getent group "${APP_GID}" | cut -d: -f1)"; \
        groupadd --non-unique --gid "${APP_GID}" app || \
            echo "[Dockerfile] 重用現有 group ${existing_group} 作為 app 主 gid."; \
    else \
        groupadd --system --gid "${APP_GID}" app; \
    fi; \
    if getent passwd "${APP_UID}" >/dev/null; then \
        existing_user="$(getent passwd "${APP_UID}" | cut -d: -f1)"; \
        useradd --non-unique --uid "${APP_UID}" --gid "${APP_GID}" \
            --home-dir /home/app --shell /sbin/nologin --create-home app || \
            echo "[Dockerfile] 重用現有 user ${existing_user} 作為 app uid."; \
    else \
        useradd --system --uid "${APP_UID}" --gid "${APP_GID}" \
            --home-dir /home/app --shell /sbin/nologin --create-home app; \
    fi

WORKDIR /app

# 先複製僅 pyproject 與 README, 讓依賴安裝層可以被 cache.
COPY pyproject.toml README.md ./
COPY src/ ./src/

# 安裝套件 (含 dev extras 以便在 container 內執行 pytest).
RUN pip install --upgrade pip \
    && pip install ".[dev]"

# 再複製其他必要檔案; .dockerignore 會排除 logs / .git / 測試 artefact 等.
COPY configs/ ./configs/
COPY tests/ ./tests/
COPY run.sh ./run.sh

# logs 目錄需允許非 root 寫入; 由 docker-compose 掛載宿主機 logs/ 覆蓋.
# 認證以 `CLAUDE_CODE_OAUTH_TOKEN` env 為主 (見檔頭註解); 保留
# `/home/app/.claude` 空目錄僅為 CLI 可能寫入 cache/log 之便, 不再
# 承擔認證載體角色.
RUN mkdir -p /app/logs /home/app/.claude \
    && chown -R app:app /app /home/app

USER app

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "ring_of_hands.cli", "run", "--config", "configs/default.yaml"]
