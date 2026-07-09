#!/usr/bin/env python3
"""
Usage: verify_unit.py --param <param_sheet.yaml> --host <ssh_alias> [--zone <zone>] [--out <result.html>]

単体試験: firewall-cmd --list-all の実測値とパラメータシートの期待値を突合し、
項目ごとに合否を判定する（非破壊・参照系のみ）。

出力:
  stdout にテキスト形式の試験結果サマリ
  --out を指定すれば HTML ファイルに保存
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML が必要です。  pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def ssh_run(alias: str, cmd: str) -> str:
    result = subprocess.run(
        ["ssh", alias, cmd],
        capture_output=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(f"SSH失敗: {cmd}\n{result.stderr}")
    return result.stdout.strip()


def parse_list_all(text: str) -> dict:
    state = {
        "interfaces": [],
        "sources": [],
        "services": [],
        "ports": [],
        "rich_rules": [],
        "target": "default",
    }
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("interfaces:"):
            state["interfaces"] = line.split(":", 1)[1].strip().split()
        elif line.startswith("sources:"):
            state["sources"] = line.split(":", 1)[1].strip().split()
        elif line.startswith("services:"):
            state["services"] = line.split(":", 1)[1].strip().split()
        elif line.startswith("ports:"):
            state["ports"] = line.split(":", 1)[1].strip().split()
        elif line.startswith("target:"):
            state["target"] = line.split(":", 1)[1].strip()
        elif line.startswith("rule "):
            state["rich_rules"].append(line)
    return state


def compare(zone_name: str, expected: dict, actual_rt: dict, actual_perm: dict) -> list[dict]:
    rows = []

    def check_set(key: str, expected_list: list, actual_list: list, label: str):
        exp_set = set(expected_list)
        act_set = set(actual_list)
        ok = exp_set == act_set
        rows.append({
            "zone": zone_name,
            "item": f"{key} ({label})",
            "expected": ", ".join(sorted(exp_set)) or "(none)",
            "actual":   ", ".join(sorted(act_set)) or "(none)",
            "result":   "PASS" if ok else "FAIL",
        })

    for key in ["interfaces", "sources", "services", "ports", "rich_rules"]:
        exp = expected.get(key, [])
        check_set(key, exp, actual_rt.get(key, []), "runtime")
        # interfaces は NetworkManager 管理時に permanent XML へ書かれないため永続チェックをスキップ
        if key != "interfaces":
            check_set(key, exp, actual_perm.get(key, []), "permanent")

    exp_target = expected.get("target", "default")
    for label, actual in [("runtime", actual_rt), ("permanent", actual_perm)]:
        act_target = actual.get("target", "default")
        rows.append({
            "zone": zone_name,
            "item": f"target ({label})",
            "expected": exp_target,
            "actual":   act_target,
            "result":   "PASS" if exp_target == act_target else "FAIL",
        })

    return rows


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_html(rows: list[dict], total: int, passed: int, failed: int, host: str, timestamp: str) -> str:
    overall_class = "pass" if failed == 0 else "fail"
    overall_label = "合格" if failed == 0 else "不合格"
    pass_pct = round(passed / total * 100) if total > 0 else 0

    row_html = ""
    prev_zone = None
    for r in rows:
        css  = "pass" if r["result"] == "PASS" else "fail"
        mark = "✓" if r["result"] == "PASS" else "✗"
        zone_cell = ""
        if r["zone"] != prev_zone:
            zone_count = sum(1 for x in rows if x["zone"] == r["zone"])
            zone_cell  = f'<td class="zone-cell" rowspan="{zone_count}">{escape(r["zone"])}</td>'
            prev_zone  = r["zone"]
        row_html += (
            f'<tr class="{css}">'
            f'{zone_cell}'
            f'<td>{escape(r["item"])}</td>'
            f'<td class="code">{escape(r["expected"])}</td>'
            f'<td class="code">{escape(r["actual"])}</td>'
            f'<td class="result-cell"><span class="pill {css}">{mark} {r["result"]}</span></td>'
            f'</tr>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>単体試験結果 — {escape(host)}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Segoe UI", "Hiragino Sans", sans-serif;
      background: #f4f6f9;
      color: #1a1a2e;
      padding: 2rem;
      font-size: 14px;
    }}

    /* ── ヘッダー ── */
    .header {{
      background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
      color: #fff;
      border-radius: 10px;
      padding: 1.6rem 2rem;
      margin-bottom: 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      flex-wrap: wrap;
      gap: 1rem;
    }}
    .header h1 {{ font-size: 1.3rem; font-weight: 700; letter-spacing: 0.02em; }}
    .header .meta {{ font-size: 0.82rem; opacity: 0.85; margin-top: 0.3rem; line-height: 1.7; }}
    .overall-badge {{
      font-size: 1rem; font-weight: 700;
      padding: 0.5rem 1.4rem;
      border-radius: 999px;
      white-space: nowrap;
      border: 2px solid rgba(255,255,255,0.5);
    }}
    .overall-badge.pass {{ background: #22c55e; }}
    .overall-badge.fail {{ background: #ef4444; }}

    /* ── サマリカード ── */
    .cards {{
      display: flex;
      gap: 1rem;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
    }}
    .card {{
      background: #fff;
      border-radius: 8px;
      padding: 1rem 1.5rem;
      flex: 1;
      min-width: 130px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
      text-align: center;
    }}
    .card .num {{ font-size: 2rem; font-weight: 700; line-height: 1.1; }}
    .card .label {{ font-size: 0.78rem; color: #666; margin-top: 0.25rem; }}
    .card.total  .num {{ color: #1e3a5f; }}
    .card.passed .num {{ color: #16a34a; }}
    .card.failed .num {{ color: #dc2626; }}

    /* プログレスバー */
    .progress-wrap {{
      background: #fff;
      border-radius: 8px;
      padding: 0.9rem 1.5rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }}
    .progress-label {{
      display: flex;
      justify-content: space-between;
      font-size: 0.8rem;
      color: #555;
      margin-bottom: 0.4rem;
    }}
    .progress-bar {{
      height: 10px;
      background: #fee2e2;
      border-radius: 999px;
      overflow: hidden;
    }}
    .progress-fill {{
      height: 100%;
      background: linear-gradient(90deg, #16a34a, #22c55e);
      border-radius: 999px;
      width: {pass_pct}%;
      transition: width 0.4s ease;
    }}

    /* ── テーブル ── */
    .table-wrap {{
      background: #fff;
      border-radius: 8px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
      overflow: hidden;
    }}
    table {{ border-collapse: collapse; width: 100%; }}
    thead tr {{ background: #1e3a5f; color: #fff; }}
    th {{ padding: 10px 14px; font-weight: 600; font-size: 0.82rem;
          letter-spacing: 0.03em; text-align: left; white-space: nowrap; }}
    td {{ padding: 9px 14px; border-bottom: 1px solid #eef0f4; vertical-align: middle; }}
    tr:last-child td {{ border-bottom: none; }}

    td.zone-cell {{
      background: #f0f4ff;
      font-weight: 600;
      color: #1e3a5f;
      white-space: nowrap;
      border-right: 2px solid #c7d5f0;
    }}
    td.code {{
      font-family: "Consolas", "Courier New", monospace;
      font-size: 0.8rem;
      color: #334;
      word-break: break-all;
    }}
    td.result-cell {{ white-space: nowrap; text-align: center; }}

    tr.pass {{ background: #f0fdf4; }}
    tr.fail {{ background: #fff5f5; }}
    tr.pass:hover {{ background: #dcfce7; }}
    tr.fail:hover {{ background: #fee2e2; }}

    .pill {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 700;
    }}
    .pill.pass {{ background: #dcfce7; color: #15803d; }}
    .pill.fail {{ background: #fee2e2; color: #b91c1c; }}

    /* ── フッター ── */
    .footer {{ margin-top: 1.2rem; font-size: 0.75rem; color: #999; text-align: right; }}
  </style>
</head>
<body>

  <div class="header">
    <div>
      <h1>firewalld 単体試験結果</h1>
      <div class="meta">
        対象ホスト: <strong>{escape(host)}</strong><br>
        実施日時: {escape(timestamp)}
      </div>
    </div>
    <span class="overall-badge {overall_class}">総合判定: {overall_label}</span>
  </div>

  <div class="cards">
    <div class="card total">
      <div class="num">{total}</div>
      <div class="label">試験項目数</div>
    </div>
    <div class="card passed">
      <div class="num">{passed}</div>
      <div class="label">PASS</div>
    </div>
    <div class="card failed">
      <div class="num">{failed}</div>
      <div class="label">FAIL</div>
    </div>
  </div>

  <div class="progress-wrap">
    <div class="progress-label">
      <span>PASS 率</span>
      <span>{pass_pct}%</span>
    </div>
    <div class="progress-bar"><div class="progress-fill"></div></div>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>zone</th><th>項目</th><th>expected</th><th>actual</th><th>合否</th>
        </tr>
      </thead>
      <tbody>
{row_html}      </tbody>
    </table>
  </div>

  <div class="footer">Generated by cc-deploy-servers / verify_unit.py</div>

</body>
</html>
"""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--param", required=True, help="パラメータシート YAML")
    p.add_argument("--host",  required=True, help="SSH alias")
    p.add_argument("--zone",  help="対象zone（省略時は全zone）")
    p.add_argument("--out",   help="結果を保存するフォルダパス（例: evidence/unit_20260101_120000）。フォルダを作成し result.html を出力する")
    args = p.parse_args()

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(args.param) as f:
        param = yaml.safe_load(f)

    host_name = param.get("host", {}).get("name", args.host)
    zones = param.get("zones", [])
    if args.zone:
        zones = [z for z in zones if z["name"] == args.zone]

    all_rows = []
    for zone_conf in zones:
        zone_name = zone_conf["name"]
        print(f"  取得中: zone={zone_name} ...")
        try:
            rt_text   = ssh_run(args.host, f"sudo firewall-cmd --zone={zone_name} --list-all")
            perm_text = ssh_run(args.host, f"sudo firewall-cmd --zone={zone_name} --list-all --permanent")
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

        actual_rt   = parse_list_all(rt_text)
        actual_perm = parse_list_all(perm_text)
        rows = compare(zone_name, zone_conf, actual_rt, actual_perm)
        all_rows.extend(rows)

    total  = len(all_rows)
    passed = sum(1 for r in all_rows if r["result"] == "PASS")
    failed = total - passed

    print(f"合計: {total}件 / PASS: {passed}件 / FAIL: {failed}件")

    if args.out:
        html = format_html(all_rows, total, passed, failed, host_name, timestamp)
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "result.html"
        out_file.write_text(html, encoding="utf-8")
        print(f"結果保存: {out_file}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
