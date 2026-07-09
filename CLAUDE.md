# cc-deploy-servers

検証環境のLinuxサーバに対して firewalld 設定・試験・エビデンス作成を安全に実施する Claude Code Skill プロジェクト。

## スキルの起動

「firewalldを設定したい」「ポートを開放したい」などと話しかけると自動起動する。
または明示的に Skill ツールで `firewalld-setup` を指定する。

## ディレクトリ構成

```
cc-deploy-servers/
├── .claude/
│   └── skills/
│       └── firewalld-setup.md   # スキル定義（正本）
├── docs/                        # 補足ドキュメント
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
├── CLAUDE.md                    # このファイル（Claude Code 向けプロジェクト概要）
└── README.md
```

## 重要な制約

- 対象は**検証環境のみ**。本番環境には絶対に使用しない。
- 変更系コマンドはユーザー承認後のみ実行（`apply_config.sh` は特に厳守）。
- SSH認証情報（秘密鍵・パスワード）はエージェントに渡さない。`~/.ssh/config` + ssh-agent で完結させる。

## スクリプトの扱い

`scripts/` 配下は `--help` で引数を確認してから使う。ソースを全読みしない。

## 事前準備

作業前に `~/.ssh/config` で対象ホストのエイリアスを設定し、必要なら `ssh-add` しておく。
依存パッケージ: `pip install pyyaml`
