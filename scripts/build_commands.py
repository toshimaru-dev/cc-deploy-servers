#!/usr/bin/env python3
"""
Usage: build_commands.py --param <param_sheet.yaml> --state <state_dir> [--zone <zone>]

パラメータシートと collect_state.sh の取得結果を比較し、
適用すべき firewall-cmd コマンド列を生成する（非破壊・dry-run専用）。

出力: stdout にコマンド一覧（承認後に apply_config.sh へ渡す）
      --out を指定すれば JSON ファイルにも保存

lockout警告:
  生成コマンドの適用後に ssh service または 22/tcp が失われる場合は
  WARN: LOCKOUT RISK を出力して終了コード 2 で終了する。
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML が必要です。  pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def parse_list_all(text: str) -> dict:
    """firewall-cmd --list-all の出力をパース"""
    result = {
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
            result["interfaces"] = line.split(":", 1)[1].strip().split()
        elif line.startswith("sources:"):
            result["sources"] = line.split(":", 1)[1].strip().split()
        elif line.startswith("services:"):
            result["services"] = line.split(":", 1)[1].strip().split()
        elif line.startswith("ports:"):
            result["ports"] = line.split(":", 1)[1].strip().split()
        elif line.startswith("rich rules:"):
            pass  # multi-line: handled separately below
        elif re.match(r"rule ", line):
            result["rich_rules"].append(line)
        elif line.startswith("target:"):
            result["target"] = line.split(":", 1)[1].strip()
    return result


def load_current_state(state_dir: Path, zone: str) -> dict:
    perm_file = state_dir / f"list_all_permanent_{zone}.txt"
    rt_file   = state_dir / f"list_all_{zone}.txt"
    if perm_file.exists():
        return parse_list_all(perm_file.read_text())
    if rt_file.exists():
        return parse_list_all(rt_file.read_text())
    return {}


def diff_sets(expected: list, actual: list):
    e, a = set(expected), set(actual)
    return sorted(e - a), sorted(a - e)   # to_add, to_remove


def check_lockout(zone_name: str, desired: dict) -> bool:
    """SSH到達手段が確保されているか確認"""
    has_ssh_service = "ssh" in desired.get("services", [])
    has_port_22 = any(p.startswith("22/") for p in desired.get("ports", []))
    has_source   = bool(desired.get("sources"))
    has_rich_ssh = any("22" in r for r in desired.get("rich_rules", []))
    return has_ssh_service or has_port_22 or (has_source and has_rich_ssh)


def build_zone_commands(zone_name: str, desired: dict, current: dict) -> list[str]:
    cmds = []

    # interfaces
    add_iface, rem_iface = diff_sets(desired.get("interfaces", []), current.get("interfaces", []))
    for i in add_iface:
        cmds.append(f"firewall-cmd --zone={zone_name} --add-interface={i} --permanent")
    for i in rem_iface:
        cmds.append(f"firewall-cmd --zone={zone_name} --remove-interface={i} --permanent")

    # sources
    add_src, rem_src = diff_sets(desired.get("sources", []), current.get("sources", []))
    for s in add_src:
        cmds.append(f"firewall-cmd --zone={zone_name} --add-source={s} --permanent")
    for s in rem_src:
        cmds.append(f"firewall-cmd --zone={zone_name} --remove-source={s} --permanent")

    # services
    add_svc, rem_svc = diff_sets(desired.get("services", []), current.get("services", []))
    for s in add_svc:
        cmds.append(f"firewall-cmd --zone={zone_name} --add-service={s} --permanent")
    for s in rem_svc:
        cmds.append(f"firewall-cmd --zone={zone_name} --remove-service={s} --permanent")

    # ports
    add_port, rem_port = diff_sets(desired.get("ports", []), current.get("ports", []))
    for p in add_port:
        cmds.append(f"firewall-cmd --zone={zone_name} --add-port={p} --permanent")
    for p in rem_port:
        cmds.append(f"firewall-cmd --zone={zone_name} --remove-port={p} --permanent")

    # rich_rules
    add_rules, rem_rules = diff_sets(desired.get("rich_rules", []), current.get("rich_rules", []))
    for r in add_rules:
        cmds.append(f'firewall-cmd --zone={zone_name} --add-rich-rule=\'{r}\' --permanent')
    for r in rem_rules:
        cmds.append(f'firewall-cmd --zone={zone_name} --remove-rich-rule=\'{r}\' --permanent')

    # target
    desired_target  = desired.get("target", "default")
    current_target  = current.get("target", "default")
    if desired_target != current_target:
        cmds.append(f"firewall-cmd --zone={zone_name} --set-target={desired_target} --permanent")

    return cmds


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--param",  required=True, help="パラメータシート YAML")
    p.add_argument("--state",  required=True, help="collect_state.sh の出力ディレクトリ")
    p.add_argument("--zone",   help="対象zone名（省略時は param_sheet 内全zone）")
    p.add_argument("--out",    help="コマンドリストを保存する JSON ファイルパス")
    args = p.parse_args()

    param_path = Path(args.param)
    state_dir  = Path(args.state)

    if not param_path.exists():
        print(f"ERROR: パラメータシートが見つかりません: {param_path}", file=sys.stderr)
        sys.exit(1)
    if not state_dir.exists():
        print(f"ERROR: stateディレクトリが見つかりません: {state_dir}", file=sys.stderr)
        sys.exit(1)

    with open(param_path) as f:
        param = yaml.safe_load(f)

    zones = param.get("zones", [])
    if args.zone:
        zones = [z for z in zones if z["name"] == args.zone]
        if not zones:
            print(f"ERROR: zone '{args.zone}' がパラメータシートにありません", file=sys.stderr)
            sys.exit(1)

    all_commands = []
    lockout_zones = []

    for zone_conf in zones:
        zone_name = zone_conf["name"]
        current   = load_current_state(state_dir, zone_name)
        cmds      = build_zone_commands(zone_name, zone_conf, current)
        all_commands.extend(cmds)

        if not check_lockout(zone_name, zone_conf):
            lockout_zones.append(zone_name)

    if all_commands:
        all_commands.append("firewall-cmd --reload")

    print("=== 生成コマンド（dry-run） ===")
    if not all_commands:
        print("(差分なし — 変更不要)")
    else:
        for cmd in all_commands:
            print(f"  {cmd}")

    if lockout_zones:
        print("\nWARN: LOCKOUT RISK", file=sys.stderr)
        print(f"  以下のzoneにSSH到達手段（ssh service / 22/tcp）が含まれていません:", file=sys.stderr)
        for z in lockout_zones:
            print(f"    - {z}", file=sys.stderr)
        print("  適用するとSSH接続が切断される可能性があります。承認前に必ず確認してください。", file=sys.stderr)

    if args.out and all_commands:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"commands": all_commands, "lockout_risk": bool(lockout_zones)}, indent=2, ensure_ascii=False))
        print(f"\nコマンドリスト保存: {args.out}")

    if lockout_zones:
        sys.exit(2)


if __name__ == "__main__":
    main()
