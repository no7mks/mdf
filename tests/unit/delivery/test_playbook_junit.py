"""观察到 JUnit 的转换：防止步骤遗漏、同名覆盖与失败误报。"""
import json
import xml.etree.ElementTree as ET

import pytest

from playbook_junit import write_report


def _inputs(tmp_path, rows):
    books = ["tests/playbooks/a/check.md", "tests/playbooks/b/check.md"]
    (tmp_path / "pending.json").write_text(json.dumps({
        "suite": "billing", "playbooks": [{"path": p, "steps": ["S01"]} for p in books],
    }))
    source = tmp_path / "observations.json"
    source.write_text(json.dumps(rows))
    return books, source


def _row(**overrides):
    return {"id": "S01", "result": "failed", "time": 1.2,
            "observation": '实际值 < 预期值 & "失败"', "logs": [".mdf/logs/run.log"], **overrides}


def test_writer_separates_same_names_and_preserves_failure(tmp_path):
    books, source = _inputs(tmp_path, [_row()])
    paths = [write_report(tmp_path, book, source) for book in books]
    assert paths[0] != paths[1]
    for book, path in zip(books, paths):
        case = ET.parse(path).getroot().find("testcase")
        assert case.attrib == {"classname": book, "name": "S01", "time": "1.2"}
        assert case.find("failure").get("message") == _row()["observation"]
        assert ".mdf/logs/run.log" in case.findtext("system-out")
    source.write_text(json.dumps([_row(result="passed")]))
    assert write_report(tmp_path, books[0], source) == paths[0]
    assert ET.parse(paths[0]).getroot().find("testcase/failure") is None


@pytest.mark.parametrize("rows", [
    [], [_row(), _row()], [_row(id="S02")], [_row(result="skipped")],
    [_row(time=-1)], [_row(time=float("nan"))], [_row(observation="")], [_row(logs="not-a-list")],
])
def test_writer_rejects_incomplete_or_invalid_observations(tmp_path, rows):
    books, source = _inputs(tmp_path, rows)
    with pytest.raises(ValueError):
        write_report(tmp_path, books[0], source)
    assert not list(tmp_path.glob("*.xml"))
