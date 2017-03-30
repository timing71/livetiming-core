import re
import simplejson
from setuptools import setup, find_packages


try:
    with open('web/package.json', 'r') as package:
        package_json = simplejson.load(package)
        verstr = package_json['version']
except:
    verstr = 'unknown'

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
    setup_requires = [
        "simplejson"
    ],
    install_requires=[
        "autobahn[twisted]",
        "dictdiffer",
        "enum34",
        "icalendar",
        "lzstring",
        "pyopenssl",
        "python-dotenv",
        "service_identity",
        "signalr-client",
        "simplejson",
        "socketio-client",
        "subprocess32"
    ],
    entry_points={
        'console_scripts': [
                'livetiming-directory = livetiming.directory:main',
                'livetiming-recordings = livetiming.recording:main',
                'livetiming-service = livetiming.service:main',
                'livetiming-service-manager = livetiming.servicemanager:main',
                'livetiming-rectool = livetiming.rectool:main'
            ],
        }
      )
