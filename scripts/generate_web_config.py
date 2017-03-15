from livetiming.network import MessageClass, RPC, Realm, Channel
from livetiming.racing import FlagStatus
import simplejson


WEB_CONFIG_FILE = "app/config/config.json"

config = {}

def document_class(clazz, transform=lambda x: x):
    key = clazz.__name__
    config[key] = {}
    for attr in [a for a in dir(clazz) if not a.startswith('_')]:
        config[key][attr] = transform(getattr(clazz, attr))


document_class(MessageClass, lambda x: x.value)

document_class(RPC)

document_class(Realm)

document_class(Channel)

document_class(FlagStatus)


with open(WEB_CONFIG_FILE, 'w') as confFile:
    simplejson.dump(config, confFile)