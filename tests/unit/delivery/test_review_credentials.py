"""code-review 凭证：release 复用子交付证据时的净增量、组合影响面与 0 reviewer 校验。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403

load_core_module()
from mdf_core.execution.modules import parse_modules  # noqa: E402
from mdf_core.foundation.errors import MDFError  # noqa: E402
from mdf_core.foundation.yamlutil import parse_yaml  # noqa: E402
from mdf_core.reviewing import credentials, report, schema  # noqa: E402
from mdf_core.reviewing.context import fingerprint  # noqa: E402


def modules_text(*, shared=False, depends=""):
    def module(name, pattern, deps=""):
        return (f"  {name}:\n    sourceset: ['{pattern}']\n    ignore: []\n    lint: 'true'\n    build: 'true'\n"
                + "".join(f"    {s}:\n      command: 'true'\n      tests: ['t/**']\n" for s in ("quick", "smoke", "release"))
                + "    named: []\n" + (f"    depends_on: [{deps}]\n" if deps else ""))
    if shared:
        return "modules:\n" + module("both", "*.py")
    return "modules:\n" + module("ma", "a.py") + module("mb", "b.py", depends)


def config(**kwargs):
    return parse_modules(parse_yaml(modules_text(**kwargs)))


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".mdf").mkdir()
    (root / ".mdf/modules.yaml").write_text(modules_text())
    (root / "a.py").write_text("a = 1\n")
    (root / "b.py").write_text("b = 1\n")
    init_git(root)
    return root


def identity(repo, paths, rules="r1"):
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    return credentials.code_identity(repo, head, paths, rules, "- [ ] 目标\n", {})


def record(repo, source, paths, kind="feature", rules="r1"):
    ident = identity(repo, paths, rules)
    credentials.record_code_credential(repo, {"source": source, "kind": kind, "credential": ident}, 1)
    return ident


def test_identity_ignores_objective_progress_but_tracks_content(repo):
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    done = credentials.code_identity(repo, head, ["a.py"], "r1", "- [x] 目标\n", {})
    assert done["key"] == identity(repo, ["a.py"])["key"]
    assert done["key"] != identity(repo, ["a.py"], rules="r2")["key"]
    assert done["key"] != identity(repo, ["a.py", "b.py"])["key"]


def test_release_with_every_path_covered_by_one_child_allows_zero_reviewers(repo):
    record(repo, "feature/a", ["a.py"])
    record(repo, "feature/b", ["b.py"])
    analysis = credentials.reuse_analysis(repo, "release/1.0.0", identity(repo, ["a.py", "b.py"], "r1"), config())
    assert analysis["net_increment"] == [] and analysis["combined_impact"] == []
    assert analysis["zero_reviewers_allowed"] is True and len(analysis["child_credentials"]) == 2


def test_net_increment_or_changed_rules_require_reviewers(repo):
    record(repo, "feature/a", ["a.py"])
    uncovered = credentials.reuse_analysis(repo, "release/1.0.0", identity(repo, ["a.py", "b.py"]), config())
    assert uncovered["net_increment"] == ["b.py"] and not uncovered["zero_reviewers_allowed"]
    other_rules = credentials.reuse_analysis(repo, "release/1.0.0", identity(repo, ["a.py"], rules="r2"), config())
    assert other_rules["net_increment"] == ["a.py"] and not other_rules["zero_reviewers_allowed"]


def test_file_touched_by_two_children_is_combined_impact(repo):
    record(repo, "feature/a", ["a.py"])
    record(repo, "feature/c", ["a.py"], rules="r1")
    (repo / "a.py").write_text("a = 2\n")
    git(repo, "commit", "-qam", "change")
    record(repo, "feature/d", ["a.py"])
    analysis = credentials.reuse_analysis(repo, "release/1.0.0", identity(repo, ["a.py"]), config())
    assert analysis["combined_impact"] == ["a.py"] and not analysis["zero_reviewers_allowed"]


def test_combined_impact_counts_distinct_deliveries_not_rounds(repo):
    record(repo, "feature/a", ["a.py"])
    record(repo, "feature/a", ["a.py"], rules="r1")
    analysis = credentials.reuse_analysis(repo, "release/1.0.0", identity(repo, ["a.py"]), config())
    assert analysis["combined_impact"] == [] and analysis["zero_reviewers_allowed"] is True


def test_children_touching_one_or_dependent_modules_are_combined_impact(repo):
    record(repo, "feature/a", ["a.py"])
    record(repo, "feature/b", ["b.py"])
    both = identity(repo, ["a.py", "b.py"])
    shared = credentials.reuse_analysis(repo, "release/1.0.0", both, config(shared=True))
    assert shared["combined_modules"] == ["both"] and not shared["zero_reviewers_allowed"]
    linked = credentials.reuse_analysis(repo, "release/1.0.0", both, config(depends="ma"))
    assert linked["combined_modules"] == ["ma", "mb"] and not linked["zero_reviewers_allowed"]
    assert linked["combined_impact"] == [] and linked["net_increment"] == []


def test_changes_requested_revokes_pass_and_tampered_context_is_rejected(repo):
    ident = record(repo, "feature/a", ["a.py"])
    assert credentials.reuse_analysis(repo, "release/1.0.0", ident, config())["net_increment"] == []
    credentials.record_code_credential(repo, {"source": "feature/a", "kind": "feature", "credential": ident}, 1,
                                       decision="changes_requested")
    assert credentials.reuse_analysis(repo, "release/1.0.0", ident, config())["net_increment"] == ["a.py"]
    tampered = {**ident, "code_digest": "tampered"}
    with pytest.raises(MDFError) as caught:
        credentials.confirm_code_context(repo, {
            "review_head": "HEAD", "paths": ["a.py"], "credential": tampered,
            "artifacts": {"changes/unreleased/a/objectives.md": "- [ ] 目标\n"},
        })
    assert caught.value.code == "credential_mismatch"


def test_release_and_own_credentials_are_never_child_evidence(repo):
    record(repo, "release/0.9.0", ["a.py"], kind="release")
    record(repo, "release/1.0.0", ["a.py"], kind="feature")
    analysis = credentials.reuse_analysis(repo, "release/1.0.0", identity(repo, ["a.py"]), config())
    assert analysis["child_credentials"] == [] and analysis["net_increment"] == ["a.py"]


def _context(kind):
    return {"kind": kind, "incomplete": [], "paths": ["a.py"], "roster": {"reviewers": 1, "review_strategy": "replicate"}}


def test_zero_reviewer_report_is_valid_only_with_full_reuse(repo, monkeypatch):
    monkeypatch.setattr(schema, "check", lambda *a, **k: None)
    ctx = {**_context("release"), "round": "initial", "source": "s", "delivery_base": "b",
           "review_base": "b", "review_head": "h", "policy_ref": "p", "rules_sha256": "r"}
    ctx["context_sha256"] = fingerprint(ctx)
    rep = {k: ctx[k] for k in ("source", "delivery_base", "review_base", "review_head", "policy_ref",
                                "rules_sha256", "context_sha256")}
    rep.update(schema_version=3, decision="pass", incomplete=[], reviewers=[])
    ok = report.validate(ctx, rep, {"zero_reviewers_allowed": True})
    assert ok["reviewers"] == 0
    with pytest.raises(MDFError):
        report.validate(ctx, rep, {"zero_reviewers_allowed": False})
    with pytest.raises(MDFError):
        report.validate(ctx, rep, None)
    with pytest.raises(MDFError):
        report.validate({**ctx, "kind": "feature"}, rep, {"zero_reviewers_allowed": True})


def _release_files(tmp_path, repo, paths):
    ctx = {**_context("release"), "round": "initial", "source": "release/1.0.0", "delivery_base": "b",
           "review_base": "b", "review_head": "h", "policy_ref": "p", "rules_sha256": "r1", "paths": paths,
           "credential": identity(repo, paths, "r1")}
    ctx["context_sha256"] = fingerprint(ctx)
    rep = {k: ctx[k] for k in ("source", "delivery_base", "review_base", "review_head", "policy_ref",
                                "rules_sha256", "context_sha256")}
    rep.update(schema_version=3, decision="pass", incomplete=[], reviewers=[])
    (tmp_path / "c.json").write_text(json.dumps(ctx))
    (tmp_path / "r.json").write_text(json.dumps(rep))
    return ["review-report-check", "--repo", str(repo), "--context-file", str(tmp_path / "c.json"),
            "--report-file", str(tmp_path / "r.json")]


def test_cli_accepts_zero_reviewers_only_when_children_cover_release(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "check", lambda *a, **k: None)
    record(repo, "feature/a", ["a.py"])
    covered = mdf("python", *_release_files(tmp_path, repo, ["a.py"]))
    assert covered.returncode == 0, covered.stderr
    result = json.loads(covered.stdout)["result"]
    assert result["reviewers"] == 0 and result["reuse"]["zero_reviewers_allowed"] is True
    uncovered = mdf("python", *_release_files(tmp_path, repo, ["a.py", "b.py"]))
    assert uncovered.returncode != 0 and "冻结 roster" in uncovered.stderr
    # 0 reviewer 的通过不写新凭证：release 自身不能成为子交付证据
    assert not [r for r in credentials.records(repo, "code-review") if r["source"] == "release/1.0.0"]
