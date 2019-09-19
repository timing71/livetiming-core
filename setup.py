from setuptools import setup, find_packages


setup(
    name='livetiming-core',
    description='Timing 71 live timing aggregator - core functionality',
    author='James Muscat',
    author_email='jamesremuscat@gmail.com',
    url='https://github.com/jamesremuscat/livetiming',
    packages=find_packages('src', exclude=["*.tests"]),
    package_dir={'': 'src'},
    long_description='''
    Core functionality for the Timing 71 live timing aggregator.

    This is a framework for obtaining, processing, analysing and publishing
    motorsport live timing data feeds from a variety of sources.
    ''',
    include_package_data=True,
    install_requires=[
        "autobahn[serialization,twisted]>=17.6.2",
        "dictdiffer",
        "fastjsonschema",
        "google-api-python-client",
        "icalendar",
        "lzstring==1.0.3",
        "oauth2client",  # Not included in google-api-python-client despite what Google say
        "pluginbase",
        "pyopenssl",
        "python-dateutil",
        "python-dotenv",
        "python-twitter",
        "sentry-sdk",
        "service_identity",
        "simplejson",
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
            'livetiming-directory = livetiming.orchestration.directory:main',
            'livetiming-dvr = livetiming.orchestration.dvr:main',
            'livetiming-recordings = livetiming.recording:main',
            'livetiming-recordings-index = livetiming.recording:update_recordings_index',
            'livetiming-rectool = livetiming.orchestration.rectool:main',
            'livetiming-schedule = livetiming.orchestration.schedule.__main__:main',
            'livetiming-scheduler = livetiming.orchestration.scheduler:main',
            'livetiming-service = livetiming.service:main',
            'livetiming-service-manager = livetiming.orchestration.servicemanager:main',
        ],
    }
)
