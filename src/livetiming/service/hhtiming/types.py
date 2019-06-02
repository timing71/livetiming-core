class MessageType(object):
    BASIC_TIME_CROSSING = 'HTiming.Core.Definitions.Communication.Messages.BasicTimeCrossingMessage'
    CLASS_INFORMATION = 'HTiming.Core.Definitions.Communication.Messages.ClassInformationMessage'
    COMPETITOR = 'HTiming.Core.Definitions.Communication.Messages.CompetitorMessage'
    DRIVER = 'HTiming.Core.Definitions.Communication.Messages.DriverMessage'
    DRIVER_UPDATE = 'HTiming.Core.Definitions.Communication.Messages.DriverUpdateMessage'
    EVENT = 'HTiming.Core.Definitions.Communication.Messages.EventMessage'
    GPS = 'HHTiming.Core.Definitions.Communication.Messages.CarGpsPointMessage'
    HEARTBEAT = 'HTiming.Core.Definitions.Communication.Messages.HeartbeatMessage'
    INTERNAL_HEARTBEAT = 'HTiming.Core.Definitions.Communication.Messages.InternalHHHeartbeatMessage'
    LAPTIME_UPDATE = 'HTiming.Core.Definitions.Communication.Messages.LaptimeResultsUpdateMessage'
    PIT_IN = 'HTiming.Core.Definitions.Communication.Messages.PitInMessage'
    PIT_OUT = 'HTiming.Core.Definitions.Communication.Messages.PitOutMessage'
    RACE_CONTROL_MESSAGE = 'HTiming.Core.Definitions.Communication.Messages.GeneralRaceControlMessage'
    SECTOR_STATUS = 'HTiming.Core.Definitions.Communication.Messages.TrackSectorStatusMessage'
    SECTOR_TIME_ADV = 'HTiming.Core.Definitions.Communication.Messages.AdvSectorTimeLineCrossing'
    SECTOR_TIME_UPDATE = 'HTiming.Core.Definitions.Communication.Messages.SectorTimeResultsUpdateMessage'
    SESSION_INFO = 'HTiming.Core.Definitions.Communication.Messages.SessionInfoMessage'
    SPEED_TRAP = 'HTiming.Core.Definitions.Communication.Messages.SpeedTrapCrossingMessage'
    TOP_SPEED_UPDATE = 'HTiming.Core.Definitions.Communication.Messages.TopSpeedResultsUpdateMessage'
    TRACK_INFO_ADV = 'HTiming.Core.Definitions.Communication.Messages.AdvTrackInformationMessage'
    WEATHER = 'HTiming.Core.Definitions.Communication.Messages.WeatherTSMessage'


class SectorStatus(object):
    CLEAR = 0
    SLOW_ZONE = 8
