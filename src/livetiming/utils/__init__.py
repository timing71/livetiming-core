import time


def uncache(url, param_name='t'):
    def inner():
        if "?" in url:
            return "{}&{}={}".format(url, param_name, int(time.time()))
        return "{}?{}={}".format(url, param_name, int(time.time()))
    return inner


class PitOutDebouncer(object):
    def __init__(self, threshold=25):
        self._previous_changes = {}
        self.threshold = threshold
        self._init_time = time.time()

    def value_for(self, key, feed_value):
        prev_value, prev_time = self._previous_changes.get(key, (None, None))
        if feed_value != prev_value:
            now = time.time()

            init_threshold_passed = self._init_time + self.threshold <= now

            if prev_time and now < prev_time + self.threshold and init_threshold_passed:
                return prev_value

            self._previous_changes[key] = (feed_value, time.time())
        return feed_value
