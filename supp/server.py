import sys
import os.path
import logging

logger = logging.getLogger('server')

try:
    import supp
except ImportError:
    old_path = sys.path[:]
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    try:
        import supp
    finally:
        sys.path = old_path

from supp import assistant, linter
from supp.umsgpack import loads, dumps
from supp.project import Project
from supp.compat import nstr


class Server(object):
    def __init__(self, conn):
        self.conn = conn

    def configure(self, config):
        self.project = Project(config['sources'], dyn_modules=config.get('dyn_modules'))

    def process(self, name, args, kwargs):
        try:
            is_ok = True
            result = getattr(self, name)(*args, **kwargs)
        except Exception as e:
            logger.exception('%s error', name)
            is_ok = False
            result = e.__class__.__name__, str(e)

        return result, is_ok

    def assist(self, source, position, filename):
        with self.project.check_changes():
            return assistant.assist(self.project, nstr(source), tuple(position), filename)

    def location(self, source, position, filename):
        with self.project.check_changes():
            return assistant.location(self.project, nstr(source), tuple(position), filename)

    def lint(self, source, filename, syntax_only=False):
        with self.project.check_changes():
            return [r[:4] for r in linter.lint(self.project, nstr(source), filename)]

    def eval(self, source):
        ctx = {}
        source = '\n'.join('    ' + r for r in nstr(source).splitlines())
        source = 'def boo():\n{}\nresult = boo()'.format(source)
        exec(source, ctx)
        return ctx['result']

    def run(self):
        conn = self.conn
        while True:
            if conn.poll(1):
                try:
                    args = loads(conn.recv_bytes())
                except EOFError:
                    break
                except Exception:
                    logger.exception('IO error')
                    break

                if args[0] == 'close':
                    conn.close()
                    break
                else:
                    result, is_ok = self.process(*args)
                    try:
                        content = dumps((result, is_ok))
                    except:
                        content = dumps((('SerializeError', 'Serialize error'), False))
                    try:
                        self.conn.send_bytes(content)
                    except:
                        logger.exception('Send error')


if __name__ == '__main__':
    from multiprocessing.connection import Listener

    if 'SUPP_LOG_LEVEL' in os.environ:
        level = int(os.environ['SUPP_LOG_LEVEL'])
    else:
        level = logging.ERROR

    if 'SUPP_LOG_FILE' in os.environ:
        logging.basicConfig(
            filename=os.environ['SUPP_LOG_FILE'],
            format="%(asctime)s %(name)s %(levelname)s: %(message)s", level=level)
    else:
        logging.basicConfig(format="%(name)s %(levelname)s: %(message)s", level=level)

    listener = Listener(sys.argv[1])
    conn = listener.accept()
    server = Server(conn)
    server.run()
