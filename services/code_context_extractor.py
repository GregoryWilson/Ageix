from __future__ import annotations

import ast
from pathlib import Path


class CodeContextExtractor:
    """Extracts compact, deterministic code slices for worker context."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root)

    def extract_file_slice(
        self,
        path: str,
        *,
        symbols: list[str] | None = None,
        include_imports: bool = True,
        include_adjacent_helpers: bool = True,
        max_lines: int = 120,
        allow_full_file_fallback: bool = True,
    ) -> str:
        source_path = self.repo_root / path
        if not source_path.exists() or not source_path.is_file():
            return ""
        text = source_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return self._fallback(lines, max_lines, allow_full_file_fallback)

        ranges: list[tuple[int, int]] = []
        if include_imports:
            ranges.extend(self._import_ranges(tree))

        symbol_set = set(symbols or [])
        if symbol_set:
            ranges.extend(self._symbol_ranges(tree, symbol_set))
        else:
            ranges.extend(self._public_definition_ranges(tree, limit=3))

        if include_adjacent_helpers:
            ranges.extend(self._adjacent_helper_ranges(tree, ranges))

        if not ranges:
            return self._fallback(lines, max_lines, allow_full_file_fallback)

        selected = self._render_ranges(lines, ranges, max_lines)
        if not selected.strip():
            return self._fallback(lines, max_lines, allow_full_file_fallback)
        return selected

    def extract_function_slice(self, path: str, function_name: str, *, max_lines: int = 120) -> str:
        return self.extract_file_slice(path, symbols=[function_name], max_lines=max_lines)

    def extract_class_slice(self, path: str, class_name: str, *, max_lines: int = 120) -> str:
        return self.extract_file_slice(path, symbols=[class_name], max_lines=max_lines)

    def extract_imports(self, path: str) -> str:
        source_path = self.repo_root / path
        if not source_path.exists():
            return ""
        text = source_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return ""
        return self._render_ranges(lines, self._import_ranges(tree), max_lines=len(lines) or 1)

    def _import_ranges(self, tree: ast.AST) -> list[tuple[int, int]]:
        ranges = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                ranges.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
        return ranges

    def _symbol_ranges(self, tree: ast.AST, symbols: set[str]) -> list[tuple[int, int]]:
        ranges = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in symbols:
                ranges.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
        return ranges

    def _public_definition_ranges(self, tree: ast.AST, *, limit: int) -> list[tuple[int, int]]:
        ranges = []
        for node in getattr(tree, "body", []):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                ranges.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
            if len(ranges) >= limit:
                break
        return ranges

    def _adjacent_helper_ranges(self, tree: ast.AST, existing: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not existing:
            return []
        helpers = []
        starts = [start for start, _end in existing]
        for node in getattr(tree, "body", []):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("_"):
                continue
            end = getattr(node, "end_lineno", node.lineno)
            if any(abs(node.lineno - start) <= 25 for start in starts):
                helpers.append((node.lineno, end))
        return helpers[:3]

    def _render_ranges(self, lines: list[str], ranges: list[tuple[int, int]], max_lines: int) -> str:
        merged = self._merge_ranges(ranges)
        output: list[str] = []
        remaining = max_lines
        for start, end in merged:
            if remaining <= 0:
                break
            chunk = lines[start - 1 : end]
            chunk = chunk[:remaining]
            if output:
                output.append("...")
                remaining -= 1
            output.extend(chunk)
            remaining -= len(chunk)
        return "\n".join(output).rstrip() + ("\n" if output else "")

    def _merge_ranges(self, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not ranges:
            return []
        normalized = sorted((max(1, s), max(s, e)) for s, e in ranges)
        merged = [normalized[0]]
        for start, end in normalized[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end + 1:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    def _fallback(self, lines: list[str], max_lines: int, allow: bool) -> str:
        if not allow:
            return ""
        return "\n".join(lines[:max_lines]).rstrip() + ("\n" if lines else "")
