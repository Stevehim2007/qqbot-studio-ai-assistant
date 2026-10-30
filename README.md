# QQ Bot Studio · AI 助手 B（可选生成式 AI）

这是 QQ Bot Studio 主项目之外的**独立子项目**。它用 Python 标准库提供本地 HTTP
服务与中文 Web UI，通过 DeepSeek OpenAI-compatible API 提供可选的生成式 AI 聊天能力。
默认只监听回环地址；也支持用户**显式选择**高风险公网绑定。B 只回答 QQ Bot Studio
项目相关问题，按 Linux/Windows 使用代码内置的固定短摘要，并限制上下文与输出 token。
固定摘要已同步主项目 **v3.11** 的提示词列表、AstrBot 记忆/Persona、会话切换、
ambient、群身份、统一 AI tool marker、收藏与 `/food` 等能力。

> **A 默认保留；B 可选。** 主项目已有的离线知识库助手 A 不因 B 改变。B 不替代 A，
> 代码也不进入主仓库。未安装或 B 配置/联网失败时，A 必须继续可用。

- 当前版本：`0.5.0`
- 固定模型：`deepseek-flash`
- 固定上游：`https://api.deepseek.com/v1/chat/completions`
- 运行依赖：Python 3.10+，无第三方 Python 包

---

## 1. A / B 区别

| | 助手 A（主项目现有） | 助手 B（本仓库） |
|---|---|---|
| 默认状态 | **默认安装/保留** | **可选安装**，默认不装 |
| 定位 | 离线知识库问答/内置控制台 | 仅项目范围的在线生成式 AI 聊天 |
| Token | 不消耗 | 消耗用户自己的 DeepSeek Key |
| 外部 API | 无 | DeepSeek |
| 代码 | 主项目仓库 | 独立仓库 `qqbot-studio-ai-assistant` |
| 数据 | 主项目管理 | `~/.local/share/qqbot-studio/ai-assistant/` |
| 入口 | 主项目控制台 | 默认 `http://127.0.0.1:8766/`；公网模式使用 `public_host:8766` |

设计边界：B 独立仓库、独立配置、独立进程；主项目更新/升级不得自动安装 B；
B 失败不得阻塞 A。

---

## 2. 功能

- HTTP 服务默认只绑定 `127.0.0.1`；仅可显式配置 `host=0.0.0.0` 开放所有网卡。
- 公网模式支持 `public_host` 显示域名/IP，但 `public_host` 不是认证或防火墙。
- 中文 Web UI：Enter 发送、Shift+Enter 换行、清空浏览器内对话。
- 模型和上游地址固定，网页/配置不能把 Key 导向其他域名。
- **项目范围固定且只读**：只回答本项目/AstrBot/SnowLuma/OneBot/DeepSeek 相关问题；
  无关问题固定回复“我只回答 QQ Bot Studio 相关问题。”
- **平台差异化**：`platform=auto` 默认按运行平台，或锁定 `linux` / `windows`；
  两类平台使用代码内置的固定短摘要，不把整份 README 放进 prompt。
- **v3.11 项目知识固定摘要**：多提示词 profile/active、AstrBot 每群记忆/Persona、
  `/会话列表`/`/会话 名称`/`/新会话 名称`、ambient 低频参与与 @ 降级、群身份上下文、
  统一 AI tool marker、全局多分类/语义收藏池、`/food`。
- **省 token**：固定系统前缀、最近最多 6 条上下文、上下文字符上限、
  输出 `max_tokens=350-500`；不重复大段文档。
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
./install.sh --port 8766

# 交互式设置独立 Key：输入不回显，不进入 shell history
python3 assistant.py \
  --config "$HOME/.local/share/qqbot-studio/ai-assistant/config.json" \
  --set-key

~/.local/bin/qqbot-ai-assistant
```

浏览器打开 <http://127.0.0.1:8766/>。也可用编辑器填写 config 中的 `api_key`，
随后执行 `chmod 600 <config>`。服务读取时会再次收紧并校验权限。

可选 systemd 用户服务：

```bash
./install.sh --install-service
systemctl --user status qqbot-ai-assistant.service
journalctl --user -u qqbot-ai-assistant.service -f
```

WSL/容器若没有 systemd user bus，直接用启动器手动运行。默认仍只监听回环地址；
只有显式配置 `host=0.0.0.0` 才会开放所有网卡。

显式公网绑定（高风险；详见 §6.1）：

```bash
./install.sh --port 8766 --host 0.0.0.0 --public-host bot.example.com
```

安装器会打印无认证警告。不要裸奔公网；必须先配置防火墙/安全组、VPN 或带认证的反向代理。

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

powershell -ExecutionPolicy Bypass -File .\install.ps1 -Port 8766

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

Windows 显式公网绑定（高风险）：

```powershell
.\install.ps1 -Port 8766 -BindHost 0.0.0.0 -PublicHost bot.example.com
```

这是显式取消回环限制。服务无内置认证，禁止裸奔公网；必须用 Windows 防火墙/云安全组
限制来源，或通过 VPN、带认证的反向代理访问。

---

## 6. 配置与命令

示例见 [`config.example.json`](config.example.json)。

```json
{
  "version": 1,
  "host": "127.0.0.1",
  "public_host": "",
  "port": 8766,
  "key_source": "independent",
  "api_key": "",
  "instance_id": "",
  "timeout_seconds": 120,
  "platform": "auto",
  "project_scope_enforced": true,
  "max_context_messages": 6,
  "max_context_chars": 3000,
  "max_output_tokens": 450,
  "system_prompt": ""
}
```

- `host`：默认 `127.0.0.1`；允许 `127.0.0.1`、`localhost`、`::1`，以及**显式**
  `0.0.0.0`（所有网卡，高风险）。不接受其他具体网卡地址。
- `public_host`：公网模式下用于启动日志/链接显示的纯 IP 或域名。不得包含协议、路径、
  端口；它只是显示信息，**不改变监听地址、不提供认证或防火墙**。
- `port`：1–65535；默认 `8766`。主项目管理端口默认是 `8765`，B 不应使用，
  否则可能连到/撞上管理服务；旧配置若仍是 `8765` 可以加载，但 `--diagnose` 会报冲突。
- `key_source`：`independent`（默认）或 `instance`。
- `api_key`：独立 Key；`instance` 模式下不读取此字段。
- `instance_id`：`instance` 模式必填；仅允许字母/数字/`.`/`_`/`-`。
- `timeout_seconds`：5–600。
- `platform`：`auto`（默认，按运行平台选择）、`linux` 或 `windows`。
- `project_scope_enforced`：必须为 `true`，项目范围限制**不能关闭**。
- `max_context_messages`：0–20，默认 6；只发送最近的历史消息。
- `max_context_chars`：1–12000，默认 3000；按最近历史内容字符数截断。
- `max_output_tokens`：350–500，默认 450；作为 DeepSeek `max_tokens` 发送。
- `system_prompt`：**只读兼容占位字段**，保留用于旧配置格式；无论填写什么内容都
  始终被忽略。项目范围、安全规则、平台摘要全部由代码内置，用户不能通过该字段覆盖
  或关闭。新安装仍会生成空占位，但不提供任何可编辑提示词能力。
- 模型和上游 URL **故意不可配置**。
- 旧配置兼容：缺少 `public_host` 等新字段时使用安全默认值（`public_host=""`、host 默认
  `127.0.0.1`），不会因升级直接失败。

```bash
# 检查本地配置和 Key 是否就绪；不请求 DeepSeek，也不输出 Key
python3 assistant.py --config <config.json> --check

# 启动/公网接入自检：输出 JSON，不显示 Key
python3 assistant.py --config <config.json> --diagnose

python3 assistant.py --print-config-path
python3 assistant.py --help
```

### 6.0 项目范围、平台摘要与省 token 模式

**项目范围固定且只读。** 可回答：

- QQ Bot Studio 的安装、配置、运行、更新、卸载和故障排查；
- AstrBot / SnowLuma / OneBot / DeepSeek 在 QQ Bot Studio 中的集成、端口、
  插件、记忆、表情、管理控制台、`/assistant`、AI 工具白名单和安全边界；
- Linux 与 Windows 的平台差异、路径、命令和版本边界。

**无关问题统一拒绝。** 闲聊、通用代码题、新闻、其它软件等固定回复：

```text
我只回答 QQ Bot Studio 相关问题。
```

本地会先做保守的明显无关预检；通过预检的问题再由固定的系统提示约束。系统提示明确
要求不得编造项目功能、不能执行电脑控制、不能读取文件、不能调用外部工具；信息不足时
先说明。B 本身没有电脑控制、文件读取或工具调用实现。

**固定平台摘要（代码内置、简短）：**

| 平台 | 摘要重点 |
|---|---|
| Linux/Ubuntu | Docker Compose；`~/.local/share/qqbot-studio`；`screen`；`0.0.0.0`；实例端口 `5000-10000`；noVNC |
| Windows | Docker Desktop/WSL2；`%LOCALAPPDATA%\QQBotStudio\data`；PowerShell；Native bootstrap 与 Docker；两个 EXE；noVNC 差异 |

两个平台摘要都固定包含 AstrBot/SnowLuma/OneBot 关系、管理控制台、`/assistant`、
插件开关、AI 工具白名单、更新、安全边界和版本差异。版本差异包括：Linux 主项目与
Windows 双 EXE 发行版分开维护；Windows 两个 EXE 同版本线发布，Docker 版为稳定版，
Native 为 POC。`platform=auto` 默认按运行平台；显式配置可锁定平台用于排查/文档生成。

**省 token：**

- 系统提示以固定的公共短前缀开头，后面只追加固定的平台摘要，便于上游缓存；
  用户 `system_prompt` 不参与拼接。
- 历史只发送最近 `max_context_messages` 条，并受 `max_context_chars` 字符预算限制；
  当前用户消息始终单独发送（仍受消息输入上限约束）。
- 输出 `max_tokens` 固定在 350–500，引导回答短而可执行。
- 不重复发送整份 README，不提供工具/电脑/网络访问。

`/api/status` 会返回 `platform`、`project_scope_enforced`、`scope_notice`、
`token_mode`、`max_context_messages`、`max_context_chars`、`max_output_tokens`、
`system_prompt_read_only`、`system_prompt_ignored`，供主项目 `/assistant` 页面显示
“仅回答项目问题 / 平台 / 省 token 模式”。

#### v3.11 固定知识摘要（代码内置，用户不可修改）

固定 prompt 中包含以下短摘要，不投放整份 README：

- **提示词列表**：每个实例可有多 profile，同一时刻仅一个置顶/active。切换后，
  `direct` 模式下一轮直接使用新 prompt；`AstrBot memory` 模式下一轮新建
  conversation 并绑定专用 Persona，切换可能显示 pending。
- **AstrBot memory 模式**：每个群使用独立 conversation 记忆和 Persona，复用同一个
  DeepSeek provider/API，不新增 Key；不得编造按群隔离已生效，需以实际状态为准。
- **按名称切换会话**：群聊 `/会话列表`、`/会话 名称`、`/新会话 名称`；新建/切换后
  绑定当前群人格，群之间隔离。
- **ambient 群聊**：默认关闭；开启后低频参与，显式 @ 必回；@ 发言人优先官方 At，
  组件不可用时降级为 `@昵称` 文本，不把 QQ 号写进文本。
- **群身份上下文**：按当前发送者身份区分群成员；QQ/昵称/群号仅用于身份区分，
  不在回复或日志中暴露。
- **统一 AI tool marker**：单套工具/表情白名单，一次事件最多一条文字 + 一个附件；
  不使用电脑控制、沙箱、终端或任意文件路径。
- **收藏表情**：全局收藏池，支持多分类归属、SHA-256 去重、tags/meaning/tone
  语义标签；分类查询跨会话可见。
- **`/food`**：固定 `https://food.dlsz.top`，最多 5 家，不额外调用 LLM。
- **Windows 发布边界**：正式 Release 与 Native POC 状态必须以 Windows 独立仓库的
  `VERSION`/README/VALIDATION 为准，不得编造版本或发布状态。

该摘要只增加约几百个中文字符；系统提示、历史上下文和输出 token 上限仍沿用上面的
省 token 设置。用户 `system_prompt` 依旧完全不参与 prompt。

### 6.1 显式公网绑定（高风险，默认关闭）

默认必须保持回环。只有在清楚风险并已设置网络边界时，才可显式编辑配置：

```json
{
  "host": "0.0.0.0",
  "public_host": "bot.example.com",
  "port": 8766
}
```

或首次安装时：

```bash
./install.sh --port 8766 --host 0.0.0.0 --public-host bot.example.com
```

Windows：

```powershell
.\install.ps1 -Port 8766 -BindHost 0.0.0.0 -PublicHost bot.example.com
```

启动后：

- `0.0.0.0` 是监听地址，不是可访问地址；请使用服务器公网 IP 或域名。
- 启动日志会明确打印实际监听地址和以下警告：**服务无内置用户认证，禁止裸奔公网；
  必须使用防火墙/安全组限制来源，或通过 VPN、带认证的反向代理访问。**
- `public_host` 仅改变启动日志中显示的 URL，不允许把 Key 发往其他上游。
- `Host` 必须是无畸形字符且带**实际监听端口**的合法公网 IP/域名；`0.0.0.0`、
  `::`、缺端口、错误端口、路径、userinfo 等会被拒绝。
- 浏览器 `Origin` 必须与 `Host` 的 hostname、实际端口一致；公网模式允许 HTTP/HTTPS
  来源，回环模式仍只允许 HTTP 同源。`Host`/`Origin` 校验不是身份认证。
- 若前置反向代理，代理必须保留 `Host`/`Origin` 与端口的一致性；B 不信任
  `X-Forwarded-*`，也不自行提供 TLS、登录或访问控制。
- API 仍没有鉴权。Host/Origin 防跨站不能阻止任何一个能直接连接该端口的客户端。

> **安全底线：无认证服务禁止裸奔公网。** 至少要用云安全组/防火墙按来源 IP 限制，
> 更推荐 VPN；若使用反向代理，必须在其上启用认证和 TLS，并保留本服务要求的
> Host/Origin 端口一致性。

### 6.2 `--diagnose` 启动/公网接入自检

```bash
python3 assistant.py \
  --config "$HOME/.local/share/qqbot-studio/ai-assistant/config.json" \
  --studio-home "$HOME/.local/share/qqbot-studio" \
  --diagnose

# 安装器生成启动器后也可直接：
~/.local/bin/qqbot-ai-assistant --diagnose
```

`--diagnose` 只输出一个 UTF-8 JSON 文档，不显示 API Key，适合主控制台/脚本解析。
主要字段：

| 字段 | 含义 |
|---|---|
| `ok` | 技术自检是否可用：端口可 bind，或已运行的 B health 正常 |
| `ready_for_chat` | `ok` 且 Key 已配置且 B 正在运行 |
| `config_path` | 本机配置路径（不含 Key） |
| `configured` / `key_source` / `key_error` | Key 是否就绪及来源；错误信息已脱敏 |
| `platform` / `platform_config` | 实际解析平台 / 配置值（auto/linux/windows） |
| `project_scope_enforced` / `scope_notice` | 固定项目范围标志与“仅回答项目问题”标签 |
| `token_mode` / `max_*` | 省 token 模式、上下文条数/字符和输出 token 上限 |
| `system_prompt_read_only` / `system_prompt_ignored` | 系统提示只读；配置字段是否被忽略 |
| `host` / `port` / `public_host` | 配置值 |
| `url` / `url_hint` | 对外 URL；公网模式未配置 public_host 时为 `null` 并提示 |
| `listener` | 能连上 health 时显示实际 socket host/port/mode/source |
| `bind_test` | 实际尝试 bind；`ok`、`port_in_use`、errno/error |
| `health` | 从本机 `127.0.0.1`/适当回环地址请求 `/api/health` 的结果 |
| `public_host_health` | 公网模式下用 `public_host` 作为 Host 的额外本地探测 |
| `host_guard` | 用非法 Host 探测，期望 421 + `code=invalid_host` |
| `listener_matches_config` | health 返回的实际 mode 是否与配置一致 |
| `management_port_conflict` | 是否误用管理端口 `8765` |
| `security_warnings` | 无认证/公网暴露/Key 未配置等安全警告 |
| `external_reachability` | 固定为 `not_verified`（本工具不做外部拨测） |
| `external_access_note` | 解释云安全组/防火墙/NAT 需要另行检查 |

如何区分问题：

- `bind_test.ok=true` + `health.ok=false`：本机端口当前可用，但 B 未启动或未监听该
  host/port；这是**本机监听/启动问题**。
- `bind_test.port_in_use=true` + `health.ok=true`：B 已在运行，本机 health 正常。
- `bind_test.port_in_use=true` + `health.ok=false`：端口被其他进程/管理服务占用，
  `/api/health` 不是 B；不要继续把它当成“网络没放行”。
- 如果 TCP 直接拒绝连接，说明没有可达的 listener；如果连接到了 B 但 Host 不合法，
  B 会返回 HTTP **421** 和 JSON `code=invalid_host`，不会被误报成防火墙。
- 本机 bind/health 通过，只证明**本机监听成功**。`0.0.0.0` 不等于云安全组和主机防火墙
  已放行；从外网访问还需确认 TCP 端口、来源 IP、NAT/端口映射和 `public_host`。
- 本工具固定 `external_reachability=not_verified`，不会声称公网 8766 已验证。

例如用户服务器公网地址为 `192.144.206.201`，应配置：

```json
{"host": "0.0.0.0", "public_host": "192.144.206.201", "port": 8766}
```

本机诊断成功仍不代表 `192.144.206.201:8766` 的外部入站已放行；必须在云安全组、主机
防火墙/ufw/firewalld 中只对可信来源放行 TCP 8766。

退出码：`0` 表示技术自检可用（端口可绑定或 B health 正常）；`1` 表示配置错误、
管理端口冲突、端口被非 B 服务占用等需要处理的问题。聊天是否就绪请看
`ready_for_chat`。

---

## 7. HTTP API

无内置用户认证。默认仅供本机使用；显式 `host=0.0.0.0` 公网绑定时属于高风险部署，
必须按 §6.1 建立防火墙/VPN/反向代理认证边界。

### `GET /api/health`

```json
{
  "ok": true,
  "app": "qqbot-studio-ai-assistant",
  "version": "0.5.0",
  "listen_mode": "loopback",
  "listen_host": "127.0.0.1",
  "listen_port": 8766
}
```

监听 `0.0.0.0` 时 `listen_mode` 为 `public_bind`、`listen_host` 为 `0.0.0.0`。
本机仍可通过 `127.0.0.1:8766` + 合法 `Host: 127.0.0.1:8766` 进行 health 检查。

### `GET /api/status`

```json
{
  "ok": true,
  "app": "qqbot-studio-ai-assistant",
  "version": "0.5.0",
  "configured": true,
  "key_source": "independent",
  "key_error": "",
  "model": "deepseek-flash",
  "endpoint": "https://api.deepseek.com/v1/chat/completions",
  "host": "127.0.0.1",
  "public_host": "",
  "platform": "linux",
  "platform_config": "auto",
  "project_scope_enforced": true,
  "scope_notice": "仅回答 QQ Bot Studio 相关问题",
  "token_mode": "concise",
  "max_context_messages": 6,
  "max_context_chars": 3000,
  "max_output_tokens": 450,
  "system_prompt_read_only": true,
  "system_prompt_ignored": false
}
```

响应中没有 API Key。`system_prompt_ignored=true` 表示旧配置中保留了该字段，但运行时
不会使用其内容。

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
{
  "ok": true,
  "reply": "……",
  "model": "deepseek-flash",
  "scope_refused": false,
  "platform": "linux",
  "project_scope_enforced": true,
  "token_mode": "concise",
  "max_output_tokens": 450
}
```

无关问题会在本地直接返回 `scope_refused=true` 和固定拒绝语，不发送 DeepSeek 请求。
项目问题才按当前配置调用上游。请求历史超过上下文限制时内部截断；旧 API 的
`ok/reply/model` 字段保持兼容。

未配置 Key 返回 503，上游失败返回 502/504，请求错误返回 400。服务端不持久化聊天记录。
服务会严格解析 `Host` 并校验实际监听端口；默认回环模式拒绝公网 Host。显式
`host=0.0.0.0` 时允许合法公网 IP/域名，但仍要求带实际端口，浏览器 `Origin` 必须与
`Host` 的 hostname/端口一致。不返回 CORS 允许头。

Host 不合法时返回 HTTP 421 和可诊断 JSON（示例）：

```json
{
  "ok": false,
  "code": "invalid_host",
  "error": "Host 头校验失败：当前为 0.0.0.0 公网绑定：Host 必须是合法公网域名/IP，包含实际端口……",
  "listen_mode": "public_bind",
  "expected_port": 8766
}
```

Origin 不一致时返回 HTTP 403、`code=invalid_origin` 和 `expected_port`。这些响应表明
请求已经到达 B；如果完全连不上，则问题在本机 listener、端口映射或防火墙，而不是 Host 校验。

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
- 主项目如提供 `host=0.0.0.0` + `public_host`，可直接写入 B 配置；B 接受该组合，
  但主项目必须把 `0.0.0.0` 视为显式高风险选择，默认仍写 `127.0.0.1`。
- 主项目不得把 `public_host` 当成监听地址或访问认证；实际监听地址是 `host`。

### 8.3 主控制台

主控制台应有独立的“AI 助手 B（可选）”入口/卡片，至少支持：

| 能力 | 契约 |
|---|---|
| 入口 | 默认 `http://127.0.0.1:8766/`；host=0.0.0.0 时用 `public_host:port`（缺 public_host 则提示手动） |
| 安装 | 目标路径不存在时 clone；存在时不重复 clone |
| 状态 | 调 `GET /api/health`；失败只显示未运行，不影响 A |
| 模式标签 | 从 `/api/status` 读取 `scope_notice`、`platform`、`token_mode`，显示“仅回答项目问题/平台/省 token 模式” |
| 提示词 | `system_prompt` 必须按只读兼容字段处理；主控制台不得提供修改入口，B 会忽略该字段并使用代码内置提示 |
| 诊断 | 调用 `python3 assistant.py --config <config> --diagnose`；解析 JSON 的 `ok`、`ready_for_chat`、`bind_test`、`health`、`host_guard`、`external_reachability` |
| 更新 | 扩展目录内 `git pull --ff-only`；失败保留旧版本并提示 |
| 启动 | Linux 用 B launcher/systemd；Windows 用 .cmd/计划任务 |
| 风险提示 | host=0.0.0.0 时控制台必须显示“无认证、禁止裸奔公网、防火墙/VPN/反代认证” |
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

共 **44 个** mock 测试，覆盖：配置 `0600`、独立/实例 Key、旧配置缺省字段兼容、路径越界、
`/api/status`、`/api/chat`、固定 `deepseek-flash`、`stream=false`、Key 不出现在响应/错误、
上游 401 脱敏、拒绝上游重定向、Host/Origin/Content-Type/输入校验、CSP 等安全头。
项目范围测试覆盖无关问题固定拒绝且不调用上游、项目问题正常、Linux/Windows 固定摘要
内容与平台选择、只读 system_prompt 被忽略、未配置 Key 时无关问题仍直接拒绝、
上下文条数/字符截断、`max_tokens` 350–500、状态模式字段和旧响应兼容。公网模式验证 `0.0.0.0` 绑定、默认回环拒绝公网 Host、公网
Host/Origin 接受、错误端口/畸形 Host/不一致 Origin 拒绝、health listener 字段、
421/403 可诊断错误。诊断测试验证 loopback/公网运行、实际 listener、health、
public_host_health、host_guard、端口占用、8765 冲突以及 `--diagnose` 输出不含 Key。
测试不访问外网、不消耗 token。

GitHub Actions 在 Ubuntu 和 Windows 上运行 Python 3.10/3.12 的 mock 测试；
Linux 和 Windows 还会执行安装器 smoke test（创建配置/启动器、运行 `--version`、
卸载与 purge），Windows 另做 PowerShell 语法解析检查。

### 当前验证边界（重要）

- 开发和验证环境为 Linux/WSL2；**没有真实 DeepSeek API Key，未进行真实 DeepSeek 联调**。
  所有通过均为本地 mock HTTP 测试，不能声称真实 API 已联通。
- 本次开发环境是 Linux；不过 GitHub Actions 的 Windows runner 已实际执行
  `install.ps1` 的配置创建、NTFS ACL、.cmd 启动器 `--version`、卸载与 purge smoke test。
  `-InstallService` 的登录计划任务创建/登录触发仍需在真实 Windows 用户会话中手测；
  CI 不覆盖该可选分支。
- 没有可用已部署 AstrBot 实例，实例 Key 复用仅用合成 `cmd_config.json` mock 验证；
  字段依据 AstrBot v4.29 结构，升级后需复核。
- `deepseek-flash` 是否对目标账号可用、DeepSeek 接口是否变化，需要用户真实 Key 验证。
- Windows 是登录计划任务，不是完整 Windows Service。
- `host=0.0.0.0` 公网模式仅在本机 TCP socket 上用合成 Host/Origin 做 mock 验证；
  `--diagnose` 的 `external_reachability` 固定为 `not_verified`，未在真实公网 IP、
  云安全组、防火墙、VPN 或认证反向代理后做外部拨测。
- 无内置鉴权、速率限制、内容审核、对话持久化或 TLS 终止。公网绑定必须置于
  防火墙/VPN/带认证反代之后，禁止裸奔公网。
- 项目范围先用保守本地关键词预检，再由固定系统提示约束。预检可能把带项目通用词但
  实际无关的问题交给上游，最终应由固定提示拒绝；未用真实 DeepSeek Key 做完整语义验收。
- 固定前缀只是有利于上游缓存，不保证 DeepSeek 一定命中缓存或按缓存价格计费；
  `max_tokens` 由上游执行情况决定。用户配置的 `system_prompt` 始终被忽略。
- v3.11 知识摘要来自当前主项目文档；AstrBot/QQ 的具体运行时状态、提示词切换是否
  pending、群会话/Persona/ambient 的真实效果未被本次 B mock 测试端到端验证。
- Windows 当前正式 Release/Native POC 状态不在 B 中硬编码，必须查询 Windows 仓库
  `VERSION`/README/VALIDATION；B 的提示要求不得猜测。

真实联调时优先保持默认回环，用低风险测试消息并检查 DeepSeek 用量。若必须测试公网绑定，
先设置最小来源范围的防火墙规则和认证边界，测试后立即关闭。不要提交真实 Key。

---

## 10. 安全边界

- Key 是本地配置文件中的**明文**；`0600`/NTFS ACL 只限制其他普通 OS 用户。
  当前用户、root/Administrator、被入侵的本机仍可读取。B 不提供加密保险库。
- Key 只被发送到固定的 `https://api.deepseek.com/v1/chat/completions`，模型固定
  `deepseek-flash`；上游 HTTP 重定向被拒绝，但未额外固定 DNS 解析结果。
- 用户聊天内容会发送给 DeepSeek；不要输入新的密钥或其他敏感信息。
- 服务无认证。默认回环绑定才是最安全配置。显式 `0.0.0.0` 会把 API/UI 暴露到
  所有网卡；Host/Origin 校验不是身份认证，无法阻止能直接连接端口的客户端。
- 公网部署必须使用防火墙/云安全组限制来源，或置于 VPN/启用认证与 TLS 的反向代理后；
  **禁止裸奔公网**。反向代理还需保留 Host/Origin 的 hostname+实际端口一致性。
- Host/Origin 校验、JSON Content-Type、CSP、no-CORS 可降低浏览器跨站风险，
  但不能替代网络隔离或认证。
- 访问日志不含请求体和请求头，也不记录查询串；上游错误响应会替换 Key 与常见
  `sk-*`/`Bearer`/`api_key=` 形式后再返回。
- 复用实例 Key 时，B 每次聊天读取实例 `cmd_config.json`；B 不写回、不复制该 Key，
  但 Key 会进入 B 进程内存并用于 DeepSeek 请求。
- 上游错误、Windows ACL、代理环境变量、DNS/TLS 解析，以及真实公网/防火墙/
  VPN/认证反代的组合仍属未做端到端验证的边界。

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
- **能公网访问吗**：默认不能，`127.0.0.1` 只能本机/SSH 隧道。若显式配置
  `host=0.0.0.0` 则可以可达，但这是高风险选项：无认证/TLS/滥用防护，
  **禁止裸奔公网**，必须使用防火墙/安全组、VPN 或带认证的反向代理。
- **Host 校验 421 / Origin 403**：确认请求 Host 带实际监听端口；公网模式 Origin
  的 hostname 和端口必须与 Host 一致。反向代理改写了 Host/Origin 或端口会触发拒绝。

## 13. 许可证

MIT，见 [LICENSE](LICENSE)。
