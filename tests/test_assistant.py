from __future__ import annotations

import http.client
import json
import os
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


class RunningAssistant:
    def __init__(self, config: Path, studio_home: Path, api_url: str) -> None:
        self.server = assistant.create_server(config, studio_home, host="127.0.0.1", port=0, api_url=api_url)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

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
        for value in ({"host": "0.0.0.0"}, {"port": 70000}, {"key_source": "other"},
                      {"key_source": "instance", "instance_id": "../escape"}):
            with self.assertRaises(assistant.ConfigError):
                assistant.validate_config(value)

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
        for expected in ("QQ Bot Studio · AI 助手 B", "不替代离线知识库助手 A", "deepseek-flash"):
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
        status, _headers, _raw = self.running.request("GET", "/api/status", headers={"Host": "evil.example"})
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
        self.assertNotIn(SECRET, json.dumps(data))


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
            assistant.set_independent_key(config, SECRET)
            with mock.patch("builtins.print") as output:
                rc = assistant.main(["--config", str(config), "--check"])
            rendered = " ".join(str(call) for call in output.call_args_list)
            self.assertEqual(rc, 0)
            self.assertNotIn(SECRET, rendered)
            self.assertIn("deepseek-flash", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
