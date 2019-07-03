PROPERTY_DELETED_FLAG = '_jsondiff_del'


def patch(orig, delta):
    for n, i in delta.items():

        if i == PROPERTY_DELETED_FLAG:
            try:
                del orig[n]
            except KeyError:
                pass
        elif isinstance(i, list):
            orig[n] = i
        elif i is None:
            orig[n] = None
        elif isinstance(i, dict) and i.get('__jsondiff_t') == 'a':
            patch_array(orig[n], i)
        elif n in orig:
            r = orig[n]
            if isinstance(r, dict):
                patch(r, i)
            else:
                orig[n] = i
        else:
            orig[n] = i
    return orig


def patch_array(orig, delta):
    for n, i in delta.get('u', {}).items():
        n = int(n)
        if isinstance(i, dict) and i.get('__jsondiff_t') == 'a':
            patch_array(orig[n], i)
        elif len(orig) > n and isinstance(orig[n], dict):
            patch(orig[n], i)
        else:
            while len(orig) <= n:
                orig.append(None)
            orig[n] = i
    if 'i' in delta:
        original_items = delta['i']
        for orig_item in original_items:
            orig.append(orig_item)

    return orig
