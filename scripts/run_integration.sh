#!/usr/bin/env bash
# Usage: run_integration.sh --src <src_ssh_alias> --target-ip <ip> --tests <tests.yaml> [--out <result.md>]
#
# 別サーバ（試験元）から対象ホストへの到達性を確認する結合試験（非破壊）。
#
# tests.yaml フォーマット:
#   - port: 22
#     proto: tcp
#     expect: reachable      # reachable / unreachable
#     description: SSH
#   - port: 8080
#     proto: tcp
#     expect: reachable
#     description: App HTTP
#   - port: 3306
#     proto: tcp
#     expect: unreachable
#     description: MySQL（遮断確認）
#
# オプション:
#   --src <ssh_alias>    試験元サーバのSSHエイリアス（必須）
#   --target-ip <ip>     試験先ホストのIPアドレス（必須）
#   --tests <yaml>       試験定義YAMLファイル（必須）
#   --out <file.md>      結果をMarkdownに保存（省略可）
#   --timeout <sec>      nc のタイムアウト秒（デフォルト: 5）

set -euo pipefail

SRC_ALIAS=""
TARGET_IP=""
TESTS_FILE=""
OUT_FILE=""
TIMEOUT=5

usage() {
  grep '^#' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

die() { echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src)        SRC_ALIAS="$2";   shift 2 ;;
    --target-ip)  TARGET_IP="$2";  shift 2 ;;
    --tests)      TESTS_FILE="$2"; shift 2 ;;
    --out)        OUT_FILE="$2";   shift 2 ;;
    --timeout)    TIMEOUT="$2";    shift 2 ;;
    --help|-h)    usage ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ -z "$SRC_ALIAS" ]]   && die "--src は必須です"
[[ -z "$TARGET_IP" ]]   && die "--target-ip は必須です"
[[ -z "$TESTS_FILE" ]]  && die "--tests は必須です"
[[ -f "$TESTS_FILE" ]]  || die "試験定義ファイルが見つかりません: $TESTS_FILE"

# YAML を python で解析してTSV出力
TESTS_TSV=$(python3 - "$TESTS_FILE" <<'PYEOF'
import sys, yaml
with open(sys.argv[1]) as f:
    tests = yaml.safe_load(f)
for t in tests:
    print(f"{t['port']}\t{t.get('proto','tcp')}\t{t['expect']}\t{t.get('description','')}")
PYEOF
)

PASS_COUNT=0
FAIL_COUNT=0
ROWS=()

echo "=== 結合試験: $SRC_ALIAS → $TARGET_IP ==="
echo ""
printf "%-6s %-5s %-12s %-12s %s\n" "port" "proto" "expected" "actual" "合否"
printf "%-6s %-5s %-12s %-12s %s\n" "------" "-----" "------------" "------------" "----"

while IFS=$'\t' read -r port proto expect desc; do
  actual_label="unreachable"
  nc_result=0

  ssh "$SRC_ALIAS" "nc -z -w ${TIMEOUT} ${TARGET_IP} ${port}" 2>/dev/null && nc_result=0 || nc_result=1

  if [[ $nc_result -eq 0 ]]; then
    actual_label="reachable"
  fi

  if [[ "$expect" == "$actual_label" ]]; then
    mark="PASS"
    ((PASS_COUNT++)) || true
  else
    mark="FAIL"
    ((FAIL_COUNT++)) || true
  fi

  printf "%-6s %-5s %-12s %-12s %s  %s\n" "$port" "$proto" "$expect" "$actual_label" "$mark" "$desc"
  ROWS+=("| $SRC_ALIAS | ${port}/${proto} | $expect | $actual_label | $mark |  $desc |")
done <<< "$TESTS_TSV"

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo ""
echo "合計: ${TOTAL}件 / PASS: ${PASS_COUNT}件 / FAIL: ${FAIL_COUNT}件"

if [[ -n "$OUT_FILE" ]]; then
  mkdir -p "$(dirname "$OUT_FILE")"
  {
    echo "## 結合試験結果"
    echo ""
    echo "| 試験元 | 対象port | 期待 | 実測 | 合否 | 説明 |"
    echo "|--------|----------|------|------|------|------|"
    for row in "${ROWS[@]}"; do
      echo "$row"
    done
    echo ""
    echo "**合計: ${TOTAL}件 / PASS: ${PASS_COUNT}件 / FAIL: ${FAIL_COUNT}件**"
  } > "$OUT_FILE"
  echo "結果保存: $OUT_FILE"
fi

[[ $FAIL_COUNT -eq 0 ]] && exit 0 || exit 1
