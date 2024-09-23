from astropy.io import fits
from pyssata import global_precision
from pyssata import float_dtype_list
from pyssata import complex_dtype_list

class BaseTimeObj:
    def __init__(self, precision=None):
        """
        Creates a new base_time object.

        Parameters:
        precision (int, optional): if None will use the global_precision, otherwise pass 0 for double, 1 for single

        """
        self._time_resolution = int(1e9)
        self._generation_time = -1

        if precision is None:
            self._precision = global_precision
        else:
            self._precision = precision
        self.dtype = float_dtype_list[self._precision]
        self.complex_dtype = complex_dtype_list[self._precision]

    @property
    def generation_time(self):
        return self._generation_time

    @generation_time.setter
    def generation_time(self, value):
        self._generation_time = value

    @property
    def time_resolution(self):
        return self._time_resolution

    @time_resolution.setter
    def time_resolution(self, value):
        self._time_resolution = value

    @property
    def precision(self):
        return self._precision

    @precision.setter
    def precision(self, value):
        self._precision = value
        self.dtype = float_dtype_list[self._precision]
        self.complex_dtype = complex_dtype_list[self._precision]


    def t_to_seconds(self, t):
        return float(t) / float(self._time_resolution)

    def seconds_to_t(self, seconds):
        if self._time_resolution == 0:
            return 0

        ss = f"{float(seconds):.9f}".rstrip('0').rstrip('.')
        if '.' not in ss:
            ss += '.0'

        dotpos = ss.find('.')
        intpart = ss[:dotpos]
        fracpart = ss[dotpos + 1:]

        return (int(intpart) * self._time_resolution +
                int(fracpart) * (self._time_resolution // (10 ** len(fracpart))))

    def save(self, filename):
        hdr = fits.Header()
        hdr['GEN_TIME'] = self._generation_time
        hdr['TIME_RES'] = self._time_resolution

        primary_hdu = fits.PrimaryHDU(header=hdr)
        hdul = fits.HDUList([primary_hdu])
        hdul.writeto(filename, overwrite=True)

    def read(self, filename):
        with fits.open(filename) as hdul:
            hdr = hdul[0].header
            self._generation_time = int(hdr.get('GEN_TIME', 0))
            self._time_resolution = int(hdr.get('TIME_RES', 0))

    def get_properties_list(self):
        return vars(self)

