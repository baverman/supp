from setuptools import setup, find_packages

setup(
    name = 'supp',
    version = '0.1dev',
    author = 'Anton Bobrov',
    author_email = 'bobrov@vl.ru',
    description = 'Python code completion library',
    long_description = open('README.rst').read(),
    zip_safe = False,
    packages = find_packages(exclude=('tests', )),
    include_package_data = True,
    url = 'http://github.com/baverman/supp',
    classifiers = [
        "Programming Language :: Python",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 4 - Beta",
        "Natural Language :: English",
    ],
)
