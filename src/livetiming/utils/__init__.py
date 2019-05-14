import time


def uncache(url, param_name='t'):
    def inner():
        if "?" in url:
            return "{}&{}={}".format(url, param_name, int(time.time()))
        return "{}?{}={}".format(url, param_name, int(time.time()))
    return inner
