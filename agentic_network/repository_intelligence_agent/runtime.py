"""Non-LLM repository intelligence indexing runtime.

The Repository Intelligence Agent reads supported repository files and writes
structured JSON indexes. It does not execute project code, run commands, apply
patches, install packages, load models, or modify repository source files.
"""

from __future__ import annotations

import ast
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.safety.filesystem_policy import load_filesystem_policy

REPOSITORY_INTELLIGENCE_DIR = "repository_intelligence"
OUTPUT_FILES = {
    "functions": "functions.json",
    "classes": "classes.json",
    "imports": "imports.json",
    "call_graph": "call_graph.json",
    "routes": "routes.json",
    "tests_map": "tests_map.json",
    "dependency_graph": "dependency_graph.json",
    "project_summary": "project_summary.json",
}
SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yml", ".yaml", ".md"}
PYTHON_EXTENSIONS = {".py"}
JAVASCRIPT_EXTENSIONS = {".js", ".ts", ".tsx", ".jsx"}
TEST_PREFIXES = ("test_",)
TEST_SUFFIXES = ("_test.py", ".test.js", ".test.ts", ".spec.js", ".spec.ts", ".test.tsx", ".spec.tsx")
EXCLUDED_PARTS = {
    ".git",
    "outputs",
    "knowledge",
    "models",
    "venv",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "cache",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "unsloth_compiled_cache",
    ".tmp",
    ".next",
    ".ms-playwright",
    "generated-projects",
    "migration-backups",
    "logs",
    "releases",
}
EXCLUDED_PREFIXES = (Path("training/datasets"), Path("training/adapters"))
DEFAULT_MAX_FILES = 5000
MAX_FILE_BYTES = 512_000


@dataclass(frozen=True)
class RepositoryIntelligenceResult:
    """Result metadata for one repository intelligence scan."""

    project_root: str
    output_dir: str
    files_scanned: int
    functions: int
    classes: int
    routes: int
    tests: int
    languages_detected: list[str]
    output_files: dict[str, str]
    warnings: list[str]
    validation_errors: list[str]

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def build_repository_intelligence(
    project_root: Path | None = None,
    output_dir: Path | None = None,
    *,
    allowed_roots: list[Path] | None = None,
    max_files: int = DEFAULT_MAX_FILES,
) -> RepositoryIntelligenceResult:
    """Scan supported repository files and write repository_intelligence JSON indexes."""

    root = (project_root or _project_root_from_env()).resolve()
    out_dir = (output_dir or root / REPOSITORY_INTELLIGENCE_DIR).resolve()
    warnings: list[str] = []
    validation_errors: list[str] = []
    roots = _allowed_roots(root, allowed_roots, warnings)
    safe_roots: list[Path] = []
    for scan_root in roots:
        errors = _validate_scan_root(scan_root, root)
        if errors:
            validation_errors.extend(errors)
            continue
        safe_roots.append(scan_root)

    files = _scan_files(root, safe_roots, max_files=max_files, warnings=warnings)
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    files_by_module: dict[str, str] = {}
    languages = sorted({_language_for(path) for path in files if _language_for(path)})

    for path in files:
        relative = path.relative_to(root).as_posix()
        module = _module_name(path.relative_to(root))
        if module:
            files_by_module[module] = relative

    for path in files:
        relative = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            warnings.append(f"unreadable_file:{relative}:{type(exc).__name__}")
            continue
        if suffix in PYTHON_EXTENSIONS:
            parsed = _parse_python_file(relative, text)
            functions.extend(parsed["functions"])
            classes.extend(parsed["classes"])
            imports.extend(parsed["imports"])
            calls.extend(parsed["calls"])
            routes.extend(parsed["routes"])
        elif suffix in JAVASCRIPT_EXTENSIONS:
            parsed = _parse_javascript_file(relative, text)
            functions.extend(parsed["functions"])
            classes.extend(parsed["classes"])
            imports.extend(parsed["imports"])
            calls.extend(parsed["calls"])
            routes.extend(parsed["routes"])
        elif suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError:
                warnings.append(f"invalid_json:{relative}")

    import_entries = _attach_cross_file_dependencies(imports, files_by_module)
    tests_map = _build_tests_map(files, root)
    dependency_graph = _build_dependency_graph(
        files=files,
        project_root=root,
        imports=import_entries,
        calls=calls,
        routes=routes,
    )
    summary = _build_project_summary(
        files=files,
        project_root=root,
        functions=functions,
        classes=classes,
        routes=routes,
        tests_map=tests_map,
        languages=languages,
    )

    payloads = {
        "functions": functions,
        "classes": classes,
        "imports": import_entries,
        "call_graph": calls,
        "routes": routes,
        "tests_map": tests_map,
        "dependency_graph": dependency_graph,
        "project_summary": summary,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    output_files: dict[str, str] = {}
    for key, filename in OUTPUT_FILES.items():
        path = out_dir / filename
        path.write_text(json.dumps(payloads[key], indent=2, sort_keys=True), encoding="utf-8")
        output_files[key] = str(path)

    validation_errors.extend(validate_repository_intelligence(out_dir))
    return RepositoryIntelligenceResult(
        project_root=str(root),
        output_dir=str(out_dir),
        files_scanned=len(files),
        functions=len(functions),
        classes=len(classes),
        routes=len(routes),
        tests=len(_test_files(files)),
        languages_detected=languages,
        output_files=output_files,
        warnings=_dedupe(warnings),
        validation_errors=_dedupe(validation_errors),
    )


def repository_intelligence_summary_fields(
    result: RepositoryIntelligenceResult | None,
) -> dict[str, Any]:
    """Return summary.json fields for Repository Intelligence Agent."""

    if result is None:
        return {}
    return {
        "repository_intelligence_enabled": True,
        "repository_intelligence_files_scanned": result.files_scanned,
        "repository_intelligence_functions": result.functions,
        "repository_intelligence_classes": result.classes,
        "repository_intelligence_routes": result.routes,
        "repository_intelligence_tests": result.tests,
        "repository_intelligence_validation_passed": result.validation_passed,
        "repository_intelligence_errors": result.validation_errors,
        "repository_intelligence_warnings": result.warnings,
    }


def validate_repository_intelligence(output_dir: Path) -> list[str]:
    """Validate required index files exist and contain valid JSON."""

    errors: list[str] = []
    for key, filename in OUTPUT_FILES.items():
        path = output_dir / filename
        if not path.exists():
            errors.append(f"missing_output:{filename}")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"invalid_json:{filename}")
        except OSError:
            errors.append(f"unreadable_output:{filename}")
    return _dedupe(errors)


def _parse_python_file(relative: str, text: str) -> dict[str, list[dict[str, Any]]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"functions": [], "classes": [], "imports": [], "calls": [], "routes": []}
    visitor = _PythonVisitor(relative)
    visitor.visit(tree)
    return {
        "functions": visitor.functions,
        "classes": visitor.classes,
        "imports": visitor.imports,
        "calls": visitor.calls,
        "routes": visitor.routes,
    }


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self, relative: str) -> None:
        self.relative = relative
        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.imports: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.routes: list[dict[str, Any]] = []
        self.scope: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                {
                    "file": self.relative,
                    "line": node.lineno,
                    "type": "import",
                    "module": alias.name,
                    "name": alias.name,
                    "alias": alias.asname or "",
                }
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * int(node.level or 0) + (node.module or "")
        for alias in node.names:
            self.imports.append(
                {
                    "file": self.relative,
                    "line": node.lineno,
                    "type": "from",
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname or "",
                }
            )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        methods = [item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
        self.classes.append(
            {
                "name": node.name,
                "file": self.relative,
                "line": node.lineno,
                "bases": [_expr_name(base) for base in node.bases if _expr_name(base)],
                "methods": methods,
                "decorators": [_expr_name(item) for item in node.decorator_list if _expr_name(item)],
            }
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, async_function=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, async_function=True)

    def visit_Call(self, node: ast.Call) -> None:
        caller = ".".join(self.scope) if self.scope else "<module>"
        callee = _expr_name(node.func)
        if callee:
            self.calls.append(
                {
                    "caller": caller,
                    "callee": callee,
                    "file": self.relative,
                    "line": node.lineno,
                    "call_type": "method" if "." in callee else "function",
                }
            )
            route = _include_router_record(node, self.relative)
            if route:
                self.routes.append(route)
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, *, async_function: bool) -> None:
        decorators = [_expr_name(item) for item in node.decorator_list if _expr_name(item)]
        self.functions.append(
            {
                "name": node.name,
                "file": self.relative,
                "line": node.lineno,
                "args": _function_args(node.args),
                "returns": _expr_name(node.returns) if node.returns is not None else "",
                "decorators": decorators,
                "visibility": "private" if node.name.startswith("_") else "public",
                "async": async_function,
            }
        )
        for decorator in node.decorator_list:
            route = _route_record_from_decorator(decorator, node.name, self.relative, node.lineno)
            if route:
                self.routes.append(route)
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()


def _parse_javascript_file(relative: str, text: str) -> dict[str, list[dict[str, Any]]]:
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    for match in re.finditer(r"(?m)^\s*import\s+(?P<what>.+?)\s+from\s+['\"](?P<module>[^'\"]+)['\"]", text):
        imports.append(
            {
                "file": relative,
                "line": _line_for(text, match.start()),
                "type": "import",
                "module": match.group("module"),
                "name": match.group("what").strip(),
                "alias": "",
            }
        )
    for match in re.finditer(r"(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\((?P<args>[^)]*)\)", text):
        functions.append(
            {
                "name": match.group("name"),
                "file": relative,
                "line": _line_for(text, match.start()),
                "args": _js_args(match.group("args")),
                "returns": "",
                "decorators": [],
                "visibility": "private" if match.group("name").startswith("_") else "public",
                "async": "async" in match.group(0),
            }
        )
    for match in re.finditer(r"(?m)^\s*(?:export\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)(?:\s+extends\s+(?P<base>[A-Za-z_$][\w$.]*))?", text):
        classes.append(
            {
                "name": match.group("name"),
                "file": relative,
                "line": _line_for(text, match.start()),
                "bases": [match.group("base")] if match.group("base") else [],
                "methods": [],
                "decorators": [],
            }
        )
    for match in re.finditer(r"(?P<caller>[A-Za-z_$][\w$]*)?\s*\.?(?P<callee>[A-Za-z_$][\w$]*)\s*\(", text):
        callee = match.group("callee")
        if callee in {"if", "for", "while", "switch", "function", "return"}:
            continue
        calls.append(
            {
                "caller": "<module>",
                "callee": callee,
                "file": relative,
                "line": _line_for(text, match.start()),
                "call_type": "function",
            }
        )
    for match in re.finditer(r"\b(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]", text):
        routes.append(
            {
                "path": match.group(2),
                "method": match.group(1).upper(),
                "handler": "",
                "file": relative,
                "line": _line_for(text, match.start()),
                "router": "router" if "router." in match.group(0) else "app",
            }
        )
    return {"functions": functions, "classes": classes, "imports": imports, "calls": calls, "routes": routes}


def _attach_cross_file_dependencies(
    imports: list[dict[str, Any]],
    files_by_module: dict[str, str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for entry in imports:
        module = str(entry.get("module", "")).lstrip(".")
        resolved = _resolve_import_module(module, files_by_module)
        copied = dict(entry)
        copied["resolved_file"] = resolved
        copied["is_cross_file"] = bool(resolved and resolved != entry.get("file"))
        output.append(copied)
    return output


def _build_tests_map(files: list[Path], project_root: Path) -> dict[str, list[str]]:
    relative_files = [path.relative_to(project_root).as_posix() for path in files]
    tests = sorted(path for path in relative_files if _is_test_path(path))
    sources = sorted(path for path in relative_files if path not in tests and Path(path).suffix in {".py", ".js", ".ts", ".tsx", ".jsx"})
    mapping: dict[str, list[str]] = {}
    for source in sources:
        source_stem = _normalized_stem(source)
        matches = [
            test
            for test in tests
            if source_stem and (source_stem in _normalized_stem(test) or _normalized_stem(test) in source_stem)
        ]
        if not matches:
            sibling = f"test_{Path(source).stem}"
            matches = [test for test in tests if Path(test).stem.startswith(sibling)]
        mapping[source] = sorted(_dedupe(matches))
    return mapping


def _build_dependency_graph(
    *,
    files: list[Path],
    project_root: Path,
    imports: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    routes: list[dict[str, Any]],
) -> dict[str, Any]:
    relative_files = sorted(path.relative_to(project_root).as_posix() for path in files)
    depends_on: dict[str, set[str]] = {path: set() for path in relative_files}
    depended_by: dict[str, set[str]] = {path: set() for path in relative_files}
    for entry in imports:
        source = str(entry.get("file", ""))
        target = str(entry.get("resolved_file", ""))
        if source and target:
            depends_on.setdefault(source, set()).add(target)
            depended_by.setdefault(target, set()).add(source)
    service_dependencies: list[dict[str, Any]] = []
    for call in calls:
        callee = str(call.get("callee", ""))
        if any(token in callee.lower() for token in ("service", "send_", "check_", "create_", "update_", "delete_")):
            service_dependencies.append(call)
    route_dependencies = [
        {
            "route": route.get("path", ""),
            "method": route.get("method", ""),
            "handler": route.get("handler", ""),
            "file": route.get("file", ""),
        }
        for route in routes
    ]
    return {
        "file_dependencies": [
            {
                "file": path,
                "depends_on": sorted(depends_on.get(path, set())),
                "depended_by": sorted(depended_by.get(path, set())),
            }
            for path in relative_files
        ],
        "service_dependencies": service_dependencies,
        "route_dependencies": route_dependencies,
    }


def _build_project_summary(
    *,
    files: list[Path],
    project_root: Path,
    functions: list[dict[str, Any]],
    classes: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    tests_map: dict[str, list[str]],
    languages: list[str],
) -> dict[str, Any]:
    module_counts: dict[str, int] = defaultdict(int)
    for path in files:
        relative = path.relative_to(project_root)
        top = relative.parts[0] if relative.parts else relative.name
        module_counts[top] += 1
    return {
        "number_of_files": len(files),
        "number_of_functions": len(functions),
        "number_of_classes": len(classes),
        "number_of_routes": len(routes),
        "number_of_tests": len(_test_files(files)),
        "top_modules": [
            {"module": module, "files": count}
            for module, count in sorted(module_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        ],
        "languages_detected": languages,
        "sources_with_tests": sum(1 for tests in tests_map.values() if tests),
    }


def _scan_files(root: Path, roots: list[Path], *, max_files: int, warnings: list[str]) -> list[Path]:
    files: list[Path] = []
    for scan_root in roots:
        for directory, dirnames, filenames in os.walk(scan_root):
            directory_path = Path(directory)
            try:
                relative_dir = directory_path.relative_to(root)
            except ValueError:
                dirnames[:] = []
                continue
            if _is_excluded(relative_dir):
                dirnames[:] = []
                continue
            dirnames[:] = [name for name in dirnames if not _is_excluded(relative_dir / name)]
            for filename in filenames:
                path = directory_path / filename
                try:
                    relative = path.relative_to(root)
                except ValueError:
                    continue
                if not _is_supported_file(relative):
                    continue
                if _is_oversize_file(path, warnings, relative):
                    continue
                files.append(path)
                if len(files) >= max_files:
                    warnings.append("max_files_reached")
                    return sorted(_dedupe_paths(files))
    try:
        root_children = list(root.iterdir())
    except OSError:
        root_children = []
    for child in root_children:
        if not child.is_file():
            continue
        try:
            relative = child.relative_to(root)
        except ValueError:
            continue
        if _is_supported_file(relative):
            if _is_oversize_file(child, warnings, relative):
                continue
            files.append(child)
            if len(files) >= max_files:
                warnings.append("max_files_reached")
                return sorted(_dedupe_paths(files))
    return sorted(_dedupe_paths(files))


def _allowed_roots(root: Path, allowed_roots: list[Path] | None, warnings: list[str]) -> list[Path]:
    if allowed_roots is not None:
        return [path.resolve() for path in allowed_roots]
    env_value = os.getenv("ANN_ALLOWED_ROOTS", "").strip()
    if env_value:
        raw_parts = [part.strip() for part in re.split(r"[;,]", env_value) if part.strip()]
        roots = [(Path(part) if Path(part).is_absolute() else root / part).resolve() for part in raw_parts]
        project_roots = [path for path in roots if _is_relative_to(path, root)]
        if project_roots:
            return project_roots
        if load_filesystem_policy(project_root=root).is_path_allowed(root):
            return _default_scan_roots(root, warnings)
        return roots
    return _default_scan_roots(root, warnings)


def _default_scan_roots(root: Path, warnings: list[str]) -> list[Path]:
    preferred = ["app", "apps", "src", "lib", "agentic_network", "packages", "scripts", "tests", "docs"]
    roots = [root / name for name in preferred if (root / name).is_dir()]
    if not roots:
        warnings.append("allowed_roots_defaulted_to_project_root")
        return [root]
    return roots


def _validate_scan_root(scan_root: Path, project_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        scan_root.relative_to(project_root)
    except ValueError:
        errors.append(f"scan_root_outside_project_root:{scan_root}")
    try:
        relative = scan_root.relative_to(project_root)
    except ValueError:
        return errors
    if _is_excluded(relative):
        errors.append(f"protected_scan_root:{relative.as_posix()}")
    if not scan_root.exists():
        errors.append(f"scan_root_missing:{scan_root}")
    return errors


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _route_record_from_decorator(
    decorator: ast.expr,
    handler: str,
    relative: str,
    line: int,
) -> dict[str, Any] | None:
    if not isinstance(decorator, ast.Call):
        return None
    target = _expr_name(decorator.func)
    if not target or "." not in target:
        return None
    router, method = target.rsplit(".", 1)
    if method.lower() not in {"get", "post", "put", "delete", "patch"}:
        return None
    path = _literal_arg(decorator)
    return {
        "path": path,
        "method": method.upper(),
        "handler": handler,
        "file": relative,
        "line": line,
        "router": router,
    }


def _include_router_record(node: ast.Call, relative: str) -> dict[str, Any] | None:
    target = _expr_name(node.func)
    if not target or not target.endswith(".include_router"):
        return None
    router_name = _expr_name(node.args[0]) if node.args else ""
    prefix = ""
    for keyword in node.keywords:
        if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
            prefix = str(keyword.value.value)
    return {
        "path": prefix,
        "method": "INCLUDE_ROUTER",
        "handler": router_name,
        "file": relative,
        "line": node.lineno,
        "router": target.rsplit(".", 1)[0],
    }


def _literal_arg(call: ast.Call) -> str:
    if not call.args:
        return ""
    first = call.args[0]
    if isinstance(first, ast.Constant):
        return str(first.value)
    return _expr_name(first)


def _function_args(args: ast.arguments) -> list[str]:
    output = [arg.arg for arg in args.posonlyargs + args.args]
    if args.vararg:
        output.append("*" + args.vararg.arg)
    output.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg:
        output.append("**" + args.kwarg.arg)
    return output


def _expr_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _expr_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Subscript):
        return _expr_name(node.value)
    if isinstance(node, ast.Call):
        return _expr_name(node.func)
    return ""


def _resolve_import_module(module: str, files_by_module: dict[str, str]) -> str:
    if not module:
        return ""
    if module in files_by_module:
        return files_by_module[module]
    parts = module.split(".")
    for index in range(len(parts), 0, -1):
        candidate = ".".join(parts[:index])
        if candidate in files_by_module:
            return files_by_module[candidate]
    return ""


def _module_name(relative: Path) -> str:
    if relative.suffix.lower() != ".py":
        return ""
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_supported_file(relative: Path) -> bool:
    return relative.suffix.lower() in SUPPORTED_EXTENSIONS and not _is_excluded(relative)


def _is_oversize_file(path: Path, warnings: list[str], relative: Path) -> bool:
    try:
        size = path.stat().st_size
    except OSError:
        warnings.append(f"unreadable_stat:{relative.as_posix()}")
        return True
    if size > MAX_FILE_BYTES:
        warnings.append(f"oversize_file_skipped:{relative.as_posix()}")
        return True
    return False


def _is_excluded(relative: Path) -> bool:
    if set(relative.parts) & EXCLUDED_PARTS:
        return True
    for prefix in EXCLUDED_PREFIXES:
        try:
            relative.relative_to(prefix)
            return True
        except ValueError:
            pass
    return False


def _is_test_path(path_text: str) -> bool:
    path = Path(path_text)
    name = path.name.lower()
    return (
        "tests" in path.parts
        or name.startswith(TEST_PREFIXES)
        or any(name.endswith(suffix) for suffix in TEST_SUFFIXES)
    )


def _test_files(files: list[Path]) -> list[Path]:
    return [path for path in files if _is_test_path(path.as_posix())]


def _normalized_stem(path_text: str) -> str:
    stem = Path(path_text).stem.lower()
    stem = re.sub(r"^(test_|spec_)", "", stem)
    stem = re.sub(r"(_test|_spec|\.test|\.spec)$", "", stem)
    return stem


def _language_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".json": "JSON",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".md": "Markdown",
    }.get(suffix, "")


def _js_args(arg_text: str) -> list[str]:
    return [item.strip() for item in arg_text.split(",") if item.strip()]


def _line_for(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _project_root_from_env() -> Path:
    return Path(os.getenv("ANN_PROJECT_ROOT") or os.getenv("PROJECT_ROOT") or Path.cwd()).resolve()


def _dedupe(values) -> list[Any]:
    seen: set[str] = set()
    output: list[Any] = []
    for value in values:
        key = json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    output: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        output.append(resolved)
    return output
