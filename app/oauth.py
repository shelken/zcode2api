"""Z.AI OAuth 登录流程（桌面同款链）。

桌面实际流程（日志实证）:
  authorize（浏览器）: GET https://chat.z.ai/api/oauth/authorize
                      ?redirect_uri=zcode://oauth/callback
                      &client_id=client_P8X5CMWmlaRO9gyO-KSqtg
                      &response_type=code&state=<state>
  回调 code → token:  POST https://zcode.z.ai/api/v1/oauth/token
                      {provider: "zai", code, redirect_uri, state}
                      → data.token (zcode JWT, HS256 无过期)

旧的 /oauth/cli/init · /oauth/cli/poll 端点已被 Z.AI 服务端移除（404），
故改为桌面同款链 + 本地回调端口接收 code。
"""

from __future__ import annotations

import secrets
import urllib.parse

import httpx

OAUTH_AUTHORIZE_URL = "https://chat.z.ai/api/oauth/authorize"
OAUTH_TOKEN_URL = "https://zcode.z.ai/api/v1/oauth/token"
OAUTH_CLIENT_ID = "client_P8X5CMWmlaRO9gyO-KSqtg"  # 生产 client_id（asar 实证）
# 回调走容器已映射端口（compose 3000:3000），浏览器在宿主机可直接访问
OAUTH_REDIRECT_URI = "http://127.0.0.1:3000/admin/api/login/callback"

# flow_id → 收到的 code（内存态，本机单用户足够）
_codes: dict[str, str] = {}
# flow_id → 兑换后的 ready 结果
_ready: dict[str, dict] = {}

# 回调 code 由 admin_api 的 /login/callback 接收（走容器 3000 端口）


class ZaiAuthFlow:
    def __init__(self, api_base: str = "https://zcode.z.ai/api/v1") -> None:
        self.api_base = api_base
        # flow_id 即本地回调服务的 state（校验防伪造）
        self.state = secrets.token_hex(32)

    def build_authorize_url(self) -> str:
        params = {
            "redirect_uri": OAUTH_REDIRECT_URI,
            "client_id": OAUTH_CLIENT_ID,
            "response_type": "code",
            "state": self.state,
        }
        return f"{OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    async def init(self) -> tuple[str, str]:
        """返回 (flow_id, authorize_url)。flow_id = state。"""
        return self.state, self.build_authorize_url()

    async def poll(self, flow_id: str) -> dict:
        """查回调是否收到 code；收到则兑换 token 并返回 ready。"""
        code = _codes.pop(flow_id, None)
        if not code:
            return {"status": "pending"}
        try:
            token = await self.exchange_token(code)
            _ready[flow_id] = {"status": "ready", "token": token}
            return _ready.pop(flow_id)
        except Exception as err:  # noqa: BLE001
            return {"status": "failed", "message": str(err)}

    async def exchange_api_key(self, access_token: str) -> str:
        """OAuth access_token → 业务 token → 机构/项目 → API Key（回退用）。"""
        async with httpx.AsyncClient(timeout=30) as client:
            login = await client.post(
                "https://api.z.ai/api/auth/z/login",
                headers={"Content-Type": "application/json"},
                json={"token": access_token},
            )
            login.raise_for_status()
            biz = (login.json().get("data") or {})
            biz_token = biz.get("access_token") or biz.get("accessToken")
            if not biz_token:
                raise RuntimeError("返回数据中不含业务凭证")

            info = await client.get(
                "https://api.z.ai/api/biz/customer/getCustomerInfo",
                headers={"Authorization": f"Bearer {biz_token}"},
            )
            info.raise_for_status()
            orgs = (info.json().get("data") or {}).get("organizations") or []
            org = next((o for o in orgs if "默认机构" in (o.get("organizationName") or "")), None) or (orgs[0] if orgs else None)
            if not org:
                raise RuntimeError("找不到可用的机构")
            projects = org.get("projects") or []
            proj = next((p for p in projects if "默认项目" in (p.get("projectName") or "")), None) or (projects[0] if projects else None)
            if not proj:
                raise RuntimeError("找不到可用的项目")

            org_id, proj_id = org["organizationId"], proj["projectId"]
            key_url = f"https://api.z.ai/api/biz/v1/organization/{org_id}/projects/{proj_id}/api_keys"

            keys_res = await client.get(key_url, headers={"Authorization": f"Bearer {biz_token}"})
            keys_res.raise_for_status()
            keys = keys_res.json().get("data") or []
            key_obj = next((k for k in keys if k.get("name") == "zcode-api-key"), None)
            if not key_obj:
                create = await client.post(
                    key_url,
                    headers={"Authorization": f"Bearer {biz_token}", "Content-Type": "application/json"},
                    json={"name": "zcode-api-key"},
                )
                create.raise_for_status()
                key_obj = create.json().get("data")

            api_key = (key_obj or {}).get("apiKey")
            if not api_key:
                raise RuntimeError("获取 API Key 失败")

            copy = await client.get(
                f"{key_url}/copy/{api_key}",
                headers={"Authorization": f"Bearer {biz_token}"},
            )
            copy.raise_for_status()
            secret_key = (copy.json().get("data") or {}).get("secretKey")
            if not secret_key:
                raise RuntimeError("未能解密 Secret Key")
        return f"{api_key}.{secret_key}"

    async def exchange_token(self, code: str, state: str | None = None) -> str:
        """code → zcode JWT。state 默认用本 flow 的，回调场景可传入匹配的 flow state。"""
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                OAUTH_TOKEN_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "provider": "zai",
                    "code": code,
                    "redirect_uri": OAUTH_REDIRECT_URI,
                    "state": state or self.state,
                },
            )
        res.raise_for_status()
        data = res.json().get("data") or {}
        token = data.get("token")
        if not token:
            raise RuntimeError(f"token 兑换失败: {res.text[:200]}")
        return token
