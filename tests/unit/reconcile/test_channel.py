"""逐提交拒绝输入、rename、revert 和 manifest 配置逃逸。"""
import pytest

from mdf_test_support import git
from support_delivery import commit
from support_reconcile import repository
from mdf_core.foundation.errors import MDFError
from mdf_core.workspace.reconcile_channel import require_history


@pytest.mark.parametrize("path", ["src/hidden.py", "docs/system/testing/hidden.md", ".mdf/modules.yaml"])
@pytest.mark.parametrize("revert", [False, True])
def test_reconcile_never_hides_inputs_by_revert(tmp_path, path, revert):
    repo = repository(tmp_path)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("不允许的变更\n")
    commit(repo)
    if revert:
        git(repo, "revert", "--no-edit", "HEAD")
    with pytest.raises(MDFError):
        require_history(repo, base, "HEAD")


def test_manifest_only_latest_release_and_declared_docs_inputs(tmp_path):
    repo = repository(tmp_path)
    path = repo / ".mdf/modules.yaml"
    path.write_text(path.read_text().replace('    sourceset:\n', '    sourceset:\n      - "docs/runtime/**"\n'))
    commit(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace('latest_release: "1.2.0"', 'latest_release: "1.3.0"'))
    commit(repo)
    require_history(repo, base, "HEAD")
    path = repo / "docs/runtime/data.md"
    path.parent.mkdir()
    path.write_text("实现输入\n")
    commit(repo)
    with pytest.raises(MDFError, match="验证输入"):
        require_history(repo, base, "HEAD")


def test_manifest_policy_change_is_rejected(tmp_path):
    repo = repository(tmp_path)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace("state: ready", "state: draft"))
    commit(repo)
    with pytest.raises(MDFError, match="latest_release"):
        require_history(repo, base, "HEAD")


def test_declared_manifest_cannot_use_latest_release_exception(tmp_path):
    repo = repository(tmp_path)
    path = repo / ".mdf/modules.yaml"
    path.write_text(path.read_text().replace('    sourceset:\n', '    sourceset:\n      - ".mdf/manifest.yaml"\n'))
    commit(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    manifest = repo / ".mdf/manifest.yaml"
    manifest.write_text(manifest.read_text().replace('latest_release: "1.2.0"', 'latest_release: "1.3.0"'))
    commit(repo)
    with pytest.raises(MDFError):
        require_history(repo, base, "HEAD")


def test_rename_checks_both_sides(tmp_path):
    repo = repository(tmp_path)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "mv", "src/service.py", "docs/service.md")
    commit(repo)
    with pytest.raises(MDFError):
        require_history(repo, base, "HEAD")


def test_manifest_mode_is_not_a_latest_release_change(tmp_path):
    repo = repository(tmp_path)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / ".mdf/manifest.yaml").chmod(0o755)
    commit(repo)
    with pytest.raises(MDFError):
        require_history(repo, base, "HEAD")
