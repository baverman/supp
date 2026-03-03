from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from .evaluator import EvalCtx
from .nast import extract_scope
from .util import (
    Source,
    get_all_usages,
    get_marked_atribute,
    get_marked_import,
    get_marked_name,
    join_pkg,
    print_dump,
    split_pkg,
)

if TYPE_CHECKING:
    from .name import AttrList, Name, Object
    from .project import Project
    from .util import loc_t

log = logging.getLogger('supp.assistant')


def list_packages(project: Project, root: str, filename: str) -> list[str]:
    root = project.norm_package(root, filename)
    return sorted(r for r in project.list_packages(root))


def assist(
    project: Project,
    source_text: str,
    position: loc_t,
    filename: str | None = None,
    debug: bool = False,
) -> tuple[str, list[str]]:
    source = Source(source_text, filename, position)
    ctx = EvalCtx(project)
    ln, col = position
    line = source.lines[ln - 1][:col]
    if line.lstrip().startswith('from ') and ' import ' not in line:
        iname = line.rpartition(' ')[2]
        package, sep, prefix = iname.rpartition('.')
        if (not package or package.startswith('.')) and sep:
            package += '.'
        return prefix, list_packages(project, package, source.filename)

    if debug:
        print_dump(source.tree)

    marked_import = get_marked_import(source.tree)
    if marked_import:
        head, tail = marked_import
        if tail is None:
            head, tail = split_pkg(head)
            return tail, list_packages(project, head, source.filename)
        else:
            plist = list_packages(project, head, source.filename)
            module = project.get_nmodule(head, source.filename)
            return tail, sorted(set(plist) | set(module.attr_list(ctx)))

    extract_scope(source, project)

    prefix = re.split(r'(\.|\s|\()', line)[-1]
    attr = get_marked_atribute(source.tree)
    names: AttrList = {}
    if attr:
        value = ctx.evaluate(attr.value)
        if value:
            names = value.attr_list(ctx)
    else:
        name = get_marked_name(source.tree)
        if name:
            names = name.flow.names_at(position)

    return prefix, sorted(names)


def _loc(location: loc_t, filename: str | None) -> dict[str, object]:
    return {'loc': location, 'file': filename}


def location(
    project: Project,
    source_text: str,
    position: loc_t,
    filename: str | None = None,
    debug: bool = False,
) -> list[list[dict[str, object]]]:
    source = Source(source_text, filename, position)

    if debug:
        print_dump(source.tree)

    extract_scope(source, project)

    result = []
    marked_import = get_marked_import(source.tree)
    ctx = EvalCtx(project)

    name: Object | Name | None
    if marked_import:
        head, tail = marked_import
        if tail is None:
            name = project.get_nmodule(head, source.filename)
        else:
            if not tail:
                full = head
                head, tail = split_pkg(head)
            else:
                full = join_pkg(head, tail)

            module = project.get_nmodule(head, source.filename)
            name = module.get_attr(ctx, tail)
            if not name:
                name = project.get_nmodule(full, source.filename)

        result = ctx.declarations(name, [])  # type: ignore[arg-type]  # TODO
    else:
        node = get_marked_name(source.tree) or get_marked_atribute(source.tree)
        if node:
            result = ctx.declarations(node, [])

    locs = []
    for r in result:
        locs.append([_loc(n.declared_at, n.filename) for n in r])

    return locs


def usages(project: Project, source_text: str, filename: str | None = None) -> None:
    source = Source(source_text, filename)
    extract_scope(source, project)
    ctx = EvalCtx(project)

    for utype, nname, loc, node in get_all_usages(source.tree):
        # print(scope, node)
        value = ctx.declarations(node, [])  # type: ignore[arg-type]  # TODO

        if value:
            if utype == 'attr':
                print('GUT', utype, nname, loc, value)
        else:
            print('BAD', utype, nname, loc, vars(node))
