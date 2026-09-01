from __future__ import annotations

import ast
import contextlib
import importlib
import io
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Iterable, Iterator, Optional


_LAW_DOCUMENT_PATHS = (
    ".cursor/skills/verify-cbcs/references/handles.md",
)


@dataclass(frozen=True)
class _Baseline:
    root: Path
    check_index: bool


def find_policy_violations(
    repo_root: Path,
    tracked_files: Optional[Iterable[str]],
    baseline_root: Optional[Path] = None,
) -> list[str]:
    try:
        with _baseline_for_policy(repo_root, baseline_root) as baseline:
            if baseline is None:
                return []
            evidence = _run_baseline_checker(
                repo_root,
                baseline.root,
                None if tracked_files is None else list(tracked_files),
                check_index=baseline.check_index,
            )
    except Exception as exc:
        return [f"policy: cannot load baseline checker: {exc}"]

    if not evidence:
        return []
    return [f"policy: judge edit would fail baseline checker: {evidence}"]


@contextlib.contextmanager
def _baseline_for_policy(
    repo_root: Path,
    baseline_root: Optional[Path],
) -> Iterator[Optional[_Baseline]]:
    if baseline_root is not None:
        baseline = baseline_root.resolve()
        if not _judge_changed(repo_root, baseline):
            yield None
            return
        yield _Baseline(baseline, False)
        return

    if not (repo_root / "tools" / "dune").is_dir():
        yield None
        return

    changed_paths = _git_changed_paths(repo_root)
    if not _git_judge_changed(repo_root, changed_paths):
        yield None
        return

    with tempfile.TemporaryDirectory(prefix="dune-baseline-") as temp_dir:
        baseline = Path(temp_dir) / "baseline"
        _materialize_git_baseline(repo_root, baseline)
        yield _Baseline(baseline, True)


def _judge_changed(repo_root: Path, baseline_root: Path) -> bool:
    current_checkers = _checker_paths(repo_root)
    baseline_checkers = _checker_paths(baseline_root)
    if current_checkers != baseline_checkers:
        return True
    if any(
        (repo_root / path).read_bytes()
        != (baseline_root / path).read_bytes()
        for path in current_checkers
    ):
        return True
    if _path_bytes(repo_root / "dune.yaml") != _path_bytes(
        baseline_root / "dune.yaml"
    ):
        return True
    if any(
        _path_bytes(repo_root / path)
        != _path_bytes(baseline_root / path)
        for path in _LAW_DOCUMENT_PATHS
    ):
        return True
    return _budget_map(repo_root) != _budget_map(baseline_root)


def _checker_paths(repo_root: Path) -> set[str]:
    checker_root = repo_root / "tools" / "dune"
    if not checker_root.is_dir():
        return set()
    return {
        path.relative_to(repo_root).as_posix()
        for path in checker_root.rglob("*.py")
        if path.is_file()
    }


def _path_bytes(path: Path) -> Optional[bytes]:
    if not path.is_file():
        return None
    return path.read_bytes()


def _budget_map(repo_root: Path) -> dict[str, dict[str, int]]:
    budgets: dict[str, dict[str, int]] = {}
    for path in repo_root.rglob("*.py"):
        if not path.is_file():
            continue
        values = _budget_values(path.read_text(encoding="utf-8"))
        if values:
            budgets[path.relative_to(repo_root).as_posix()] = values
    return budgets


def _budget_values(source: str) -> dict[str, int]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    values: dict[str, int] = {}
    for node in tree.body:
        target: Optional[ast.expr] = None
        value: Optional[ast.expr] = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if not isinstance(target, ast.Name) or value is None:
            continue
        if "BUDGET" not in target.id.upper():
            continue
        numeric_value = _integer_expression(value)
        if numeric_value is not None:
            values[target.id] = numeric_value
    return values


def _integer_expression(node: ast.AST) -> Optional[int]:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            return node.value
        return None
    if isinstance(node, ast.UnaryOp) and isinstance(
        node.op,
        (ast.UAdd, ast.USub),
    ):
        operand = _integer_expression(node.operand)
        if operand is None:
            return None
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if not isinstance(node, ast.BinOp):
        return None
    left = _integer_expression(node.left)
    right = _integer_expression(node.right)
    if left is None or right is None:
        return None
    if isinstance(node.op, ast.Add):
        return left + right
    if isinstance(node.op, ast.Sub):
        return left - right
    if isinstance(node.op, ast.Mult):
        return left * right
    if isinstance(node.op, ast.FloorDiv) and right:
        return left // right
    return None


def _git_changed_paths(repo_root: Path) -> set[str]:
    staged = _run_git(
        repo_root,
        "diff",
        "--cached",
        "--name-only",
        "--no-renames",
        "-z",
        "HEAD",
        "--",
    )
    unstaged = _run_git(
        repo_root,
        "diff",
        "--name-only",
        "--no-renames",
        "-z",
        "--",
    )
    untracked = _run_git(
        repo_root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    return {
        path
        for path in (staged + unstaged + untracked).split("\0")
        if path
    }


def _git_judge_changed(repo_root: Path, changed_paths: set[str]) -> bool:
    if "dune.yaml" in changed_paths:
        return True
    if changed_paths.intersection(_LAW_DOCUMENT_PATHS):
        return True
    if any(_is_checker_path(path) for path in changed_paths):
        return True
    for path in changed_paths:
        if not path.endswith(".py"):
            continue
        current = _path_bytes(repo_root / path)
        index = _git_optional_blob(repo_root, f":{path}")
        baseline = _git_optional_blob(repo_root, f"HEAD:{path}")
        baseline_values = _budget_values_from_bytes(baseline)
        if _budget_values_from_bytes(current) != baseline_values:
            return True
        if _budget_values_from_bytes(index) != baseline_values:
            return True
    return False


def _is_checker_path(path: str) -> bool:
    return path.startswith("tools/dune/") and path.endswith(".py")


def _budget_values_from_bytes(source: Optional[bytes]) -> dict[str, int]:
    if source is None:
        return {}
    return _budget_values(source.decode("utf-8"))


def _materialize_git_baseline(repo_root: Path, baseline_root: Path) -> None:
    paths = _run_git(
        repo_root,
        "ls-tree",
        "-r",
        "--name-only",
        "-z",
        "HEAD",
        "--",
        "tools/dune",
        "dune.yaml",
        *_LAW_DOCUMENT_PATHS,
    )
    for relative_path in paths.split("\0"):
        if not relative_path:
            continue
        target = baseline_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            _git_required_blob(repo_root, f"HEAD:{relative_path}")
        )


def _overlay_baseline_law_documents(
    baseline_root: Path,
    subject_root: Path,
) -> None:
    for relative_path in _LAW_DOCUMENT_PATHS:
        target = subject_root / relative_path
        if target.is_symlink() or target.exists():
            target.unlink()
        source = baseline_root / relative_path
        if not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _git_optional_blob(repo_root: Path, object_name: str) -> Optional[bytes]:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "show", object_name],
        check=False,
        capture_output=True,
    )
    if completed.returncode == 0:
        return completed.stdout
    return None


def _git_required_blob(repo_root: Path, object_name: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "show", object_name],
        check=False,
        capture_output=True,
    )
    if completed.returncode == 0:
        return completed.stdout
    detail = completed.stderr.decode("utf-8", errors="replace").strip()
    raise RuntimeError(f"git show failed for {object_name}: {detail}")


def _run_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "unknown error"
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def _run_baseline_checker(
    repo_root: Path,
    baseline_root: Path,
    tracked_files: Optional[list[str]],
    *,
    check_index: bool,
) -> str:
    with tempfile.TemporaryDirectory(prefix="dune-policy-") as temp_dir:
        temp_root = Path(temp_dir)
        package_name = f"_dune_baseline_{uuid.uuid4().hex}"
        package_root = temp_root / package_name
        baseline_dune = baseline_root / "tools" / "dune"
        if not (baseline_dune / "check.py").is_file():
            raise RuntimeError("baseline tools/dune/check.py is missing")
        shutil.copytree(baseline_dune, package_root)
        (package_root / "__init__.py").touch()
        (package_root / "policy.py").write_text(
            "from __future__ import annotations\n"
            "\n"
            "def find_policy_violations(*args, **kwargs):\n"
            "    return []\n",
            encoding="utf-8",
        )
        subject_root = temp_root / "subject"
        _build_subject_root(repo_root, baseline_root, subject_root)

        sys.path.insert(0, str(temp_root))
        try:
            module = importlib.import_module(f"{package_name}.check")
            evidence = _invoke_baseline_checker(
                module,
                subject_root,
                tracked_files,
            )
            if not evidence and check_index:
                index_root = temp_root / "index"
                _build_index_subject_root(
                    repo_root,
                    baseline_root,
                    index_root,
                )
                evidence = _invoke_baseline_checker(
                    module,
                    index_root,
                    None,
                )
        finally:
            sys.path.remove(str(temp_root))
            for name in tuple(sys.modules):
                if name == package_name or name.startswith(f"{package_name}."):
                    del sys.modules[name]

    return evidence


def _invoke_baseline_checker(
    module: ModuleType,
    subject_root: Path,
    tracked_files: Optional[list[str]],
) -> str:
    output = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        exit_code = module.run(subject_root, tracked_files)
    if exit_code == 0:
        return ""
    evidence = errors.getvalue().strip()
    if evidence:
        return evidence.splitlines()[0]
    return f"baseline checker exited {exit_code}"


def _build_subject_root(
    repo_root: Path,
    baseline_root: Path,
    subject_root: Path,
) -> None:
    subject_root.mkdir()
    for source in repo_root.iterdir():
        if source.name in {".cursor", "dune.yaml", "tools"}:
            continue
        (subject_root / source.name).symlink_to(source)

    subject_tools = subject_root / "tools"
    subject_tools.mkdir()
    current_tools = repo_root / "tools"
    if current_tools.is_dir():
        for source in current_tools.iterdir():
            if source.name == "dune":
                continue
            (subject_tools / source.name).symlink_to(source)

    baseline_manifest = baseline_root / "dune.yaml"
    if not baseline_manifest.is_file():
        raise RuntimeError("baseline dune.yaml is missing")
    shutil.copy2(baseline_manifest, subject_root / "dune.yaml")
    shutil.copytree(
        baseline_root / "tools" / "dune",
        subject_tools / "dune",
    )
    _overlay_baseline_law_documents(baseline_root, subject_root)


def _build_index_subject_root(
    repo_root: Path,
    baseline_root: Path,
    subject_root: Path,
) -> None:
    subject_root.mkdir()
    _run_git(
        repo_root,
        "checkout-index",
        "--all",
        f"--prefix={subject_root.as_posix()}/",
    )
    git_path = repo_root / ".git"
    if git_path.exists():
        (subject_root / ".git").symlink_to(git_path)

    manifest = subject_root / "dune.yaml"
    if manifest.is_symlink() or manifest.exists():
        manifest.unlink()
    baseline_manifest = baseline_root / "dune.yaml"
    if not baseline_manifest.is_file():
        raise RuntimeError("baseline dune.yaml is missing")
    shutil.copy2(baseline_manifest, manifest)

    subject_dune = subject_root / "tools" / "dune"
    if subject_dune.exists():
        shutil.rmtree(subject_dune)
    subject_dune.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        baseline_root / "tools" / "dune",
        subject_dune,
    )
    _overlay_baseline_law_documents(baseline_root, subject_root)
