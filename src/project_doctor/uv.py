from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - package requires py3.11+
    tomllib = None  # type: ignore[assignment]

from .dependencies import load_declared_dependencies
from .models import UvLockSummary
from .utils import canonicalize_name


@dataclass(frozen=True)
class UvLockedPackage:
    name: str
    version: str | None


def load_uv_packages(lock_path: Path) -> tuple[list[UvLockedPackage], list[str]]:
    warnings: list[str] = []
    if tomllib is None:
        return [], ["uv.lock exists, but tomllib is unavailable."]
    if not lock_path.exists():
        return [], [f"uv lock file not found: {lock_path}"]

    try:
        data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [], [f"Could not parse uv.lock: {exc}"]

    packages: list[UvLockedPackage] = []
    raw_packages = data.get("package") or []
    if not isinstance(raw_packages, list):
        return [], ["Could not parse uv.lock: expected [[package]] entries."]

    for item in raw_packages:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        version = item.get("version")
        if isinstance(name, str):
            packages.append(UvLockedPackage(name=name, version=str(version) if version is not None else None))

    return sorted(packages, key=lambda item: canonicalize_name(item.name)), warnings


def sync_check_uv(lock_path: Path) -> UvLockSummary:
    lock_path = lock_path.expanduser().resolve()
    project_root = lock_path.parent
    packages, warnings = load_uv_packages(lock_path)
    if warnings:
        return UvLockSummary(
            lock_path=str(lock_path),
            status="error",
            package_count=len(packages),
            reason=" ".join(warnings),
        )

    declared_dependencies, dep_warnings = load_declared_dependencies(project_root)
    runtime_dependencies = [dep for dep in declared_dependencies if dep.scope == "runtime"]
    if dep_warnings:
        reason = " ".join(dep_warnings)
    else:
        reason = None

    locked_names = {canonicalize_name(package.name) for package in packages}
    project_direct_names, direct_warnings = _load_project_direct_dependency_names(lock_path, project_root)
    if direct_warnings:
        reason = " ".join(filter(None, (reason, *direct_warnings)))
    direct_locked_names = project_direct_names if project_direct_names is not None else locked_names
    direct_names = {dep.normalized_name: dep.name for dep in runtime_dependencies}
    missing = tuple(sorted(direct_names[name] for name in set(direct_names) - direct_locked_names))
    locked_direct = tuple(sorted(direct_names[name] for name in set(direct_names) & direct_locked_names))

    return UvLockSummary(
        lock_path=str(lock_path),
        status="ok" if not missing and reason is None else "out-of-sync",
        package_count=len(packages),
        locked_direct_dependencies=locked_direct,
        missing_direct_dependencies=missing,
        reason=reason,
    )


def locked_package_version(lock_path: Path, package_name: str) -> str | None:
    packages, warnings = load_uv_packages(lock_path.expanduser().resolve())
    if warnings:
        return None
    wanted = canonicalize_name(package_name)
    for package in packages:
        if canonicalize_name(package.name) == wanted:
            return package.version
    return None


def _load_project_direct_dependency_names(lock_path: Path, project_root: Path) -> tuple[set[str] | None, list[str]]:
    if tomllib is None:
        return None, []
    if not lock_path.exists():
        return None, []

    try:
        data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, [f"Could not parse uv.lock direct dependencies: {exc}"]

    raw_packages = data.get("package") or []
    if not isinstance(raw_packages, list):
        return None, []

    project_name = _project_name(project_root)
    for item in raw_packages:
        if not isinstance(item, dict):
            continue
        if not _is_project_lock_package(item, project_name):
            continue
        dependencies = _dependency_names_from_lock_entries(item.get("dependencies") or [])
        optional_dependencies = item.get("optional-dependencies") or {}
        if isinstance(optional_dependencies, dict):
            for entries in optional_dependencies.values():
                dependencies.update(_dependency_names_from_lock_entries(entries or []))
        return dependencies, []

    return None, []


def _project_name(project_root: Path) -> str | None:
    pyproject = project_root / "pyproject.toml"
    if tomllib is None or not pyproject.exists():
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:
        return None
    project = data.get("project") or {}
    name = project.get("name") if isinstance(project, dict) else None
    return str(name) if isinstance(name, str) else None


def _is_project_lock_package(item: dict[str, Any], project_name: str | None) -> bool:
    source = item.get("source") or {}
    if isinstance(source, dict):
        source_values = {str(value) for value in source.values()}
        if "." in source_values:
            return True
    if project_name is None:
        return False
    name = item.get("name")
    return isinstance(name, str) and canonicalize_name(name) == canonicalize_name(project_name)


def _dependency_names_from_lock_entries(entries: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(entries, list):
        return names
    for entry in entries:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str):
                names.add(canonicalize_name(name))
        elif isinstance(entry, str):
            names.add(canonicalize_name(entry))
    return names


def uv_summary_to_dict(summary: UvLockSummary) -> dict[str, Any]:
    return {
        "lock_path": summary.lock_path,
        "status": summary.status,
        "package_count": summary.package_count,
        "locked_direct_dependencies": list(summary.locked_direct_dependencies),
        "missing_direct_dependencies": list(summary.missing_direct_dependencies),
        "reason": summary.reason,
    }
