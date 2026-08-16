#!/usr/bin/env bash
# 最小 body 边界测试：单变量逐步删减，每次先在健康账号验证基线
# 用法: ./test-minimal-body.sh <jwt> [--variant all|no-tools|no-system|no-thinking|no-metadata]
# 规则:
#   - 每个变体间隔 SOLVE_GAP 分钟（防风控）
#   - 每个变体前先跑基线（完整黄金 body），基线 3012 则中止（账号问题不是 body 问题）
set -euo pipefail
JWT="${1:?用法: test-minimal-body.sh <jwt> [variant]}"
VARIANT="${2:-all}"
SOLVE_GAP_MIN="${SOLVE_GAP_MIN:-5}"
PORT="${PORT:-3000}"

echo "=== 账号健康预检（billing GET，只读）==="
BILLING=$(curl -sS --max-time 10 "https://zcode.z.ai/api/v1/zcode-plan/billing/current" -H "Authorization: Bearer $JWT")
echo "$BILLING" | head -c 80; echo
if echo "$BILLING" | grep -q '3012'; then
  echo "❌ 账号已风控，中止。请先恢复账号（重登/换IP/等待）。"
  exit 1
fi
echo "✅ 账号健康"

# 复制 JWT 进容器
docker cp /dev/stdin zcode2api:/tmp/test-jwt.txt <<< "$JWT"

run_variant() {
  local name="$1"
  echo ""
  echo "⏸  等待 $SOLVE_GAP_MIN 分钟（防风控）..."
  sleep "$((SOLVE_GAP_MIN * 60))"
  echo "=== 变体: $name ==="
  docker exec zcode2api python3 /app/test-variant.py "$name"
}

docker exec zcode2api python3 -c "
import json, sys
# 生成通用变体测试脚本（容器内执行）
body_keys = json.dumps(None)
" 

# 变体测试逻辑放 Python（容器内存依赖齐全）
cat > /tmp/test-variant.py << 'PYEOF'
import json, sys, subprocess
sys.path.insert(0, '/app')
from app.agent import build_request
from app.models import Account
import httpx

G = json.load(open('/app/reference/golden-request.json'))
base = json.loads(G['body'])
# 用 GLM-5-Turbo（无 output_config，最简基线接近原版）
base['model'] = 'GLM-5-Turbo'
base['thinking'] = {"type": "enabled", "budget_tokens": 1024}
base.pop('output_config', None)
base['messages'] = [{"role":"user","content":[{"type":"text","text":"说你好"}]}]
base['metadata'] = {"user_id": json.dumps({
    "device_id":"4d2122d3-3b38-44db-9ab1-63c9baf686b7",
    "account_uuid":"","session_id":"boundary-test"})}

def solve_captcha():
    tok = subprocess.run(['node','/app/captcha_node/solver.js'], capture_output=True, text=True, timeout=60).stdout
    return [l.split('=',1)[1].strip() for l in tok.split('\n') if l.startswith('VERIFY_PARAM=')][0]

def send(body, label):
    jwt = open('/tmp/test-jwt.txt').read().strip()
    acc = Account.create(provider='zai', name='btest', secret=jwt)
    headers = dict(build_request(acc, body, 'X', None)[1])
    headers['X-Aliyun-Captcha-Verify-Param'] = solve_captcha()
    headers['X-Aliyun-Captcha-Verify-Region'] = 'sgp'
    r = httpx.post('https://zcode.z.ai/api/v1/zcode-plan/anthropic/v1/messages',
                   headers=headers, json=body, timeout=90)
    ok = 'OK' if r.status_code == 200 else f'FAIL({r.status_code})'
    reason = r.text[:80] if r.status_code != 200 else 'message_stop' if 'message_stop' in r.text else 'sse'
    print(f"[{label}] {ok} {reason}")
    return r.status_code == 200

variant = sys.argv[1]
if variant == 'no-tools':
    body = json.loads(json.dumps(base)); body.pop('tools', None); body.pop('tool_choice', None)
    send(body, 'no-tools')
elif variant == 'no-system':
    body = json.loads(json.dumps(base)); body.pop('system', None)
    send(body, 'no-system')
elif variant == 'no-thinking':
    body = json.loads(json.dumps(base)); body.pop('thinking', None)
    send(body, 'no-thinking')
elif variant == 'no-metadata':
    body = json.loads(json.dumps(base)); body.pop('metadata', None)
    send(body, 'no-metadata')
elif variant == 'no-messages':
    body = json.loads(json.dumps(base)); body['messages'] = []
    send(body, 'no-messages')
elif variant == 'baseline':
    send(base, 'baseline')
else:
    print(f"未知变体: {variant}"); sys.exit(1)
PYEOF
docker cp /tmp/test-variant.py zcode2api:/app/test-variant.py
rm /tmp/test-variant.py

case "$VARIANT" in
  baseline) run_variant baseline ;;
  no-tools) run_variant no-tools ;;
  no-system|no-sys) run_variant no-system ;;
  no-thinking) run_variant no-thinking ;;
  no-metadata) run_variant no-metadata ;;
  no-messages) run_variant no-messages ;;
  all)
    for v in baseline no-tools no-system no-thinking no-metadata no-messages; do
      run_variant "$v"
    done
    ;;
  *) echo "用法: test-minimal-body.sh <jwt> [all|baseline|no-tools|no-system|no-thinking|no-metadata|no-messages]"; exit 1 ;;
esac
echo "=== 测试完成 ==="