from livetiming.analysis import Analysis
from collections import defaultdict
from livetiming.analysis.data import FieldExtractor
from livetiming.racing import Stat


class Session(Analysis):
    def getName(self):
        return "Session stats"

    def getData(self):
        results = {}

        flag_stats = {}

        for flag, start_lap, start_time, stop_lap, stop_time in self.data_centre.session.flag_periods:
            if flag not in flag_stats:
                flag_stats[flag] = {
                    'time': 0,
                    'count': 0,
                    'laps': 0
                }
            flag_stats[flag]['count'] += 1

            if stop_time:
                flag_stats[flag]['time'] += (stop_time - start_time)
            else:
                flag_stats[flag]['time'] += (self.data_centre.latest_timestamp - start_time)

            if stop_lap:
                flag_stats[flag]['laps'] += (stop_lap - start_lap)
            else:
                flag_stats[flag]['laps'] += (self.data_centre.leader_lap - start_lap)

        car_per_state = defaultdict(int)
        f = FieldExtractor(self.data_centre.column_spec)
        for car in self.data_centre.current_state['cars']:
            car_per_state[f.get(car, Stat.STATE)] += 1

        results['flagStats'] = flag_stats
        results['carPerState'] = car_per_state
        results['currentFlagPeriod'] = self.data_centre.session.flag_periods[-1]
        results['currentTimestamp'] = self.data_centre.latest_timestamp
        results['leaderLap'] = self.data_centre.leader_lap

        return results
