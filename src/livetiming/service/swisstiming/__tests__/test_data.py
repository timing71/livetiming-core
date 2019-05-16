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
    initial = {'LapNumber': 29, 'Intermediates': [{'TimeState': 0, 'Speed': 219, 'SpeedState': 0, 'Time': '24.126'}, {'SpeedState': 0, 'TimeState': 0}, {'SpeedState': 0, 'TimeState': 0}], 'TimeState': 0}

    delta = {'Intermediates': {'__jsondiff_t': 'a', 'u': {'1': {'Speed': 213, 'Time': '31.864'}}}}

    patch(initial, delta)

    assert(initial['Intermediates'][1]) == {'Speed': 213, 'Time': '31.864', 'SpeedState': 0, 'TimeState': 0}


def test_array_of_ints():
    initial = {'a': [1, 2, 3]}
    delta = {'a': {'__jsondiff_t': 'a', 'u': {'1': 4}}}
    patch(initial, delta)

    assert initial['a'] == [1, 4, 3]
