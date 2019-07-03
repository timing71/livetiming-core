from bs4 import BeautifulSoup
from datetime import datetime
from livetiming.racing import FlagStatus

import re


FLAG_MESSAGE_CLASSES = re.compile('MessageDC[2-4]')


def parse_feed(fp):
    soup = BeautifulSoup(fp, "lxml")
    all_rows = soup.body.table.find_all('tr')

    headings_row = all_rows[2].find_all('td')
    series = headings_row[0].string
    session = headings_row[1].string

    session_times_row = all_rows[3].find_all('td')
    time_remain = parse_session_time(session_times_row[0].string)

    column_spec = map(
        lambda t: t.string,
        soup.body.table.find_all('td', recursive=False)
    )

    messages = map(
        lambda td: unicode(td.string.strip()),
        soup.body.table.find_all(class_='MessageDC1')
    )

    flag = FlagStatus.NONE

    flag_messages = soup.body.table.find_all(class_=FLAG_MESSAGE_CLASSES)
    if len(flag_messages) == 1:
        flag_message = flag_messages[0]
        clazz = flag_message['class'][0]
        text = flag_message.string.strip()
        if clazz == 'MessageDC2' and text == 'RED FLAG':
            flag = FlagStatus.RED
        elif clazz == 'MessageDC3':
            if 'YELLOW FLAG' in text:
                flag = FlagStatus.YELLOW
                messages.append(text)
            elif text == 'SAFETY CAR':
                flag = FlagStatus.SC
        elif clazz == 'MessageDC4' and text == 'GREEN FLAG':
            flag = FlagStatus.GREEN
        else:
            print "Unknown flag/class combo {} {}".format(text, clazz)

    return {
        "series": series,
        "session": session,
        "timeRemain": time_remain,
        "cars": map_car_rows(all_rows[8:-1], column_spec),
        'messages': messages,
        'flag': flag
    }


def parse_session_time(raw):
    splits = raw.split(':')
    if len(splits) == 4:
        return int(splits[3]) + (int(splits[2]) * 60) + (int(splits[1]) * 3600)
    return None


def parse_laptime(formattedTime):
    if formattedTime == "" or formattedTime is None or formattedTime[0] == '-':
        return ''
    try:
        return float(formattedTime)
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S.%f")
            return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            try:
                ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
                return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
            except:
                return None


def maybe_unicode(raw):
    if raw:
        return unicode(raw)
    else:
        return None


LAPS_REGEX = re.compile('==(?P<lapcount>[0-9]+)==')


def map_car_rows(rows, column_spec):
    accum = {}

    def map_car_row(row):
        tds = row.find_all('td')

        def get(col, string=True):
            idx = column_spec.index(col) if col in column_spec else None
            if idx is not None:
                if string:
                    return maybe_unicode(tds[idx].string)
                return tds[idx]
            else:
                return None

        gap_idx = column_spec.index('Gap') if 'Gap' in column_spec else None
        lap_idx = column_spec.index('Lap') if 'Lap' in column_spec else None
        if gap_idx:
            laps_or_gap = unicode(tds[gap_idx].string)

            maybe_lap = LAPS_REGEX.match(laps_or_gap)
            gap = laps_or_gap
            if maybe_lap:
                new_lap = int(maybe_lap.group('lapcount'))
                if 'leader_lap' in accum:
                    gap_laps = accum['leader_lap'] - new_lap
                    gap = '{} lap{}'.format(
                        gap_laps,
                        '' if gap_laps == 1 else 's'
                    )
                else:
                    gap = ''
                    accum['leader_lap'] = new_lap

                accum['lap'] = new_lap
            else:
                try:
                    gap = parse_laptime(laps_or_gap)
                except ValueError:
                    gap = ''
        if lap_idx:
            accum['lap'] = unicode(tds[lap_idx].string)

        return {
            'pos': get('Pos'),
            'state': map_car_state(get('Now', False)),
            'num': get('#'),
            'class': get('Cla'),
            'team': get('Team'),
            'driver': get('Drivers on Track'),
            's1': map_sector(get('S1', False)),
            's2': map_sector(get('S2', False)),
            's3': map_sector(get('S3', False)),
            'best_lap': map_laptime(get('Best Time', False)),
            'last_lap': map_laptime(get('Last Time', False)),
            'laps': accum.get('lap'),
            'gap': gap,
            'pits': get('PS')
        }

    return map(map_car_row, rows)


def map_car_state(state_td):
    if state_td:
        clazz = state_td['class']
        if state_td.string == 'IN':
            return 'PIT'
        elif state_td.string == 'OUT':
            return 'OUT'
        elif 'chronos_run' in clazz:
            return 'RUN'
        elif 'chronos_pitin' in clazz:
            return 'PIT'
        elif 'chronos_pitout' in clazz:
            return 'OUT'
    return ''


def map_laptime(time_td):
    if time_td:
        clazz = time_td['class']
        flag = ''
        if 'chronos_bestgen' in clazz:
            flag = 'sb'
        elif 'chronos_bestperso' in clazz:
            flag = 'pb'
        return (parse_laptime(maybe_unicode(time_td.string)), flag)
    return None


def map_sector(sector_td):
    if sector_td:
        val = ''
        flag = ''
        raw = maybe_unicode(sector_td.string)
        if raw:
            val = parse_laptime(raw) or '?'

        if 'chronos_bestgen' in sector_td['class']:
            flag = 'sb'
        elif 'chronos_bestperso' in sector_td['class']:
            flag = 'pb'

        return (val, flag)
    return None
