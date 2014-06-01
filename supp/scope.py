from ast import parse

from .astwalk import NameExtractor


def create_scope(source, filename=None):
    filename = filename or '<string>'
    tree = parse(source, filename)
    NameExtractor(None, tree).process()
