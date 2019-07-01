from io import StringIO
from kitchen.text.converters import to_bytes, to_unicode
import simplejson
import urllib.request, urllib.parse, urllib.error


PREHEADER_LENGTH = 10


def parse_message(raw):
    if len(raw) > PREHEADER_LENGTH and raw[PREHEADER_LENGTH] == '{':
        header_length = int(raw[0:PREHEADER_LENGTH])
        header = simplejson.loads(raw[PREHEADER_LENGTH:PREHEADER_LENGTH + header_length])
        body = raw[PREHEADER_LENGTH + header_length:]
        if header.get('compressor') == 'lzw':
            decompressed = decompress(to_unicode(to_bytes(body)))
            return simplejson.loads(urllib.parse.unquote(decompressed))
    return None


def decompress(compressed):
    dict_size = 256
    dictionary = dict((i, chr(i)) for i in range(dict_size))

    compressed = list(map(ord, compressed))

    result = StringIO()
    w = chr(compressed.pop(0))
    result.write(w)
    for k in compressed:
        if k in dictionary:
            entry = dictionary[k]
        elif k == dict_size:
            entry = w + w[0]
        else:
            raise ValueError('Bad compressed k: %s' % k)
        result.write(entry)

        # Add w+entry[0] to the dictionary.
        dictionary[dict_size] = w + entry[0]
        dict_size += 1

        w = entry
    return result.getvalue()
