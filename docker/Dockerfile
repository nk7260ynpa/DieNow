# syntax=docker/dockerfile:1.7
# 攜手之戒關卡執行環境 Docker image.
# 以 Python 3.11-slim 為基底, 安裝 pyproject 相依, 並以非 root user 執行.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# 建立非 root 執行身份 (UID/GID 1001 避開常見系統帳號).
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --home-dir /app --shell /sbin/nologin app

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
RUN mkdir -p /app/logs \
    && chown -R app:app /app

USER app

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "ring_of_hands.cli", "run", "--config", "configs/default.yaml"]
