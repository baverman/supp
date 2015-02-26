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

from supp.project import Project
from supp.assistant import assist
from supp.umsgpack import dumps, loads


class Server(object):
    def __init__(self, conn):
        self.conn = conn
        self.projects = {}
        self.configs = {}
        # self.monitor = get_monitor()
        # self.monitor.start()

    def configure_project(self, path, config):
        self.configs[path] = config
        self.projects[path] = self.create_project(path)

    def create_project(self, path):
        # config = self.configs.get(path, {})
        # config.setdefault('hooks', []).insert(0, 'supplement.hooks.override')
        p = Project(path) #, self.configs.get(path, {}))
        return p

    def get_project(self, path):
        try:
            return self.projects[path]
        except KeyError:
            pass

        p = self.projects[path] = self.create_project(path)
        return p

    def process(self, name, args, kwargs):
        try:
            is_ok = True
            result = getattr(self, name)(*args, **kwargs)
        except Exception as e:
            logger.exception('%s error', name)
            is_ok = False
            result = e.__class__.__name__, str(e)

        return result, is_ok

    def assist(self, path, source, position, filename):
        return assist(self.get_project(path), source, tuple(position), filename)

    def eval(self, source):
        ctx = {}
        source = '\n'.join('    ' + r for r in source.splitlines())
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
                        self.conn.send_bytes(dumps((result, is_ok)))
                    except:
                        logger.exception('Send error')

if __name__ == '__main__':
    from multiprocessing.connection import Listener

    if 'SUPP_LOG_LEVEL' in os.environ:
        level = int(os.environ['SUPP_LOG_LEVEL'])
    else:
        level = logging.ERROR

    if 'SUPP_LOG_FILE' in os.environ:
        logging.basicConfig(filename=os.environ['SUPP_LOG_FILE'],
            format="%(asctime)s %(name)s %(levelname)s: %(message)s", level=level)
    else:
        logging.basicConfig(format="%(name)s %(levelname)s: %(message)s", level=level)

    listener = Listener(sys.argv[1])
    conn = listener.accept()
    server = Server(conn)
    server.run()
