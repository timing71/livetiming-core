from livetiming.service.swisstiming.data import patch, PROPERTY_DELETED_FLAG


def test_simple_patch():
    initial = {'a': 1, 'b': 2}
    patched = patch(initial, {'a': 3})
    assert initial == {'a': 3, 'b': 2}


def test_simple_delete():
    initial = {'a': 1, 'b': 2}
    patch(initial, {'a': PROPERTY_DELETED_FLAG})
    assert initial == {'b': 2}


def test_simple_insert():
    initial = {'a': 1, 'b': 2}
    patch(initial, {'c': 3})
    assert initial == {'a': 1, 'b': 2, 'c': 3}


def test_nested_patch():
    initial = {
        'a': {
            'aa': 1,
            'ab': 2
        }
    }

    patch(initial, {'a': {'aa': 4}})

    assert initial == {
        'a': {
            'aa': 4,
            'ab': 2
        }
    }


def test_array_of_dicts():
    initial = {
        'LapNumber': 29,
        'Intermediates': [
            {'TimeState': 0, 'Speed': 219, 'SpeedState': 0, 'Time': '24.126'},
            {'SpeedState': 0, 'TimeState': 0}, {'SpeedState': 0, 'TimeState': 0}
        ],
        'TimeState': 0
    }

    delta = {'Intermediates': {'__jsondiff_t': 'a', 'u': {'1': {'Speed': 213, 'Time': '31.864'}}}}

    patch(initial, delta)

    assert(initial['Intermediates'][1]) == {'Speed': 213, 'Time': '31.864', 'SpeedState': 0, 'TimeState': 0}


def test_array_of_ints():
    initial = {'a': [1, 2, 3]}
    delta = {'a': {'__jsondiff_t': 'a', 'u': {'1': 4}}}
    patch(initial, delta)

    assert initial['a'] == [1, 4, 3]


def test_array_append():
    initial = {
        'Messages': [{'Text': 'ESTIMATED START OF SESSION 11:15 TBC', 'Type': 1, 'Time': '31.05.2019 11:06:59'}]
    }

    delta = {
        'Messages': {
            '__jsondiff_t': 'a',
            'i': [{'Text': 'START OF SESSION WILL BE DELAYED BY 5 MINUTES', 'Type': 1, 'Time': '31.05.2019 11:06:19'}],
            'u': {
                '1': {'Text': 'ESTIMATED START OF SESSION 11:15 TBC', 'Time': '31.05.2019 11:06:59'},
                '0': {'Text': 'START TIME 11:15 CONFIRMED', 'Time': '31.05.2019 11:14:04'}
            }
        }
    }

    patch(initial, delta)
    assert len(initial['Messages']) == 3
    assert initial['Messages'][0]['Text'] == 'START TIME 11:15 CONFIRMED'
    assert initial['Messages'][1]['Text'] == 'ESTIMATED START OF SESSION 11:15 TBC'
    assert initial['Messages'][2]['Text'] == 'START OF SESSION WILL BE DELAYED BY 5 MINUTES'


def test_array_assign():
    initial = {}
    delta = {
        'a': [1, 2, 3]
    }
    patch(initial, delta)

    assert initial.get('a') == [1, 2, 3]
