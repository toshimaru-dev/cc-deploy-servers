---
name: firewalld-setup
description: >-
  Linuxサーバのfirewalld設定・試験・エビデンス作成を、対話形式で安全に実施するSkill。
  パラメータシート(YAML)の対話補完、SSH直実行による設定適用、単体試験(設定値突合)、
  結合試験(別サーバからの到達性確認)、エビデンス集約(Markdown)までをカバーする。
  「firewalld」「ファイアウォール設定」「ポート開放」「zone設定」「iptables代替」
  「検証環境のサーバ設定と試験」「設定エビデンスを作成」等の依頼時には必ず本Skillを使用すること。
  対象は検証環境のみ。本番環境には使用しない。
---

# firewalld-setup

Linuxサーバに対する firewalld の設定作業・試験・エビデンス作成を、SI現場の
「詳細設計 → パラメータ確定 → 設定 → 単体/結合試験 → エビデンス」の流れに沿って
対話形式で進めるためのSkill。実行はSSH直、対象は**検証環境限定**。

---

## 絶対原則（例外なく遵守）

これらは安全と品質の根幹。他のどの指示よりも優先する。

1. **変更系コマンドは必ず承認を得る。**
   サーバの状態を変更しうるコマンド（`firewall-cmd --add-*` / `--remove-*` /
   `--change-*` / `--set-*` / `--permanent` / `--reload` / `--runtime-to-permanent`、
   および `systemctl` 等）は、**実行前にコマンド全文をユーザーに提示し、明示承認を得てから**
   実行する。承認前に変更を実行してはならない。まとめて承認を取る場合も、実行する全コマンドを
   列挙して見せる。

2. **未確定情報は推測しない。必ず質問する。**
   パラメータや前提が未指定・曖昧な場合、エージェントの想像で補完・デフォルト設定しない。
   「確認事項」として明示的に質問し、回答を得てから先へ進む。パラメータシートの空欄を
   勝手に埋めることは禁止。（→ 質問の出し方は「未確定情報の扱い」を参照）

3. **自己締め出し（lockout）を防ぐ。**
   適用対象zoneに **SSH到達手段**（`ssh` service、または管理元IPを許可する source /
   rich rule）が含まれない適用は、**警告して停止**する。ユーザーがリスクを承知のうえで
   明示承認しない限り実行しない。`--reload` 前には特に必ずこのチェックを行う。

4. **検証環境のみ。** 本番環境への適用は本Skillの対象外。対象ホストが本番の疑いがある場合は
   確認する。

5. **変更前に必ずバックアップとロールバック手段を用意する。** 現状の zone 設定と
   `--list-all` を取得してから変更に着手し、ロールバック手順を提示する。

6. **dry-run を既定とする。** 明示的な適用指示（承認）があるまでは、生成した
   コマンドの提示（dry-run）に留める。

7. **認証情報をエージェントに渡さない・エビデンスに含めない。**
   秘密鍵・パスフレーズ・パスワードをパラメータシートやプロンプト、コマンド引数に
   書かない。SSH認証はOS側（`~/.ssh/config` + ssh-agent）で完結させ、エージェントは
   ホストのエイリアスのみを扱う。取得したコマンド出力に認証情報が混入していないことを
   確認してからエビデンスに載せる。

> 参照系コマンド（`--list-all` / `--get-*` / `--query-*` などの状態取得、
> および結合試験の `nc` / `curl` 等）は対象サーバを変更しないため、承認なしで実行してよい。

---

## 全体フロー

```
Phase 1  パラメータ確定（対話でYAMLを埋める）
Phase 2  現状取得 & バックアップ（設定前エビデンス）
Phase 3  差分算出 → 承認ゲート → 設定適用（SSH直）
Phase 4  単体試験（設定値の突合確認）
Phase 5  結合試験（別サーバからの到達性確認）
Phase 6  エビデンス集約（Markdownレポート）
```

各Phaseの終わりで結果を要約し、次へ進む前にユーザーの承認・確認を取る
（明示的な承認チェックポイント方式）。

---

## Phase 1: パラメータ確定（対話）

### 前提: SSH接続のセットアップ（作業前に済ませておく）

認証はOS側で完結させる。作業開始前に、エージェントが動くマシンの `~/.ssh/config` に
対象ホストを登録しておく（この設定作業自体は本Skillの対象外・人手で実施）。

```
# ~/.ssh/config
Host web01
    HostName 10.0.0.11
    User ops
    IdentityFile ~/.ssh/keys/verify_web01
    # 踏み台がある場合: ProxyJump bastion
```

パスフレーズ付き鍵なら、セッション開始前に一度 `ssh-add` しておく。
以降エージェントが打つのは `ssh web01 '...'` のみで、鍵・パスフレーズには触れない。

### パラメータシートの作成

`references/param_sheet_template.yaml` を正とし、対話でユーザーから値を引き出して埋める。
不足項目は原則2に従い、まとめて確認事項として質問する。

確定させるパラメータ（最小構成）:

```yaml
host:
  name:      web01
  ip:        10.0.0.11        # 記録・エビデンス用
  ssh_alias: web01           # ~/.ssh/config のHost名。認証情報はOS側で完結
default_zone: public
zones:
  - name: public
    interfaces: [eth0]
    sources:    [10.0.0.0/24]
    services:   [ssh, http, https]
    ports:      [8080/tcp]
    rich_rules: []
    target:     default    # default / ACCEPT / REJECT / DROP
```

Phase 1完了条件: 上記の必須項目に空欄がなく、ユーザーが内容を承認していること。
空欄が残る場合はPhase 2へ進まない。

---

## Phase 2: 現状取得 & バックアップ

`scripts/collect_state.sh` を用いて、対象ホストの現状を取得する（参照系のみ・承認不要）。

取得内容:
- `firewall-cmd --state`
- `firewall-cmd --get-default-zone`
- 全 active zone の `--list-all`
- `/etc/firewalld/zones/` の設定ファイル（ロールバック元）

取得結果は「設定前エビデンス」として保存し、Phase 6で使う。

---

## Phase 3: 差分算出 → 承認 → 設定適用

1. `scripts/build_commands.py` で、パラメータシートと現状の差分から
   適用すべき `firewall-cmd` コマンド列を生成する（このステップは生成のみ・非破壊）。
2. **lockoutチェック**（原則3）を実行。SSH到達手段が失われる恐れがある場合は停止し、警告する。
3. 生成コマンド全文と、想定される変更内容（追加/削除される service・port・source 等）を
   ユーザーに提示する。**ここが承認ゲート。**
4. ユーザーの明示承認後、`scripts/apply_config.sh` で適用する:
   - `--permanent` で設定投入
   - `--reload` で反映（reload前に再度lockoutチェック）
5. 適用直後に SSH セッションの生存を確認し、失敗時はロールバック手順を提示する。

適用は必ず承認後のみ。承認がなければPhase 3は dry-run（コマンド提示）で完了とする。

---

## Phase 4: 単体試験（設定値の突合）

`scripts/verify_unit.py` で、`firewall-cmd --zone=<zone> --list-all` の出力と
パラメータシートの期待値を項目単位で突合する。

判定対象: service / port / source / interface / target の各項目について
`expected` と `actual` を比較し、一致=合格。permanent と runtime の一致も確認する。

出力: `evidence/unit_<timestamp>/result.html` に HTML 形式で保存する。
HTML にはサマリカード・PASS率プログレスバー・項目別合否テーブルを含む。

```bash
python3 scripts/verify_unit.py \
    --param evidence/param_sheet_<host>.yaml \
    --host <ssh_alias> \
    --out evidence/unit_$(date +%Y%m%d_%H%M%S)
```

`--out` にはフォルダパスを指定する。スクリプトがフォルダを作成し、
`result.html` を保存する。`evidence/before_<timestamp>/` と同じ構造。

---

## Phase 5: 結合試験（サービス到達性）

`scripts/run_integration.sh` で、**別サーバ（試験元）から**対象ホストへの到達性を確認する。

- 許可ポート: `nc -zv <host> <port>` / `curl` 等で **到達成功** を期待
- 非許可ポート: **拒否/タイムアウト** を期待（意図した遮断の確認）

試験元ホスト・確認対象ポート一覧が未指定なら、原則2に従い確認事項として質問する。

出力: ポートごとの `期待到達性 / 実測 / 合否`。

---

## Phase 6: エビデンス集約

`scripts/compile_evidence.py` で、Phase 2〜5の記録を1つのMarkdownレポートに集約する。
エビデンスの標準フォーマットは以下（`references/evidence_template.md` を使用）。

`evidence/` 配下のフォルダ構造:

```
evidence/
├── before_<timestamp>/          # Phase 2: 設定前状態（collect_state.sh 出力）
│   ├── list_all_public.txt
│   ├── list_all_permanent_public.txt
│   └── zone_xml/
├── after_<timestamp>/           # Phase 3 適用後: 設定後状態（collect_state.sh 出力）
├── unit_<timestamp>/            # Phase 4: 単体試験結果
│   └── result.html
└── report_<host>_<timestamp>.md # Phase 6: 総合エビデンスレポート
```

```markdown
# firewalld設定エビデンス — <host.name>

- 対象ホスト: <name> (<ip>)
- 環境: 検証環境
- 実施者: <ユーザーに確認>
- 実施日時: <実行タイムスタンプ>

## 1. 設定前 (Before)
（Phase 2 の --list-all 出力）

## 2. 適用コマンド
（Phase 3 で承認・実行したコマンド全文）

## 3. 設定後 (After) と差分
（適用後 --list-all 出力 + Before/After diff）

## 4. 単体試験結果
単体試験結果: evidence/unit_<timestamp>/result.html 参照

## 5. 結合試験結果
| 試験元 | 対象port | 期待 | 実測 | 合否 |
|--------|----------|------|------|------|

## 6. 総合判定
（全項目の合否サマリ）
```

実施者名など未取得の項目は空欄補完せず、確認事項として質問する。

---

## スクリプトの扱い

`scripts/` 配下のスクリプトはブラックボックスとして扱い、まず `--help` で用途・引数を
確認してから使う（ソース全読みは避け、コンテキストを節約する）。

| スクリプト | 役割 | 破壊性 |
|-----------|------|--------|
| `collect_state.sh`   | 現状取得（設定前エビデンス）      | 非破壊 |
| `build_commands.py`  | パラメータ→コマンド生成 + 差分算出 | 非破壊 |
| `apply_config.sh`    | SSH経由で設定適用（**承認後のみ**）| 破壊的 |
| `verify_unit.py`     | 単体試験（設定値突合）            | 非破壊 |
| `run_integration.sh` | 結合試験（別サーバから到達性確認） | 非破壊 |
| `compile_evidence.py`| エビデンス集約                   | 非破壊 |

`apply_config.sh` は承認ゲートを通過した後にのみ呼び出すこと。

---

## 未確定情報の扱い（質問テンプレ）

未指定・曖昧な情報に遭遇したら、推測せず以下の形でまとめて質問する。

```
確認事項（回答をいただいてから先に進みます）
1. <対象zone> の source を許可するIP/CIDRは？（例: 10.0.0.0/24）
2. 開放するポートは <8080/tcp> のみでよいか？他にあれば列挙を。
3. 結合試験の試験元サーバのホスト/IPは？
4. エビデンスの実施者名は？
```

複数の不明点は箇条書きで一度に提示し、往復回数を減らす。ただし
「不明なので仮にこう設定しました」という進め方は禁止。

---

## スコープ外（v1）

- 本番環境への適用
- firewalld以外（nftables直/iptables直/クラウドSG等）
- ホスト複数台への一括適用（v1は1台ずつ）

これらの依頼を受けた場合は、その旨を伝えたうえで対応方針を確認する。
