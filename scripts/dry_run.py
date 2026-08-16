#!/usr/bin/env python3
"""Dry-run：对比网关生成的请求与黄金桌面请求（捕捉自真实桌面）。

用法:
    python3 scripts/dry_run.py                 # 用黄金模板的 JWT 对比
    python3 scripts/dry_run.py --jwt <jwt>     # 指定 JWT

输出差异报告；exit 0 = 完全一致（动态 uuid 除外），1 = 有差异。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── 黄金参照（桌面真实请求）─────────────────────────────────────────────
GOLDEN = json.loads((ROOT / "reference" / "golden-request.json").read_text())
GOLDEN_HEADERS = GOLDEN["headers"]
GOLDEN_BODY = json.loads(GOLDEN["body"])

# 动态值字段（每次请求都不同，对比时忽略值只看有无）
_DYNAMIC_HEADERS = {
    "x-query-id", "x-request-id", "x-session-id", "x-zcode-trace-id",
    "x-aliyun-captcha-verify-param", "authorization", "x-api-key",
}
_DYNAMIC_BODY = {"metadata"}


def _norm(h: dict) -> dict:
    return {k.lower(): v for k, v in h.items()}


def main() -> int:
    args = sys.argv[1:]
    jwt = args[args.index("--jwt") + 1] if "--jwt" in args else None
    verify = args[args.index("--verify") + 1] if "--verify" in args else ""
    if not jwt:
        # 从黄金模板提取
        auth = GOLDEN_HEADERS.get("authorization", "").replace("Bearer ", "")
        if not auth or "JWT" in auth:
            print("错误: 黄金模板无 JWT，请用 --jwt <jwt>")
            return 2
        jwt = auth

    from app.agent import build_request
    from app.routes.gateway import _normalize_body
    from app.models import Account

    # 用黄金 body 的 model/messages 模拟客户端输入
    client_payload = {
        "model": GOLDEN_BODY["model"],
        "messages": GOLDEN_BODY["messages"],
    }
    body = _normalize_body(client_payload)

    account = Account.create(provider="zai", name="dry-run", secret=jwt)
    url, headers = build_request(account, body, verify or None, None)

    # ── headers 对比 ──
    gh = _norm(GOLDEN_HEADERS)
    nh = _norm(headers)
    diffs = []

    for k in sorted(set(gh) | set(nh)):
        if k in _DYNAMIC_HEADERS:
            g_present = k in gh and bool(gh[k])
            n_present = k in nh and bool(nh[k])
            if g_present != n_present:
                diffs.append(f"[HEADER] {k}: 黄金={'有' if g_present else '无'} vs 网关={'有' if n_present else '无'}")
            continue
        gv, nv = gh.get(k), nh.get(k)
        if k == "http-referer":  # 值规范化（尾部斜杠）
            gv, nv = (v.rstrip("/") if v else v for v in (gv, nv))
        if gv != nv:
            diffs.append(f"[HEADER] {k}: 黄金={gv!r} vs 网关={nv!r}")

    # ── body 对比（结构 & 静态字段）──
    gb, nb = GOLDEN_BODY, body
    for k in sorted(set(gb) | set(nb)):
        if k == "metadata":
            g_meta = json.loads(gb.get("metadata", {}).get("user_id", "{}"))
            n_meta = json.loads(nb.get("metadata", {}).get("user_id", "{}"))
            for mk in ("device_id", "account_uuid", "session_id"):
                g_present = bool(g_meta.get(mk))
                n_present = bool(n_meta.get(mk))
                if g_present != n_present:
                    diffs.append(f"[BODY.metadata] {mk}: 黄金={'有' if g_present else '无'} vs 网关={'有' if n_present else '无'}")
            continue
        if k == "messages":
            continue  # 客户端输入，不强求一致
        gv, nv = gb.get(k), nb.get(k)
        if gv != nv:
            gs = f"<{len(gv)}块>" if isinstance(gv, list) else repr(gv)[:80]
            ns = f"<{len(nv)}块>" if isinstance(nv, list) else repr(nv)[:80]
            diffs.append(f"[BODY.{k}]: 黄金={gs} vs 网关={ns}")

    if diffs:
        print("❌ 差异报告:")
        for d in diffs:
            print(f"   {d}")
        print(f"\n共 {len(diffs)} 处差异")
        return 1

    print("✅ 完全一致（动态 uuid 除外）")
    print(f"    headers: {len(gh)} 个全部对齐")
    print(f"    body: 静态字段对齐 | system {len(nb['system'])}块 tools {len(nb['tools'])}个 thinking/output_config/tool_choice 对齐")
    return 0


if __name__ == "__main__":
    sys.exit(main())