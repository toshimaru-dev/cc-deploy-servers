#!/usr/bin/env python3
"""
Usage: compile_evidence.py --param <param_sheet.yaml>
                            --state-before <state_dir>
                            --state-after  <state_dir>
                            --apply-log    <apply_log.log>
                            --unit-result  <unit_result.md>
                            --integration-result <integration_result.md>
                            --operator     <実施者名>
                            --out          <evidence.md>

Phase 2〜5 の各記録を1つのMarkdownエビデンスレポートに集約する（非破壊）。
references/evidence_template.md のフォーマットに従って出力する。
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML が必要です。  pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def read_file(path: str | None, label: str) -> str:
    if not path:
        return f"(未指定: {label})"
    p = Path(path)
    if not p.exists():
        return f"(ファイルが見つかりません: {path})"
    return p.read_text(encoding="utf-8")


def load_list_all(state_dir: Path, zone: str, permanent: bool = False) -> str:
    suffix = "_permanent" if permanent else ""
    f = state_dir / f"list_all{suffix}_{zone}.txt"
    if f.exists():
        return f.read_text(encoding="utf-8")
    return "(取得なし)"


def diff_text(before: str, after: str) -> str:
    before_lines = before.splitlines()
    after_lines  = after.splitlines()
    diff_lines   = []
    before_set   = set(before_lines)
    after_set    = set(after_lines)
    for line in sorted(before_set - after_set):
        diff_lines.append(f"- {line}")
    for line in sorted(after_set - before_set):
        diff_lines.append(f"+ {line}")
    return "\n".join(diff_lines) if diff_lines else "(変更なし)"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--param",                required=True)
    p.add_argument("--state-before",         required=True)
    p.add_argument("--state-after",          required=True)
    p.add_argument("--apply-log",            default=None)
    p.add_argument("--unit-result",          default=None)
    p.add_argument("--integration-result",   default=None)
    p.add_argument("--operator",             required=True, help="実施者名")
    p.add_argument("--out",                  required=True)
    args = p.parse_args()

    with open(args.param, encoding="utf-8") as f:
        param = yaml.safe_load(f)

    host     = param.get("host", {})
    hostname = host.get("name", "(不明)")
    host_ip  = host.get("ip",   "(不明)")
    zones    = param.get("zones", [])

    state_before = Path(args.state_before)
    state_after  = Path(args.state_after)
    now          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- Section 1: Before ---
    before_sections = []
    for zone_conf in zones:
        z = zone_conf["name"]
        before_sections.append(f"### zone: {z} (runtime)\n```\n{load_list_all(state_before, z)}\n```")
        before_sections.append(f"### zone: {z} (permanent)\n```\n{load_list_all(state_before, z, permanent=True)}\n```")
    section_before = "\n\n".join(before_sections)

    # --- Section 2: 適用コマンド ---
    apply_log = read_file(args.apply_log, "適用ログ")
    section_apply = f"```\n{apply_log}\n```"

    # --- Section 3: After & diff ---
    after_sections = []
    for zone_conf in zones:
        z = zone_conf["name"]
        b = load_list_all(state_before, z, permanent=True)
        a = load_list_all(state_after,  z, permanent=True)
        d = diff_text(b, a)
        after_sections.append(
            f"### zone: {z} (runtime)\n```\n{load_list_all(state_after, z)}\n```\n"
            f"### zone: {z} (permanent)\n```\n{a}\n```\n"
            f"### diff (permanent: Before → After)\n```diff\n{d}\n```"
        )
    section_after = "\n\n".join(after_sections)

    # --- Section 4: 単体試験 ---
    section_unit = read_file(args.unit_result, "単体試験結果")

    # --- Section 5: 結合試験 ---
    section_integration = read_file(args.integration_result, "結合試験結果")

    # --- Section 6: 総合判定 ---
    unit_pass        = "FAIL" not in section_unit        if args.unit_result        else "未実施"
    integration_pass = "FAIL" not in section_integration if args.integration_result else "未実施"
    overall          = "合格" if (unit_pass is True and integration_pass is True) else "要確認"

    section_summary = f"""| 試験区分 | 結果 |
|----------|------|
| 単体試験 | {"PASS" if unit_pass is True else "FAIL" if unit_pass is False else "未実施"} |
| 結合試験 | {"PASS" if integration_pass is True else "FAIL" if integration_pass is False else "未実施"} |
| **総合** | **{overall}** |"""

    report = f"""# firewalld設定エビデンス — {hostname}

- 対象ホスト: {hostname} ({host_ip})
- 環境: 検証環境
- 実施者: {args.operator}
- 実施日時: {now}

---

## 1. 設定前 (Before)

{section_before}

---

## 2. 適用コマンド

{section_apply}

---

## 3. 設定後 (After) と差分

{section_after}

---

## 4. 単体試験結果

{section_unit}

---

## 5. 結合試験結果

{section_integration}

---

## 6. 総合判定

{section_summary}
"""

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"エビデンスレポート出力: {args.out}")


if __name__ == "__main__":
    main()
