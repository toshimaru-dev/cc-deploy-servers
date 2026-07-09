# cc-deploy-servers

検証環境のLinuxサーバに対して、firewalld設定・試験・エビデンス作成を安全に実施するための Claude Code Skill プロジェクト。

## 概要

`/firewalld-setup` スキルを使って、以下のフローを対話形式で進める。

```
Phase 1  パラメータ確定（対話でYAMLを埋める）
Phase 2  現状取得 & バックアップ（設定前エビデンス）
Phase 3  差分算出 → 承認ゲート → 設定適用（SSH直）
Phase 4  単体試験（設定値の突合確認）
Phase 5  結合試験（別サーバからの到達性確認）
Phase 6  エビデンス集約（Markdownレポート）
```

変更系コマンドは必ずユーザー承認を得てから実行。対象は**検証環境のみ**。

## ディレクトリ構成

```
cc-deploy-servers/
├── .claude/
│   └── skills/
│       └── firewalld-setup.md   # スキル定義（正本）
├── scripts/
│   ├── collect_state.sh         # Phase 2: firewalld現状取得（非破壊）
│   ├── build_commands.py        # Phase 3: コマンド生成 + lockoutチェック（非破壊）
│   ├── apply_config.sh          # Phase 3: 設定適用（承認後のみ・破壊的）
│   ├── verify_unit.py           # Phase 4: 単体試験（非破壊）
│   ├── run_integration.sh       # Phase 5: 結合試験（非破壊）
│   └── compile_evidence.py      # Phase 6: エビデンス集約（非破壊）
├── references/
│   ├── param_sheet_template.yaml        # パラメータシートひな形
│   ├── evidence_template.md             # エビデンスレポートひな形
│   └── integration_tests_template.yaml  # 結合試験定義ひな形
├── evidence/                    # 実行ログ・試験結果・レポートの出力先
└── CLAUDE.md                    # Claude Code 向けプロジェクト概要
```

## 事前準備

### 1. SSH設定

エージェントが動くマシンの `~/.ssh/config` に対象ホストを登録する。

```
Host web01
    HostName 10.0.0.11
    User ops
    IdentityFile ~/.ssh/keys/verify_web01
    # 踏み台がある場合: ProxyJump bastion
```

パスフレーズ付き鍵の場合は `ssh-add` で事前に登録しておく。

### 2. 依存パッケージ

```bash
pip install pyyaml
```

## 使い方

Claude Code で以下を入力するとスキルが起動する。

```
/firewalld-setup
```

Phase 1 の確認事項に答えながら対話形式で進める。
スキルの詳細な仕様・原則は [.claude/skills/firewalld-setup.md](./.claude/skills/firewalld-setup.md) を参照。

## スクリプト単体での実行

```bash
# Phase 2: 現状取得
bash scripts/collect_state.sh --host web01 --out evidence/before_20240101

# Phase 3: コマンド生成（dry-run）
python3 scripts/build_commands.py --param param_sheet.yaml --state evidence/before_20240101

# Phase 3: 設定適用（承認後のみ）
bash scripts/apply_config.sh --host web01 --commands commands.json

# Phase 4: 単体試験
python3 scripts/verify_unit.py --param param_sheet.yaml --host web01 --out evidence/unit_result.md

# Phase 5: 結合試験
bash scripts/run_integration.sh --src test01 --target-ip 10.0.0.11 \
    --tests references/integration_tests_template.yaml --out evidence/integration_result.md

# Phase 6: エビデンス集約
python3 scripts/compile_evidence.py \
    --param param_sheet.yaml \
    --state-before evidence/before_20240101 \
    --state-after  evidence/after_20240101 \
    --apply-log    evidence/apply_20240101.log \
    --unit-result  evidence/unit_result.md \
    --integration-result evidence/integration_result.md \
    --operator "山田 太郎" \
    --out evidence/report_web01_20240101.md
```

## 注意事項

- 本スキルは**検証環境専用**。本番環境には使用しない。
- `apply_config.sh` は承認ゲートを通過した後にのみ呼び出す。
- SSH認証情報（秘密鍵・パスワード）はエージェントに渡さない。
