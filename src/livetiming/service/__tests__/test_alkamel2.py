from livetiming.service.alkamel2 import augment_data_with_loops, calculate_gap


def test_calculate_gap():
    one = augment_data_with_loops({
        u'bestLapTime': 71962,
        u'currentSectors': u'1;26750;true;false;false;false;2;26632;false;false;false;false;3;18580;false;false;false;false;',
        u'currentLoopSectors': u'',
        u'previousLoopSectors': u'1;4967;2;8343;3;26750;4;46390;5;53382;6;53899;7;71153;8;71962;',
        u'bestLapNumber': 331,
        u'isLastLapBestPersonal': True,
        u'isCheckered': False,
        u'lastSectors': u'1;26750;false;false;false;false;2;26632;false;false;false;false;3;18580;false;false;false;false;',
        u'currentLapStartTime': 1539470402612,
        u'isRunning': True,
        u'data': u'1;10;CLASSIFIED;1;331;11;172.494;1539470402612;TRACK;332;',
        u'class': u'P',
        u'lastLapTime': 71962
    })

    two = augment_data_with_loops({
        u'bestLapTime': 71855,
        u'currentSectors': u'1;26858;false;false;false;false;2;26658;false;false;false;false;',
        u'currentLoopSectors': u'1;4942;2;8303;3;26858;4;46563;5;53516;6;54028;',
        u'previousLoopSectors': u'1;4971;2;8652;3;27380;4;47071;5;54031;6;54544;7;71869;8;72680;',
        u'bestLapNumber': 303,
        u'isLastLapBestPersonal': False,
        u'isCheckered': False,
        u'lastSectors': u'1;27380;false;false;false;false;2;26651;false;false;false;false;3;18649;false;false;false;false;',
        u'currentLapStartTime': 1539470333304,
        u'isRunning': True,
        u'data': u'2;31;CLASSIFIED;2;330;12;173.879;1539470333304;TRACK;331;',
        u'class': u'P',
        u'lastLapTime': 72680
    })

    assert calculate_gap(one, two) == 2.788
