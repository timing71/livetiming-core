from livetiming.utils import PitOutDebouncer, time


def test_debounce_on_exit(monkeypatch):
    monkeypatch.setattr(time, 'time', lambda: 1)
    debouncer = PitOutDebouncer(threshold=20)

    # Initial value should get returned
    assert debouncer.value_for(1, 'PIT') == 'PIT'

    monkeypatch.setattr(time, 'time', lambda: 5)
    # Too soon to be able to debounce!
    assert debouncer.value_for(1, 'RUN') == 'RUN'
    assert debouncer.value_for(1, 'PIT') == 'PIT'

    monkeypatch.setattr(time, 'time', lambda: 21)
    # But here we can debounce...
    assert debouncer.value_for(1, 'RUN') == 'PIT'

    monkeypatch.setattr(time, 'time', lambda: 26)
    # Long enough since previous change to accept new value
    assert debouncer.value_for(1, 'RUN') == 'RUN'


def test_debounce_on_entry(monkeypatch):
    monkeypatch.setattr(time, 'time', lambda: 1)
    debouncer = PitOutDebouncer(threshold=20)

    assert debouncer.value_for(1, 'RUN') == 'RUN'

    monkeypatch.setattr(time, 'time', lambda: 5)
    assert debouncer.value_for(1, 'PIT') == 'PIT'
    assert debouncer.value_for(1, 'RUN') == 'RUN'

    monkeypatch.setattr(time, 'time', lambda: 21)
    assert debouncer.value_for(1, 'PIT') == 'RUN'

    monkeypatch.setattr(time, 'time', lambda: 26)
    assert debouncer.value_for(1, 'PIT') == 'PIT'
