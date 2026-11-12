"""将 Agent 的逐步观察转换为 playbook JUnit；不代替实际执行或判定。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET


def write_report(report_dir: Path, playbook: str, results: Path) -> Path:
    state = json.loads((report_dir / "pending.json").read_text(encoding="utf-8"))
    expected = next((item["steps"] for item in state["playbooks"] if item["path"] == playbook), None)
    if expected is None:
        raise ValueError("playbook 不在 pending 清单中")
    rows = json.loads(results.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("results 必须为逐步观察的 JSON object 列表")
    if [row.get("id") for row in rows] != expected:
        raise ValueError("results 必须按 pending 顺序覆盖每个步骤且不重复")
    suite = ET.Element("testsuite", name=state["suite"], tests=str(len(rows)))
    failures = 0
    for row in rows:
        outcome, seconds = row.get("result"), row.get("time")
        if outcome not in {"passed", "failed"}:
            raise ValueError("result 只接受 passed 或 failed；环境未就绪使用 failed")
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("time 必须为非负有限秒数")
        observation, logs = row.get("observation"), row.get("logs")
        if not isinstance(observation, str) or not observation.strip():
            raise ValueError("observation 必须记录实际观察或无法执行的原因")
        if not isinstance(logs, list) or any(not isinstance(log, str) or not log.strip() for log in logs):
            raise ValueError("logs 必须为本步骤的日志路径列表；未运行命令时可为空")
        case = ET.SubElement(suite, "testcase", classname=playbook, name=row["id"], time=str(seconds))
        if outcome == "failed":
            failures += 1
            ET.SubElement(case, "failure", message=observation)
        ET.SubElement(case, "system-out").text = observation + "\n" + "\n".join(logs)
    suite.set("failures", str(failures))
    filename = hashlib.sha256(playbook.encode()).hexdigest() + ".xml"
    target = report_dir / filename
    ET.indent(suite)
    ET.ElementTree(suite).write(target, encoding="utf-8", xml_declaration=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--playbook", required=True)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    try:
        path = write_report(args.report_dir, args.playbook, args.results)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"playbook JUnit 生成失败: {exc}\n")
    print(json.dumps({"report": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
