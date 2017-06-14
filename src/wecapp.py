from urllib import quote_plus

import hashlib
import simplejson
import sys
import urllib2


CLIENT_ID = "c87d1a87-00fa-4229-aa8c-6b151ba25f99"
SECRET = "364a30eba38250ff90fb8c34e1ddc1b87bbe1ed7"


def get(base_url, params=[]):

    headers = get_headers(base_url, params)

    request = urllib2.Request(
        build_url(base_url, params),
        headers=headers
    )

    rq = urllib2.urlopen(request)
    if rq.getcode() != 200:
        return {}
    return simplejson.load(rq)


def get_headers(base_url, params):
    return {
        "X-Api-Client-Id": CLIENT_ID,
        "X-Api-Sig": get_signature(base_url, params)
    }


def get_signature(base_url, params=[]):
    sigString = build_url(base_url, params)

    sigString += "@{}:{}".format(
        CLIENT_ID,
        ae("netcosports{}".format(SECRET))
    )

    return ae(sigString)


def build_url(base_url, params):
    url_string = base_url

    if "?" in url_string:
        url_string += "&"
    else:
        url_string += "?"

    if params:
        for (name, value) in sorted(params):
            url_string += "{}={}&".format(
                name,
                ag(value)
            )

    return url_string


def ag(string):
    if string == "" or string is None:
        return ""
    return quote_plus(string).replace("+", "%20")


def ae(string):
    digest = hashlib.sha1()
    digest.update(string)

    result = ""

    for c in digest.digest():
        b = ord(c)
        i = (rshift(b, 4)) & 15
        i2 = 0
        while True:
            c = chr(((i - 10) + 97)) if i < 0 or i > 9 else chr(i + 48)
            result += c
            i3 = b & 15
            i = i2 + 1
            if i2 > 0:
                break
            i2 = i
            i = i3

    return result


def rshift(val, n):
    return (val % 0x100000000) >> n


if __name__ == "__main__":
    base_url = sys.argv[1]

    params = map(lambda param: param.split("="), sys.argv[2:])

    print simplejson.dumps(
        get(base_url, params),
        sort_keys=True,
        indent=4,
        separators=(',', ': ')
    )
