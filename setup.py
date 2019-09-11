from setuptools import setup, find_packages


setup(
    name='livetiming',
    description='Live timing aggregator for motorsport timing feeds',
    author='James Muscat',
    author_email='jamesremuscat@gmail.com',
    url='https://github.com/jamesremuscat/livetiming',
    packages=find_packages('src', exclude=["*.tests"]),
    package_dir={'': 'src'},
    long_description="Live timing aggregator and web service for motorsport timing feeds.",
    install_requires=[
        "autobahn[serialization,twisted]>=17.6.2",
        "beautifulsoup4",
        "dictdiffer",
        "google-api-python-client",
        "icalendar",
        "kitchen",
        "lxml",
        "lzstring==1.0.3",
        "meteor-ejson",
        "oauth2client",  # Not included in google-api-python-client despite what Google say
        "pluginbase",
        "pyopenssl",
        "python-dateutil",
        "python-dotenv",
        "python-twitter",
        "sentry-sdk",
        "service_identity",
        "signalr-client",
        "simplejson",
        "socketio-client",
        "subprocess32",
        "treq",
        "twisted"
    ],
    setup_requires=[
        'pytest-runner',
        'setuptools_scm'
    ],
    use_scm_version=True,
    tests_require=[
        'pytest'
    ],
    entry_points={
        'console_scripts': [
            'livetiming-analysis = livetiming.generate_analysis:main',
            'livetiming-directory = livetiming.directory:main',
            'livetiming-dvr = livetiming.dvr:main',
            'livetiming-recordings = livetiming.recording:main',
            'livetiming-recordings-index = livetiming.recording:update_recordings_index',
            'livetiming-rectool = livetiming.rectool:main',
            'livetiming-schedule = livetiming.schedule.__main__:main',
            'livetiming-scheduler = livetiming.scheduler:main',
            'livetiming-service = livetiming.service:main',
            'livetiming-service-manager = livetiming.servicemanager:main',
        ],
    }
)
