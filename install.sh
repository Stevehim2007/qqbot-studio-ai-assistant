#!/usr/bin/env bash
# QQ Bot Studio AI Assistant B - Linux/POSIX installer. Python 3.10+.
set -euo pipefail
umask 077

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
STUDIO_HOME="${QQBOT_STUDIO_HOME:-$HOME/.local/share/qqbot-studio}"
DATA_DIR="${QQBOT_AI_ASSISTANT_HOME:-$STUDIO_HOME/ai-assistant}"
CONFIG_PATH="${QQBOT_AI_ASSISTANT_CONFIG:-$DATA_DIR/config.json}"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/qqbot-ai-assistant"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_NAME="qqbot-ai-assistant.service"
UNIT_PATH="$UNIT_DIR/$UNIT_NAME"
PORT=8766
INSTANCE_ID=""
INSTALL_SERVICE=0
CONFIGURE_KEY=0
UNINSTALL=0
PURGE=0
PYTHON="${PYTHON:-}"

usage() {
  cat <<'EOF'
用法：./install.sh [选项]
  --port PORT           初始化端口（默认 8766；已有配置不会被覆盖）
  --instance-id ID      首次安装时显式复用该实例的 AstrBot DeepSeek Key
  --configure-key       安装后交互式输入独立 Key（不回显，不进入命令历史）
  --install-service     安装并启动 systemd 用户服务（可选）
  --uninstall           移除 systemd 服务和启动器，默认保留配置
  --purge               与 --uninstall 同用，额外删除 B 的数据目录
  -h, --help            显示帮助
环境变量：QQBOT_STUDIO_HOME / QQBOT_AI_ASSISTANT_HOME /
          QQBOT_AI_ASSISTANT_CONFIG / PYTHON
B 是独立可选子项目；A 保持默认。不会自动扫描实例 Key，也不打印 Key。
EOF
}
die() { printf '错误：%s\n' "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --port) [ "$#" -ge 2 ] || die "--port 缺少参数"; PORT="$2"; shift 2 ;;
    --instance-id) [ "$#" -ge 2 ] || die "--instance-id 缺少参数"; INSTANCE_ID="$2"; shift 2 ;;
    --configure-key) CONFIGURE_KEY=1; shift ;;
    --install-service) INSTALL_SERVICE=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --purge) PURGE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知选项：$1（使用 --help）" ;;
  esac
done
[ "$PURGE" -eq 0 ] || [ "$UNINSTALL" -eq 1 ] || die "--purge 只能与 --uninstall 一起使用"
[ "$CONFIGURE_KEY" -eq 0 ] || [ -z "$INSTANCE_ID" ] || die "--configure-key 与 --instance-id 不能同时使用"
case "$PORT" in ''|*[!0-9]*) die "端口必须是 1-65535 的整数" ;; esac
[ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || die "端口必须是 1-65535 的整数"

if [ "$UNINSTALL" -eq 1 ]; then
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user stop "$UNIT_NAME" >/dev/null 2>&1 || true
    systemctl --user disable "$UNIT_NAME" >/dev/null 2>&1 || true
  fi
  rm -f -- "$UNIT_PATH" "$LAUNCHER"
  if command -v systemctl >/dev/null 2>&1; then systemctl --user daemon-reload >/dev/null 2>&1 || true; fi
  echo "已移除 systemd 用户服务（若存在）和启动器：$LAUNCHER"
  if [ "$PURGE" -eq 1 ]; then
    if [ -z "$DATA_DIR" ] || [ "$DATA_DIR" = "/" ] || [ "$DATA_DIR" = "$HOME" ] \
      || [ "$DATA_DIR" = "$STUDIO_HOME" ] || [ "$DATA_DIR" = "$SCRIPT_DIR" ] \
      || [[ "$SCRIPT_DIR" == "$DATA_DIR"/* ]]; then
      die "拒绝删除不安全的数据目录：$DATA_DIR"
    fi
    rm -rf -- "$DATA_DIR"
    echo "已删除 B 数据目录：$DATA_DIR"
    if [ "$CONFIG_PATH" != "$DATA_DIR/config.json" ] && [ -e "$CONFIG_PATH" ]; then
      echo "注意：自定义配置文件未自动删除：$CONFIG_PATH"
    fi
  else
    echo "配置未删除。彻底删除：./install.sh --uninstall --purge"
  fi
  echo "仓库代码未删除，如不再需要请手动删除：$SCRIPT_DIR"
  exit 0
fi

if [ -z "$PYTHON" ]; then
  if command -v python3 >/dev/null 2>&1; then PYTHON="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then PYTHON="$(command -v python)"
  else die "未找到 Python 3。请安装 Python 3.10+"; fi
fi
"$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' \
  || die "需要 Python 3.10+：$PYTHON"

mkdir -p -- "$DATA_DIR" "$BIN_DIR"
if [ -n "$INSTANCE_ID" ]; then
  "$PYTHON" "$SCRIPT_DIR/assistant.py" --config "$CONFIG_PATH" --studio-home "$STUDIO_HOME" \
    --init-config --port "$PORT" --instance-id "$INSTANCE_ID"
else
  "$PYTHON" "$SCRIPT_DIR/assistant.py" --config "$CONFIG_PATH" --studio-home "$STUDIO_HOME" \
    --init-config --port "$PORT"
fi
chmod 600 -- "$CONFIG_PATH" 2>/dev/null || true

shell_quote() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
{
  printf '%s\n' '#!/bin/sh'
  printf 'exec %s %s --config %s --studio-home %s "$@"\n' \
    "$(shell_quote "$PYTHON")" "$(shell_quote "$SCRIPT_DIR/assistant.py")" \
    "$(shell_quote "$CONFIG_PATH")" "$(shell_quote "$STUDIO_HOME")"
} > "$LAUNCHER"
chmod 700 -- "$LAUNCHER"

if [ "$CONFIGURE_KEY" -eq 1 ]; then
  "$PYTHON" "$SCRIPT_DIR/assistant.py" --config "$CONFIG_PATH" --studio-home "$STUDIO_HOME" --set-key
fi

if [ "$INSTALL_SERVICE" -eq 1 ]; then
  command -v systemctl >/dev/null 2>&1 || die "未检测到 systemctl；配置和启动器已安装"
  mkdir -p -- "$UNIT_DIR"
  systemd_quote() {
    local value="$1"
    value="${value//%/%%}"
    value="${value//\"/\\\"}"
    printf '"%s"' "$value"
  }
  cat > "$UNIT_PATH" <<EOF
[Unit]
Description=QQ Bot Studio optional AI Assistant B
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$(systemd_quote "$PYTHON") $(systemd_quote "$SCRIPT_DIR/assistant.py") --config $(systemd_quote "$CONFIG_PATH") --studio-home $(systemd_quote "$STUDIO_HOME")
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF
  chmod 600 -- "$UNIT_PATH"
  systemctl --user daemon-reload || die "systemd --user 不可用；服务文件已保存：$UNIT_PATH"
  systemctl --user enable --now "$UNIT_NAME" || die "无法启动 systemd 用户服务；检查 systemctl --user status $UNIT_NAME"
  echo "systemd 用户服务已安装并启动：$UNIT_NAME"
fi

echo
echo "AI 助手 B 安装完成。"
echo "  启动命令：$LAUNCHER"
echo "  访问地址：http://127.0.0.1:$PORT/"
echo "  配置文件：$CONFIG_PATH（权限 600；API Key 为本地明文存储）"
echo "  固定模型：deepseek-flash"
if [ -n "$INSTANCE_ID" ]; then
  echo "  Key 来源：显式复用实例 $INSTANCE_ID 的 AstrBot 配置（运行时只读）"
elif [ "$CONFIGURE_KEY" -eq 0 ]; then
  echo "  下一步：编辑 config.json 的 api_key，或运行："
  echo "  $PYTHON \"$SCRIPT_DIR/assistant.py\" --config \"$CONFIG_PATH\" --set-key"
fi
[ "$INSTALL_SERVICE" -eq 1 ] || echo "  可选 systemd 服务：./install.sh --install-service"
echo "  卸载：./install.sh --uninstall   彻底删除配置：./install.sh --uninstall --purge"
