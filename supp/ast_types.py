from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supp.scope import Flow


class Annotation(ast.expr):
    flow: Flow


def make_annotation(e: ast.expr, flow: Flow) -> Annotation:
    e.flow = flow  # type: ignore[attr-defined]
    return e  # type: ignore[return-value]
