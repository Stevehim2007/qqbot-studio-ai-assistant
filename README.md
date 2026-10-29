# QQ Bot Studio · AI 助手 B（可选生成式 AI）

这是 QQ Bot Studio 主项目之外的**独立子项目**。它用 Python 标准库提供本机 HTTP
服务与中文 Web UI，通过 DeepSeek OpenAI-compatible API 提供可选的生成式 AI 聊天能力。

> **A 默认保留；B 可选。** 主项目已有的离线知识库助手 A 不因 B 改变。B 不替代 A，
> 代码也不进入主仓库。未安装或 B 配置/联网失败时，A 必须继续可用。

- 当前版本：`0.1.0`
- 固定模型：`deepseek-flash`
- 固定上游：`https://api.deepseek.com/v1/chat/completions`
- 运行依赖：Python 3.10+，无第三方 Python 包

---

## 1. A / B 区别

| | 助手 A（主项目现有） | 助手 B（本仓库） |
|---|---|---|
| 默认状态 | **默认安装/保留** | **可选安装**，默认不装 |
| 定位 | 离线知识库问答/内置控制台 | 在线生成式 AI 聊天 |
| Token | 不消耗 | 消耗用户自己的 DeepSeek Key |
| 外部 API | 无 | DeepSeek |
| 代码 | 主项目仓库 | 独立仓库 `qqbot-studio-ai-assistant` |
| 数据 | 主项目管理 | `~/.local/share/qqbot-studio/ai-assistant/` |
| 入口 | 主项目控制台 | `http://127.0.0.1:8765/`（可配置端口） |

设计边界：B 独立仓库、独立配置、独立进程；主项目更新/升级不得自动安装 B；
B 失败不得阻塞 A。

---

## 2. 功能

- 本机回环 HTTP 服务，默认只绑定 `127.0.0.1`。
- 中文 Web UI：Enter 发送、Shift+Enter 换行、清空浏览器内对话。
- 模型和上游地址固定，网页/配置不能把 Key 导向其他域名。
- 本地 JSON 配置，Linux/POSIX 权限强制 `0600`。
- 支持独立 DeepSeek Key；也支持用户在配置中**显式**复用某个已部署实例的 Key。
- 不自动扫描实例，不自动复制实例 Key。
- Key 不入 API 响应、不显示在 UI、不写访问日志；上游错误先脱敏。
- `install.sh` / `install.ps1` 创建私有配置和启动器，可选安装后台自启动。
- `GET /api/health`、`GET /api/status` 可供主控制台探测。
- mock 测试和 GitHub Actions（Ubuntu/Windows，Python 3.10/3.12）。

---

## 3. 数据与目录

按主项目集成契约，仓库固定放在：

```text
~/.local/share/qqbot-studio/extensions/ai-assistant/
```

B 的数据默认独立放在：

```text
~/.local/share/qqbot-studio/ai-assistant/
└── config.json      # 0600（POSIX），含 API Key 明文
```

Linux 启动器：`~/.local/bin/qqbot-ai-assistant`。  
Windows 对应路径：

```text
%USERPROFILE%\.local\share\qqbot-studio\extensions\ai-assistant\
%USERPROFILE%\.local\share\qqbot-studio\ai-assistant\config.json
%USERPROFILE%\.local\bin\qqbot-ai-assistant.cmd
```

可覆盖的环境变量：

| 变量 | 用途 | 默认 |
|---|---|---|
| `QQBOT_STUDIO_HOME` | 主项目数据根目录/实例定位 | `~/.local/share/qqbot-studio` |
| `QQBOT_AI_ASSISTANT_HOME` | B 数据目录 | `<QQBOT_STUDIO_HOME>/ai-assistant` |
| `QQBOT_AI_ASSISTANT_CONFIG` | B 配置文件 | `<B 数据目录>/config.json` |
| `PYTHON` | Linux 使用的 Python | 自动寻找 `python3`/`python` |

---

## 4. Linux / WSL 安装

```bash
git clone git@github.com:Stevehim2007/qqbot-studio-ai-assistant.git \
  "$HOME/.local/share/qqbot-studio/extensions/ai-assistant"
cd "$HOME/.local/share/qqbot-studio/extensions/ai-assistant"

# 创建 ~/.local/share/qqbot-studio/ai-assistant/config.json（0600）
# 和 ~/.local/bin/qqbot-ai-assistant
./install.sh --port 8765

# 交互式设置独立 Key：输入不回显，不进入 shell history
python3 assistant.py \
  --config "$HOME/.local/share/qqbot-studio/ai-assistant/config.json" \
  --set-key

~/.local/bin/qqbot-ai-assistant
```

浏览器打开 <http://127.0.0.1:8765/>。也可用编辑器填写 config 中的 `api_key`，
随后执行 `chmod 600 <config>`。服务读取时会再次收紧并校验权限。

可选 systemd 用户服务：

```bash
./install.sh --install-service
systemctl --user status qqbot-ai-assistant.service
journalctl --user -u qqbot-ai-assistant.service -f
```

WSL/容器若没有 systemd user bus，直接用启动器手动运行。服务仍只监听回环地址。

### 4.1 显式复用实例 Key

```bash
./install.sh --instance-id <实例ID>
```

仅在用户明确这样选择时才读取：

```text
~/.local/share/qqbot-studio/instances/<实例ID>/data/astrbot/cmd_config.json
```

运行时按 AstrBot v4 `provider` 列表查找 `deepseek-flash`/DeepSeek provider 的 `key`
字段。B 不把该 Key 复制进自己的 config；实例 ID 非法、路径越界、文件缺失或没有
DeepSeek Key 时返回安全错误。没有 `--instance-id` 时绝不会自动扫描实例。

---

## 5. Windows 安装

要求 Windows 10/11、PowerShell 5.1+、Python 3.10+（`python` 或 `py` 在 PATH）。

```powershell
git clone git@github.com:Stevehim2007/qqbot-studio-ai-assistant.git `
  "$HOME\.local\share\qqbot-studio\extensions\ai-assistant"
Set-Location "$HOME\.local\share\qqbot-studio\extensions\ai-assistant"

powershell -ExecutionPolicy Bypass -File .\install.ps1 -Port 8765

python .\assistant.py `
  --config "$HOME\.local\share\qqbot-studio\ai-assistant\config.json" `
  --set-key

& "$HOME\.local\bin\qqbot-ai-assistant.cmd"
```

`install.ps1` 会创建配置、启动器，并用 NTFS ACL 将 B 的数据目录和配置文件限制给
当前用户。手工创建配置、未运行安装器时，Python 标准库无法等价表达完整 Windows ACL，
请自行用 `icacls` 或文件属性检查。

可选“登录时启动”的计划任务（任务名 `QQBotStudioAIAssistant`）：

```powershell
.\install.ps1 -InstallService
schtasks /Query /TN QQBotStudioAIAssistant
```

这是当前用户 onlogon scheduled task，不是 Windows Service，不需要 NSSM。
脚本优先使用 `pythonw.exe`/`pyw.exe`。任务创建失败时仍可用 .cmd 启动器手动运行。

Windows 显式复用实例：

```powershell
.\install.ps1 -InstanceId <实例ID>
```

默认读取 `%USERPROFILE%\.local\share\qqbot-studio\instances\<实例ID>\data\astrbot\cmd_config.json`。

---

## 6. 配置与命令

示例见 [`config.example.json`](config.example.json)。

```json
{
  "version": 1,
  "host": "127.0.0.1",
  "port": 8765,
  "key_source": "independent",
  "api_key": "",
  "instance_id": "",
  "timeout_seconds": 120,
  "system_prompt": "你是 QQ Bot Studio 的生成式 AI 使用助手。"
}
```

- `host` 只允许 `127.0.0.1`、`localhost`、`::1`；B 拒绝绑定公网。
- `port` 1–65535；修改后重启。
- `key_source`：`independent`（默认）或 `instance`。
- `api_key`：独立 Key；`instance` 模式下不读取此字段。
- `instance_id`：`instance` 模式必填；仅允许字母/数字/`.`/`_`/`-`。
- `timeout_seconds`：5–600。
- `system_prompt`：最多 4000 字符。
- 模型和上游 URL **故意不可配置**。

```bash
# 检查本地配置和 Key 是否就绪；不请求 DeepSeek，也不输出 Key
python3 assistant.py --config <config.json> --check

python3 assistant.py --print-config-path
python3 assistant.py --help
```

---

## 7. 本地 API

无内置用户认证，仅供本机使用，**不要公开暴露**。

### `GET /api/health`

```json
{"ok":true,"app":"qqbot-studio-ai-assistant","version":"0.1.0"}
```

### `GET /api/status`

```json
{
  "ok": true,
  "app": "qqbot-studio-ai-assistant",
  "version": "0.1.0",
  "configured": true,
  "key_source": "independent",
  "key_error": "",
  "model": "deepseek-flash",
  "endpoint": "https://api.deepseek.com/v1/chat/completions"
}
```

响应中没有 API Key。

### `POST /api/chat`

请求：

```json
{
  "message": "你好",
  "history": [
    {"role": "user", "content": "上一条"},
    {"role": "assistant", "content": "上一条回复"}
  ]
}
```

`Content-Type: application/json`。`message` 必填；`history` 可选，最多 20 条，只允许
`user`/`assistant`。成功：

```json
{"ok":true,"reply":"……","model":"deepseek-flash"}
```

未配置 Key 返回 503，上游失败返回 502/504，请求错误返回 400。服务端不持久化聊天记录。
对浏览器请求校验同源 `Origin`，限制本机 `Host`，不返回 CORS 允许头。

---

## 8. 主项目可选安装集成契约

B 仓库不修改主项目。主项目需实现以下契约：

### 8.1 A 保持默认

- 主项目现有安装流程必须继续安装/保留 A。
- B 默认不安装；不能因升级/修复被自动安装。
- 只有用户明确选择“安装可选 AI 助手 B”才安装。
- B 安装、启动、联网、Key 配置失败都不得阻塞 A。

### 8.2 固定 clone 路径

```bash
EXT_DIR="${QQBOT_STUDIO_HOME:-$HOME/.local/share/qqbot-studio}/extensions/ai-assistant"
if [ ! -d "$EXT_DIR/.git" ]; then
  git clone git@github.com:Stevehim2007/qqbot-studio-ai-assistant.git "$EXT_DIR"
fi
bash "$EXT_DIR/install.sh"
```

- 必须 clone 到 `~/.local/share/qqbot-studio/extensions/ai-assistant`。
- 不把 B 源码复制/提交进主仓库。
- 主项目不接收、不记录、不传参 B 的 API Key；Key 生命周期归 B 本地配置。
- 主项目不自动推断实例 Key 复用；必须由用户在 B 配置/安装选项显式选择。
- 更新时不得覆盖 `<QQBOT_STUDIO_HOME>/ai-assistant/` 下的 B 配置。

### 8.3 主控制台

主控制台应有独立的“AI 助手 B（可选）”入口/卡片，至少支持：

| 能力 | 契约 |
|---|---|
| 入口 | `http://127.0.0.1:8765/`（B 配置改端口时跟随） |
| 安装 | 目标路径不存在时 clone；存在时不重复 clone |
| 状态 | 调 `GET /api/health`；失败只显示未运行，不影响 A |
| 更新 | 扩展目录内 `git pull --ff-only`；失败保留旧版本并提示 |
| 启动 | Linux 用 B launcher/systemd；Windows 用 .cmd/计划任务 |
| 卸载 | 调用 `install.sh --uninstall` / `install.ps1 -Uninstall`，默认保留 B 数据 |
| 隔离 | A 不依赖 B 安装、配置、网络状态 |

建议更新流程：

```bash
git -C "$EXT_DIR" fetch --prune
git -C "$EXT_DIR" pull --ff-only
# install.sh 幂等，可刷新启动器；不应覆盖现有默认 config
bash "$EXT_DIR/install.sh"
```

主项目只依赖以上公开契约和 API，不应读取/回显 B 的 API Key 或私自猜测配置字段。

---

## 9. 测试

```bash
python3 -m py_compile assistant.py
python3 -m unittest discover -s tests -v
bash -n install.sh
```

mock 测试覆盖：配置 `0600`、独立/实例 Key、路径越界、`/api/status`、`/api/chat`、
固定 `deepseek-flash`、`stream=false`、Key 不出现在响应/错误、上游 401 脱敏、
拒绝上游重定向、Host/Origin/Content-Type/输入校验、CSP 等安全头。测试不访问外网、不消耗 token。

GitHub Actions 在 Ubuntu 和 Windows 上运行 Python 3.10/3.12 的 mock 测试，
并在 Windows 上做 PowerShell 语法解析检查（若可运行）。

### 当前验证边界（重要）

- 开发和验证环境为 Linux/WSL2；**没有真实 DeepSeek API Key，未进行真实 DeepSeek 联调**。
  所有通过均为本地 mock HTTP 测试，不能声称真实 API 已联通。
- Windows `install.ps1` 和 Windows 计划任务未在本次 Linux 环境实际安装执行；
  CI 只验证 Python 测试和 PowerShell 解析，仍需在真实 Windows 上做安装/启动/卸载手测。
- 没有可用已部署 AstrBot 实例，实例 Key 复用仅用合成 `cmd_config.json` mock 验证；
  字段依据 AstrBot v4.29 结构，升级后需复核。
- `deepseek-flash` 是否对目标账号可用、DeepSeek 接口是否变化，需要用户真实 Key 验证。
- Windows 是登录计划任务，不是完整 Windows Service。
- 无内置鉴权、速率限制、内容审核、对话持久化或 TLS 终止。不要暴露公网。

真实联调时先确认只监听本机，再用低风险测试消息并检查 DeepSeek 用量。不要提交真实 Key。

---

## 10. 安全边界

- Key 是本地配置文件中的**明文**；`0600`/NTFS ACL 只限制其他普通 OS 用户。
  当前用户、root/Administrator、被入侵的本机仍可读取。B 不提供加密保险库。
- Key 只被发送到固定的 `https://api.deepseek.com/v1/chat/completions`，模型固定
  `deepseek-flash`；上游 HTTP 重定向被拒绝，但未额外固定 DNS 解析结果。
- 用户聊天内容会发送给 DeepSeek；不要输入新的密钥或其他敏感信息。
- 服务无认证。默认回环绑定、Host/Origin 校验、JSON Content-Type、CSP、no-CORS
  可降低浏览器跨站风险，但不能替代网络隔离。禁止端口转发或反向代理公开它。
- 访问日志不含请求体和请求头，也不记录查询串；上游错误响应会替换 Key 与常见
  `sk-*`/`Bearer`/`api_key=` 形式后再返回。
- 复用实例 Key 时，B 每次聊天读取实例 `cmd_config.json`；B 不写回、不复制该 Key，
  但 Key 会进入 B 进程内存并用于 DeepSeek 请求。
- 上游错误、Windows ACL、代理环境变量、DNS/TLS 解析等仍属未做端到端验证的边界。

---

## 11. 卸载

Linux：

```bash
cd "$HOME/.local/share/qqbot-studio/extensions/ai-assistant"
./install.sh --uninstall         # 删服务和启动器，保留配置
./install.sh --uninstall --purge # 同时删除 B 数据目录
rm -rf "$HOME/.local/share/qqbot-studio/extensions/ai-assistant" # 可选，删源码
```

Windows：

```powershell
Set-Location "$HOME\.local\share\qqbot-studio\extensions\ai-assistant"
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall -Purge
Remove-Item -LiteralPath "$HOME\.local\share\qqbot-studio\extensions\ai-assistant" -Recurse -Force
```

以上均不影响助手 A 或主项目实例数据。

---

## 12. 常见问题

- **显示尚未配置 Key**：用 `--set-key` 或编辑 `config.json` 的 `api_key`；instance 模式检查实例 ID/文件。
- **端口占用**：编辑 `port` 后重启；已有配置不会因再次 `--port` 被覆盖。
- **systemd 不可用**：WSL/容器常见；直接运行启动器。
- **PowerShell 执行策略**：用 `powershell -ExecutionPolicy Bypass -File .\install.ps1 ...`。
- **能公网访问吗**：不支持，也不应做。当前没有认证/TLS/滥用防护。

## 13. 许可证

MIT，见 [LICENSE](LICENSE)。
