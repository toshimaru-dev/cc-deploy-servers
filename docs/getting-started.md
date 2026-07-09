# はじめの手順 — リポジトリ取得から単体試験まで

本ドキュメントは、cc-deploy-servers リポジトリを取得し、対象サーバへの事前準備を行い、
firewalld 設定と単体試験エビデンス取得までを完了するための手順書。

---

## 前提条件

| 項目 | 内容 |
|------|------|
| 作業端末 OS | Windows 11（Git Bash 使用） |
| 対象サーバ OS | CentOS 10（検証環境のみ） |
| 必要ソフトウェア | Git、Python 3.x、pip、OpenSSH |
| Python パッケージ | `pyyaml`（`pip install pyyaml`） |

---

## Step 1: リポジトリを取得する

```bash
git clone <リポジトリURL>
cd cc-deploy-servers
```

依存パッケージをインストール:

```bash
pip install pyyaml
```

---

## Step 2: SSH 鍵を作成する（作業端末）

対象サーバへの鍵認証用に Ed25519 鍵ペアを生成する。
パスフレーズは空のまま Enter（スクリプトが非対話で動くため）。

```bash
ssh-keygen -t ed25519 -f ~/.ssh/<サーバ名> -C "<サーバ名>"
# 例: ssh-keygen -t ed25519 -f ~/.ssh/centos10 -C "centos10"
```

生成される鍵:
- `~/.ssh/<サーバ名>`（秘密鍵）
- `~/.ssh/<サーバ名>.pub`（公開鍵）

公開鍵の内容を確認しておく:

```bash
cat ~/.ssh/<サーバ名>.pub
```

---

## Step 3: 対象サーバの初期設定（既存ユーザーで SSH して実施）

> ここだけ既存の管理者アカウントで手動 SSH して実施する。
> 以降の作業はすべて `cc-dev` ユーザーで行う。

### 3-1. 作業用ユーザー `cc-dev` を作成

```bash
sudo useradd -m -s /bin/bash cc-dev
```

### 3-2. `sudo` をパスワードなしで実行できるよう設定

```bash
echo 'cc-dev ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/cc-dev
sudo chmod 440 /etc/sudoers.d/cc-dev
```

### 3-3. SSH 公開鍵を登録

Step 2 で確認した公開鍵（`~/.ssh/<サーバ名>.pub` の内容）を登録する。

```bash
sudo mkdir -p /home/cc-dev/.ssh
sudo chmod 700 /home/cc-dev/.ssh
echo "<公開鍵の内容>" | sudo tee /home/cc-dev/.ssh/authorized_keys
sudo chmod 600 /home/cc-dev/.ssh/authorized_keys
sudo chown -R cc-dev:cc-dev /home/cc-dev/.ssh
```

---

## Step 4: SSH 設定ファイルを作成する（作業端末）

`~/.ssh/config` に対象サーバのエントリを追加する。

```
Host centos10
    HostName 192.168.0.31
    User cc-dev
    Port 22
    IdentityFile ~/.ssh/centos10
```

> **注意:** `ControlMaster` は Windows の OpenSSH では動作しない。使用しないこと。

---

## Step 5: SSH 接続を確認する

```bash
ssh centos10 "whoami && sudo firewall-cmd --state"
```

期待する出力:
```
cc-dev
running
```

`sudo` がパスワードなしで実行できていることを必ず確認する。

---

## Step 6: 現状取得（設定前エビデンス）

`collect_state.sh` でサーバの現在の firewalld 設定を取得・保存する。

```bash
bash scripts/collect_state.sh --host centos10 --out evidence/before_$(date +%Y%m%d_%H%M%S)
```

取得されるファイル（`evidence/before_<日時>/`）:

| ファイル | 内容 |
|---------|------|
| `state.txt` | firewalld の稼働状態 |
| `default_zone.txt` | デフォルト zone 名 |
| `active_zones.txt` | アクティブな zone 一覧 |
| `list_all_<zone>.txt` | 各 zone の設定（runtime） |
| `list_all_permanent_<zone>.txt` | 各 zone の設定（permanent） |
| `zone_xml/<zone>.xml` | zone 設定ファイルのバックアップ |

---

## Step 7: パラメータシートを作成する

`references/param_sheet_template.yaml` をコピーして、適用したい設定値を記入する。

```bash
cp references/param_sheet_template.yaml evidence/param_sheet_<ホスト名>.yaml
```

記入例（SSH を踏み台 IP のみ許可する場合）:

```yaml
host:
  name:      centos10
  ip:        192.168.0.31
  ssh_alias: centos10

default_zone: public

zones:
  - name: public
    interfaces: [ens3]
    sources:    []
    services:   [cockpit, dhcpv6-client]
    ports:      []
    rich_rules:
      - 'rule family="ipv4" source address="192.168.0.174/32" service name="ssh" accept'
    target: default
```

> **原則:** パラメータシートに空欄を残したまま次のステップへ進まないこと。

---

## Step 8: 適用コマンドを生成・確認する（dry-run）

`build_commands.py` でパラメータシートと現状の差分からコマンドを生成する。
このステップは非破壊（サーバへの変更なし）。

```bash
python3 scripts/build_commands.py \
    --param evidence/param_sheet_centos10.yaml \
    --state evidence/before_<日時>
```

出力されたコマンド一覧を確認し、意図通りの変更になっているか検証する。

> **lockout 警告が出た場合は適用を中断すること。**
> SSH サービスまたは管理元 IP が保護されているか確認してから再設計する。

---

## Step 9: 設定を適用する（承認後のみ）

Step 8 の内容を確認・承認したうえで実行する。

```bash
# 例: SSH を踏み台のみ許可する場合
ssh centos10 "sudo firewall-cmd --zone=public --remove-service=ssh --permanent"
ssh centos10 "sudo firewall-cmd --zone=public --add-rich-rule='rule family=\"ipv4\" source address=\"192.168.0.174/32\" service name=\"ssh\" accept' --permanent"
ssh centos10 "sudo firewall-cmd --reload"
```

適用直後に SSH 接続の生存を確認する:

```bash
ssh centos10 "echo 'SSH OK'"
```

---

## Step 10: 単体試験を実施する

`verify_unit.py` でパラメータシートの期待値と実設定を突合する。

```bash
python3 scripts/verify_unit.py \
    --param evidence/param_sheet_centos10.yaml \
    --host centos10 \
    --out evidence/unit_result_$(date +%Y%m%d_%H%M%S).html
```

全項目 `PASS` であることを確認する:

```
合計: 11件 / PASS: 11件 / FAIL: 0件
```

エビデンスファイルが `evidence/unit_result_<日時>.md` に保存される。

---

## トラブルシューティング

### `sudo: a terminal is required to read the password`

`cc-dev` ユーザーの NOPASSWD 設定が未完了。Step 3-2 を再実施する。

### `getsockname failed: Not a socket`

Windows の OpenSSH は ControlMaster 非対応。`~/.ssh/config` から
`ControlMaster` / `ControlPath` / `ControlPersist` の行を削除する。

### `UnicodeEncodeError: 'cp932'`

スクリプトを Python 3.7 以上で実行しているか確認する。
または環境変数 `PYTHONUTF8=1` を設定する:

```bash
PYTHONUTF8=1 python3 scripts/verify_unit.py ...
```

### SSH 接続後に自分が締め出された

コンソール（KVM/IPMI 等）からサーバにアクセスし、以下を実行:

```bash
sudo firewall-cmd --reload
# または
sudo systemctl restart firewalld
```
