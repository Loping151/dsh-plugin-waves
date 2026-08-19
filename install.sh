#!/usr/bin/env bash
# 一键安装: 缺的先自己装, 再建虚拟环境、拉插件、注册进 dsh。
# 可选迁入既有部署: ./install.sh --src /path/to/gsuid_core/data
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="$ROOT/service"
PROFILE="${DSH_PROFILE:-web}"
# 计算内核按 CPython 版本分发, 仅这些版本有对应包
SUPPORTED=(3.13 3.12 3.11 3.10)
PYTHON_VERSION="${PYTHON_VERSION:-3.13}"

# 由插件在首次启动时调用: 只准备环境, 不碰 dsh 自身
ENV_ONLY=0
if [ "${1:-}" = "--env-only" ]; then ENV_ONLY=1; shift; fi

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[31m%s\033[0m\n' "$1" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

refresh_path() {
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
}

# 非交互: 有密码的 sudo 会卡住首次启动, 只在 root / sudo -n 可用时装
pkg_install() {
  if have brew; then
    brew install "$@"
    return $?
  fi
  local sudo=()
  if [ "$(id -u)" -ne 0 ]; then
    have sudo || return 1
    sudo -n true >/dev/null 2>&1 || return 1
    sudo=(sudo -n)
  fi
  if have apt-get; then
    DEBIAN_FRONTEND=noninteractive "${sudo[@]}" apt-get update -qq
    DEBIAN_FRONTEND=noninteractive "${sudo[@]}" apt-get install -y "$@"
  elif have dnf; then
    "${sudo[@]}" dnf install -y "$@"
  elif have yum; then
    "${sudo[@]}" yum install -y "$@"
  elif have pacman; then
    "${sudo[@]}" pacman -Sy --noconfirm "$@"
  elif have zypper; then
    "${sudo[@]}" zypper --non-interactive install "$@"
  elif have apk; then
    "${sudo[@]}" apk add --no-cache "$@"
  else
    return 1
  fi
}

printf '%s\n' "${SUPPORTED[@]}" | grep -qx "$PYTHON_VERSION" \
  || fail "Python $PYTHON_VERSION 不受支持, 可选: ${SUPPORTED[*]}"

refresh_path

# curl/wget: 装 uv 用
if ! have curl && ! have wget; then
  step "安装 curl"
  pkg_install curl || fail "缺少 curl/wget, 自动安装失败, 请先装其中一个"
fi

if ! have uv; then
  step "安装 uv"
  if have curl; then
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || true
  else
    wget -qO- https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || true
  fi
  refresh_path
  if ! have uv && have python3; then
    python3 -m pip install --user -q uv >/dev/null 2>&1 || true
    refresh_path
  fi
fi
have uv || fail "缺少 uv 且自动安装失败, 请手工装: curl -LsSf https://astral.sh/uv/install.sh | sh"

if ! have git; then
  step "安装 git"
  pkg_install git || fail "缺少 git 且自动安装失败, 请用系统包管理器安装(apt/dnf/brew install git)"
fi

if [ "$ENV_ONLY" != "1" ] && ! have dsh; then
  if have npm; then
    step "安装 dsh (npm -g @deepseek-ai/dsh)"
    npm install -g @deepseek-ai/dsh || true
    refresh_path
  fi
  have dsh || fail "缺少 dsh, 请先安装 DeepSeek Harness: npm i -g @deepseek-ai/dsh"
fi

step "准备 Python $PYTHON_VERSION"
# 系统没有对应版本时, uv 直接拉官方构建, 不必先装发行版 Python
uv python install "$PYTHON_VERSION" >/dev/null || true

step "创建虚拟环境 (Python $PYTHON_VERSION)"
cd "$SERVICE"
if [ ! -x .venv/bin/python ]; then
  uv venv --python "$PYTHON_VERSION" .venv
fi
ACTUAL="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
printf '%s\n' "${SUPPORTED[@]}" | grep -qx "$ACTUAL" \
  || fail "虚拟环境是 Python $ACTUAL, 不在支持范围; 删掉 service/.venv 重跑"

step "安装依赖"
uv pip install --python .venv/bin/python -q -r pyproject.toml
.venv/bin/python - <<'PY'
import importlib.util as u, sys
need = ("cv2", "cryptography", "fastapi", "sqlmodel", "PIL", "jinja2", "lxml", "msgspec")
missing = [n for n in need if u.find_spec(n) is None]
sys.exit("依赖缺失: " + ", ".join(missing)) if missing else print("依赖自检通过")
PY

step "拉取插件"
.venv/bin/python tools/update_plugins.py

step "初始化数据目录"
.venv/bin/python tools/migrate.py "$@"

if [ "$ENV_ONLY" = "1" ]; then
  echo
  echo "环境就绪。"
  exit 0
fi

step "注册进 dsh profile: $PROFILE"
dsh plugin --profile "$PROFILE" add "file:$ROOT" >/dev/null
# 加载器按自身位置解析裸包名, 这里补一条链接
DSH_NM="$(dirname "$(dirname "$(readlink -f "$(command -v dsh)")")")/node_modules"
PROFILE_PKG="${DSH_HOME:-$HOME/.dsh}/profiles/$PROFILE/node_modules/dsh-plugin-waves"
if [ -d "$DSH_NM" ] && [ -d "$PROFILE_PKG" ]; then
  ln -sfn "$PROFILE_PKG" "$DSH_NM/dsh-plugin-waves"
fi
NODE_MAJOR="$(node -v 2>/dev/null | sed 's/^v\([0-9]*\).*/\1/')"
[ -n "$NODE_MAJOR" ] && [ "$NODE_MAJOR" -lt 22 ] \
  && printf '\n\033[33m注意: 当前 node 为 v%s, dsh 需要 22+, 启动前请切换\033[0m\n' "$NODE_MAJOR"

cat <<EOF

安装完成。

启动:   dsh web
自检:   cd $SERVICE && .venv/bin/python tools/regression.py

首次使用先在对话里绑定账号:
  ww登录            取得并保存登录态
  ww绑定<特征码>     只查询公开数据时用这个

伤害计算与排行需要 WavesToken, 填在
  $SERVICE/data/XutheringWavesUID/config.json
申请方式见 README。
EOF
