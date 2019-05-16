# -*- coding: utf-8 -*-
from livetiming.service.swisstiming.message import parse_message

raw_message = u"0000000050{\"compressor\":\"lzw\",\"format\":\"json\",\"type\":\"data\"}%7B%22codeă2%3AĊdataĊăCĊChannelĔčĊRAC_PRODĀCADģ_SEASONS_JĳNĔ2ĖĄsyncğA7ĕĊpushDđēĄČĎ5Ă5ĩ7D"


def test_parse_message():
    parsed = parse_message(raw_message)
    assert parsed == {
        "Channel": "RAC_PROD|ADAC_SEASONS_JSON",
        "code": "data",
        "sync": 7,
        "pushData": []
    }
