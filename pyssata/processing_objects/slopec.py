import numpy as np
from dataclasses import dataclass, field

@dataclass
class Slopec(BaseProcessingObj):
    _pixels: any = field(default_factory=lambda: None)
    _slopes: any = field(default_factory=lambda: None)
    _slopes_ave: any = field(default_factory=lambda: None)
    _sn: any = field(default_factory=lambda: None)
    _cm: any = field(default_factory=lambda: None)
    _total_counts: any = field(default_factory=lambda: None)
    _subap_counts: any = field(default_factory=lambda: None)
    _flux_per_subaperture_vector: any = field(default_factory=lambda: None)
    _max_flux_per_subaperture_vector: any = field(default_factory=lambda: None)
    _use_sn: bool = False
    _accumulate: bool = False
    _weight_from_accumulated: bool = False
    _weight_from_acc_with_window: bool = False
    _remove_mean: bool = False
    _return0: bool = False
    _update_slope_high_speed: bool = False
    _do_rec: bool = False
    _do_filter_modes: bool = False
    _gain_slope_high_speed: float = 0.0
    _ff_slope_high_speed: float = 0.0
    _store_s: any = field(default_factory=lambda: None)
    _store_c: any = field(default_factory=lambda: None)
    _sn_scale_fact: any = field(default_factory=lambda: None)
    _command_list: any = field(default_factory=lambda: None)
    _intmat: any = field(default_factory=lambda: None)
    _recmat: any = field(default_factory=lambda: None)
    _filt_recmat: any = field(default_factory=lambda: None)
    _filt_intmat: any = field(default_factory=lambda: None)
    _accumulation_dt: int = 0
    _accumulated_pixels: any = field(default_factory=lambda: None)
    _accumulated_pixels_ptr: any = field(default_factory=lambda: None)
    _accumulated_slopes: any = field(default_factory=lambda: None)

    def __post_init__(self):
        super().__post_init__()
        self._slopes = Slopes(2)
        self._accumulated_slopes = Slopes(2)
        self._slopes_ave = BaseValue()
        self._use_sn = 1
        self._flux_per_subaperture_vector = BaseValue()
        self._max_flux_per_subaperture_vector = BaseValue()

    @property
    def in_pixels(self):
        return self._pixels

    @in_pixels.setter
    def in_pixels(self, value):
        self._pixels = value

    @property
    def in_sn(self):
        return self._sn

    @in_sn.setter
    def in_sn(self, value):
        self._sn = value

    @property
    def use_sn(self):
        return self._use_sn

    @use_sn.setter
    def use_sn(self, value):
        self._use_sn = value

    @property
    def sn_tag(self):
        return self._sn_tag

    @sn_tag.setter
    def sn_tag(self, value):
        self.load_sn(value)

    @property
    def cm(self):
        return self._cm

    @cm.setter
    def cm(self, value):
        self._cm = value

    @property
    def weight_from_accumulated(self):
        return self._weight_from_accumulated

    @weight_from_accumulated.setter
    def weight_from_accumulated(self, value):
        self._weight_from_accumulated = value

    @property
    def weight_from_acc_with_window(self):
        return self._weight_from_acc_with_window

    @weight_from_acc_with_window.setter
    def weight_from_acc_with_window(self, value):
        self._weight_from_acc_with_window = value

    @property
    def accumulate(self):
        return self._accumulate

    @accumulate.setter
    def accumulate(self, value):
        self._accumulate = value

    @property
    def accumulation_dt(self):
        return self._accumulation_dt

    @accumulation_dt.setter
    def accumulation_dt(self, value):
        self._accumulation_dt = self.seconds_to_t(value)

    @property
    def remove_mean(self):
        return self._remove_mean

    @remove_mean.setter
    def remove_mean(self, value):
        self._remove_mean = value

    @property
    def return0(self):
        return self._return0

    @return0.setter
    def return0(self, value):
        self._return0 = value

    @property
    def update_slope_high_speed(self):
        return self._update_slope_high_speed

    @update_slope_high_speed.setter
    def update_slope_high_speed(self, value):
        self._update_slope_high_speed = value

    @property
    def command_list(self):
        return self._command_list

    @command_list.setter
    def command_list(self, value):
        self._command_list = value

    @property
    def intmat(self):
        return self._intmat

    @intmat.setter
    def intmat(self, value):
        self._intmat = value

    @property
    def recmat(self):
        return self._recmat

    @recmat.setter
    def recmat(self, value):
        self._recmat = value

    @property
    def gain_slope_high_speed(self):
        return self._gain_slope_high_speed

    @gain_slope_high_speed.setter
    def gain_slope_high_speed(self, value):
        self._gain_slope_high_speed = value

    @property
    def ff_slope_high_speed(self):
        return self._ff_slope_high_speed

    @ff_slope_high_speed.setter
    def ff_slope_high_speed(self, value):
        self._ff_slope_high_speed = value

    @property
    def do_rec(self):
        return self._do_rec

    @do_rec.setter
    def do_rec(self, value):
        self._do_rec = value

    @property
    def filtmat(self):
        return self._filtmat

    @filtmat.setter
    def filtmat(self, value):
        self.set_filtmat(value)

    @property
    def in_sn_scale_fact(self):
        return self._sn_scale_fact

    @in_sn_scale_fact.setter
    def in_sn_scale_fact(self, value):
        self._sn_scale_fact = value

    def set_filtmat(self, filtmat):
        self._filt_intmat = filtmat[:, :, 0]
        self._filt_recmat = np.transpose(filtmat[:, :, 1])
        self._do_filter_modes = True

    def remove_filtmat(self):
        self._filt_intmat = None
        self._filt_recmat = None
        self._do_filter_modes = False
        print('doFilterModes set to 0')

    def build_and_save_filtmat(self, intmat, recmat, nmodes, filename):
        im = intmat[:nmodes, :]
        rm = recmat[:, :nmodes]

        output = np.stack((im, np.transpose(rm)), axis=-1)
        self.writefits(filename, output)
        print(f'saved {filename}')

    def _compute_flux_per_subaperture(self):
        raise NotImplementedError('abstract method must be implemented')

    def _compute_max_flux_per_subaperture(self):
        raise NotImplementedError('abstract method must be implemented')

    def run_check(self, time_step, errmsg=''):
        if self._use_sn and not self._sn:
            errmsg += 'Slopes null are not valid'
        if self._weight_from_accumulated and self._accumulate:
            errmsg += 'weightFromAccumulated and accumulate must not be set together'
        return not (self._weight_from_accumulated and self._accumulate) and self._pixels and self._slopes and ((not self._use_sn) or (self._use_sn and self._sn))

    def calc_slopes(self, t, accumulated=False):
        raise NotImplementedError(f'{self.repr()} Please implement calc_slopes in your derived class!')

    def load_sn(self, sn_tag):
        if self._verbose:
            print(f'reading {sn_tag}')
        sn = self._cm.read_slopenull(sn_tag)
        if sn is None:
            print(f'\nWARNING: slope null {sn_tag} is not present on disk!\n')
        else:
            self._sn = sn

    def revision_track(self):
        return '$Rev$'

    def do_accumulation(self, t):
        factor = float(self._loop_dt) / float(self._accumulation_dt)
        if not self._accumulated_pixels:
            self._accumulated_pixels = Pixels(self._pixels.size[0], self._pixels.size[1])
        if (t % self._accumulation_dt) == 0:
            self._accumulated_pixels.pixels = self._pixels.pixels * factor
        else:
            self._accumulated_pixels.pixels += self._pixels.pixels * factor
        self._accumulated_pixels_ptr = self._accumulated_pixels.pixels * (1 - factor) + self._pixels.pixels * factor
        if self._verbose:
            print(f'accumulation factor is: {factor}')
        self._accumulated_pixels.generation_time = t

    def cleanup(self):
        if self._store_s:
            del self._store_s
        if self._store_c:
            del self._store_c
        if self._intmat:
            del self._intmat
        if self._filt_recmat:
            del self._filt_recmat
        if self._filt_intmat:
            del self._filt_intmat
        if self._accumulated_pixels_ptr:
            del self._accumulated_pixels_ptr
        if self._total_counts:
            del self._total_counts
        if self._subap_counts:
            del self._subap_counts
        self._flux_per_subaperture_vector.cleanup()
        self._max_flux_per_subaperture_vector.cleanup()
        self._slopes.cleanup()
        self._accumulated_pixels.cleanup()
        self._accumulated_slopes.cleanup()

    def trigger(self, t):
        if self._accumulate:
            self.do_accumulation(t)
            if (t + self._loop_dt) % self._accumulation_dt == 0:
                self.calc_slopes(t, accumulated=True)

        if self._weight_from_accumulated:
            self.do_accumulation(t)

        if self._pixels.generation_time == t:
            self.calc_slopes(t)
            if np.isfinite(self._slopes.slopes).all():
                raise ValueError('slopes have non-finite elements')
            if self._sn and self._use_sn:
                if self._verbose:
                    print('removing slope null')
                if self._sn_scale_fact:
                    temp_sn = BaseValue()
                    if self._sn_scale_fact.generation_time >= 0:
                        temp_sn.value = self._sn.slopes * self._sn_scale_fact.value
                    else:
                        temp_sn.value = self._sn.slopes
                    if self._verbose:
                        print('ATTENTION: slope null scaled by a factor')
                        print(f' Value: {self._sn_scale_fact.value}')
                        print(f' Is it applied? {self._sn_scale_fact.generation_time >= 0}')
                    self._slopes.subtract(temp_sn)
                else:
                    self._slopes.subtract(self._sn)

            self._slopes_ave.value = [np.mean(self._slopes.xslopes), np.mean(self._slopes.yslopes)]
            self._slopes_ave.generation_time = t

            if self._remove_mean:
                sx = self._slopes.xslopes - self._slopes_ave.value[0]
                sy = self._slopes.yslopes - self._slopes_ave.value[1]
                self._slopes.xslopes = sx
                self._slopes.yslopes = sy
                if self._verbose:
                    print('mean value of x and y slope was removed')

        else:
            if self._return0:
                self._slopes.xslopes = np.zeros_like(self._slopes.xslopes)
                self._slopes.yslopes = np.zeros_like(self._slopes.yslopes)

        if self._update_slope_high_speed:
            if self._gain_slope_high_speed == 0.0:
                self._gain_slope_high_speed = 1.0
            if self._ff_slope_high_speed == 0.0:
                self._ff_slope_high_speed = 1.0
            commands = []
            for comm in self._command_list:
                if len(comm.value) > 0:
                    commands.append(comm.value)
            if self._pixels.generation_time == t:
                self._store_s = np.array([self._gain_slope_high_speed * self._slopes.xslopes, self._gain_slope_high_speed * self._slopes.yslopes])
                self._store_c = np.array(commands)
            else:
                if len(commands) > 0 and self._store_s is not None and self._store_c is not None:
                    temp = np.dot(np.array(commands) - self._store_c, self._intmat)
                    self._store_s *= self._ff_slope_high_speed
                    self._slopes.xslopes = self._store_s[0] - temp[:len(temp)//2]
                    self._slopes.yslopes = self._store_s[1] - temp[len(temp)//2:]
                    self._slopes.generation_time = t

        if self._do_filter_modes:
            m = np.dot(self._slopes.ptr_slopes, self._filt_recmat)
            sl0 = np.dot(m, self._filt_intmat)
            sl = self._slopes.slopes
            if len(sl) != len(sl0):
                raise ValueError(f'mode filtering goes wrong: original slopes size is: {len(sl)} while filtered slopes size is: {len(sl0)}')
            self._slopes.slopes -= sl0
            if self._verbose:
                print(f'Slopes have been filtered. New slopes min, max and rms : {np.min(self._slopes.slopes)}, {np.max(self._slopes.slopes)}  //  {np.sqrt(np.mean(self._slopes.slopes**2))}')
            if not np.isfinite(self._slopes.slopes).all():
                raise ValueError('slopes have non-finite elements')

        if self._do_rec:
            if has_gpu():
                m = np.dot(self._slopes.ptr_slopes, self._recmat.gpu_recmat)
            else:
                m = np.dot(self._slopes.ptr_slopes, self._recmat.ptr_recmat)
            self._slopes.slopes = m

    @staticmethod
    def make_xy(size, scale):
        return np.meshgrid(np.linspace(-scale, scale, size), np.linspace(-scale, scale, size))

    @staticmethod
    def minmax(array):
        return np.min(array), np.max(array)

    @staticmethod
    def zern(mode, xx, yy):
        return xx + yy

    @staticmethod
    def interpolate(image, x, y, grid=False, missing=0):
        return image

    @staticmethod
    def toccd(pup_pyr_tot, toccd_side):
        return pup_pyr_tot

    @staticmethod
    def make_mask(totsize, diaratio, obsratio=0):
        return np.ones((totsize, totsize))

    @staticmethod
    def ROT_AND_SHIFT_IMAGE(image, angle, shift, scale, use_interpolate=False):
        return image