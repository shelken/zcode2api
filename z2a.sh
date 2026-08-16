#!/usr/bin/env bash
# zcode2api 账号管理脚本（宿主侧，通过 admin API 操作容器内账号）
#
# 用法:
#   ./z2a.sh list                    查看所有账号（脱敏）
#   ./z2a.sh status                  网关/账号池状态
#   ./z2a.sh quota                   刷新并轮询各账号额度
#   ./z2a.sh add <jwt|key> [name]    添加账号（zai JWT 或 API Key）
#   ./z2a.sh add-file <file>         从文件添加账号（每行一个 token，忽略 # 注释）
#   ./z2a.sh remove <id>             删除账号（支持多个 id）
#   ./z2a.sh enable <id>             启用账号（支持多个 id）
#   ./z2a.sh disable <id>            停用账号（支持多个 id）
#   ./z2a.sh refresh [id]            刷新额度（全部或指定账号）
#
# 环境变量:
#   Z2A_URL      网关地址，默认 http://localhost:3000
#   Z2A_KEY      admin key，默认 zcode
set -euo pipefail

URL="${Z2A_URL:-http://localhost:3000}"
KEY="${Z2A_KEY:-zcode}"
AUTH="Authorization: Bearer $KEY"
CT="content-type: application/json"

_api() { # _api METHOD PATH [DATA]
  local method="$1" path="$2" data="${3:-}"
  if [ -n "$data" ]; then
    curl -sf --max-time 30 -X "$method" -H "$AUTH" -H "$CT" \
      -d "$data" "$URL$path"
  else
    curl -sf --max-time 30 -X "$method" -H "$AUTH" "$URL$path"
  fi
}

usage() {
  cat <<'EOF'
zcode2api 账号管理

用法:
  ./z2a.sh list                    查看所有账号（脱敏）
  ./z2a.sh status                  网关/账号池状态
  ./z2a.sh quota                   刷新并查询各账号额度
  ./z2a.sh add <jwt|key> [name]    添加账号（zai JWT 或 API Key）
  ./z2a.sh add-file <file> [name]  从文件添加账号（每行一个 token）
  ./z2a.sh remove <id> [...]       删除账号
  ./z2a.sh enable <id> [...]       启用账号
  ./z2a.sh disable <id> [...]      停用账号
  ./z2a.sh refresh [id]            刷新额度（全部或指定账号）

环境变量:
  Z2A_URL      网关地址，默认 http://localhost:3000
  Z2A_KEY      admin key，默认 zcode
EOF
  exit 1
}

cmd_list() {
  _api GET /admin/api/accounts | python3 -c '
import json, sys
d = json.load(sys.stdin)
accs, stats = d["accounts"], d["stats"]
if not accs:
    print("无账号")
else:
    print("%-40s %-20s %-8s %-9s %5s %5s  %s" % ("ID", "名称", "模式", "状态", "调用", "失败", "额度"))
    for a in accs:
        q = a.get("quota") or {}
        qstr = " ".join("%s:%s" % (m, v.get("remaining", 0)) for m, v in list(q.items())[:3]) or "-"
        print("%-40s %-20s %-8s %-9s %5d %5d  %s" % (
            a["id"], a["name"], a["mode"], a["status"],
            a["use_count"], a["fail_count"], qstr))
    print("")
    print("统计: total=%d active=%d exhausted=%d cooling=%d invalid=%d disabled=%d calls=%d fail=%d" % (
        stats["total"], stats["active"], stats["exhausted"], stats["cooling"],
        stats["invalid"], stats["disabled"], stats["calls"], stats["fail"]))
'
}

cmd_status() {
  _api GET /admin/api/status | python3 -m json.tool
}

cmd_quota() {
  # 触发全体刷新再拉一次（后台刷新间隔内拿最新）
  _api POST /admin/api/accounts/refresh '{}' >/dev/null 2>&1 || true
  sleep 1
  _api GET /admin/api/accounts | python3 -c '
import json, sys
d = json.load(sys.stdin)
for a in d["accounts"]:
    name, st, q = a["name"], a["status"], a.get("quota") or {}
    print("[%s] %s  %s" % (st, name, a["mode"]))
    for m, v in q.items():
        print("    %s: 剩余 %s / 总 %s  过期 %s" % (
            m, v.get("remaining", "?"), v.get("total", "?"), v.get("expires_at", "-")))
    p = a.get("plan") or {}
    if p:
        print("    plan: %s 状态 %s" % (p.get("name", ""), p.get("status", "")))
    if not q and not p:
        print("    额度: 无数据")
'
}

cmd_add() {
  [ $# -ge 1 ] || { echo "用法: z2a.sh add <jwt|key> [name]"; exit 1; }
  local token="$1" name="${2:-acc}"
  local payload
  payload=$(python3 -c "
import json, sys
json.dump({'provider': 'zai', 'name': sys.argv[1], 'tokens': [sys.argv[2]]}, sys.stdout)
" "$name" "$token")
  _api POST /admin/api/accounts "$payload" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("✔ 已添加 %d 个账号: %s" % (d["count"], ", ".join(d["ids"])))
'
}

cmd_add_file() {
  [ $# -ge 1 ] || { echo "用法: z2a.sh add-file <file> [name]"; exit 1; }
  local file="$1" prefix="${2:-acc}"
  local ids=() n=0
  while IFS= read -r line; do
    line="$(echo "$line" | tr -d '[:space:]')"
    [ -n "$line" ] || continue
    case "$line" in \#*) continue;; esac
    local payload
    payload=$(python3 -c "
import json, sys
json.dump({'provider': 'zai', 'name': sys.argv[1], 'tokens': [sys.argv[2]]}, sys.stdout)
" "$prefix" "$line")
    local r
    r=$(_api POST /admin/api/accounts "$payload")
    ids+=("$(echo "$r" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ids"][0])')")
    n=$((n+1))
  done < "$file"
  echo "✔ 已添加 $n 个账号: ${ids[*]}"
}

cmd_remove() {
  [ $# -ge 1 ] || { echo "用法: z2a.sh remove <id> [...]"; exit 1; }
  local payload
  payload=$(python3 -c "
import json, sys
json.dump(sys.argv[1:], sys.stdout)
" "$@")
  _api DELETE /admin/api/accounts "$payload" | python3 -c '
import json, sys
print("✔ 已删除 %d 个账号" % json.load(sys.stdin)["deleted"])
'
}

cmd_enable() {
  [ $# -ge 1 ] || { echo "用法: z2a.sh enable <id> [...]"; exit 1; }
  for id in "$@"; do
    _api POST "/admin/api/accounts/$id/enabled" '{"enabled": true}' >/dev/null
    echo "✔ 已启用 $id"
  done
}

cmd_disable() {
  [ $# -ge 1 ] || { echo "用法: z2a.sh disable <id> [...]"; exit 1; }
  for id in "$@"; do
    _api POST "/admin/api/accounts/$id/enabled" '{"enabled": false}' >/dev/null
    echo "✔ 已停用 $id"
  done
}

cmd_refresh() {
  local path="/admin/api/accounts/refresh"
  [ $# -ge 1 ] && path="/admin/api/accounts/$1/refresh" || true
  _api POST "$path" '{}' | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("✔ 刷新完成:", json.dumps(d, ensure_ascii=False)[:200])
'
}

case "${1:-}" in
  list)     cmd_list ;;
  status)   cmd_status ;;
  quota)    cmd_quota ;;
  add)      shift; cmd_add "$@" ;;
  add-file) shift; cmd_add_file "$@" ;;
  remove)   shift; cmd_remove "$@" ;;
  enable)   shift; cmd_enable "$@" ;;
  disable)  shift; cmd_disable "$@" ;;
  refresh)  shift; cmd_refresh "$@" ;;
  *) usage ;;
esac