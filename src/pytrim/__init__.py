"""Public API for PyTrim."""

from .analyze import analyze_project
from .context import AnalysisContext
from .models import (
    AnalysisReport,
    DeclaredDependency,
    DependencyUsage,
    ImportRecord,
    ImportTiming,
    LazyImportCandidate,
    PackageSize,
    PythonFileScan,
)

__version__ = "0.3.0"

__all__ = [
    "AnalysisContext",
    "AnalysisReport",
    "DeclaredDependency",
    "DependencyUsage",
    "ImportRecord",
    "ImportTiming",
    "LazyImportCandidate",
    "PackageSize",
    "PythonFileScan",
    "__version__",
    "analyze_project",
]
