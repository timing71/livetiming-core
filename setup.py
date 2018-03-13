import re
import json
from setuptools import setup, find_packages


try:
    with open('web/package.json', 'r') as package:
        package_json = json.load(package)
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
    packages=find_packages('src', exclude=["*.tests"]) + [''],
    package_dir={'': 'src'},
    long_description="Live timing aggregator and web service for motorsport timing feeds.",
    install_requires=[
        "autobahn[twisted]>=17.6.2",
        "dictdiffer",
        "enum34",
        "icalendar",
        "lzstring",
        "pyopenssl",
        "python-dotenv",
        "python-twitter",
        "raven",
        "service_identity",
        "signalr-client",
        "simplejson",
        "socketio-client",
        "subprocess32"
    ],
    entry_points={
        'console_scripts': [
            'livetiming-directory = livetiming.directory:main',
            'livetiming-dvr = livetiming.dvr:main',
            'livetiming-recordings = livetiming.recording:main',
            'livetiming-rectool = livetiming.rectool:main',
            'livetiming-scheduler = livetiming.scheduler:main',
            'livetiming-service = livetiming.service:main',
            'livetiming-service-manager = livetiming.servicemanager:main',
        ],
    }
)
