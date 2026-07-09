#!/usr/bin/env bash
# Usage: apply_config.sh --host <ssh_alias> --commands <commands.json> [--dry-run]
#
# 【破壊的操作】承認ゲートを通過した後にのみ呼び出すこと。
#
# build_commands.py が生成した commands.json を読み込み、
# SSH経由で対象ホストに firewall-cmd を適用する。
#
# オプション:
#   --host <ssh_alias>      ~/.ssh/config のHost名（必須）
#   --commands <file.json>  build_commands.py 出力のJSONファイル（必須）
#   --dry-run               コマンドを表示するだけで実行しない
#
# 終了コード:
#   0: 成功
#   1: エラー（SSH失敗・コマンド失敗等）
#   2: lockoutリスクが検出されたため停止

set -euo pipefail

SSH_ALIAS=""
COMMANDS_FILE=""
DRY_RUN=false

usage() {
  grep '^#' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

die() { echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)      SSH_ALIAS="$2";      shift 2 ;;
    --commands)  COMMANDS_FILE="$2";  shift 2 ;;
    --dry-run)   DRY_RUN=true;        shift ;;
    --help|-h)   usage ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ -z "$SSH_ALIAS" ]]      && die "--host は必須です"
[[ -z "$COMMANDS_FILE" ]]  && die "--commands は必須です"
[[ -f "$COMMANDS_FILE" ]]  || die "コマンドファイルが見つかりません: $COMMANDS_FILE"

# lockoutリスクチェック
LOCKOUT_RISK=$(python3 -c "import json,sys; d=json.load(open('$COMMANDS_FILE')); print('true' if d.get('lockout_risk') else 'false')")
if [[ "$LOCKOUT_RISK" == "true" ]]; then
  echo "WARN: LOCKOUT RISK が検出されています。" >&2
  echo "  このまま続行すると SSH 接続が切断される可能性があります。" >&2
  echo "  続行する場合はリスクを承知のうえで明示的に承認を得てください。" >&2
  exit 2
fi

# コマンドリスト取得
COMMANDS=$(python3 -c "import json; [print(c) for c in json.load(open('$COMMANDS_FILE'))['commands']]")

if [[ -z "$COMMANDS" ]]; then
  echo "適用コマンドがありません。"
  exit 0
fi

echo "=== 適用コマンド一覧 ==="
echo "$COMMANDS"
echo ""

if $DRY_RUN; then
  echo "(--dry-run モード: 実行しません)"
  exit 0
fi

echo "=== SSH接続確認: $SSH_ALIAS ==="
ssh "$SSH_ALIAS" 'echo "SSH OK: $(hostname)"' || die "SSH接続に失敗しました"

echo ""
echo "=== 設定適用開始 ==="
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="./evidence/apply_${TIMESTAMP}.log"
mkdir -p ./evidence

{
  echo "適用日時: $(date)"
  echo "対象ホスト: $SSH_ALIAS"
  echo ""
  echo "--- コマンド実行ログ ---"
} > "$LOG_FILE"

RELOAD_DONE=false
while IFS= read -r cmd; do
  [[ -z "$cmd" ]] && continue
  echo "実行: $cmd"
  echo "CMD: $cmd" >> "$LOG_FILE"

  if [[ "$cmd" == "firewall-cmd --reload" ]]; then
    echo "[reload前] SSH到達性を最終確認..."
    ssh "$SSH_ALIAS" 'echo "pre-reload SSH OK"' || {
      echo "ERROR: reload前のSSH確認が失敗しました。安全のため中断します。" >&2
      echo "ERROR: pre-reload SSH check failed" >> "$LOG_FILE"
      exit 1
    }
  fi

  OUT=$(ssh "$SSH_ALIAS" "sudo $cmd" 2>&1) || {
    echo "ERROR: コマンドが失敗しました: $cmd" >&2
    echo "  出力: $OUT" >&2
    echo "ERROR: $cmd" >> "$LOG_FILE"
    echo "OUTPUT: $OUT" >> "$LOG_FILE"
    exit 1
  }
  echo "  → $OUT"
  echo "OUTPUT: $OUT" >> "$LOG_FILE"

  if [[ "$cmd" == "firewall-cmd --reload" ]]; then
    RELOAD_DONE=true
  fi
done <<< "$COMMANDS"

echo ""
echo "=== 適用後 SSH 生存確認 ==="
if ssh "$SSH_ALIAS" 'echo "post-apply SSH OK: $(hostname)"'; then
  echo "SSH接続: 正常"
  echo "POST-APPLY SSH: OK" >> "$LOG_FILE"
else
  echo "ERROR: 適用後のSSH接続が失敗しました！" >&2
  echo "ロールバック手順:" >&2
  echo "  1. コンソール（KVM/IPMI等）でホストにアクセス" >&2
  echo "  2. sudo firewall-cmd --reload  （設定を --permanent から再読込）" >&2
  echo "  3. または: sudo systemctl restart firewalld" >&2
  echo "POST-APPLY SSH: FAILED" >> "$LOG_FILE"
  exit 1
fi

echo ""
echo "=== 適用完了: ログ → $LOG_FILE ==="
