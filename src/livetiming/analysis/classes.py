from livetiming.analysis import Analysis
from livetiming.analysis.data import FieldExtractor
from livetiming.racing import Stat


class ClassLeaders(Analysis):
    def getName(self):
        return "Class leaders"

    def getData(self):
        cars = self.data_centre.current_state['cars']
        seen_classes = {}

        f = FieldExtractor(self.data_centre.column_spec)

        for pos_minus_one, car in enumerate(cars):
            clazz = f.get(car, Stat.CLASS, '')
            if clazz not in seen_classes:
                seen_classes[clazz] = [
                    pos_minus_one + 1,
                    f.get(car, Stat.NUM),
                    f.get(car, Stat.DRIVER),
                    f.get(car, Stat.TEAM),
                    f.get(car, Stat.CAR)
                ]

        return seen_classes
