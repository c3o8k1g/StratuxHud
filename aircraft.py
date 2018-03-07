import requests
import random
import math
import configuration
import datetime
import threading
import lib.recurring_task as recurring_task


class StratuxCapabilities(object):
    """
    Get the capabilties of the Stratux, so we know what can be used
    in the HUD.
    """

    def __get_capability__(self, key):
        if key is None:
            return False

        if self.__capabilties_json__ is None:
            return False

        if key in self.__capabilties_json__:
            try:
                return bool(self.__capabilties_json__[key])
            except:
                return False

        return False

    def __init__(self, stratux_address, stratux_session, simulation_mode=False):
        """
        Builds a list of Capabilities of the stratux.
        """

        if stratux_address is None or simulation_mode:
            self.__capabilties_json__ = None
            self.traffic_enabled = False
            self.gps_enabled = False
            self.barometric_enabled = True
            self.ahrs_enabled = True
        else:
            url = "http://{0}/getSettings".format(stratux_address)

            try:
                self.__capabilties_json__ = stratux_session.get(
                    url, timeout=2).json()
            except:
                self.__capabilties_json__ = []

            self.traffic_enabled = self.__get_capability__('UAT_Enabled')
            self.gps_enabled = self.__get_capability__('GPS_Enabled')
            self.barometric_enabled = self.__get_capability__(
                'BMP_Sensor_Enabled')
            self.ahrs_enabled = self.__get_capability__('IMU_Sensor_Enabled')

    # http://192.168.10.1/getSettings - get device settings. Example output:
    # {
    # "UAT_Enabled": true,
    # "ES_Enabled": false,
    # "Ping_Enabled": false,
    # "GPS_Enabled": true,
    # "BMP_Sensor_Enabled": true,
    # "IMU_Sensor_Enabled": true,
    # "NetworkOutputs": [
    #     {
    #     "Conn": null,
    #     "Ip": "",
    #     "Port": 4000,
    #     "Capability": 5,
    #     "MessageQueueLen": 0,
    #     "LastUnreachable": "0001-01-01T00:00:00Z",
    #     "SleepFlag": false,
    #     "FFCrippled": false
    #     }
    # ],
    # "SerialOutputs": null,
    # "DisplayTrafficSource": false,
    # "DEBUG": false,
    # "ReplayLog": false,
    # "AHRSLog": false,
    # "IMUMapping": [
    #     -1,
    #     0
    # ],
    # "SensorQuaternion": [
    #     0.0068582877312501,
    #     0.0067230280142738,
    #     0.7140806859355,
    #     -0.69999752767998
    # ],
    # "C": [
    #     -0.019065523239845,
    #     -0.99225684377575,
    #     -0.019766228217414
    # ],
    # "D": [
    #     -2.7707754753258,
    #     5.544145023957,
    #     -1.890621662038
    # ],
    # "PPM": 0,
    # "OwnshipModeS": "F00000",
    # "WatchList": "",
    # "DeveloperMode": false,
    # "GLimits": "",
    # "StaticIps": [
    # ]
    # }


class AhrsData(object):
    """
    Class to hold the AHRS data
    """

    def get_heading(self):
        if self.compass_heading is None or self.compass_heading > 360 or self.compass_heading < 0 or self.compass_heading is '':
            return self.gps_heading

        return self.compass_heading

    def __init__(self):
        self.roll = 0.0
        self.pitch = 0.0
        self.compass_heading = 0.0
        self.gps_heading = 0.0
        self.compass_heading = 0.0
        self.alt = 0.0
        self.position = (0, 0)  # lat, lon
        self.groundspeed = 0
        self.vertical_speed = 0
        self.g_load = 1.0


class SimulatedValue(object):
    """
    Flucutates a value.
    """

    def direction(self):
        """
        Gets the direction of movement.
        """
        if self.__direction__ > 0.0:
            return 1.0

        return -1.0

    def simulate(self):
        """
        Changes the value.
        """
        current_time = datetime.datetime.now()
        self.__dt__ = (current_time - self.__last_sim__).total_seconds()
        self.__last_sim__ = current_time
        self.value += self.direction() * self.__rate__ * self.__dt__

        upper_limit = math.fabs(self.__limit__)
        lower_limit = 0 - upper_limit

        if self.direction() > 0.0 and self.value > upper_limit:
            self.__direction__ = -1.0
            self.value = upper_limit
        elif self.direction() < 0.0 and self.value < lower_limit:
            self.__direction__ = 1.0
            self.value = lower_limit

        return self.__offset__ + self.value

    def __init__(self, rate, limit, initial_direction, initial_value=0.0, offset=0.0):
        self.__rate__ = rate
        self.__limit__ = limit
        self.__direction__ = initial_direction
        self.__offset__ = offset
        self.value = initial_value
        self.__dt__ = 1.0 / configuration.MAX_FRAMERATE
        self.__last_sim__ = datetime.datetime.now()


class AhrsSimulation(object):
    """
    Class to simulate the AHRS data.
    """

    def simulate(self):
        """
        Ticks the simulated data.
        """
        self.ahrs_data.pitch = self.pitch_simulator.simulate()
        self.ahrs_data.roll = self.roll_simulator.simulate()
        self.ahrs_data.compass_heading = self.yaw_simulator.simulate()
        self.ahrs_data.gps_heading = self.ahrs_data.compass_heading
        self.ahrs_data.airspeed = self.speed_simulator.simulate()
        self.ahrs_data.alt = self.alt_simulator.simulate()

    def update(self):
        """
        Updates the simulation and serves as the interface for the
        the AHRS/Simulation/Other sourcing
        """

        self.simulate()

    def __init__(self):
        self.ahrs_data = AhrsData()
        self.data_source_available = True

        self.pitch_simulator = SimulatedValue(1, 30, -1)
        self.roll_simulator = SimulatedValue(5, 60, 1)
        self.yaw_simulator = SimulatedValue(5, 60, 1)
        self.speed_simulator = SimulatedValue(5, 10, 1, 85)
        self.alt_simulator = SimulatedValue(10, 300, -1, 2500)

        self.capabilities = StratuxCapabilities(None, None, True)


class AhrsStratux(object):
    """
    Class to pull actual AHRS data from a Stratux (or Stratus)
    """

    def __get_value__(self, ahrs_json, key, default):
        """
        Safely return the value from the AHRS blob
        
        Arguments:
            ahrs_json {[type]} -- [description]
            key {[type]} -- [description]
            default {[type]} -- [description]
        
        Returns:
            [type] -- [description]
        """

        if key in ahrs_json:
            try:
                return ahrs_json[key]
            except:
                return default
        
        return default
    
    def __get_value_with_fallback__(self, ahrs_json, keys, default):
        if keys is None:
            return default
                
        for key in keys:
            value = self.__get_value__(ahrs_json, key, default)

            if value is not default:
                return value
        
        return default


    def update(self):
        """
        Grabs the AHRS (if available)
        """

        new_ahrs_data = AhrsData()

        #try:
        url = "http://{0}/getSituation".format(
            self.__configuration__.stratux_address())

        try:
            ahrs_json = self.__stratux_session__.get(url, timeout=2).json()
        except:
            print "Issues decoding json"

            return

        new_ahrs_data.roll = self.__get_value__(ahrs_json, 'AHRSRoll', 0.0)
        new_ahrs_data.pitch = self.__get_value__(ahrs_json, 'AHRSPitch', 0.0)
        new_ahrs_data.compass_heading = self.__get_value__(ahrs_json, 'AHRSGyroHeading', 0.0) / 1000.0 #'AHRSMagHeading', 0.0) / 10.0
        #with_fallback__(ahrs_json, ['AHRSGyroHeading', 'AHRSMagHeading'], 0.0)
        new_ahrs_data.gps_heading = self.__get_value__(ahrs_json, 'GPSTrueCourse', 0.0)
        new_ahrs_data.alt = self.__get_value_with_fallback__(ahrs_json, ['GPSAltitudeMSL', 'BaroPressureAltitude'], None)
        new_ahrs_data.position = (
            ahrs_json['GPSLatitude'], ahrs_json['GPSLongitude'])
        new_ahrs_data.vertical_speed = self.__get_value__(ahrs_json, 'GPSVerticalSpeed', 0.0)
        new_ahrs_data.groundspeed = self.__get_value__(ahrs_json, 'GPSGroundSpeed', 0.0)
        new_ahrs_data.g_load = self.__get_value__(ahrs_json, 'AHRSGLoad', 1.0)
        self.data_source_available = True
        #except:
        #    self.data_source_available = False

        self.__set_ahrs_data__(new_ahrs_data)

        # SAMPLE FULL JSON
        #
        # {u'GPSAltitudeMSL': 68.041336,
        # u'GPSFixQuality': 1,
        #  u'AHRSGLoadMin': 0.3307450162084107
        #  u'GPSHorizontalAccuracy': 4.2,
        #  u'GPSLongitude': -122.36627,
        #  u'GPSGroundSpeed': 16.749273158117294,
        #  u'GPSLastFixLocalTime': u'0001-01-01T00:06:49.36Z',
        #  u'AHRSMagHeading': 3276.7,
        #  u'GPSSatellites': 7,
        #  u'GPSSatellitesTracked': 12,
        #  u'BaroPressureAltitude': -149.82413,
        #  u'GPSPositionSampleRate': 0,
        #  u'AHRSPitch': -1.6670512276023939,
        #  u'GPSSatellitesSeen': 12,
        #  u'GPSLastValidNMEAMessage': u'$PUBX,00,163529.60,4740.16729,N,12221.97653,W,1.939,G3,2.1,3.2,31.017,179.98,0.198,,1.93,2.43,1.89,7,0,0*4D',
        # u'AHRSSlipSkid': -25.030695817203796,
        #  u'GPSLastGPSTimeStratuxTime': u'0001-01-01T00:06:48.76Z',
        #  u'GPSLastFixSinceMidnightUTC': 59729.6,
        #  u'GPSLastValidNMEAMessageTime': u'0001-01-01T00:06:49.36Z',
        #  u'GPSNACp': 10,
        #  u'AHRSLastAttitudeTime': u'0001-01-01T00:06:49.4Z',
        #  u'GPSTurnRate': 0,
        #  u'AHRSTurnRate': -0.2607137769860283,
        #  u'GPSLastGroundTrackTime': u'0001-01-01T00:06:49.36Z',
        #  u'BaroVerticalSpeed': -11.46994,
        #  u'GPSTrueCourse': 179.98,
        #  u'BaroLastMeasurementTime': u'0001-01-01T00:06:49.4Z',
        #  u'GPSVerticalAccuracy': 6.4,
        #  u'AHRSGLoad': 0.8879934248943415,
        #  u'BaroTemperature': 30.09,
        #  u'AHRSGyroHeading': 184.67916154869323,
        #  u'AHRSRoll': 26.382463342051672,
        #  u'GPSGeoidSep': -61.67979,
        #  u'AHRSGLoadMax': 1.0895587458493998,
        #  u'GPSTime': u'2018-02-26T16:35:29Z',
        #  u'GPSVerticalSpeed': -0.6496063,
        #  u'GPSHeightAboveEllipsoid': 6.361549,
        #  u'GPSLatitude': 47.669456,
        #  u'AHRSStatus': 7}

    def __set_ahrs_data__(self, new_ahrs_data):
        """
        Atomically sets the AHRS data.
        """

        self.__lock__.acquire(True)

        self.ahrs_data = new_ahrs_data

        if new_ahrs_data.roll != None:
            if self.__configuration__.reverse_roll():
                self.ahrs_data.roll = 0.0 - new_ahrs_data.roll
            else:
                self.ahrs_data.roll = new_ahrs_data.roll

        if new_ahrs_data.pitch != None:
            if self.__configuration__.reverse_pitch():
                self.ahrs_data.pitch = 0.0 - new_ahrs_data.pitch
            else:
                self.ahrs_data.pitch = new_ahrs_data.pitch

        self.__lock__.release()

    def __update_capabilities__(self):
        """
        Check occassionally to see if the settings
        for the Stratux have been changed that would
        affect what we should show and what is actually
        available.
        """
        self.__lock__.acquire()
        self.capabilities = StratuxCapabilities(
            self.__configuration__.stratux_address(), self.__stratux_session__)
        self.__lock__.release()

    def __init__(self, configuration):
        self.__configuration__ = configuration

        self.__stratux_session__ = requests.Session()

        self.ahrs_data = AhrsData()
        self.data_source_available = False
        self.capabilities = StratuxCapabilities(
            self.__configuration__.stratux_address(), self.__stratux_session__)
        recurring_task.RecurringTask(
            'UpdateCapabilties', 15, self.__update_capabilities__)

        self.__lock__ = threading.Lock()


class Aircraft(object):
    def __init__(self):
        self.__configuration__ = configuration.Configuration(configuration.DEFAULT_CONFIG_FILE)
        self.ahrs_source = None

        if self.__configuration__.data_source() == configuration.DataSourceNames.STRATUX:
            self.ahrs_source = AhrsStratux(self.__configuration__)
        elif self.__configuration__.data_source() == configuration.DataSourceNames.SIMULATION:
            self.ahrs_source = AhrsSimulation()

        recurring_task.RecurringTask(
            'UpdateAhrs', 1.0 / (configuration.MAX_FRAMERATE * 2), self.update_orientation)

    def is_ahrs_available(self):
        """
        Returns True if the AHRS data is available
        """

        return self.ahrs_source is not None and self.ahrs_source.data_source_available

    def get_orientation(self):
        return self.ahrs_source.ahrs_data

    def update_orientation(self):
        if self.ahrs_source is not None:
            self.ahrs_source.update()


if __name__ == '__main__':
    plane = Aircraft()

    while True:
        plane.update_orientation()