from setuptools import setup, find_packages


setup(
    name='livetiming-core',
    description='Timing71 live timing aggregator - core functionality',
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
    install_requires=[
        "autobahn[serialization,twisted]>=17.6.2",
        "dictdiffer",
        "lzstring==1.0.3",
        "pluginbase",
        "pyopenssl",
        "python-dateutil",
        "python-dotenv",
        "sentry-sdk",
        "simplejson",
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
            'livetiming-plugins = livetiming.service.list_plugins:main',
            'livetiming-recordings = livetiming.recording:main',
            'livetiming-recordings-index = livetiming.recording:update_recordings_index',
            'livetiming-service = livetiming.service:main',
        ],
    }
)
