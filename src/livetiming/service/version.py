import pkg_resources


VERSION = 'unknown'
try:
    VERSION = pkg_resources.get_distribution('livetiming-core').version
except:
    pass
