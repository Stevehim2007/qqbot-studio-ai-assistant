from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
import socket
import stat
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import assistant  # noqa: E402

SECRET = "sk-unit-test-secret-1234567890"


def write_config(path: Path, **overrides: Any) -> dict[str, Any]:
    assistant.ensure_config(path)
    config = assistant.load_config(path)
    config.update(overrides)
    return assistant.save_config(path, config)


class FakeDeepSeek:
    def __init__(self, status: int = 200, reply: str = "这是 mock DeepSeek 的中文回复。",
                 raw_body: bytes | None = None) -> None:
        self.status, self.reply, self.raw_body = status, reply, raw_body
        self.calls: list[dict[str, Any]] = []
        outer = self

        class FakeHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def do_POST(self) -> None:  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                try:
                    parsed = json.loads(body.decode("utf-8"))
                except Exception:
                    parsed = None
                outer.calls.append({"path": self.path, "headers": dict(self.headers.items()), "json": parsed})
                payload = outer.raw_body or json.dumps(
                    {"choices": [{"message": {"content": outer.reply}}]}, ensure_ascii=False
                ).encode("utf-8")
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, fmt: str, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1/chat/completions"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class RunningAssistant:
    def __init__(self, config: Path, studio_home: Path, api_url: str,
                 bind_host: str = "127.0.0.1", bind_port: int = 0) -> None:
        self.bind_host = bind_host
        self.server = assistant.create_server(
            config, studio_home, host=bind_host, port=bind_port, api_url=api_url
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.listen_host, self.port = self.server.server_address[:2]
        # 0.0.0.0 is a bind address, not a destination; connect locally.
        self.host = "127.0.0.1" if str(self.listen_host) == "0.0.0.0" else str(self.listen_host)

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None,
                headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection(self.host, self.port, timeout=8)
        hdrs = dict(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        conn.request(method, path, body=body, headers=hdrs)
        response = conn.getresponse()
        raw = response.read()
        result = response.status, {k.lower(): v for k, v in response.getheaders()}, raw
        conn.close()
        return result

    def json_request(self, method: str, path: str, payload: dict[str, Any] | None = None,
                     headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], dict[str, Any]]:
        status, headers, raw = self.request(method, path, payload, headers)
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeError, json.JSONDecodeError):
            data = {"raw": raw.decode("utf-8", errors="replace")}
        return status, headers, data

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = self.root / "ai" / "config.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_init_template_and_posix_mode_600(self) -> None:
        config, created = assistant.ensure_config(self.config, port=9876)
        self.assertTrue(created)
        self.assertEqual(config["port"], 9876)
        self.assertEqual(config["host"], "127.0.0.1")
        self.assertEqual(config["public_host"], "")
        self.assertEqual(config["key_source"], "independent")
        self.assertEqual(config["api_key"], "")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)

    def test_init_with_explicit_instance_and_no_overwrite(self) -> None:
        config, created = assistant.ensure_config(self.config, port=9011, instance_id="bot-01")
        self.assertTrue(created)
        self.assertEqual((config["key_source"], config["instance_id"]), ("instance", "bot-01"))
        again, created = assistant.ensure_config(self.config, port=9022)
        self.assertFalse(created)
        self.assertEqual(again["port"], 9011)

    def test_invalid_config_is_rejected(self) -> None:
        for value in ({"host": "192.168.1.10"}, {"host": "example.com"}, {"port": 70000},
                      {"key_source": "other"},
                      {"key_source": "instance", "instance_id": "../escape"}):
            with self.assertRaises(assistant.ConfigError):
                assistant.validate_config(value)
        for public_host in ("https://example.com", "example.com:8766", "bad_host",
                            "0.0.0.0", "::", "example.com/path"):
            with self.assertRaises(assistant.ConfigError):
                assistant.validate_config({"public_host": public_host})

    def test_public_bind_config_and_public_host_are_explicit(self) -> None:
        config = assistant.validate_config(
            {"host": "0.0.0.0", "public_host": "Assistant.Example.com", "port": 8766}
        )
        self.assertEqual(config["host"], "0.0.0.0")
        self.assertEqual(config["public_host"], "assistant.example.com")
        # Defaults must remain safe loopback.
        self.assertEqual(assistant.default_config()["host"], "127.0.0.1")
        ipv6 = assistant.validate_config({"public_host": "[2001:db8::1]"})
        self.assertEqual(ipv6["public_host"], "2001:db8::1")

    def test_permissions_are_tightened_and_key_not_in_status(self) -> None:
        write_config(self.config, api_key=SECRET)
        if os.name != "nt":
            os.chmod(self.config, 0o644)
            assistant.load_config(self.config)
            self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        status = assistant.AssistantApp(self.config, self.root).public_status()
        self.assertTrue(status["configured"])
        self.assertNotIn(SECRET, json.dumps(status, ensure_ascii=False))

    def test_set_independent_key_switches_from_instance_without_output(self) -> None:
        write_config(self.config, key_source="instance", instance_id="bot-1")
        assistant.set_independent_key(self.config, SECRET)
        config = assistant.load_config(self.config)
        self.assertEqual(config["key_source"], "independent")
        self.assertEqual(config["api_key"], SECRET)
        self.assertEqual(config["instance_id"], "")


class InstanceKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.studio = self.root / ".local/share/qqbot-studio"
        self.instance = self.studio / "instances/bot-1/data/astrbot"
        self.instance.mkdir(parents=True)
        self.path = self.instance / "cmd_config.json"
        self.config = self.root / "ai-config.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        if os.name != "nt":
            os.chmod(self.path, 0o600)

    def test_extract_deepseek_key_ignores_unrelated_provider_token(self) -> None:
        payload = {"platform": [{"token": "platform-secret"}], "provider": [
            {"id": "other", "provider": "openai", "key": ["other-key"]},
            {"id": "deepseek-flash", "provider": "deepseek", "model": "deepseek-flash",
             "api_base": "https://api.deepseek.com/v1", "key": [SECRET]},
        ]}
        self.assertEqual(assistant.extract_deepseek_key(payload), SECRET)
        self._write(payload)
        self.assertEqual(assistant.read_instance_key(self.studio, "bot-1"), SECRET)

    def test_traversal_and_missing_key_are_safe(self) -> None:
        for bad in ("../escape", "bot/1", "..", "", "a\\b"):
            with self.assertRaises(assistant.KeyConfigError):
                assistant.read_instance_key(self.studio, bad)
        self._write({"provider": [{"id": "other", "key": ["not-deepseek"]}]})
        with self.assertRaises(assistant.KeyConfigError) as ctx:
            assistant.read_instance_key(self.studio, "bot-1")
        self.assertNotIn("not-deepseek", str(ctx.exception))

    def test_instance_key_used_internally_but_never_returned(self) -> None:
        self._write({"provider": [{"id": "deepseek-flash", "provider": "deepseek",
                                   "model": "deepseek-flash", "key": [SECRET]}]})
        write_config(self.config, key_source="instance", instance_id="bot-1", api_key="")
        fake = FakeDeepSeek(reply="实例 Key mock 回复")
        running = RunningAssistant(self.config, self.studio, fake.url)
        try:
            status, _headers, data = running.json_request("GET", "/api/status")
            self.assertEqual(status, 200)
            self.assertTrue(data["configured"])
            self.assertNotIn(SECRET, json.dumps(data))
            status, _headers, data = running.json_request("POST", "/api/chat", {"message": "实例测试"})
            self.assertEqual(status, 200, data)
            self.assertNotIn(SECRET, json.dumps(data))
            self.assertEqual(fake.calls[0]["headers"]["Authorization"], f"Bearer {SECRET}")
        finally:
            running.close()
            fake.close()


class HttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.studio = self.root / ".local/share/qqbot-studio"
        self.config = self.root / "ai-assistant/config.json"
        write_config(self.config, api_key=SECRET)
        self.fake = FakeDeepSeek()
        self.running = RunningAssistant(self.config, self.studio, self.fake.url)

    def tearDown(self) -> None:
        self.running.close()
        self.fake.close()
        self.tmp.cleanup()

    def test_ui_status_and_security_headers(self) -> None:
        status, headers, raw = self.running.request("GET", "/")
        self.assertEqual(status, 200)
        text = raw.decode("utf-8")
        for expected in ("QQ Bot Studio · AI 助手 B", "不替代离线知识库助手 A",
                         "deepseek-flash", "禁止裸奔公网"):
            self.assertIn(expected, text)
        self.assertIn("content-security-policy", headers)
        self.assertIn("text/html", headers["content-type"])
        status, _headers, data = self.running.json_request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(data["configured"])
        self.assertEqual(data["model"], "deepseek-flash")
        self.assertNotIn(SECRET, json.dumps(data))

    def test_chat_uses_mock_upstream_fixed_model(self) -> None:
        self.fake.reply = "mock 测试通过"
        status, _headers, data = self.running.json_request("POST", "/api/chat", {
            "message": "你好",
            "history": [{"role": "user", "content": "上一问"},
                        {"role": "assistant", "content": "上一答"}],
        })
        self.assertEqual(status, 200, data)
        self.assertEqual(data["reply"], "mock 测试通过")
        self.assertEqual(data["model"], "deepseek-flash")
        self.assertNotIn(SECRET, json.dumps(data))
        call = self.fake.calls[0]
        self.assertEqual(call["path"], "/v1/chat/completions")
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {SECRET}")
        self.assertEqual(call["json"]["model"], "deepseek-flash")
        self.assertFalse(call["json"]["stream"])
        self.assertEqual([m["role"] for m in call["json"]["messages"]],
                         ["system", "user", "assistant", "user"])

    def test_unconfigured_key_returns_safe_503(self) -> None:
        write_config(self.config, api_key="")
        status, _headers, data = self.running.json_request("POST", "/api/chat", {"message": "你好"})
        self.assertEqual(status, 503)
        self.assertIn("API Key", data["error"])
        self.assertEqual(self.fake.calls, [])
        status, _headers, data = self.running.json_request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertFalse(data["configured"])
        self.assertTrue(data["key_error"])

    def test_mock_upstream_error_never_leaks_key(self) -> None:
        self.fake.close()
        body = json.dumps({"error": {"message": f"invalid key {SECRET}"}}).encode()
        self.fake = FakeDeepSeek(status=401, raw_body=body)
        self.running.close()
        self.running = RunningAssistant(self.config, self.studio, self.fake.url)
        status, _headers, data = self.running.json_request("POST", "/api/chat", {"message": "错误测试"})
        self.assertEqual(status, 502)
        rendered = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(SECRET, rendered)
        self.assertIn("鉴权失败", rendered)

    def test_invalid_input_content_type_host_and_origin(self) -> None:
        for payload in ({}, {"message": ""}, {"message": "ok", "history": [{"role": "system", "content": "bad"}]}):
            status, _headers, data = self.running.json_request("POST", "/api/chat", payload)
            self.assertEqual(status, 400, data)
        status, _headers, _raw = self.running.request("POST", "/api/chat", headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 400)
        status, _headers, data = self.running.json_request(
            "GET", "/api/status",
            headers={"Host": f"assistant.example.com:{self.running.port}"})
        self.assertEqual(status, 421)
        self.assertEqual(data["code"], "invalid_host")
        self.assertEqual(data["listen_mode"], "loopback")
        self.assertEqual(data["expected_port"], self.running.port)
        status, _headers, _raw = self.running.request(
            "GET", "/api/status",
            headers={"Host": f"203.0.113.10:{self.running.port}"})
        self.assertEqual(status, 421)
        status, _headers, _raw = self.running.request("POST", "/api/chat", {"message": "ok"},
                                                      headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.fake.calls, [])

    def test_upstream_redirect_is_refused_without_leaking_key(self) -> None:
        self.fake.close()
        self.fake = FakeDeepSeek(status=302, raw_body=b"")
        self.running.close()
        self.running = RunningAssistant(self.config, self.studio, self.fake.url)
        status, _headers, data = self.running.json_request("POST", "/api/chat", {"message": "重定向测试"})
        self.assertEqual(status, 502)
        rendered = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(SECRET, rendered)
        self.assertIn("不允许的重定向", rendered)

    def test_same_origin_and_health(self) -> None:
        origin = f"http://127.0.0.1:{self.running.port}"
        status, _headers, data = self.running.json_request(
            "POST", "/api/chat", {"message": "同源"}, headers={"Origin": origin})
        self.assertEqual(status, 200, data)
        status, _headers, data = self.running.json_request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["listen_mode"], "loopback")
        self.assertEqual(data["listen_port"], self.running.port)
        self.assertNotIn(SECRET, json.dumps(data))


class PublicBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.studio = self.root / ".local/share/qqbot-studio"
        self.config = self.root / "ai-assistant/config.json"
        write_config(
            self.config,
            api_key=SECRET,
            host="0.0.0.0",
            public_host="assistant.example.com",
        )
        self.fake = FakeDeepSeek(reply="公网模式 mock 回复")
        self.running = RunningAssistant(
            self.config, self.studio, self.fake.url, bind_host="0.0.0.0"
        )

    def tearDown(self) -> None:
        self.running.close()
        self.fake.close()
        self.tmp.cleanup()

    def _host(self, hostname: str = "assistant.example.com") -> str:
        return f"{hostname}:{self.running.port}"

    def test_create_server_binds_all_interfaces(self) -> None:
        self.assertEqual(str(self.running.listen_host), "0.0.0.0")

    def test_public_host_ip_ipv6_and_origin_are_accepted(self) -> None:
        for hostname in ("assistant.example.com", "203.0.113.10", "[2001:db8::1]"):
            status, _headers, data = self.running.json_request(
                "GET", "/api/health", headers={"Host": self._host(hostname)}
            )
            self.assertEqual(status, 200, (hostname, data))

        host = self._host()
        status, _headers, data = self.running.json_request(
            "POST", "/api/chat", {"message": "公网 HTTP"},
            headers={"Host": host, "Origin": f"http://{host}"},
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(data["reply"], "公网模式 mock 回复")
        self.assertNotIn(SECRET, json.dumps(data, ensure_ascii=False))

        status, _headers, data = self.running.json_request(
            "POST", "/api/chat", {"message": "公网 HTTPS"},
            headers={"Host": host, "Origin": f"https://{host}"},
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(len(self.fake.calls), 2)

    def test_public_mode_status_does_not_leak_key(self) -> None:
        status, _headers, data = self.running.json_request(
            "GET", "/api/status", headers={"Host": self._host()}
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["host"], "0.0.0.0")
        self.assertEqual(data["public_host"], "assistant.example.com")
        self.assertNotIn(SECRET, json.dumps(data, ensure_ascii=False))

    def test_public_mode_health_reachable_via_loopback_host(self) -> None:
        status, _headers, data = self.running.json_request(
            "GET", "/api/health",
            headers={"Host": f"127.0.0.1:{self.running.port}"},
        )
        self.assertEqual(status, 200, data)
        self.assertEqual(data["listen_mode"], "public_bind")
        self.assertEqual(data["listen_host"], "0.0.0.0")
        self.assertEqual(data["listen_port"], self.running.port)

    def test_public_mode_rejects_bad_hosts_and_wrong_port(self) -> None:
        status, _headers, data = self.running.json_request(
            "GET", "/api/health",
            headers={"Host": f"0.0.0.0:{self.running.port}"},
        )
        self.assertEqual(status, 421)
        self.assertEqual(data["code"], "invalid_host")
        self.assertEqual(data["listen_mode"], "public_bind")
        self.assertEqual(data["expected_port"], self.running.port)
        wrong_port = self.running.port + 1 if self.running.port < 65535 else self.running.port - 1
        bad_hosts = [
            f"assistant.example.com:{wrong_port}",
            "assistant.example.com",
            f"0.0.0.0:{self.running.port}",
            f"bad host:{self.running.port}",
            f"assistant.example.com/path:{self.running.port}",
            f"assistant.example.com:{self.running.port}:extra",
            f"[::1:{self.running.port}",
            f"user@assistant.example.com:{self.running.port}",
        ]
        for host in bad_hosts:
            status, _headers, _data = self.running.request(
                "GET", "/api/health", headers={"Host": host}
            )
            self.assertEqual(status, 421, host)

    def test_public_mode_rejects_mismatched_origin(self) -> None:
        host = self._host()
        bad_origins = [
            f"http://other.example.com:{self.running.port}",
            f"http://assistant.example.com:{self.running.port + 1}",
            f"ftp://assistant.example.com:{self.running.port}",
            f"http://assistant.example.com:{self.running.port}/path",
            "null",
        ]
        for origin in bad_origins:
            status, _headers, data = self.running.json_request(
                "POST", "/api/chat", {"message": "不应发送"},
                headers={"Host": host, "Origin": origin},
            )
            self.assertEqual(status, 403, origin)
            self.assertEqual(data["code"], "invalid_origin")
            self.assertEqual(data["expected_port"], self.running.port)
        self.assertEqual(self.fake.calls, [])

    def test_public_startup_messages_warn_and_never_include_key(self) -> None:
        config = assistant.load_config(self.config)
        text = "\n".join(assistant.startup_messages(config, "0.0.0.0", 8766))
        self.assertIn("实际监听 0.0.0.0:8766", text)
        self.assertIn("socket", text)
        self.assertIn("assistant.example.com:8766", text)
        for warning in ("没有内置用户认证", "禁止裸奔公网", "防火墙", "VPN", "反向代理"):
            self.assertIn(warning, text)
        self.assertNotIn(SECRET, text)
        loopback = assistant.startup_messages(
            {**config, "host": "127.0.0.1", "public_host": ""}, "127.0.0.1", 8766
        )
        self.assertTrue(any("本机回环" in line for line in loopback))
        self.assertTrue(any("实际监听 socket" in line for line in loopback))
        self.assertFalse(any("禁止裸奔公网" in line for line in loopback))


class DiagnoseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.studio = self.root / ".local/share/qqbot-studio"
        self.config = self.root / "ai-assistant/config.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_old_config_without_public_host_is_still_compatible(self) -> None:
        port = free_port()
        self.config.parent.mkdir(parents=True)
        self.config.write_text(json.dumps({
            "version": 1,
            "host": "127.0.0.1",
            "port": port,
            "key_source": "independent",
            "api_key": "",
            "timeout_seconds": 120,
            "system_prompt": "旧配置兼容测试",
        }, ensure_ascii=False), encoding="utf-8")
        if os.name != "nt":
            os.chmod(self.config, 0o600)
        config = assistant.load_config(self.config)
        self.assertEqual(config["public_host"], "")
        self.assertEqual(config["port"], port)
        self.assertEqual(config["host"], "127.0.0.1")

    def test_diagnose_loopback_not_running_and_cli_has_no_key(self) -> None:
        port = free_port()
        write_config(self.config, host="127.0.0.1", port=port, api_key=SECRET)
        report, ok = assistant.diagnose(self.config, self.studio)
        self.assertTrue(ok)
        self.assertTrue(report["ok"])
        self.assertFalse(report["ready_for_chat"])  # server not running yet
        self.assertTrue(report["configured"])
        self.assertEqual(report["key_source"], "independent")
        self.assertEqual(report["host"], "127.0.0.1")
        self.assertEqual(report["port"], port)
        self.assertTrue(report["bind_test"]["ok"])
        self.assertFalse(report["health"]["ok"])
        self.assertFalse(report["host_guard"]["checked"])
        self.assertEqual(report["external_reachability"], "not_verified")
        rendered = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(SECRET, rendered)
        self.assertIn("security_warnings", report)
        self.assertIn("SSH", " ".join(report["security_warnings"]))

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = assistant.main([
                "--config", str(self.config),
                "--studio-home", str(self.studio),
                "--diagnose",
            ])
        self.assertEqual(rc, 0)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["port"], port)
        self.assertNotIn(SECRET, output.getvalue())

    def test_diagnose_running_public_bind_reports_socket_health_and_host_guard(self) -> None:
        port = free_port("0.0.0.0")
        write_config(
            self.config,
            host="0.0.0.0",
            public_host="192.144.206.201",
            port=port,
            api_key=SECRET,
        )
        fake = FakeDeepSeek()
        running = RunningAssistant(
            self.config, self.studio, fake.url, bind_host="0.0.0.0", bind_port=port
        )
        try:
            report, ok = assistant.diagnose(self.config, self.studio)
        finally:
            running.close()
            fake.close()
        self.assertTrue(ok)
        self.assertTrue(report["ok"])
        self.assertTrue(report["ready_for_chat"])
        self.assertEqual(report["public_host"], "192.144.206.201")
        self.assertEqual(report["url"], f"http://192.144.206.201:{port}/")
        self.assertEqual(report["listener"]["host"], "0.0.0.0")
        self.assertEqual(report["listener"]["port"], port)
        self.assertEqual(report["listener"]["mode"], "public_bind")
        self.assertEqual(report["listener"]["source"], "health")
        self.assertTrue(report["listener_matches_config"])
        self.assertTrue(report["bind_test"]["port_in_use"])
        self.assertTrue(report["health"]["ok"])
        self.assertTrue(report["public_host_health"]["ok"])
        self.assertTrue(report["host_guard"]["checked"])
        self.assertTrue(report["host_guard"]["ok"])
        self.assertEqual(report["host_guard"]["status"], 421)
        self.assertEqual(report["host_guard"]["code"], "invalid_host")
        self.assertEqual(report["external_reachability"], "not_verified")
        warnings = " ".join(report["security_warnings"])
        for word in ("没有内置用户认证", "禁止裸奔公网", "云安全组", "防火墙", "VPN", "反向代理"):
            self.assertIn(word, warnings)
        self.assertIn("192.144.206.201", report["external_access_note"])
        rendered = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(SECRET, rendered)
        self.assertNotIn("api_key", rendered)

    def test_diagnose_detects_non_assistant_port_occupancy(self) -> None:
        port = free_port()
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            holder.bind(("127.0.0.1", port))
            write_config(self.config, host="127.0.0.1", port=port, api_key="")
            report, ok = assistant.diagnose(self.config, self.studio)
        finally:
            holder.close()
        self.assertFalse(ok)
        self.assertFalse(report["ok"])
        self.assertTrue(report["bind_test"]["port_in_use"])
        self.assertFalse(report["health"]["ok"])
        self.assertIn("占用", " ".join(report["hints"]))

    def test_diagnose_flags_management_port_8765(self) -> None:
        write_config(
            self.config,
            host="127.0.0.1",
            port=assistant.MANAGEMENT_PORT,
            api_key="",
        )
        report, ok = assistant.diagnose(self.config, self.studio)
        self.assertFalse(ok)
        self.assertTrue(report["management_port_conflict"])
        self.assertIn("8765", " ".join(report["security_warnings"]))
        self.assertIn("8766", " ".join(report["hints"]))


class ValidationTests(unittest.TestCase):
    def test_validate_and_redact(self) -> None:
        message, history = assistant.validate_chat_request({
            "message": "  你好  ", "history": [{"role": "assistant", "content": " 回答 "}]
        })
        self.assertEqual((message, history), ("你好", [{"role": "assistant", "content": "回答"}]))
        with self.assertRaises(assistant.AssistantError):
            assistant.validate_chat_request({"message": "x", "history": [
                {"role": "user", "content": "x"}] * (assistant.MAX_HISTORY + 1)})
        redacted = assistant.safe_message(
            f"key={SECRET} Authorization: Bearer abcdefghijklmnop api_key=other-secret", SECRET)
        for value in (SECRET, "abcdefghijklmnop", "other-secret"):
            self.assertNotIn(value, redacted)

    def test_cli_init_and_check_do_not_print_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            with mock.patch("builtins.print") as output:
                self.assertEqual(assistant.main(["--config", str(config), "--init-config"]), 0)
            self.assertNotIn(SECRET, " ".join(str(call) for call in output.call_args_list))

            public_config = Path(tmp) / "public-config.json"
            with mock.patch("builtins.print") as output:
                self.assertEqual(assistant.main([
                    "--config", str(public_config), "--init-config",
                    "--host", "0.0.0.0", "--public-host", "assistant.example.com",
                ]), 0)
            public_output = " ".join(str(call) for call in output.call_args_list)
            self.assertIn("监听：0.0.0.0", public_output)
            self.assertIn("禁止裸奔公网", public_output)
            loaded_public = assistant.load_config(public_config)
            self.assertEqual(loaded_public["host"], "0.0.0.0")
            self.assertEqual(loaded_public["public_host"], "assistant.example.com")
            assistant.set_independent_key(config, SECRET)
            with mock.patch("builtins.print") as output:
                rc = assistant.main(["--config", str(config), "--check"])
            rendered = " ".join(str(call) for call in output.call_args_list)
            self.assertEqual(rc, 0)
            self.assertNotIn(SECRET, rendered)
            self.assertIn("deepseek-flash", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
