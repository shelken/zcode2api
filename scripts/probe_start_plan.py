#!/usr/bin/env python3
"""交互式验证 billing/balance 的 Start Plan 发放行为。

不会保存或打印 OAuth 凭据。请使用尚未获得 Start Plan 的账号。
"""

from __future__ import annotations

import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import settings  # noqa: E402
from app.oauth import OAUTH_AUTHORIZE_URL, OAUTH_CLIENT_ID, OAUTH_TOKEN_URL  # noqa: E402

PORT = 3001
CALLBACK = f"http://127.0.0.1:{PORT}/callback"
BILLING_BALANCE = f"{settings.ZCODE_BILLING_BASE}/billing/balance"


def has_start_plan(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("hasActiveStartPlan") is True:
            return True
        if "start-plan" in str(value.get("plan_id", value.get("planId", ""))):
            return True
        return any(has_start_plan(item) for item in value.values())
    if isinstance(value, list):
        return any(has_start_plan(item) for item in value)
    return False


def receive_code(state: str) -> str:
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(query.query)
            if query.path == "/callback" and params.get("state") == [state]:
                result["code"] = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write("Login received. You can close this page.".encode())
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, *_: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    params = {
        "redirect_uri": CALLBACK,
        "client_id": OAUTH_CLIENT_ID,
        "response_type": "code",
        "state": state,
    }
    webbrowser.open(f"{OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}")
    server.handle_request()
    server.server_close()
    return result["code"]


def fetch_plan(client: httpx.Client, token: str, version: str | None = None) -> bool:
    headers = {"Authorization": f"Bearer {token}"}
    if version:
        headers["X-Zcode-App-Version"] = version
    response = client.get(BILLING_BALANCE, headers=headers)
    response.raise_for_status()
    return has_start_plan(response.json())


def main() -> None:
    state = secrets.token_hex(32)
    print("请在浏览器中使用尚未获得 Start Plan 的账号登录。")
    code = receive_code(state)

    with httpx.Client(timeout=30) as client:
        response = client.post(
            OAUTH_TOKEN_URL,
            headers={"Content-Type": "application/json"},
            json={"provider": "zai", "code": code, "redirect_uri": CALLBACK, "state": state},
        )
        response.raise_for_status()
        token = (response.json().get("data") or {}).get("token")
        if not token:
            raise RuntimeError("OAuth 响应缺少 Coding Plan JWT")

        baseline = fetch_plan(client, token)
        print(f"仅 Authorization: Plan={'有' if baseline else '无'}")
        if baseline:
            print("账号实验前已有 Plan，无法验证版本头。")
            return

        activated = fetch_plan(client, token, settings.ZCODE_APP_VERSION)
        print(f"加入 X-Zcode-App-Version={settings.ZCODE_APP_VERSION}: Plan={'有' if activated else '无'}")
        print("结论：版本头触发 Plan。" if activated else "结论：版本头未触发 Plan。")


if __name__ == "__main__":
    main()
