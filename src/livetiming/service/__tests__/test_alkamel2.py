from livetiming.service.alkamel2 import augment_data_with_loops, calculate_gap


def test_calculate_gap():
    one = augment_data_with_loops({
        'bestLapTime': 71962,
        'currentSectors': '1;26750;true;false;false;false;2;26632;false;false;false;false;3;18580;false;false;false;false;',
        'currentLoopSectors': '',
        'previousLoopSectors': '1;4967;2;8343;3;26750;4;46390;5;53382;6;53899;7;71153;8;71962;',
        'bestLapNumber': 331,
        'isLastLapBestPersonal': True,
        'isCheckered': False,
        'lastSectors': '1;26750;false;false;false;false;2;26632;false;false;false;false;3;18580;false;false;false;false;',
        'currentLapStartTime': 1539470402612,
        'isRunning': True,
        'data': '1;10;CLASSIFIED;1;331;11;172.494;1539470402612;TRACK;332;',
        'class': 'P',
        'lastLapTime': 71962
    })

    two = augment_data_with_loops({
        'bestLapTime': 71855,
        'currentSectors': '1;26858;false;false;false;false;2;26658;false;false;false;false;',
        'currentLoopSectors': '1;4942;2;8303;3;26858;4;46563;5;53516;6;54028;',
        'previousLoopSectors': '1;4971;2;8652;3;27380;4;47071;5;54031;6;54544;7;71869;8;72680;',
        'bestLapNumber': 303,
        'isLastLapBestPersonal': False,
        'isCheckered': False,
        'lastSectors': '1;27380;false;false;false;false;2;26651;false;false;false;false;3;18649;false;false;false;false;',
        'currentLapStartTime': 1539470333304,
        'isRunning': True,
        'data': '2;31;CLASSIFIED;2;330;12;173.879;1539470333304;TRACK;331;',
        'class': 'P',
        'lastLapTime': 72680
    })

    assert calculate_gap(one, two) == 2.783

    three = augment_data_with_loops({
        'isCheckered': False,
        'currentLapStartTime': 1552584628031,
        'currentLoopSectors': '2;11629;',
        'data': '3;23;CLASSIFIED;3;21;0;158.171;1552584628031;TRACK;22;',
        'class': 'LMP3',
        'previousLoopSectors': '1;14468;2;25383;3;70077;4;93408;5;134888;6;151361;7;188668;8;209448;',
        'bestLapTime': 119450,
        'currentSectors': '1;70077;false;false;false;false;2;64811;false;false;false;false;3;74560;false;false;false;false;',
        'bestLapNumber': 11,
        'isLastLapBestPersonal': False,
        'laps': 21,
        'sectorsWithDiff': True,
        'currentLapNumber': 22,
        'elapsedTime': 3277570,
        'lastLapTime': 209448,
        'lastSectors': '1;70077;false;false;false;false;2;64811;false;false;false;false;3;74560;false;false;false;false;',
        'isRunning': True
    })

    four = augment_data_with_loops({
        'isCheckered': False,
        'currentLapStartTime': 1552584628848,
        'currentLoopSectors': '1;6066;2;12127;',
        'data': '4;40;CLASSIFIED;4;21;0;153.866;1552584628848;TRACK;22;',
        'class': 'LMP3',
        'previousLoopSectors': '1;15126;2;25622;3;70583;4;94164;5;134889;6;151389;7;188903;8;209610;',
        'bestLapTime': 122160,
        'currentSectors': '1;70583;false;false;false;false;2;64306;false;false;false;false;3;74721;false;false;false;false;',
        'bestLapNumber': 12,
        'isLastLapBestPersonal': False,
        'laps': 21,
        'sectorsWithDiff': True,
        'currentLapNumber': 22,
        'elapsedTime': 3278387,
        'lastLapTime': 209610,
        'lastSectors': '1;70583;false;false;false;false;2;64306;false;false;false;false;3;74721;false;false;false;false;',
        'isRunning': True
    })

    assert calculate_gap(three, four) == 1.315
