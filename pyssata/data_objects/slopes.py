import numpy as np
from astropy.io import fits

class Slopes(BaseDataObj):
    def __init__(self, length=None, slopes=None, interleave=False):
        if slopes is not None:
            self._slopes = slopes
        else:
            self._slopes = np.zeros(length, dtype=float)

        self._interleave = interleave
        self._pupdata_tag = ''

        if not super().__init__("slopes", "Slopes object"):
            return

    @property
    def slopes(self):
        return self._slopes

    @slopes.setter
    def slopes(self, value):
        self._slopes = value

    @property
    def ptr_slopes(self):
        return self._slopes

    @property
    def size(self):
        return self._slopes.size

    @property
    def xslopes(self):
        return self._slopes[self.indx()]

    @xslopes.setter
    def xslopes(self, value):
        self._slopes[self.indx()] = value

    @property
    def yslopes(self):
        return self._slopes[self.indy()]

    @yslopes.setter
    def yslopes(self, value):
        self._slopes[self.indy()] = value

    @property
    def interleave(self):
        return self._interleave

    @interleave.setter
    def interleave(self, value):
        self._interleave = value

    @property
    def pupdata_tag(self):
        return self._pupdata_tag

    @pupdata_tag.setter
    def pupdata_tag(self, value):
        self._pupdata_tag = value

    def indx(self):
        if self._interleave:
            return np.arange(0, self.size // 2) * 2
        else:
            return np.arange(0, self.size // 2)

    def indy(self):
        if self._interleave:
            return self.indx() + 1
        else:
            return self.indx() + self.size // 2

    def sum(self, s2, factor):
        self._slopes += s2.slopes * factor

    def subtract(self, s2):
        if isinstance(s2, Slopes):
            if s2.slopes.size > 0:
                self._slopes -= s2.slopes
            else:
                print('WARNING (slopes object): s2 (slopes) is empty!')
        elif isinstance(s2, BaseValue):  # Assuming BaseValue is another class
            if s2.value.size > 0:
                self._slopes -= s2.value
            else:
                print('WARNING (slopes object): s2 (base_value) is empty!')

    def x_remap2d(self, frame, idx):
        frame[idx] = self._slopes[self.indx()]

    def y_remap2d(self, frame, idx):
        frame[idx] = self._slopes[self.indy()]

    def get2d(self, cm, pupdata=None):
        if pupdata is None:
            pupdata = cm.read_pupils(self._pupdata_tag)
        mask = pupdata.single_mask()
        idx = np.where(mask)
        fx = np.zeros_like(mask, dtype=float)
        fy = np.zeros_like(mask, dtype=float)
        self.x_remap2d(fx, idx)
        self.y_remap2d(fy, idx)
        fx = fx[:fx.shape[0] // 2, fx.shape[1] // 2:]
        fy = fy[:fy.shape[0] // 2, fy.shape[1] // 2:]
        return np.array([fx, fy])

    def rotate(self, angle, flipx=False, flipy=False):
        sx = self.xslopes
        sy = self.yslopes
        alpha = np.arctan2(sy, sx) + np.radians(angle)
        modulus = np.sqrt(sx**2 + sy**2)
        signx = -1 if flipx else 1
        signy = -1 if flipy else 1
        self.xslopes = np.cos(alpha) * modulus * signx
        self.yslopes = np.sin(alpha) * modulus * signy

    def save(self, filename, hdr=None):
        if hdr is None:
            hdr = fits.Header()
        hdr['VERSION'] = 2
        hdr['INTRLVD'] = int(self._interleave)
        hdr['PUPD_TAG'] = self._pupdata_tag

        super().save(filename, hdr)
        fits.append(filename, self._slopes)

    def read(self, filename, hdr=None, exten=0):
        super().read(filename, hdr, exten)
        self._slopes = fits.getdata(filename, ext=exten)
        exten += 1

    @staticmethod
    def restore(filename):
        hdr = fits.getheader(filename)
        version = int(hdr['VERSION'])

        if version > 2:
            raise ValueError(f"Error: unknown version {version} in file {filename}")

        s = Slopes(length=1)
        s.interleave = bool(hdr['INTRLVD'])
        if version >= 2:
            s.pupdata_tag = str(hdr['PUPD_TAG']).strip()
        s.read(filename, hdr)
        return s

    def revision_track(self):
        return '$Rev$'

    def cleanup(self):
        self._slopes = None
        super().cleanup()