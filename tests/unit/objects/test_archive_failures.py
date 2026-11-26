"""archive 与移动失败时保留现场。"""
from __future__ import annotations
from mdf_test_support import *  # noqa: F403


def test_archive_post_validation_failure_leaves_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    core = load_core_module()
    repo = copy_fixture(tmp_path)
    replace(
        repo / "docs/proposals" / PRP_NAME,
        "status: ready\ndepends_on: []",
        (
            "status: released\ndepends_on: []\n"
            ""
            "released_in: 1.2.0"
        ),
    )
    init_git(repo)

    calls = {"n": 0}

    def fake_findings(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"findings": []}, 0
        return {"findings": [core.Finding("injected.failure", "forced post-validation failure").as_dict()]}, 2

    monkeypatch.setattr("mdf_core.commands_misc.check_payload", fake_findings)
    args = SimpleNamespace(repo=str(repo), epoch="1.2", dry_run=False)
    with pytest.raises(core.MDFError) as caught:
        core.command_archive(args)
    assert caught.value.code == "post_validation_failed"
    assert not (repo / "docs/proposals" / PRP_NAME).exists()
    assert (repo / "docs/proposals" / "archive" / "1.2" / PRP_NAME).is_file()
    assert git(repo, "status", "--porcelain").stdout


def test_move_rewrite_failure_leaves_partial_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    core = load_core_module()
    repo = tmp_path / "repo"
    source = repo / "docs/proposals" / "record"
    source.mkdir(parents=True)
    (source / "item.md").write_text("# Item\n", encoding="utf-8")
    reference = repo / "reference.md"
    reference.write_text(
        "[Item](docs/proposals/record/item.md)\n", encoding="utf-8"
    )
    destination = repo / "docs/proposals" / "archive" / "1.0" / "record"
    moves = {source: destination}
    rewrites = core.replacement_plan(repo, moves)

    original_write = Path.write_text

    def fail_reference(path, *args, **kwargs):
        if path == reference:
            raise OSError("injected rewrite failure")
        return original_write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_reference)
    with pytest.raises(OSError, match="injected rewrite failure"):
        core.apply_moves_and_rewrites(moves, rewrites)

    assert not source.exists()
    assert (destination / "item.md").is_file()
    assert reference.read_text(encoding="utf-8") == (
        "[Item](docs/proposals/record/item.md)\n"
    )
    assert (repo / "docs/proposals" / "archive").is_dir()
