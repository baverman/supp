from supp.util import unmark, SOURCE_MARK


def mark(name):
    return name.replace('|', SOURCE_MARK)


def test_marks():
    assert unmark(mark('|boo')) == 'boo'
    assert unmark(mark('bo|o')) == 'boo'
    assert unmark(mark('boo|')) == 'boo'

    assert unmark(mark('foo.|boo')) == 'foo.boo'
    assert unmark(mark('foo.bo|o')) == 'foo.boo'
    assert unmark(mark('foo.boo|')) == 'foo.boo'

    assert unmark(mark('foo.|boo.bar')) == 'foo.boo'
    assert unmark(mark('foo.bo|o.bar')) == 'foo.boo'
    assert unmark(mark('foo.boo|.bar')) == 'foo.boo'
