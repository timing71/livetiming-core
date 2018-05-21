from autobahn.twisted.websocket import WebSocketClientProtocol
from twisted.logger import Logger

import ejson


class oid(str):
    pass


def decode(ejson_message):
    return ejson.loads(
        ejson_message,
        custom_type_hooks=[
            ('oid', oid)
        ]
    )


def encode(obj):
    body = ejson.dumps(
        obj,
        custom_type_hooks=[
            (oid, 'oid', str)
        ]
    )
    return ejson.dumps([body])


class CollectionData(object):
    def __init__(self):
        self.data = {}

    def add_data(self, collection, id, fields):
        if collection not in self.data:
            self.data[collection] = {}
        if id not in self.data[collection]:
            self.data[collection][id] = {}
        for key, value in fields.items():
            self.data[collection][id][key] = value

    def change_data(self, collection, id, fields, cleared):
        for key, value in fields.items():
            self.data[collection][id][key] = value

        for key in cleared:
            del self.data[collection][id][key]

    def remove_data(self, collection, id):
        del self.data[collection][id]

    def collections(self):
        return self.data.keys()

    def __repr__(self):
        result = u""
        for coll, data in self.data.iteritems():
            result += u"{} :=> {}\n".format(coll, data)
        return result


def DDPProtoclFactory(handler):
    class DDPProtocol(WebSocketClientProtocol):
        """ A translation into Twisted of https://github.com/hharnisc/python-ddp/blob/master/DDPClient.py (or at least the relevant bits). """
        def __init__(self, *args, **kwargs):
            super(DDPProtocol, self).__init__(*args, **kwargs)
            self._callbacks = {}
            self._uid = 0
            self.log = Logger()

        def _next_id(self):
            """Get the next id that will be sent to the server"""
            self._uid += 1
            return str(self._uid)

        def _handler_call(self, name, *args, **kwargs):
            if handler:
                if hasattr(handler, name):
                    attr = getattr(handler, name)
                    if callable(attr):
                        attr(*args, **kwargs)
                    else:
                        self.log.warn("Attribute {attr} on handler is not callable!", attr=attr)
                else:
                    self.log.warn("Handler can't handle method {name}", name=name)

        def onConnect(self, response):
            self.send({
                "msg": "connect",
                "version": "1",
                "support": ["1", "pre2", "pre1"]
            })
            self._handler_call('connect', self)

        def onMessage(self, payload, isBinary):
            self.log.debug("<<< {payload}", payload=payload)
            if payload[0] != 'a':
                return

            messages = decode(str(payload[1:]))

            for message in messages:
                data = decode(message)
                if not data.get('msg'):
                    return

                elif data['msg'] == 'failed':
                    self.log.warn('Something failed')
                    # self._ddp_version_index += 1
                    # self._retry_new_version = data.get('version', True)
                    # self.emit('failed', data)

                elif data['msg'] == 'connected':
                    self._session = data.get('session')
                    # if self._is_reconnecting:
                    #     self.ddpsocket._debug_log("* RECONNECTED")
                    #     self.emit('reconnected')
                    #     self._is_reconnecting = False
                    # else:
                    #     self.ddpsocket._debug_log("* CONNECTED")
                    #     self.emit('connected')
                    #     self._retry_new_version = False

                # method result
                elif data['msg'] == 'result':
                    # call the optional callback
                    callback = self._callbacks.get(data['id'])
                    if callback:
                        callback(data.get('error'), data.get('result'))
                        self._callbacks.pop(data['id'])

                # missing subscription
                elif data['msg'] == 'nosub':
                    callback = self._callbacks.get(data['id'])
                    if callback:
                        callback(data.get('error'), data['id'])
                        self._callbacks.pop(data['id'])

                # document added to collection
                elif data['msg'] == 'added':
                    self._handler_call(
                        'added',
                        data['collection'],
                        data['id'],
                        data.get('fields', {})
                    )

                # document changed in collection
                elif data['msg'] == 'changed':
                    self._handler_call(
                        'changed',
                        data['collection'],
                        data['id'],
                        data.get('fields', {}),
                        data.get('cleared', {})
                    )

                # document removed from collection
                elif data['msg'] == 'removed':
                    self._handler_call('removed', data['collection'], data['id'])

                # subcription ready
                elif data['msg'] == 'ready':
                    for sub_id in data.get('subs', []):
                        callback = self._callbacks.get(sub_id)
                        if callback:
                            callback(data.get('error'), sub_id)
                            self._callbacks.pop(sub_id)

                elif data['msg'] == 'ping':
                    msg = {'msg': 'pong'}
                    id = data.get('id')
                    if id is not None:
                        msg['id'] = id
                    self.send(msg)

                else:
                    pass

        def send(self, obj):
            message = encode(obj)
            self.log.debug(">>> {message}", message=message)
            self.sendMessage(message)

        def call(self, method, params, callback=None):
            """Call a method on the server
            Arguments:
            method - the remote server method
            params - an array of commands to send to the method
            Keyword Arguments:
            callback - a callback function containing the return data"""
            cur_id = self._next_id()
            if callback:
                self._callbacks[cur_id] = callback
            self.send({'msg': 'method', 'id': cur_id, 'method': method, 'params': params})

        def subscribe(self, name, params, callback=None):
            """Subcribe to add/change/remove events for a collection
            Arguments:
            name - the name of the publication to subscribe
            params - params to subscribe (parsed as ejson)
            Keyword Arguments:
            callback - a callback function that gets executed when the subscription has completed"""
            cur_id = self._next_id()
            if callback:
                self._callbacks[cur_id] = callback
            self.send({'msg': 'sub', 'id': cur_id, 'name': name, 'params': params})
            return cur_id

        def unsubscribe(self, sub_id):
            """Unsubscribe from a collection
            Arguments:
            sub_id - the id of the subsciption (returned by subcribe)"""
            self.send({'msg': 'unsub', 'id': sub_id})
    return DDPProtocol


class MeteorClient(object):
    def __init__(self):
        self.log = Logger()
        self.collection_data = CollectionData()
        self.subscriptions = {}

    #
    # Meteor Method Call
    #

    def call(self, method, params, callback=None):
        """Call a remote method
        Arguments:
        method - remote method name
        params - remote method parameters
        Keyword Arguments:
        callback - callback function containing return data"""
        self.ddp_client.call(method, params, callback=callback)

    #
    # Subscription Management
    #

    def subscribe(self, name, params=[], callback=None):
        """Subscribe to a collection
        Arguments:
        name - the name of the publication
        params - the subscription parameters
        Keyword Arguments:
        callback - a function callback that returns an error (if exists)"""
        def subscribed(error, sub_id):
            if error:
                self._remove_sub_by_id(sub_id)
                if callback:
                    callback(error.get('reason'))
                return
            if callback:
                callback(None)

        if name in self.subscriptions:
            raise MeteorClientException('Already subcribed to {}'.format(name))

        sub_id = self.ddp_client.subscribe(name, params, subscribed)
        self.subscriptions[name] = {
            'id': sub_id,
            'params': params
        }

    def unsubscribe(self, name):
        """Unsubscribe from a collection
        Arguments:
        name - the name of the publication"""
        if name not in self.subscriptions:
            raise MeteorClientException('No subscription for {}'.format(name))
        self.ddp_client.unsubscribe(self.subscriptions[name]['id'])
        del self.subscriptions[name]

    #
    # Collection Management
    #

    def find(self, collection, selector={}):
        """Find data in a collection
        Arguments:
        collection - collection to search
        Keyword Arguments:
        selector - the query (default returns all items in a collection)"""
        results = []
        for _id, doc in self.collection_data.data.get(collection, {}).items():
            doc.update({'_id': _id})
            if selector == {}:
                results.append(doc)
            for key, value in selector.items():
                if key in doc and doc[key] == value:
                    results.append(doc)
        return results

    def find_one(self, collection, selector={}):
        """Return one item from a collection
        Arguments:
        collection - collection to search
        Keyword Arguments:
        selector - the query (default returns first item found)"""
        for _id, doc in self.collection_data.data.get(collection, {}).items():
            doc.update({'_id': _id})
            if selector == {}:
                return doc
            for key, value in selector.items():
                if key in doc and doc[key] == value:
                    return doc
        return None

    def insert(self, collection, doc, callback=None):
        """Insert an item into a collection
        Arguments:
        collection - the collection to be modified
        doc - The document to insert. May not yet have an _id attribute,
        in which case Meteor will generate one for you.
        Keyword Arguments:
        callback - Optional. If present, called with an error object as the first argument and,
        if no error, the _id as the second."""
        self.call("/" + collection + "/insert", [doc], callback=callback)

    def update(self, collection, selector, modifier, callback=None):
        """Insert an item into a collection
        Arguments:
        collection - the collection to be modified
        selector - specifies which documents to modify
        modifier - Specifies how to modify the documents
        Keyword Arguments:
        callback - Optional. If present, called with an error object as the first argument and,
        if no error, the number of affected documents as the second."""
        self.call("/" + collection + "/update", [selector, modifier], callback=callback)

    def remove(self, collection, selector, callback=None):
        """Remove an item from a collection
        Arguments:
        collection - the collection to be modified
        selector - Specifies which documents to remove
        Keyword Arguments:
        callback - Optional. If present, called with an error object as its argument."""
        self.call("/" + collection + "/remove", [selector], callback=callback)

    #
    # Event Handlers
    #

    def connect(self, ddp):
        self.ddp_client = ddp
        self.onConnect()

    def added(self, collection, id, fields):
        self.collection_data.add_data(collection, id, fields)

    def changed(self, collection, id, fields, cleared):
        self.collection_data.change_data(collection, id, fields, cleared)

    def removed(self, collection, id):
        self.collection_data.remove_data(collection, id)

    # Extra hooks

    def onConnect(self):
        pass
