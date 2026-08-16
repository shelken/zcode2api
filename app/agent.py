"""上游请求构建。

负责根据账号凭证选择端点、组装请求头。实际发送与流式透传在 routes/gateway.py。
"""

from __future__ import annotations

import uuid

from . import settings
from .models import Account

# 透传客户端 header 时需要剔除的字段
_DROP_HEADERS = {
    "host",
    "content-length",
    "x-api-key",
    "authorization",
    "user-agent",
    "http-referer",
    "accept-encoding",
    "connection",
    "x-aliyun-captcha-verify-param",
    "x-aliyun-captcha-verify-region",
}


def _new_id() -> str:
    """与桌面客户端一致的 trace / query / request / session id。"""
    return str(uuid.uuid4())


def _official_identity_headers() -> dict:
    """完整复刻桌面客户端 /v1/messages 请求的身份头（黄金样本 19 头）。

    注意：模型 /v1/messages 请求不带 x-device-mid / x-client-language /
    x-client-timezone / x-release-channel（那些是 API-client 请求才有），
    带多了反而不一致。
    """
    return {
        "X-Zcode-App-Version": "3.7.7",
        "X-Zcode-Agent": "glm",
        "X-Title": "Z Code@electron",
        "HTTP-Referer": "https://zcode.z.ai",
        "X-Platform": "darwin-arm64",
        "X-Os-Category": "macos",
        "X-Os-Version": "25.5.0",
        "X-Query-Id": _new_id(),
        "X-Request-Id": _new_id(),
        "X-Session-Id": _new_id(),
        "X-Zcode-Trace-Id": _new_id(),
    }


def build_request(
    account: Account,
    body: dict,
    verify_param: str | None,
    incoming_headers: dict | None = None,
) -> tuple[str, dict]:
    """返回 (目标 URL, 请求头)。"""
    provider = account.provider

    if provider == "zai":
        if account.mode == "jwt" and account.jwt_token:
            target_url = settings.UPSTREAM["zai"]
            jwt = account.jwt_token
            auth = {
                "Authorization": f"Bearer {jwt}",
                # 桌面客户端双头认证：x-api-key 也携带同一 JWT
                "x-api-key": jwt,
            }
        elif account.api_key:
            target_url = settings.UPSTREAM["zai_fallback"]
            auth = {"x-api-key": account.api_key}
        else:
            raise RuntimeError("账号缺少有效凭证")
    elif provider == "bigmodel":
        target_url = settings.UPSTREAM["bigmodel"]
        if not account.api_key:
            raise RuntimeError("BigModel 账号缺少 API Key")
        auth = {"x-api-key": account.api_key}
    else:
        raise RuntimeError(f"未知提供商: {provider}")

    headers = {
        "content-type": "application/json",
        **auth,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "mid-conversation-system-2026-04-07",
        # 桌面真实 UA（带 ai-sdk 版本号）
        "User-Agent": "ZCode/3.7.7 ai-sdk/provider-utils/4.0.27 runtime/node.js/24",
        **_official_identity_headers(),
    }
    if verify_param:
        headers["X-Aliyun-Captcha-Verify-Param"] = verify_param
        headers["X-Aliyun-Captcha-Verify-Region"] = "sgp"

    for key, value in (incoming_headers or {}).items():
        lower = key.lower()
        if lower in _DROP_HEADERS or lower.startswith("x-zcode"):
            continue
        headers[key] = value

    return target_url, headers