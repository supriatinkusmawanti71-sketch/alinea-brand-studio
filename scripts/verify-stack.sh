#!/usr/bin/env sh

set -eu

EXPECTED_SERVICES="postgres redis minio api worker web"
PROXY_SERVICES="gateway nginx"
VERIFY_TIMEOUT_SECONDS="${VERIFY_TIMEOUT_SECONDS:-60}"

info() {
  printf '%s\n' "[verify] $1"
}

fail() {
  printf '%s\n' "[error] $1" >&2
  exit 1
}

env_value() {
  name="$1"
  default="$2"

  value="$(printenv "$name" 2>/dev/null || true)"
  if [ -n "$value" ]; then
    printf '%s' "$value"
    return
  fi

  if [ -f .env ]; then
    value="$(
      awk -F= -v key="$name" '
        $0 !~ /^[[:space:]]*#/ && $1 == key {
          sub(/^[^=]*=/, "")
          gsub(/^[[:space:]]+|[[:space:]]+$/, "")
          gsub(/^"|"$/, "")
          print
          exit
        }
      ' .env
    )"
    if [ -n "$value" ]; then
      printf '%s' "$value"
      return
    fi
  fi

  printf '%s' "$default"
}

GATEWAY_PORT="$(env_value GATEWAY_PORT 8080)"
WEB_PORT="$(env_value WEB_PORT 3000)"
API_PORT="$(env_value API_PORT 8000)"
MINIO_API_PORT="$(env_value MINIO_API_PORT 9000)"
MINIO_CONSOLE_PORT="$(env_value MINIO_CONSOLE_PORT 9001)"

check_url() {
  name="$1"
  url="$2"

  deadline=$(( $(date +%s) + VERIFY_TIMEOUT_SECONDS ))
  info "$name: $url"
  while [ "$(date +%s)" -le "$deadline" ]; do
    if curl --fail --silent --show-error --max-time 10 "$url" >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done

  fail "$name 未响应：$url"
}

check_service() {
  service="$1"
  deadline=$(( $(date +%s) + VERIFY_TIMEOUT_SECONDS ))

  while [ "$(date +%s)" -le "$deadline" ]; do
    container_id="$(docker compose ps -q "$service" 2>/dev/null || true)"
    if [ -n "$container_id" ]; then
      state="$(
        docker inspect \
          --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
          "$container_id"
      )"
      set -- $state
      status="${1:-unknown}"
      health="${2:-none}"

      if [ "$status" = "running" ] && { [ "$health" = "healthy" ] || [ "$health" = "none" ]; }; then
        info "$service: running${health:+ / $health}"
        return
      fi

      if [ "$health" = "unhealthy" ] || [ "$status" = "exited" ]; then
        break
      fi
    fi
    sleep 1
  done

  docker compose ps "$service" || true
  fail "$service 服务未在 ${VERIFY_TIMEOUT_SECONDS}s 内进入 healthy/running 状态"
}

check_proxy_service() {
  for service in $PROXY_SERVICES; do
    if [ -n "$(docker compose ps -q "$service" 2>/dev/null || true)" ]; then
      check_service "$service"
      return
    fi
  done

  fail "未找到反向代理服务，期望其中之一：$PROXY_SERVICES"
}

command -v docker >/dev/null 2>&1 || fail "Docker 未安装。"
command -v curl >/dev/null 2>&1 || fail "curl 未安装。"
docker info >/dev/null 2>&1 || fail "Docker 服务未运行，请先启动 Docker Desktop。"
docker compose version >/dev/null 2>&1 || fail "Docker Compose 不可用。"

info "Docker Compose 服务状态："
docker compose ps

for service in $EXPECTED_SERVICES; do
  check_service "$service"
done
check_proxy_service

check_url "gateway" "http://127.0.0.1:${GATEWAY_PORT}/health"
check_url "web" "http://127.0.0.1:${WEB_PORT}/api/health"
check_url "api" "http://127.0.0.1:${API_PORT}/api/v1/health/ready"
check_url "api docs" "http://127.0.0.1:${API_PORT}/api/docs"
check_url "minio live" "http://127.0.0.1:${MINIO_API_PORT}/minio/health/live"
check_url "minio console" "http://127.0.0.1:${MINIO_CONSOLE_PORT}/"
info "所有服务验收通过。"
