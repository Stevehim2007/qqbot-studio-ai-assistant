#!/usr/bin/env python3
"""QQ Bot Studio optional AI assistant B: local, standard-library HTTP service."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import socket
import stat
import sys
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

APP_NAME = "qqbot-studio-ai-assistant"
APP_VERSION = "0.1.0"
MODEL = "deepseek-flash"
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT = 120
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
KEY_SOURCES = ("independent", "instance")
INSTANCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_BODY = 512 * 1024
MAX_UPSTREAM = 2 * 1024 * 1024
MAX_UPSTREAM_ERROR = 32 * 1024
MAX_MESSAGE = 12_000
MAX_HISTORY = 20
MAX_TOTAL_CHAT = 80_000
MAX_KEY = 4_096
MAX_PROMPT = 4_000
DEFAULT_PROMPT = (
    "你是 QQ Bot Studio 的生成式 AI 使用助手。请用简洁、准确的中文回答。"
    "不要声称自己已经执行了未实际执行的操作；信息不足时请明确说明。"
)
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9._-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,;\"']+"),
)
UI_PATH = Path(__file__).resolve().with_name("ui.html")


class AssistantError(Exception):
    pass


class ConfigError(AssistantError):
    pass


class KeyConfigError(AssistantError):
    pass


class DeepSeekError(AssistantError):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_GATEWAY) -> None:
        super().__init__(message)
        self.http_status = int(status)


def default_studio_home() -> Path:
    raw = os.environ.get("QQBOT_STUDIO_HOME", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".local" / "share" / "qqbot-studio"


def default_config_path() -> Path:
    raw = os.environ.get("QQBOT_AI_ASSISTANT_CONFIG", "").strip()
    return Path(raw).expanduser() if raw else default_studio_home() / "ai-assistant" / "config.json"


def default_config(port: int = DEFAULT_PORT) -> dict[str, Any]:
    return {
        "version": 1,
        "host": "127.0.0.1",
        "port": int(port),
        "key_source": "independent",
        "api_key": "",
        "instance_id": "",
        "timeout_seconds": DEFAULT_TIMEOUT,
        "system_prompt": DEFAULT_PROMPT,
    }


def _int_value(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"配置项 {name} 必须是整数")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"配置项 {name} 必须是整数") from None
    if not low <= result <= high:
        raise ConfigError(f"配置项 {name} 必须在 {low} 到 {high} 之间")
    return result


def validate_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    config = default_config()
    config.update(dict(raw))
    host = str(config.get("host") or "").strip().lower()
    if host not in LOOPBACK_HOSTS:
        raise ConfigError("host 只能使用本机回环地址 127.0.0.1 / localhost / ::1")
    config["host"] = host
    config["port"] = _int_value(config.get("port"), "port", 1, 65_535)
    config["timeout_seconds"] = _int_value(
        config.get("timeout_seconds"), "timeout_seconds", 5, 600
    )
    source = str(config.get("key_source") or "independent").strip()
    if source not in KEY_SOURCES:
        raise ConfigError("key_source 只能是 independent 或 instance")
    config["key_source"] = source
    config["instance_id"] = str(config.get("instance_id") or "").strip()
    config["api_key"] = str(config.get("api_key") or "").strip()
    if len(config["api_key"]) > MAX_KEY or "\r" in config["api_key"] or "\n" in config["api_key"]:
        raise ConfigError("api_key 格式异常")
    if config["instance_id"] and not INSTANCE_ID_RE.fullmatch(config["instance_id"]):
        raise ConfigError("instance_id 只能包含字母、数字、点、下划线和连字符")
    prompt = str(config.get("system_prompt") or DEFAULT_PROMPT).strip() or DEFAULT_PROMPT
    if len(prompt) > MAX_PROMPT:
        raise ConfigError(f"system_prompt 不能超过 {MAX_PROMPT} 字符")
    config["system_prompt"] = prompt
    return config


def secure_private_file(path: Path) -> None:
    """POSIX: enforce exactly 0600. Windows ACLs are applied by install.ps1."""
    if os.name == "nt":
        return
    try:
        os.chmod(path, 0o600)
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise ConfigError("无法将配置文件权限设置为 600") from exc
    if mode & 0o077:
        raise ConfigError("配置文件权限不是 600，已拒绝继续")


def write_json_private(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
    temp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
    fd: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(temp, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = None
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        secure_private_file(path)
    except ConfigError:
        raise
    except OSError as exc:
        raise ConfigError("无法安全写入本地配置文件") from exc
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temp.unlink()
        except OSError:
            pass


def ensure_config(path: Path, port: int = DEFAULT_PORT, instance_id: str = "") -> tuple[dict[str, Any], bool]:
    if path.exists():
        return load_config(path), False
    config = default_config(port)
    if instance_id:
        if not INSTANCE_ID_RE.fullmatch(instance_id):
            raise ConfigError("instance_id 格式无效")
        config["key_source"] = "instance"
        config["instance_id"] = instance_id
    config = validate_config(config)
    write_json_private(path, config)
    return config, True


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return ensure_config(path)[0]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError("无法读取本地配置文件") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"本地配置文件不是有效 JSON（第 {exc.lineno} 行）") from None
    if not isinstance(raw, dict):
        raise ConfigError("本地配置文件顶层必须是 JSON 对象")
    config = validate_config(raw)
    if os.name != "nt":
        secure_private_file(path)
    return config


def save_config(path: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_config(config)
    write_json_private(path, validated)
    return validated


def set_independent_key(path: Path, key: str) -> dict[str, Any]:
    key = str(key or "").strip()
    if not key or len(key) > MAX_KEY or "\r" in key or "\n" in key:
        raise ConfigError("API Key 为空或格式异常")
    config = load_config(path)
    config.update(key_source="independent", api_key=key, instance_id="")
    return save_config(path, config)


def _provider_key(provider: Mapping[str, Any]) -> str:
    raw = provider.get("key")
    if isinstance(raw, list):
        return next((str(item).strip() for item in raw if isinstance(item, str) and item.strip()), "")
    if isinstance(raw, str):
        return raw.strip()
    return ""


def extract_deepseek_key(astrbot_config: Mapping[str, Any]) -> str:
    """Read only an explicitly selected DeepSeek provider; ignore other tokens."""
    raw = astrbot_config.get("provider")
    providers = [raw] if isinstance(raw, Mapping) else list(raw) if isinstance(raw, list) else []
    candidates: list[tuple[int, Mapping[str, Any]]] = []
    for provider in providers:
        if not isinstance(provider, Mapping):
            continue
        name = str(provider.get("provider") or "").lower()
        provider_id = str(provider.get("id") or "")
        model = str(provider.get("model") or "")
        api_base = str(provider.get("api_base") or "").lower()
        if provider_id == MODEL or model == MODEL or name == "deepseek" or "api.deepseek.com" in api_base:
            priority = 0 if provider_id == MODEL or model == MODEL else 1
            if provider.get("enable") is not False:
                priority -= 1
            candidates.append((priority, provider))
    for _priority, provider in sorted(candidates, key=lambda item: item[0]):
        key = _provider_key(provider)
        if key:
            return key
    return ""


def read_instance_key(studio_home: Path, instance_id: str) -> str:
    if not INSTANCE_ID_RE.fullmatch(str(instance_id or "")):
        raise KeyConfigError("实例 ID 格式无效，已拒绝读取")
    instances_root = (studio_home / "instances").resolve()
    path = instances_root / instance_id / "data" / "astrbot" / "cmd_config.json"
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        raise KeyConfigError(f"找不到实例 {instance_id} 的 AstrBot 配置文件") from None
    if resolved != instances_root and instances_root not in resolved.parents:
        raise KeyConfigError("实例配置路径越界，已拒绝读取")
    try:
        if resolved.stat().st_size > 8 * 1024 * 1024:
            raise KeyConfigError("实例配置文件过大，已拒绝读取")
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except KeyConfigError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise KeyConfigError("无法解析实例的 AstrBot 配置文件") from None
    if not isinstance(raw, Mapping):
        raise KeyConfigError("实例 AstrBot 配置格式不符合预期")
    key = extract_deepseek_key(raw)
    if not key:
        raise KeyConfigError("实例配置中未找到 DeepSeek deepseek-flash 的 API Key")
    if len(key) > MAX_KEY or "\r" in key or "\n" in key:
        raise KeyConfigError("实例配置中的 API Key 格式异常")
    return key


@dataclass(frozen=True)
class KeyResolution:
    key: str
    source: str


def resolve_key(config: Mapping[str, Any], studio_home: Path) -> KeyResolution:
    source = str(config.get("key_source") or "independent")
    if source == "independent":
        key = str(config.get("api_key") or "").strip()
        if not key:
            raise KeyConfigError(
                "尚未配置独立 API Key。请编辑本机配置文件的 api_key 字段，"
                "或运行 assistant.py --set-key。"
            )
        return KeyResolution(key, source)
    if source == "instance":
        instance_id = str(config.get("instance_id") or "").strip()
        if not instance_id:
            raise KeyConfigError("已选择复用实例 Key，但未配置 instance_id")
        return KeyResolution(read_instance_key(studio_home, instance_id), source)
    raise KeyConfigError("未知的 key_source 配置")


def safe_message(value: Any, secret: str = "", limit: int = 500) -> str:
    text = str(value or "")
    if secret:
        text = text.replace(secret, "<已隐藏>")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("<已隐藏>", text)
    return text[:limit]


class DeepSeekClient:
    def __init__(self, api_url: str = DEEPSEEK_CHAT_URL) -> None:
        self.api_url = api_url

    @staticmethod
    def _detail(body: bytes, secret: str) -> str:
        try:
            parsed = json.loads(body.decode("utf-8", errors="replace"))
        except (UnicodeError, json.JSONDecodeError):
            return ""
        detail = ""
        if isinstance(parsed, Mapping):
            error = parsed.get("error")
            if isinstance(error, Mapping):
                detail = str(error.get("message") or error.get("code") or "")
            elif isinstance(parsed.get("message"), str):
                detail = parsed["message"]
        detail = safe_message(detail, secret, 300).strip()
        return f"：{detail}" if detail else ""

    def complete(self, api_key: str, messages: Sequence[Mapping[str, str]], timeout: int) -> str:
        request = Request(
            self.api_url,
            data=json.dumps({"model": MODEL, "messages": list(messages), "stream": False}, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": f"{APP_NAME}/{APP_VERSION}",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_UPSTREAM + 1)
        except HTTPError as exc:
            try:
                body = exc.read(MAX_UPSTREAM_ERROR)
            except Exception:
                body = b""
            finally:
                exc.close()
            detail = self._detail(body, api_key)
            if exc.code in (401, 403):
                raise DeepSeekError("DeepSeek 鉴权失败，请检查 API Key 是否有效" + detail) from None
            raise DeepSeekError(f"DeepSeek 请求失败（HTTP {int(exc.code)}）{detail}") from None
        except (socket.timeout, TimeoutError):
            raise DeepSeekError(f"DeepSeek 请求超时（{timeout} 秒）", HTTPStatus.GATEWAY_TIMEOUT) from None
        except URLError as exc:
            reason = safe_message(getattr(exc, "reason", ""), api_key, 200)
            raise DeepSeekError("无法连接 DeepSeek 服务" + (f"：{reason}" if reason else "")) from None
        except OSError:
            raise DeepSeekError("连接 DeepSeek 服务时发生网络错误") from None
        if len(raw) > MAX_UPSTREAM:
            raise DeepSeekError("DeepSeek 返回内容过大")
        try:
            data = json.loads(raw.decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
        except (UnicodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise DeepSeekError("DeepSeek 返回了无法解析或缺少内容的响应") from None
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("DeepSeek 返回了空回复")
        return content.strip()


def validate_chat_request(payload: Any) -> tuple[str, list[dict[str, str]]]:
    if not isinstance(payload, Mapping):
        raise AssistantError("请求 JSON 必须是对象")
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        raise AssistantError("请输入消息")
    message = message.strip()
    if len(message) > MAX_MESSAGE:
        raise AssistantError(f"单条消息不能超过 {MAX_MESSAGE} 字符")
    raw_history = payload.get("history", [])
    if raw_history is None:
        raw_history = []
    if not isinstance(raw_history, list):
        raise AssistantError("history 必须是数组")
    if len(raw_history) > MAX_HISTORY:
        raise AssistantError(f"历史消息最多 {MAX_HISTORY} 条")
    history: list[dict[str, str]] = []
    total = len(message)
    for index, item in enumerate(raw_history):
        if not isinstance(item, Mapping):
            raise AssistantError(f"history 第 {index + 1} 项格式无效")
        role, content = item.get("role"), item.get("content")
        if role not in ("user", "assistant"):
            raise AssistantError("history 只允许 user 和 assistant 角色")
        if not isinstance(content, str) or not content.strip():
            raise AssistantError(f"history 第 {index + 1} 项内容为空")
        content = content.strip()
        if len(content) > MAX_MESSAGE:
            raise AssistantError(f"history 第 {index + 1} 项内容过长")
        total += len(content)
        history.append({"role": role, "content": content})
    if total > MAX_TOTAL_CHAT:
        raise AssistantError("对话内容总长度过大，请清空对话后重试")
    return message, history


class AssistantApp:
    def __init__(self, config_path: Path | str, studio_home: Path | str | None = None,
                 api_url: str = DEEPSEEK_CHAT_URL, client: DeepSeekClient | None = None) -> None:
        self.config_path = Path(config_path).expanduser()
        self.studio_home = Path(studio_home).expanduser() if studio_home else default_studio_home()
        self.client = client or DeepSeekClient(api_url)

    def config(self) -> dict[str, Any]:
        return load_config(self.config_path)

    def public_status(self) -> dict[str, Any]:
        config = self.config()
        configured, error = False, ""
        try:
            resolve_key(config, self.studio_home)
            configured = True
        except KeyConfigError as exc:
            error = safe_message(exc)
        return {
            "ok": True, "app": APP_NAME, "version": APP_VERSION,
            "configured": configured, "key_source": config["key_source"],
            "key_error": error, "model": MODEL, "endpoint": DEEPSEEK_CHAT_URL,
        }

    def chat(self, message: str, history: Sequence[Mapping[str, str]]) -> str:
        config = self.config()
        key = resolve_key(config, self.studio_home)
        messages = [{"role": "system", "content": config["system_prompt"]}]
        messages.extend({"role": item["role"], "content": item["content"]} for item in history)
        messages.append({"role": "user", "content": message})
        return self.client.complete(key.key, messages, int(config["timeout_seconds"]))


class AssistantHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], app: AssistantApp) -> None:
        self.app = app
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> AssistantApp:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        path = urlsplit(getattr(self, "path", "")).path
        sys.stderr.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {getattr(self, 'command', '-')} {path}\n")

    def _headers_common(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        )

    def _send(self, status: int, ctype: str, body: bytes) -> None:
        self.send_response(int(status))
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._headers_common()
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _json(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", body)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": safe_message(message)})

    def _host_parts(self) -> tuple[str, int | None] | None:
        raw = self.headers.get("Host", "")
        if not raw:
            return None
        try:
            parts = urlsplit("//" + raw)
            return (parts.hostname or "").lower(), parts.port
        except ValueError:
            return None

    def _actual_port(self) -> int:
        return int(self.server.server_address[1])  # type: ignore[attr-defined]

    def _host_ok(self) -> bool:
        parts = self._host_parts()
        if not parts:
            return False
        host, port = parts
        return host in LOOPBACK_HOSTS and (port if port is not None else 80) == self._actual_port()

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host_parts = self._host_parts()
        if not self._host_ok() or not host_parts:
            return False
        try:
            parsed = urlsplit(origin)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and (parsed.hostname or "").lower() == host_parts[0]
            and (port if port is not None else 80) == self._actual_port()
        )

    def _read_json(self) -> Any:
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise ValueError("Content-Type 必须是 application/json")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("缺少 Content-Length")
        try:
            length = int(raw_length)
        except ValueError:
            raise ValueError("Content-Length 格式无效") from None
        if length < 0 or length > MAX_BODY:
            raise OverflowError("请求体过大")
        body = self.rfile.read(length)
        if len(body) != length:
            raise ValueError("请求体不完整")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError("请求体不是有效 JSON") from None

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._error(HTTPStatus.MISDIRECTED_REQUEST, "Host 头不受信任")
            return
        path = urlsplit(self.path).path
        if path == "/":
            try:
                html = UI_PATH.read_text(encoding="utf-8")
            except OSError:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "找不到 Web UI 文件 ui.html")
                return
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", html.encode("utf-8"))
            return
        if path == "/api/status":
            try:
                self._json(HTTPStatus.OK, self.app.public_status())
            except ConfigError as exc:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            except Exception:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "读取本地配置失败")
            return
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "app": APP_NAME, "version": APP_VERSION})
            return
        if path == "/favicon.ico":
            self._send(HTTPStatus.NO_CONTENT, "image/x-icon", b"")
            return
        self._error(HTTPStatus.NOT_FOUND, "接口不存在")

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._error(HTTPStatus.MISDIRECTED_REQUEST, "Host 头不受信任")
            return
        if not self._origin_ok():
            self._error(HTTPStatus.FORBIDDEN, "跨站请求已被拒绝")
            return
        if urlsplit(self.path).path != "/api/chat":
            self._error(HTTPStatus.NOT_FOUND, "接口不存在")
            return
        try:
            payload = self._read_json()
        except OverflowError as exc:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, str(exc))
            return
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        try:
            message, history = validate_chat_request(payload)
        except AssistantError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        try:
            reply = self.app.chat(message, history)
        except KeyConfigError as exc:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            return
        except DeepSeekError as exc:
            self._error(exc.http_status, str(exc))
            return
        except ConfigError as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        except Exception:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "服务器处理聊天请求时发生内部错误")
            return
        self._json(HTTPStatus.OK, {"ok": True, "reply": reply, "model": MODEL})


def create_server(config_path: Path | str, studio_home: Path | str | None = None,
                  host: str | None = None, port: int | None = None,
                  api_url: str = DEEPSEEK_CHAT_URL,
                  client: DeepSeekClient | None = None) -> AssistantHTTPServer:
    app = AssistantApp(config_path, studio_home, api_url, client)
    config = load_config(app.config_path)
    bind_host = str(host if host is not None else config["host"]).strip().lower()
    if bind_host not in LOOPBACK_HOSTS:
        raise ConfigError("服务只能绑定本机回环地址")
    bind_port = config["port"] if port is None else int(port)
    if not 0 <= bind_port <= 65_535:
        raise ConfigError("监听端口无效")
    return AssistantHTTPServer((bind_host, bind_port), app)


def serve(config_path: Path, studio_home: Path) -> int:
    try:
        server = create_server(config_path, studio_home)
    except ConfigError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1
    config = load_config(config_path)
    shown_port = int(server.server_address[1])
    print(f"{APP_NAME} {APP_VERSION} 已启动：http://127.0.0.1:{shown_port}/")
    print(f"模型固定为 {MODEL}；配置文件：{config_path}")
    try:
        resolve_key(config, studio_home)
        print("API Key 已就绪（内容不会显示）。")
    except KeyConfigError as exc:
        print(f"提示：{safe_message(exc)}")
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\n正在停止服务…")
    finally:
        server.server_close()
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="QQ Bot Studio 可选 AI 助手 B（DeepSeek，标准库服务）")
    p.add_argument("--config", default=str(default_config_path()), help="本地配置文件路径")
    p.add_argument("--studio-home", default=str(default_studio_home()), help="QQ Bot Studio 数据根目录")
    p.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--init-config", action="store_true", help="创建配置模板（不覆盖已有文件）")
    group.add_argument("--set-key", action="store_true", help="交互式保存独立 API Key（不回显）")
    group.add_argument("--check", action="store_true", help="检查配置和 Key，不启动服务")
    group.add_argument("--print-config-path", action="store_true", help="输出默认配置路径")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="初始化端口，默认 8765")
    p.add_argument("--instance-id", default="", help="初始化时显式复用该实例的 Key")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = Path(args.config).expanduser()
    studio_home = Path(args.studio_home).expanduser()
    if args.print_config_path:
        print(config_path)
        return 0
    if args.init_config:
        try:
            config, created = ensure_config(config_path, args.port, args.instance_id)
        except ConfigError as exc:
            print(f"初始化失败：{exc}", file=sys.stderr)
            return 1
        print(("已创建配置文件：" if created else "配置文件已存在，未覆盖：") + str(config_path))
        if not created and args.instance_id:
            print("提示：已有配置不会自动改为复用实例，请手动编辑 key_source / instance_id。")
        print(f"Key 来源：{config['key_source']}；端口：{config['port']}；固定模型：{MODEL}")
        if config["key_source"] == "instance":
            print(f"复用实例 ID：{config['instance_id']}")
        elif not config["api_key"]:
            print("下一步：运行 --set-key 输入独立 DeepSeek API Key，或用编辑器填写 api_key。")
        return 0
    if args.set_key:
        try:
            ensure_config(config_path)
            key = getpass.getpass("请输入 DeepSeek API Key（输入不会回显）：")
            if not key.strip():
                print("未保存：API Key 为空", file=sys.stderr)
                return 2
            set_independent_key(config_path, key)
        except (ConfigError, EOFError, KeyboardInterrupt) as exc:
            print(f"保存失败：{safe_message(exc) if str(exc) else '已取消'}", file=sys.stderr)
            return 1
        print("已保存独立 API Key 到本机配置文件；不会显示 Key 内容。")
        return 0
    if args.check:
        try:
            status = AssistantApp(config_path, studio_home).public_status()
        except ConfigError as exc:
            print(json.dumps({"ok": False, "error": safe_message(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["configured"] else 1
    try:
        return serve(config_path, studio_home)
    except ConfigError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
