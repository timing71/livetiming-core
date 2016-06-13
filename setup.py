from setuptools import setup, find_packages
import re

VERSIONFILE = "src/livetiming/_version.py"
verstr = "unknown"
try:
    verstrline = open(VERSIONFILE, "rt").read()
    VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"
    mo = re.search(VSRE, verstrline, re.M)
    if mo:
        verstr = mo.group(1)
except EnvironmentError:
    print "unable to find version in %s" % (VERSIONFILE,)
    raise RuntimeError("if %s exists, it is required to be well-formed" % (VERSIONFILE,))

setup(
    name='livetiming',
    version=verstr,
    description='Live timing aggregator for motorsport timing feeds',
    author='James Muscat',
    author_email='jamesremuscat@gmail.com',
    url='https://github.com/jamesremuscat/livetiming',
    packages=find_packages('src', exclude=["*.tests"]),
    package_dir = {'':'src'},
      long_description="Live timing aggregator and web service for motorsport timing feeds.",
    install_requires=["autobahn[twisted]", "enum34", "simplejson"],
    entry_points={
        'console_scripts': [
                'livetiming-directory = livetiming.directory:main',
                'livetiming-service = livetiming.service:main',
            ],
        }
      )
