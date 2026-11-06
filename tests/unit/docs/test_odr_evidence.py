"""ODR 证据目录不能隐藏缺失的 child Change。"""
import pytest

from mdf_core.inspection.validate_changes import validate_changes


@pytest.mark.parametrize("kind,included,referenced,missing", [
    ("on-demand-release", [], True, False),
    ("on-demand-release", ["evidence"], True, True),
    ("on-demand-release", [], False, True),
    ("release", [], True, True),
])
def test_version_evidence_keeps_child_validation(tmp_path, kind, included, referenced, missing):
    root = tmp_path / "changes/1.3.0"
    evidence = root / "evidence/report.md"
    evidence.parent.mkdir(parents=True)
    evidence.write_text("验证结果\n")
    artifacts = "[changes/1.3.0/evidence/report.md]" if referenced else "[]"
    (root / "CHANGE.md").write_text(
        f"---\nchange_kind: {kind}\nincluded_changes: {included}\n"
        f"evidence:\n  artifacts: {artifacts}\n---\n")
    findings = []
    validate_changes(tmp_path, findings)
    assert any(f.code == "change.missing" and f.path == "changes/1.3.0/evidence" for f in findings) == missing
