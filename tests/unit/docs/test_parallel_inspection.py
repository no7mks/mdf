"""检查实际重叠执行，findings 顺序、错误和 scope 语义保持一致。"""
from threading import Barrier, Event, Lock

from mdf_test_support import *  # noqa: F403


def serial_checks(checks, **kwargs):
    return [finding for _, check in checks for finding in check()]


def test_parallel_findings_keep_input_order_when_later_check_finishes_first():
    from mdf_core.foundation.errors import Finding
    from mdf_core.inspection.parallel import collect_parallel

    finished = Event()
    first = Finding("first", "先登记的检查")
    second = Finding("second", "先完成的检查")

    def slow():
        assert finished.wait(5), "另一个检查未并行执行"
        return [first]

    def fast():
        finished.set()
        return [second]

    assert collect_parallel([("slow", slow), ("fast", fast)]) == [first, second]


def test_parallel_failure_keeps_exception_and_does_not_report_all_complete(capsys):
    from mdf_core.inspection.parallel import collect_parallel

    error = RuntimeError("检查失败")

    def fail():
        raise error

    with pytest.raises(RuntimeError) as caught:
        collect_parallel([("失败项", fail)], label="检查")
    assert caught.value is error
    assert "已检查 1/1" not in capsys.readouterr().err


def test_parallel_empty_checks(capsys):
    from mdf_core.inspection.parallel import collect_parallel

    assert collect_parallel([], label="检查") == []
    assert "已检查 0/0" in capsys.readouterr().err


def test_parallel_checks_limit_active_workers():
    from mdf_core.inspection.parallel import collect_parallel

    barrier = Barrier(4, timeout=5)
    lock = Lock()
    active = 0
    peak = 0

    def check():
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait()
        with lock:
            active -= 1
        return []

    assert collect_parallel([(str(index), check) for index in range(8)]) == []
    assert peak == 4


def overlap(monkeypatch, module, names):
    barrier = Barrier(len(names), timeout=5)
    for name in names:
        original = getattr(module, name)

        def check(*args, _original=original, **kwargs):
            barrier.wait()
            return _original(*args, **kwargs)

        monkeypatch.setattr(module, name, check)


def test_doctor_check_groups_overlap(monkeypatch, tmp_path):
    from mdf_core.inspection import doctor

    repo = copy_fixture(tmp_path)
    init_git(repo)
    overlap(monkeypatch, doctor, ["validate_jots", "validate_links"])
    assert doctor.collect_findings(repo, full=True) == []


def test_evidence_documents_overlap(monkeypatch, tmp_path):
    from mdf_core.inspection import validate_evidence

    repo = copy_fixture(tmp_path)
    documents = [repo / "docs/system/interfaces/api.md", repo / "docs/system/data/model.md"]
    monkeypatch.setattr(validate_evidence, "fact_documents", lambda _: documents)
    barrier = Barrier(2, timeout=5)
    original = validate_evidence.read_frontmatter

    def read(path):
        barrier.wait()
        return original(path)

    monkeypatch.setattr(validate_evidence, "read_frontmatter", read)
    findings = []
    validate_evidence.validate_evidence(repo, findings, check_staleness=False)
    assert findings == []


def test_audit_structure_checks_overlap(monkeypatch, tmp_path):
    from mdf_core.inspection import audit

    repo = copy_fixture(tmp_path)
    init_git(repo)
    overlap(monkeypatch, audit, ["size_findings", "structure_findings"])
    payload, code = audit.audit_payload(repo, "full", [], [])
    assert code == 0
    assert payload["findings"] == []


@pytest.mark.parametrize("scope", ["full", "branch", "paths"])
def test_parallel_and_serial_audit_payloads_match(scope, monkeypatch, tmp_path):
    from mdf_core.inspection import audit, doctor, validate_evidence

    repo = copy_fixture(tmp_path)
    init_git(repo)
    base = git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "src/service.py").write_text("# 实现已改变\n")
    document = "docs/system/interfaces/api.md"
    (repo / document).write_text("---\ntitle: 接口\ndoc_type: system-data\n---\n\n# 接口\n")
    implementation = ["src/service.py"] if scope == "paths" else []
    documents = [document] if scope == "paths" else []
    audit_base = base if scope == "branch" else None
    parallel = audit.audit_payload(repo, scope, implementation, documents, audit_base)
    parallel_doctor = doctor.collect_findings(repo, full=True)
    for module in (audit, doctor, validate_evidence):
        monkeypatch.setattr(module, "collect_parallel", serial_checks)
    assert audit.audit_payload(repo, scope, implementation, documents, audit_base) == parallel
    assert doctor.collect_findings(repo, full=True) == parallel_doctor
    assert parallel[1] == 2
    assert "evidence.stale" in {finding["code"] for finding in parallel[0]["findings"]}
