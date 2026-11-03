"""pyproject.toml's requires-python must cover the syntax the code relies on."""

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _declared_minimum() -> tuple[int, int]:
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'requires-python\s*=\s*">=\s*(\d+)\.(\d+)"', text)
    assert m, "pyproject.toml must declare requires-python = \">=X.Y\""
    return int(m.group(1)), int(m.group(2))


class _RuntimeUnionFinder(ast.NodeVisitor):
    """Find ``X | Y`` annotations that Python evaluates when the module loads.

    Without ``from __future__ import annotations`` function signatures and
    module/class level variable annotations are evaluated, and ``X | Y`` on
    types only works from Python 3.10. Annotations on local variables inside a
    function body are never evaluated, so they are skipped.
    """

    def __init__(self):
        self.hits: list[int] = []
        self._depth = 0

    def _check(self, node):
        if node is not None and any(
            isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)
            for n in ast.walk(node)
        ):
            self.hits.append(node.lineno)

    def _visit_function(self, node):
        a = node.args
        for arg in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg]:
            if arg is not None:
                self._check(arg.annotation)
        self._check(node.returns)
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_AnnAssign(self, node):
        if self._depth == 0:
            self._check(node.annotation)
        self.generic_visit(node)


def test_requires_python_covers_runtime_union_annotations():
    needs_310 = []
    for path in sorted((REPO / "src").rglob("*.py")) + sorted((REPO / "scripts").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        future = any(
            isinstance(n, ast.ImportFrom) and n.module == "__future__"
            and any(alias.name == "annotations" for alias in n.names)
            for n in tree.body
        )
        if future:
            continue
        finder = _RuntimeUnionFinder()
        finder.visit(tree)
        needs_310 += [f"{path.relative_to(REPO)}:{line}" for line in finder.hits]

    if needs_310:
        assert _declared_minimum() >= (3, 10), (
            "X | Y annotations are evaluated at import time and need Python "
            "3.10, but pyproject.toml allows older versions: "
            + ", ".join(needs_310[:5])
        )
