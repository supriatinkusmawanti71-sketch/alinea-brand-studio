#!/usr/bin/env sh
set -eu

missing=0

for command in git docker; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "缺少命令: $command"
    missing=1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose 不可用，请安装或启动 Docker Desktop。"
  missing=1
fi

if [ "$missing" -ne 0 ]; then
  exit 1
fi

echo "Git: $(git --version)"
echo "Docker: $(docker --version)"
echo "Compose: $(docker compose version)"
echo "共同开发环境检查通过。"
