from __future__ import annotations

from pathlib import Path

import pytest

from project_doctor.analyze import analyze_project
from project_doctor.cli import main
from project_doctor.context import AnalysisContext
from project_doctor.dependencies import InstalledPackageIndex
from project_doctor.uv import sync_check_uv


def _empty_context() -> AnalysisContext:
    return AnalysisContext(installed_packages=InstalledPackageIndex.from_import_to_distributions({}))


def test_common_distribution_import_name_mismatches_do_not_need_environment_metadata(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["beautifulsoup4>=4", "python-dotenv>=1", "Pillow>=10"]
""",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("import bs4\nimport dotenv\nimport PIL\n", encoding="utf-8")

    report = analyze_project(tmp_path, context=_empty_context())

    assert report.undeclared_imports == []
    assert {(item.dependency, item.status) for item in report.dependency_usage} == {
        ("beautifulsoup4", "used"),
        ("python-dotenv", "used"),
        ("Pillow", "used"),
    }


def test_uv_sync_checks_project_direct_dependencies_not_any_transitive_lock_entry(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["urllib3>=2"]
""",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text(
        """
version = 1

[[package]]
name = "demo"
version = "0.1.0"
source = { virtual = "." }
dependencies = [
    { name = "requests" },
]

[[package]]
name = "requests"
version = "2.32.0"
dependencies = [
    { name = "urllib3" },
]

[[package]]
name = "urllib3"
version = "2.2.0"
""",
        encoding="utf-8",
    )

    result = sync_check_uv(tmp_path / "uv.lock")

    assert result.status == "out-of-sync"
    assert result.locked_direct_dependencies == ()
    assert result.missing_direct_dependencies == ("urllib3",)


def test_type_checking_imports_are_not_runtime_dependency_usage(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = []
""",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def render(frame: "pd.DataFrame") -> None:
    pass
""",
        encoding="utf-8",
    )

    report = analyze_project(tmp_path, context=_empty_context())

    assert "pandas" not in report.imported_modules
    assert "pandas" not in report.third_party_imports
    assert report.undeclared_imports == []


def test_src_namespace_packages_are_inferred_as_local_roots(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = []
""",
        encoding="utf-8",
    )
    namespace = tmp_path / "src" / "acme"
    namespace.mkdir(parents=True)
    (namespace / "tools.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("import acme.tools\n", encoding="utf-8")

    report = analyze_project(tmp_path, context=_empty_context())

    assert "acme" in report.local_import_roots
    assert "acme" not in report.third_party_imports
    assert report.undeclared_imports == []


def test_runtime_scope_excludes_optional_and_dev_dependencies_by_default(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["requests>=2"]

[project.optional-dependencies]
plot = ["matplotlib>=3"]

[dependency-groups]
dev = ["pytest>=8"]
""",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("import requests\n", encoding="utf-8")

    status = main(["check", str(tmp_path), "--max-unused", "0"])

    assert status == 0


def test_all_scope_preserves_dependency_usage_scope_in_api(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["requests>=2"]

[project.optional-dependencies]
plot = ["matplotlib>=3"]

[dependency-groups]
dev = ["pytest>=8"]
""",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("import requests\n", encoding="utf-8")

    report = analyze_project(tmp_path, dependency_scope="all")

    scopes = {item.dependency: item.scope for item in report.dependency_usage}
    assert scopes == {
        "requests": "runtime",
        "matplotlib": "optional",
        "pytest": "dev",
    }


def test_all_scope_includes_optional_and_dev_dependencies_when_requested(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["requests>=2"]

[project.optional-dependencies]
plot = ["matplotlib>=3"]

[dependency-groups]
dev = ["pytest>=8"]
""",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("import requests\n", encoding="utf-8")

    status = main(["check", str(tmp_path), "--scope", "all", "--max-unused", "0"])

    captured = capsys.readouterr()
    assert status == 1
    assert "Likely unused dependencies: 2 > 0" in captured.out


def test_duplicate_dependency_declarations_are_counted_once(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["requests>=2"]
""",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("requests>=2\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("", encoding="utf-8")

    report = analyze_project(tmp_path, context=_empty_context())

    assert len(report.declared_dependencies) == 1
    assert len(report.unused_dependencies) == 1
    assert report.declared_dependencies[0].source == "pyproject.toml:[project.dependencies], requirements.txt"


def test_cli_rejects_non_positive_limits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status = main(["analyze", str(tmp_path), "--max-files", "0"])

    captured = capsys.readouterr()
    assert status == 2
    assert "argument --max-files: must be at least 1" in captured.err
