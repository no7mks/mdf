"""项目 rule 文件加载、路径边界与配置契约。"""

import hashlib
import json

import pytest

from mdf_core.cli import main
from mdf_core.foundation.constants import BASELINES
from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.gitutil import run
from mdf_core.workspace.init_repo import init_files, render_manifest
from mdf_core.workspace.project_rules import load_project_rule, validate_rules
from mdf_core.inspection.validate_manifest import validate_manifest
from mdf_core.foundation.yamlutil import parse_yaml


@pytest.fixture
def repo(tmp_path):
    run(["git", "init", "-b", "master"], cwd=tmp_path)
    (tmp_path / ".mdf").mkdir()
    return tmp_path


def track(repo, path=".mdf/rules/design.md", data=b"Project rule\r\n"):
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(data)
    run(["git", "add", "--", path], cwd=repo)
    return file


@pytest.mark.parametrize("rules", [
    None, [], "rule.md", {"implement": "rule.md"}, {"design": None},
    {"design": ""}, {"design": " "}, {"design": "/rule.md"},
    {"design": "../rule.md"}, {"design": ["rule.md"]},
    {"design": {"type": "command", "path": "rule.sh"}},
])
def test_invalid_config(rules):
    with pytest.raises(MDFError, match="rule"):
        validate_rules({"rules": rules})


def test_optional_rules():
    assert validate_rules({}) == {}
    assert validate_rules({"rules": {}}) == {}
    assert load_project_rule(None, {}, "design") is None


@pytest.mark.parametrize("stage", ["design", "code-review"])
def test_full_text_fingerprint_and_dirty_tracked_file(repo, stage):
    file = track(repo)
    data = "项目优先\r\n".encode() + b"$(touch should-not-exist)\n"
    file.write_bytes(data)
    rule = load_project_rule(repo, {"rules": {stage: ".mdf/rules/design.md"}}, stage)
    assert rule == {"path": ".mdf/rules/design.md", "content": data.decode(),
                    "sha256": hashlib.sha256(data).hexdigest()}
    assert not (repo / "should-not-exist").exists()


@pytest.mark.parametrize("kind", ["missing", "untracked", "directory", "empty", "encoding"])
def test_invalid_files(repo, kind):
    path = ".mdf/rules/design.md"
    if kind == "directory":
        (repo / path).mkdir(parents=True)
    elif kind != "missing":
        data = {"empty": b" \r\n", "encoding": b"\xff"}.get(kind, b"rule")
        file = track(repo, data=data)
        if kind == "untracked":
            run(["git", "rm", "--cached", "--", path], cwd=repo)
            assert file.exists()
    with pytest.raises(MDFError, match="rules.design"):
        load_project_rule(repo, {"rules": {"design": path}}, "design")


@pytest.mark.parametrize("parent", [False, True])
def test_symlink_in_path_rejected(repo, parent):
    target = track(repo)
    link = repo / "link"
    link.symlink_to(target.parent if parent else target, target_is_directory=parent)
    raw = "link/design.md" if parent else "link"
    with pytest.raises(MDFError, match="symlink"):
        load_project_rule(repo, {"rules": {"design": raw}}, "design")


def test_literal_git_path_does_not_match_other_tracked_file(repo):
    track(repo, "rules/other.md")
    (repo / "rules/*.md").write_text("untracked")
    with pytest.raises(MDFError, match="tracked"):
        load_project_rule(repo, {"rules": {"design": "rules/*.md"}}, "design")


def test_cli_and_manifest_validation(repo, capsys):
    track(repo)
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text("rules:\n  design: .mdf/rules/design.md\n")
    assert main(["project-rules", "--repo", str(repo), "--stage", "design"]) == 0
    loaded = json.loads(capsys.readouterr().out)
    assert loaded["project_rule"]["content"] == "Project rule\r\n"
    assert main(["project-rules", "--repo", str(repo), "--stage", "code-review"]) == 0
    assert json.loads(capsys.readouterr().out)["project_rule"] is None
    manifest.write_text("rules:\n  design: missing.md\n")
    assert main(["project-rules", "--repo", str(repo), "--stage", "design"]) == 1
    assert json.loads(capsys.readouterr().err.splitlines()[-1])["error"] == "invalid_rules"
    findings = []
    validate_manifest(repo, findings)
    assert any(f.code == "manifest.rules" for f in findings)


@pytest.mark.parametrize("rules", [{}, {"design": "rules/design.md", "code-review": "review.md"}])
def test_init_preserves_rules_and_does_not_create_files(repo, rules):
    baselines = {name: {"status": "not_applicable", "reason": "测试"} for name in BASELINES}
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(render_manifest(baselines, None, ["src"], rules=rules))
    files = init_files(repo, baselines, latest_release=None,
                       verification={name: "true" for name in ("lint", "build", "quick", "smoke", "release")},
                       implementation_roots=["src"])
    assert parse_yaml(files[manifest])["rules"] == rules
    assert not any(path.as_posix().endswith("rules/design.md") for path in files)


def test_init_rejects_invalid_rules_instead_of_dropping_them(repo):
    (repo / ".mdf/manifest.yaml").write_text("rules: null\n")
    with pytest.raises(MDFError, match="rules"):
        init_files(repo, {}, latest_release=None, verification={}, implementation_roots=["src"])


def test_rule_fingerprint_detects_content_changes(repo):
    file = track(repo)
    manifest = {"rules": {"design": ".mdf/rules/design.md"}}
    first = load_project_rule(repo, manifest, "design")
    file.write_text("new project rule")
    second = load_project_rule(repo, manifest, "design")
    assert first["sha256"] != second["sha256"]
    assert second["content"] == "new project rule"


def test_worktree_reads_its_own_rule(repo, tmp_path_factory):
    track(repo)
    (repo / ".mdf/manifest.yaml").write_text("rules:\n  design: .mdf/rules/design.md\n")
    run(["git", "add", ".mdf/manifest.yaml"], cwd=repo)
    run(["git", "commit", "-m", "test: 创建 rule 基线"], cwd=repo)
    owner = tmp_path_factory.mktemp("rule-owner") / "worktree"
    run(["git", "worktree", "add", "--detach", str(owner)], cwd=repo)
    (owner / ".mdf/rules/design.md").write_text("owner rule")
    manifest = {"rules": {"design": ".mdf/rules/design.md"}}
    assert load_project_rule(owner, manifest, "design")["content"] == "owner rule"
    assert load_project_rule(repo, manifest, "design")["content"] == "Project rule\r\n"
