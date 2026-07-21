#!/usr/bin/env sh

set -eu

KEEP_STACK="${KEEP_STACK:-0}"
E2E_PYTHON="${E2E_PYTHON:-}"

info() {
  printf '%s\n' "[e2e] $1"
}

fail() {
  printf '%s\n' "[error] $1" >&2
  exit 1
}

cleanup() {
  if [ "$KEEP_STACK" = "1" ]; then
    info "KEEP_STACK=1，保留 Docker Compose 服务运行。"
    return
  fi

  info "停止 Docker Compose 服务。"
  docker compose stop >/dev/null
}

command -v docker >/dev/null 2>&1 || fail "Docker 未安装。"
docker info >/dev/null 2>&1 || fail "Docker 服务未运行，请先启动 Docker Desktop。"
docker compose version >/dev/null 2>&1 || fail "Docker Compose 不可用。"

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    info "已从 .env.example 创建 .env。"
  else
    fail "缺少 .env，且未找到 .env.example。"
  fi
fi

if [ -z "$E2E_PYTHON" ]; then
  if [ -x .venv/bin/python ]; then
    E2E_PYTHON=".venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    E2E_PYTHON="python3"
  else
    fail "未找到 Python。"
  fi
fi

trap cleanup EXIT INT TERM

info "构建并启动 Docker Compose 服务。"
docker compose up --build -d

info "运行服务验收脚本。"
./scripts/verify-stack.sh

info "运行 E2E smoke 测试。"
BRAND_STUDIO_RUN_E2E=1 "$E2E_PYTHON" -m pytest tests/e2e

info "E2E smoke 测试通过。"
