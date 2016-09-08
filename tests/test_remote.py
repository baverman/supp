from supp.remote import Environment
from .helpers import sp


def test_remote_assist():
    env = Environment()
    env.configure({'sources': ['.']})
    source, p = sp('''\
        foo = 10
        |
    ''')
    m, result = env.assist(source, p, 'boo.py')
    assert m == ''
    assert 'foo' in result
