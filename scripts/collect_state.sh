#!/usr/bin/env bash
# Usage: collect_state.sh --host <ssh_alias> [--out <output_dir>]
#
# SSH経由で対象ホストのfirewalld現状を取得し、output_dirに保存する。
# 参照系のみ（非破壊）。承認不要で実行してよい。
#
# Output files:
#   <output_dir>/state.txt          firewall-cmd --state
#   <output_dir>/default_zone.txt   デフォルトzone名
#   <output_dir>/active_zones.txt   --get-active-zones
#   <output_dir>/list_all_<zone>.txt  各zoneの --list-all（runtime）
#   <output_dir>/list_all_permanent_<zone>.txt  各zoneの --list-all --permanent
#   <output_dir>/zone_files.txt     /etc/firewalld/zones/ のファイル一覧
#   <output_dir>/zone_xml/<zone>.xml  各zoneのXMLバックアップ

set -euo pipefail

SSH_ALIAS=""
OUT_DIR="./evidence/state_$(date +%Y%m%d_%H%M%S)"

usage() {
  grep '^#' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

die() { echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)   SSH_ALIAS="$2"; shift 2 ;;
    --out)    OUT_DIR="$2";   shift 2 ;;
    --help|-h) usage ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ -z "$SSH_ALIAS" ]] && die "--host <ssh_alias> は必須です"

ssh_run() { ssh "$SSH_ALIAS" "$@"; }

mkdir -p "$OUT_DIR/zone_xml"

echo "=== firewalld状態取得: $SSH_ALIAS → $OUT_DIR ==="

echo "[1/6] firewall-cmd --state"
ssh_run 'sudo firewall-cmd --state' > "$OUT_DIR/state.txt" 2>&1 || true
cat "$OUT_DIR/state.txt"

echo "[2/6] default-zone"
ssh_run 'sudo firewall-cmd --get-default-zone' > "$OUT_DIR/default_zone.txt"
cat "$OUT_DIR/default_zone.txt"

echo "[3/6] active-zones"
ssh_run 'sudo firewall-cmd --get-active-zones' > "$OUT_DIR/active_zones.txt"
cat "$OUT_DIR/active_zones.txt"

echo "[4/6] --list-all (runtime) per zone"
ZONES=$(ssh_run 'sudo firewall-cmd --get-zones')
for zone in $ZONES; do
  outfile="$OUT_DIR/list_all_${zone}.txt"
  echo "  zone: $zone"
  ssh_run "sudo firewall-cmd --zone=${zone} --list-all" > "$outfile" 2>&1 || echo "(zone not active)" >> "$outfile"
done

echo "[5/6] --list-all --permanent per zone"
for zone in $ZONES; do
  outfile="$OUT_DIR/list_all_permanent_${zone}.txt"
  echo "  zone (permanent): $zone"
  ssh_run "sudo firewall-cmd --zone=${zone} --list-all --permanent" > "$outfile" 2>&1 || echo "(not configured)" >> "$outfile"
done

echo "[6/6] /etc/firewalld/zones/ バックアップ"
ssh_run 'sudo ls /etc/firewalld/zones/ 2>/dev/null || echo "(empty)"' > "$OUT_DIR/zone_files.txt"
for zone in $ZONES; do
  xmlfile="/etc/firewalld/zones/${zone}.xml"
  ssh_run "sudo test -f ${xmlfile} && sudo cat ${xmlfile} || echo '(not found)'" \
    > "$OUT_DIR/zone_xml/${zone}.xml" 2>&1 || true
done

echo ""
echo "=== 取得完了: $OUT_DIR ==="
echo "$OUT_DIR"
