from supp.remote import Environment
from .helpers import sp

def test_remote_assist():
    env = Environment()
    source, p = sp('''\
        foo = 10
        |
    ''')
    result = env.assist('.', source, p, 'boo.py')
    assert 'foo' in result
