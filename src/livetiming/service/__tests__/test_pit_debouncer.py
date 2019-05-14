from livetiming.service.indycar import PitOutDebouncer


def test_debounce_on_exit():
    debouncer = PitOutDebouncer()

    assert debouncer.value_for(1, 'PIT') == 'PIT'
    assert debouncer.value_for(1, 'RUN') == 'RUN'
    assert debouncer.value_for(1, 'PIT') == 'RUN'
    assert debouncer.value_for(1, 'RUN') == 'RUN'


def test_debounce_on_entry():
    debouncer = PitOutDebouncer()

    assert debouncer.value_for(1, 'RUN') == 'RUN'
    assert debouncer.value_for(1, 'PIT') == 'PIT'
    assert debouncer.value_for(1, 'RUN') == 'PIT'
    assert debouncer.value_for(1, 'PIT') == 'PIT'
