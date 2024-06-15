# type: ignore
import sys
import time
import os.path

from threading import Thread, Lock

from .umsgpack import dumps, loads
from . import umsgpack

# umsgpack.compatibility = True


class Environment(object):
    """Supplement server client"""

    def __init__(self, executable=None, env=None, logfile=None):
        """Environment constructor

        :param executable: path to python executable. May be path to virtualenv interpreter
              start script like ``/path/to/venv/bin/python``.

        :param env: environment variables dict, e.g. ``DJANGO_SETTINGS_MODULE`` value.

        :param logfile: explicit log file, can be passed via environment SUPP_LOG_FILE
        """
        self.executable = executable or sys.executable
        self.env = env
        self.logfile = logfile

        self.prepare_thread = None
        self.prepare_lock = Lock()

    def _run(self):
        from subprocess import Popen
        from multiprocessing.connection import Client, arbitrary_address

        if sys.platform == 'win32':
            addr = arbitrary_address('AF_PIPE')
        else:
            addr = arbitrary_address('AF_UNIX')

        supp_server = os.path.join(os.path.dirname(__file__), 'server.py')
        args = [self.executable, supp_server, addr]

        env = os.environ.copy()
        if self.env:
            env.update(self.env)

        if self.logfile and 'SUPP_LOG_FILE' not in env:
            env['SUPP_LOG_FILE'] = self.logfile

        self.proc = Popen(args, env=env)

        start = time.time()
        while True:
            try:
                self.conn = Client(addr)
            except Exception as e:
                if time.time() - start > 5:
                    raise Exception('Supp server launching timeout exceed: ' + str(e))

                time.sleep(0.3)
            else:
                break

    def _threaded_run(self):
        try:
            self._run()
        finally:
            self.prepare_thread = None

    def prepare(self):
        with self.prepare_lock:
            if self.prepare_thread:
                return

            if hasattr(self, 'conn'):
                return

            self.prepare_thread = Thread(target=self._threaded_run)
            self.prepare_thread.start()

    def run(self):
        with self.prepare_lock:
            if self.prepare_thread:
                self.prepare_thread.join()

            if not hasattr(self, 'conn'):
                self._run()

    def _call(self, name, *args, **kwargs):
        try:
            self.conn
        except AttributeError:
            self.run()

        self.conn.send_bytes(dumps((name, args, kwargs)))
        result, is_ok = loads(self.conn.recv_bytes())

        if is_ok:
            return result
        else:
            raise Exception(result[1])

    def lint(self, source, filename, syntax_only=False):
        return self._call('lint', source, filename, syntax_only)

    def assist(self, source, position, filename):
        """Return completion match and list of completion proposals

        :param source: code source
        :param position: tuple of (line, column)
        :param filename: absolute path of file with source code
        :returns: tuple (completion match, sorted list of proposals)
        """
        return self._call('assist', source, position, filename)

    def location(self, source, position, filename):
        """Return position and file path where name under cursor is defined

        If position is None location wasn't finded. If file path is None, defenition is located in
        the same source.

        :param source: code source
        :param position:  tuple of (line, column)
        :param filename: absolute path of file with source code
        :returns: tuple ((line, column), file path)
        """
        return self._call('location', source, position, filename)

    # def get_docstring(self, project_path, source, position, filename):
    #     """Return signature and docstring for current cursor call context

    #     Some examples of call context::

    #        func(|
    #        func(arg|
    #        func(arg,|

    #        func(arg, func2(|    # call context is func2

    #     Signature and docstring can be None

    #     :param project_path: absolute project path
    #     :param source: unicode or byte string code source
    #     :param position: character or byte cursor position
    #     :param filename: absolute path of file with source code
    #     :returns: tuple (signarure, docstring)
    #     """
    #     return self._call('get_docstring', project_path, source, position, filename)

    def configure(self, config):
        """Reconfigure project

        :param config: dict with config key/values
        """
        return self._call('configure', config)

    # def get_scope(self, project_path, source, lineno, filename, continous=True):
    #     """
    #     Return scope name at cursor position

    #     For example::

    #         class Foo:
    #             def foo(self):
    #                 pass
    #                 |
    #             def bar(self):
    #                 pass

    #     get_scope return Foo.foo if continuous is True and Foo otherwise.

    #     :param project_path: absolute project path
    #     :param source: unicode or byte string code source
    #     :param position: character or byte cursor position
    #     :param filename: absolute path of file with source code
    #     :param continous: allow parent scope beetween children if False
    #     """
    #     return self._call('get_scope', project_path, source, lineno, filename, continous=continous)

    def eval(self, source):
        return self._call('eval', source)

    def close(self):
        """Shutdown server"""

        try:
            self.conn
        except AttributeError:
            pass
        else:
            self.conn.send_bytes(dumps(('close', (), {}), 2))
            self.conn.close()
            del self.conn
