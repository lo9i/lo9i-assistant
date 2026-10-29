"""The text a package marks for translation (core/i18n), read from its code, to check each language's table
against: `t("...")`, `self._t("...")` and `translatable("...")` with the English text written in the call."""

import ast
from pathlib import Path

_CALLS = {"t", "_t", "translatable"}


def marked_texts(package: Path) -> set[str]:
    return {text for path in sorted(package.rglob("*.py")) for text in _in(ast.parse(path.read_text()))}


def _in(tree: ast.AST) -> list[str]:
    return [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _name(node.func) in _CALLS
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ]


def _name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""
