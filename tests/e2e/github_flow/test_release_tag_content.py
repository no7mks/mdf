"""所有发布路径都校验 annotated tag 的实际正文。"""
from mdf_test_support import *  # noqa: F403
from support_delivery import start_repo, commit, write_changelog_release
from support_github_flow import github_flow_repo


@pytest.mark.parametrize("github", [False, True])
@pytest.mark.parametrize("remote_exists", [False, True])
def test_existing_tag_with_missing_notes_is_rejected(python_exe, tmp_path, github, remote_exists):
    from mdf_core.foundation.errors import MDFError
    from mdf_core.lifecycle.pull_publish import tag_release
    repo, remote = github_flow_repo(tmp_path, origin=True) if github else start_repo(tmp_path)
    write_changelog_release(repo, "1.3.0")
    commit(repo)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "tag", "-a", "v1.3.0", "-m", "v1.3.0")
    if remote_exists:
        git(repo, "push", "origin", "refs/tags/v1.3.0")
    before = git(remote, "show-ref").stdout
    with pytest.raises(MDFError) as caught:
        tag_release(repo, {"release_head" if github else "merge_commit": head}, "1.3.0")
    assert caught.value.code == "tag_conflict"
    assert git(remote, "show-ref").stdout == before
    assert git(repo, "for-each-ref", "--format=%(contents)", "refs/tags/v1.3.0").stdout.strip() == "v1.3.0"


def test_signed_annotation_preserves_the_release_body(tmp_path):
    from mdf_core.lifecycle.closeout_render import expected_tag_message, require_tag_content
    repo, _ = start_repo(tmp_path)
    write_changelog_release(repo, "1.3.0")
    commit(repo)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    message = expected_tag_message(repo, "1.3.0", head)
    # 只验证 Git 对 annotation 与 signature 字段的分离，签名真实性由 Git 的签名机制处理。
    signature = "-----BEGIN PGP SIGNATURE-----\nformat-test-only\n-----END PGP SIGNATURE-----"
    git(repo, "tag", "-a", "v1.3.0", "--cleanup=verbatim", "-m", message + "\n\n" + signature)
    tag = require_tag_content(repo, "1.3.0", head)
    assert tag["head"] == head
    assert git(repo, "for-each-ref", "--format=%(contents:signature)", "refs/tags/v1.3.0").stdout.strip() == signature
