PROPERTY_DELETED_FLAG = '_jsondiff_del'


def patch(orig, delta):
    for n, i in delta.iteritems():

        if i == PROPERTY_DELETED_FLAG:
            try:
                del orig[n]
            except KeyError:
                pass
        elif isinstance(i, list):
            # e.updateProperty(n, $HR(i));
            print 'TODO', orig, n, i
            pass
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
    for n, i in delta.get('u', {}).iteritems():
        n = int(n)
        if isinstance(i, dict) and i.get('__jsondiff_t') == 'a':
            patch_array(orig[n], i)
        elif isinstance(orig[n], dict):
            patch(orig[n], i)
        else:
            orig[n] = i

    return orig
