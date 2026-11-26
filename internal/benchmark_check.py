"""测量 issue #2 的静态检查。运行示例见 docs/system/testing/check-benchmark.md。"""

import argparse
import io
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = "skills/mdf/scripts/mdf.py"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE).decode().strip()


def commit(repo, message):
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=Benchmark", "-c", "user.email=benchmark@example.invalid", "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def synthetic(repo, fixture):
    shutil.copytree(fixture, repo)
    for index in range(200):
        (repo / "src" / f"entry_{index:03}.py").write_text(f"VALUE = {index}\n")
    for index in range(40):
        path = repo / "docs/system/interfaces" / f"entry-{index:03}.md"
        path.write_text(
            f"---\ntitle: Entry {index}\ndoc_type: system-interfaces\nevidence: [src/entry_{index:03}.py]\n"
            f"---\n\n# Entry {index}\n\nVALUE 为 {index}。\n"
        )
    git(repo, "init", "-q", "-b", "main")
    base = commit(repo, "初始化 benchmark")
    git(repo, "branch", "benchmark-side", base)
    (repo / "src/entry_000.py").write_text("VALUE = 200\n")
    commit(repo, "更新实现")
    git(repo, "checkout", "-q", "benchmark-side")
    target = repo / "docs/system/interfaces/entry-001.md"
    target.write_text(target.read_text() + "\n保留本页定义。\n")
    commit(repo, "更新事实")
    git(repo, "checkout", "-q", "main")
    git(repo, "-c", "user.name=Benchmark", "-c", "user.email=benchmark@example.invalid",
        "merge", "--no-ff", "-qm", "合入事实更新", "benchmark-side")
    return base


def setup_ig(repo, source, revision, code, document):
    git(source, "clone", "--quiet", "--shared", "--no-checkout", "--", str(source), str(repo))
    git(repo, "checkout", "--quiet", "--detach", revision)
    git(repo, "checkout", "-qb", "benchmark")
    path = repo / code
    path.write_text(path.read_text() + "\n# benchmark\n")
    commit(repo, "更新实现")
    path = repo / document
    path.write_text(path.read_text() + "\n<!-- benchmark -->\n")
    commit(repo, "更新事实")
    return revision


def measure(argv, env):
    start = time.perf_counter()
    result = subprocess.run(argv, env=env, capture_output=True, text=True)
    elapsed = time.perf_counter() - start
    if "-c" in argv:
        result.check_returncode()
        return elapsed, None
    if result.returncode not in {0, 2}:
        raise RuntimeError(f"{argv}: {result.stderr}")
    result_data = json.loads(result.stdout)
    body = result_data.get("result", {}).get("audit", result_data)
    findings = [
        {key: value for key, value in finding.items() if key != "id"}
        for finding in body.get("findings", []) + body.get("warnings", [])
    ]
    return elapsed, {
        "exit": result.returncode, "findings": findings,
        "normal_workflows_allowed": result_data.get("normal_workflows_allowed"),
    }


def stats(samples):
    return {"samples_seconds": samples, "median_seconds": statistics.median(samples),
            "p95_seconds": sorted(samples)[math.ceil(.95 * len(samples)) - 1]}


def compare(root, dataset, prepare, baseline, rounds, env):
    commands = {
        "baseline_entry": (baseline, ["doctor"]),
        "entry": (ROOT, ["check", "--profile", "entry"]),
        "baseline_dev": (baseline, ["fact-audit", "--quick", "--scope", "branch", "--base", "{base}"]),
        "dev": (ROOT, ["check", "--profile", "dev", "--scope", "branch", "--base", "{base}"]),
        "baseline_strict": (baseline, ["validate", "--level", "strict"]),
        "strict": (ROOT, ["validate", "--level", "strict"]),
        "closeout": (ROOT, ["check", "--profile", "closeout", "--scope", "branch", "--base", "{base}"]),
    }
    warm = root / f"{dataset}-warm"
    warm_base = prepare(warm)
    report = {}
    for temperature in ("cold", "warm"):
        samples = {name: [] for name in commands} | {"python_startup": []}
        outcomes = {}
        for iteration in range(rounds):
            samples["python_startup"].append(measure([sys.executable, "-B", "-c", "pass"], env)[0])
            for name, (core, command) in commands.items():
                repo = root / f"{dataset}-{name}-{iteration}" if temperature == "cold" else warm
                base = prepare(repo) if temperature == "cold" else warm_base
                argv = [sys.executable, "-B", str(core / CLI), *(base if arg == "{base}" else arg for arg in command)]
                elapsed, outcome = measure([*argv, "--repo", str(repo)], env)
                samples[name].append(elapsed)
                if name in outcomes and outcomes[name] != outcome:
                    raise RuntimeError(f"{dataset}/{temperature}/{name} findings changed between rounds")
                outcomes[name] = outcome
                if temperature == "cold":
                    shutil.rmtree(repo)
        report[temperature] = {name: stats(values) for name, values in samples.items()}
        for name, outcome in outcomes.items():
            report[temperature][name].update(
                outcome=outcome, net=stats([max(0., elapsed - startup)
                                           for elapsed, startup in zip(samples[name], samples["python_startup"])]),
            )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="MDF 实施前 Git commit")
    parser.add_argument("--ig-repo", type=Path, required=True, help="只读使用的 integration-gate Git 仓库")
    parser.add_argument("--ig-revision", default="HEAD")
    parser.add_argument("--ig-source", default="src/ig_config.py")
    parser.add_argument("--ig-document", default="docs/system/operations/configuration.md")
    parser.add_argument("--rounds", type=int, default=5)
    args = parser.parse_args()
    if args.rounds < 5:
        parser.error("--rounds 至少为 5")
    fixture = ROOT / "tests/fixtures/mdf/valid_repo"
    baseline_sha = git(ROOT, "rev-parse", "--verify", f"{args.baseline}^{{commit}}")
    ig_sha = git(args.ig_repo, "rev-parse", "--verify", f"{args.ig_revision}^{{commit}}")
    with tempfile.TemporaryDirectory(prefix="mdf-check-benchmark-") as temp:
        root = Path(temp).resolve()
        baseline = root / "baseline"
        baseline.mkdir()
        archive = subprocess.check_output(["git", "-C", str(ROOT), "archive", baseline_sha, "skills/mdf"])
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(baseline, filter="data")
        env = {**os.environ, "MDF_LOG_DIR": str(root / "logs")}
        report = {
            "baseline": baseline_sha, "ig_revision": ig_sha, "rounds": args.rounds,
            "cold": "新建 checkout 后启动新进程", "warm": "复用 checkout，每轮启动新进程",
            "synthetic": compare(root, "synthetic", lambda repo: synthetic(repo, fixture), baseline, args.rounds, env),
            "integration_gate": compare(
                root, "ig", lambda repo: setup_ig(repo, args.ig_repo, ig_sha, args.ig_source, args.ig_document),
                baseline, args.rounds, env,
            ),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
