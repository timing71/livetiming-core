import pkg_resources


VERSION = 'unknown'
try:
    VERSION = pkg_resources.get_distribution('livetiming-core').version
except Exception:
    pass

USER_AGENT = 'Timing71/{}'.format(VERSION)
