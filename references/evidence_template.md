# firewalld設定エビデンス — <host.name>

- 対象ホスト: <name> (<ip>)
- 環境: 検証環境
- 実施者: <ユーザーに確認>
- 実施日時: <実行タイムスタンプ>

---

## 1. 設定前 (Before)

### zone: <zone名> (runtime)
```
（Phase 2 の firewall-cmd --zone=<zone> --list-all 出力）
```

### zone: <zone名> (permanent)
```
（Phase 2 の firewall-cmd --zone=<zone> --list-all --permanent 出力）
```

---

## 2. 適用コマンド

```
（Phase 3 で承認・実行した firewall-cmd コマンド全文）
```

---

## 3. 設定後 (After) と差分

### zone: <zone名> (runtime)
```
（適用後 firewall-cmd --zone=<zone> --list-all 出力）
```

### zone: <zone名> (permanent)
```
（適用後 firewall-cmd --zone=<zone> --list-all --permanent 出力）
```

### diff (permanent: Before → After)
```diff
- （削除された行）
+ （追加された行）
```

---

## 4. 単体試験結果

| zone | 項目 | expected | actual | 合否 |
|------|------|----------|--------|------|
| public | services (runtime) | ssh, http, https | ssh, http, https | ✓ PASS |
| public | services (permanent) | ssh, http, https | ssh, http, https | ✓ PASS |
| public | ports (runtime) | 8080/tcp | 8080/tcp | ✓ PASS |
| public | ports (permanent) | 8080/tcp | 8080/tcp | ✓ PASS |

**合計: N件 / PASS: N件 / FAIL: 0件**

---

## 5. 結合試験結果

| 試験元 | 対象port | 期待 | 実測 | 合否 |
|--------|----------|------|------|------|
| test01 | 22/tcp | reachable | reachable | ✓ PASS |
| test01 | 80/tcp | reachable | reachable | ✓ PASS |
| test01 | 3306/tcp | unreachable | unreachable | ✓ PASS |

**合計: N件 / PASS: N件 / FAIL: 0件**

---

## 6. 総合判定

| 試験区分 | 結果 |
|----------|------|
| 単体試験 | PASS |
| 結合試験 | PASS |
| **総合** | **合格** |
