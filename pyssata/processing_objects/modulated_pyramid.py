import numpy as np
from pyssata import cp, cpuArray

from pyssata.base_processing_obj import BaseProcessingObj
from pyssata.base_value import BaseValue
from pyssata.connections import InputValue
from pyssata.data_objects.ef import ElectricField
from pyssata.lib.make_xy import make_xy
from pyssata.data_objects.intensity import Intensity
from pyssata.lib.make_mask import make_mask
from pyssata.lib.toccd import toccd

# from cupyx.scipy.fft import get_fft_plan
# import cupyx.scipy.fft

@cp.fuse(kernel_name='pyr1_fused')
def pyr1_fused(u_fp, ffv, myexp, fp_mask):
    psf = cp.real(u_fp * cp.conj(u_fp))
    fpsf = psf * ffv
    u_fp *= fp_mask
    u_fp_pyr = u_fp * myexp
    return u_fp_pyr, fpsf                                                
            
class ModulatedPyramid(BaseProcessingObj):
    def __init__(self,
                 pixel_pupil: int,
                 pixel_pitch: float,
                 wavelengthInNm: float,
                 fov: float,
                 pup_diam: int,
                 output_resolution: int,
                 mod_amp: float = 3.0,
                 mod_step: int = None,
                 fov_errinf: float = 0.5,
                 fov_errsup: float = 2,
                 pup_dist: int = None,
                 pup_margin: int = 2,
                 fft_res: float = 3.0,
                 fp_obs: float = None,
                 pup_shifts = (0.0, 0.0),
                 pyr_tlt_coeff: float = None,
                 pyr_edge_def_ld: float = 0.0,
                 pyr_tip_def_ld: float = 0.0,
                 pyr_tip_maya_ld: float = 0.0,
                 min_pup_dist: float = None,                 
                 target_device_idx: int = None, 
                 precision: int = None
                ):
        super().__init__(target_device_idx=target_device_idx, precision=precision)        

        DpupPix = pixel_pupil
        FoV = fov
        ccd_side = output_resolution        
        result = self.calc_geometry(DpupPix, pixel_pitch, wavelengthInNm, FoV, pup_diam, ccd_side,
                                            fov_errinf=fov_errinf, fov_errsup=fov_errsup, pup_dist=pup_dist, pup_margin=pup_margin,
                                            fft_res=fft_res, min_pup_dist=min_pup_dist)

        wavelengthInNm = result['wavelengthInNm']
        fov_res = result['fov_res']
        fp_masking = result['fp_masking']
        fft_res = result['fft_res']
        tilt_scale = result['tilt_scale']
        fft_sampling = result['fft_sampling']
        fft_padding = result['fft_padding']
        fft_totsize = result['fft_totsize']
        toccd_side = result['toccd_side']
        final_ccd_side = result['final_ccd_side']

        # Compute focal plane central obstruction dimension ratio                 
        fp_obsratio = fp_obs / (fft_totsize / fft_res) if fp_obs is not None else 0

        self._wavelength_in_nm = wavelengthInNm
        self._fov_res = fov_res
        self._fp_masking = fp_masking
        self._fp_obsratio = fp_obsratio
        self._fft_res = fft_res
        self._tilt_scale = tilt_scale
        self._fft_sampling = fft_sampling
        self._fft_padding = int(fft_padding)
        self._fft_totsize = int(cpuArray(fft_totsize))
        self._toccd_side = toccd_side
        self._final_ccd_side = final_ccd_side
        self._pyr_tlt_coeff = pyr_tlt_coeff
        self._pyr_edge_def_ld = pyr_edge_def_ld
        self._pyr_tip_def_ld = pyr_tip_def_ld
        self._pyr_tip_maya_ld = pyr_tip_maya_ld
        self._rotAnglePhInDeg = 0
        self._pup_shifts = pup_shifts

        if not all([fft_res, fov_res, tilt_scale, fft_sampling, fft_totsize, toccd_side, final_ccd_side]):
            raise Exception('Not all geometry settings have been calculated')

        min_mod_step = round(max([1., mod_amp / 2. * 8.])) * 2.
        if mod_step is None:
            mod_step = min_mod_step
        else:
            if mod_step < min_mod_step:
                print(f' Attention mod_step={mod_step} is too low!')
                print(f' Would you like to change it to {min_mod_step}? [y,n]')
                ans = input()
                if ans.lower() == 'y':
                    print(' mod_step changed.')
                    mod_step = min_mod_step

        fft_totsize = int(fft_totsize)
        
        self._out_i = Intensity(final_ccd_side, final_ccd_side, precision=self.precision, target_device_idx=self._target_device_idx)
        self._psf_tot = BaseValue(self.xp.zeros((fft_totsize, fft_totsize), dtype=self.dtype), target_device_idx=self._target_device_idx)
        self._psf_bfm = BaseValue(self.xp.zeros((fft_totsize, fft_totsize), dtype=self.dtype), target_device_idx=self._target_device_idx)
        self._out_transmission = BaseValue(0, target_device_idx=self._target_device_idx)

        self.inputs['in_ef'] = InputValue(type=ElectricField)
        self.outputs['out_i'] = self.out_i
        self.outputs['out_psf_tot'] = self._psf_tot
        self.outputs['out_psf_bfm'] = self._psf_bfm
        self.outputs['out_transmission'] = self._out_transmission

        self._pyr_tlt = self.get_pyr_tlt(fft_sampling, fft_padding)
        self._tlt_f = self.get_tlt_f(fft_sampling, fft_padding)
        self._tilt_x = self.get_modulation_tilt(fft_sampling, X=True)
        self._tilt_y = self.get_modulation_tilt(fft_sampling, Y=True)
        self._fp_mask = self.get_fp_mask(fft_totsize, fp_masking, obsratio=fp_obsratio)
        self._extended_source_in_on = False
        iu = 1j  # complex unit
        self._myexp = self.xp.exp(-2 * self.xp.pi * iu * self._pyr_tlt, dtype=self.complex_dtype)

        # Pre-computation of ttexp will be done when mod_steps will be set or re-set
        if int(mod_step) != mod_step:
            raise ValueError('Modulation step number is not an integer')

        self._mod_amp = mod_amp
        self._mod_steps = int(mod_step)
        self._ttexp = None
        self.cache_ttexp()

    @property
    def mod_amp(self):
        return self._mod_amp

    @mod_amp.setter
    def mod_amp(self, value):
        if value != self._mod_amp:
            self._mod_amp = value
            self.cache_ttexp()

    @property
    def mod_steps(self):
        return self._mod_steps

    @mod_steps.setter
    def mod_steps(self, value):
        if value != self._mod_steps:
            self._mod_steps = value
            self.cache_ttexp()

    @property
    def fp_masking(self):
        return self._fp_masking

    @fp_masking.setter
    def fp_masking(self, value):
        self._fp_masking = value

    @property
    def pup_shifts(self):
        return self._pup_shifts

    @pup_shifts.setter
    def pup_shifts(self, value):
        self._pup_shifts = value

    @property
    def ext_source_psf(self):
        return self._extSourcePsf

    @ext_source_psf.setter
    def ext_source_psf(self, value):
        self._extSourcePsf = value

    @property
    def rot_angle_ph_in_deg(self):
        return self._rotAnglePhInDeg

    @rot_angle_ph_in_deg.setter
    def rot_angle_ph_in_deg(self, value):
        self._rotAnglePhInDeg = value

    @property
    def out_i(self):
        return self._out_i

    def calc_geometry(self,
        DpupPix,                # number of pixels of input phase array
        pixel_pitch,            # pixel sampling [m] of DpupPix
        lambda_,                # working lambda of the sensor [nm]
        FoV,                    # requested FoV in arcsec
        pup_diam,               # pupil diameter in subapertures
        ccd_side,               # requested output ccd side, in pixels
        fov_errinf=0.1,         # accepted error in reducing FoV, default = 0.1 (-10%)
        fov_errsup=0.5,         # accepted error in enlarging FoV, default = 0.5 (+50%)
        pup_dist=None,          # pupil distance in subapertures, optional
        pup_margin=2,           # zone of respect around pupils for margins, optional, default=2px
        fft_res=3.0,            # requested minimum PSF sampling, 1.0 = 1 pixel / PSF, default=3.0
        min_pup_dist=None,
        NOTEST=False            # skip the time estimation done with a test pyramid
    ):
        # Calculate pup_distance if not given, using the pup_margin
        if pup_dist is None:
            pup_dist = pup_diam + pup_margin * 2

        if min_pup_dist is None:
            min_pup_dist = pup_diam + pup_margin * 2

        if pup_dist < min_pup_dist:
            print(f"Error: pup_dist (px) = {pup_dist} is not enough to hold the pupil geometry. Minimum allowed distance is {min_pup_dist}")
            return 0

        min_ccd_side = pup_dist + pup_diam + pup_margin * 2
        if ccd_side < min_ccd_side:
            print(f"Error: ccd_side (px) = {ccd_side} is not enough to hold the pupil geometry. Minimum allowed side is {min_ccd_side}")
            return 0

        RAD2ARCSEC = 206265
        D = DpupPix * pixel_pitch
        Fov_internal = lambda_ * 1e-9 / D * (D / pixel_pitch) * RAD2ARCSEC

        minfov = FoV * (1 - fov_errinf)
        maxfov = FoV * (1 + fov_errsup)
        fov_res = 1.0

        if Fov_internal < minfov:
            fov_res = int(minfov / Fov_internal)
            if Fov_internal * fov_res < minfov:
                fov_res += 1

        if Fov_internal > maxfov:
            print("Error: Calculated FoV is higher than maximum accepted FoV.")
            print("Please revise error margin, or the input phase dimension and/or pitch")
            return 0

        if fov_res > 1:
            Fov_internal *= fov_res
            print(f"Interpolated FoV (arcsec): {Fov_internal:.2f}")
            print(f"Warning: reaching the requested FoV requires {fov_res}x interpolation of input phase array.")
            print("Consider revising the input phase dimension and/or pitch to improve performance.")

        fp_masking = FoV / Fov_internal

        if Fov_internal != FoV:
            print(f"FoV reduction from {Fov_internal:.2f} to {FoV:.2f} will be performed with a focal plane mask")

        DpupPixFov = DpupPix * fov_res
        pitch_internal = pixel_pitch / fov_res

        fft_res_min = (pup_dist + pup_diam) / pup_diam * 1.1
        if fft_res < fft_res_min:
            fft_res = fft_res_min

        internal_ccd_side = self.xp.around(fft_res * pup_diam / 2) * 2
        fft_res = internal_ccd_side / float(pup_diam)

        totsize = self.xp.around(DpupPixFov * fft_res / 2) * 2
        fft_res = totsize / float(DpupPixFov)

        padding = self.xp.around((DpupPixFov * fft_res - DpupPixFov) / 2) * 2

        results = {
            'fov_res': fov_res,
            'fp_masking': fp_masking,
            'fft_res': fft_res,
            'tilt_scale': fft_res / ((pup_dist / float(pup_diam)) / 2.0),
            'fft_sampling': DpupPixFov,
            'fft_padding': padding,
            'fft_totsize': totsize,
            'wavelengthInNm': lambda_,
            'toccd_side': internal_ccd_side,
            'final_ccd_side': ccd_side
        }

        return results

    def set_extended_source(self, source):
        self._extSource = source
        self._extended_source_in_on = True

        self._ext_xtilt = self.zern(2, make_xy(self._fft_sampling, 1.0), xp=self.xp)
        self._ext_ytilt = self.zern(3, make_xy(self._fft_sampling, 1.0), xp=self.xp)
        self._ext_focus = self.zern(4, make_xy(self._fft_sampling, 1.0), xp=self.xp)

        if source.npoints == 0:
            raise ValueError('ERROR: number of points of extended source is 0!')
        else:
            self._mod_steps = source.npoints

        del self._ttexp

        print(f'modulated_pyramid --> Setting up extended source with {self._mod_steps} points')

        if self._mod_steps <= 0:
            return

        iu = 1j  # complex unit
        
        self._ttexp = self.xp.ndarray(shape=(self._tilt_x.shape[0], self._tilt_x.shape[1], self._mod_steps), dtype=self.complex_dtype)

        for tt in range(self._mod_steps):
            angle = 2 * self.xp.pi * (tt / self._mod_steps)
            pup_tt = source.coeff_tiltx[tt] * self._ext_xtilt + source.coeff_tilty[tt] * self._ext_ytilt
            pup_focus = -1 * source.coeff_focus[tt] * self._ext_focus
            self._ttexp[:, :, tt] = self.xp.exp(-iu * (pup_tt + pup_focus))

        i = source.coeff_flux
        idx = self.xp.where(self.xp.abs(i) < self.xp.max(self.xp.abs(i)) * 1e-5)[0]
        if len(idx[0]) > 0:
            i[idx] = 0
        self._flux_factor_vector = i

    def get_pyr_tlt(self, p, c):
        A = int((p + c) // 2)
        pyr_tlt = self.xp.zeros((2 * A, 2 * A), dtype=self.dtype)
        #tlt_basis = self.xp.tile(self.xp.arange(A), (A, 1))
        y, x = self.xp.mgrid[0:A,0:A]

        if self._pyr_tlt_coeff is not None:
            k = self._pyr_tlt_coeff

            tlt_basis -= self.xp.mean(tlt_basis)

            pyr_tlt[0:A, 0:A] = k[0, 0] * tlt_basis + k[1, 0] * tlt_basis.T
            pyr_tlt[A:2*A, 0:A] = k[0, 1] * tlt_basis + k[1, 1] * tlt_basis.T
            pyr_tlt[A:2*A, A:2*A] = k[0, 2] * tlt_basis + k[1, 2] * tlt_basis.T
            pyr_tlt[0:A, A:2*A] = k[0, 3] * tlt_basis + k[1, 3] * tlt_basis.T
            pyr_tlt[0:A, 0:A] -= self.xp.min(pyr_tlt[0:A, 0:A])
            pyr_tlt[A:2*A, 0:A] -= self.xp.min(pyr_tlt[A:2*A, 0:A])
            pyr_tlt[A:2*A, A:2*A] -= self.xp.min(pyr_tlt[A:2*A, A:2*A])
            pyr_tlt[0:A, A:2*A] -= self.xp.min(pyr_tlt[0:A, A:2*A])

        else:
            #pyr_tlt[0:A, 0:A] = tlt_basis + tlt_basis.T
            #pyr_tlt[A:2*A, 0:A] = A - 1 - tlt_basis + tlt_basis.T
            #pyr_tlt[A:2*A, A:2*A] = 2 * A - 2 - tlt_basis - tlt_basis.T
            #pyr_tlt[0:A, A:2*A] = A - 1 + tlt_basis - tlt_basis.T
            pyr_tlt[:A, :A] = x + y
            pyr_tlt[:A, A:] = x[:,::-1] + y
            pyr_tlt[A:, :A] = x + y[::-1]
            pyr_tlt[A:, A:] = x[:,::-1] + y[::-1]

        xx, yy = make_xy(A * 2, A, xp=self.xp)

        # distance from edge
        dx = self.xp.sqrt(xx ** 2)
        dy = self.xp.sqrt(yy ** 2)
        idx_edge = self.xp.where((dx <= self._pyr_edge_def_ld * self._fft_res / 2) | 
                            (dy <= self._pyr_edge_def_ld * self._fft_res / 2))[0]
        if len(idx_edge) > 0:
            pyr_tlt[idx_edge] = self.xp.max(pyr_tlt) * self.xp.random.rand(len(idx_edge[0]))
            print(f'get_pyr_tlt: {len(idx_edge[0])} pixels set to 0 to consider pyramid imperfect edges')

        # distance from tip
        d = self.xp.sqrt(xx ** 2 + yy ** 2)
        idx_tip = self.xp.where(d <= self._pyr_tip_def_ld * self._fft_res / 2)[0]
        if len(idx_tip) > 0:
            pyr_tlt[idx_tip] = self.xp.max(pyr_tlt) * self.xp.random.rand(len(idx_tip[0]))
            print(f'get_pyr_tlt: {len(idx_tip[0])} pixels set to 0 to consider pyramid imperfect tip')

        # distance from tip
        idx_tip_m = self.xp.where(d <= self._pyr_tip_maya_ld * self._fft_res / 2)[0]
        if len(idx_tip_m) > 0:
            pyr_tlt[idx_tip_m] = self.xp.min(pyr_tlt[idx_tip_m])
            print(f'get_pyr_tlt: {len(idx_tip_m[0])} pixels set to 0 to consider pyramid imperfect tip')

        return pyr_tlt / self._tilt_scale

    def get_tlt_f(self, p, c):
        iu = 1j  # complex unit
        p = int(p)
        xx, yy = make_xy(2 * p, p, quarter=True, zero_sampled=True, xp=self.xp)
        tlt_g = xx + yy

        tlt_f = self.xp.exp(-2 * self.xp.pi * iu * tlt_g / (2 * (p + c)))
        return tlt_f

    def get_fp_mask(self, totsize, mask_ratio, obsratio=0):
        return make_mask(totsize, diaratio=mask_ratio, obsratio=obsratio, xp=self.xp)

    def get_modulation_tilt(self, p, X=False, Y=False):
        p = int(p)
        xx, yy = make_xy(p, p // 2, xp=self.xp)
        mm = self.minmax(xx)
        tilt_x = xx * self.xp.pi / ((mm[1] - mm[0]) / 2)
        tilt_y = yy * self.xp.pi / ((mm[1] - mm[0]) / 2)

        if X:
            return tilt_x
        if Y:
            return tilt_y

    def cache_ttexp(self):
        if not self._extended_source_in_on:
            del self._ttexp
            if self._mod_steps <= 0:
                return

            iu = 1j  # complex unit

            self._ttexp = self.xp.ndarray(shape=(self._tilt_x.shape[0], self._tilt_x.shape[1], self._mod_steps), dtype=self.complex_dtype)
            for tt in range(self._mod_steps):
                angle = 2 * self.xp.pi * (tt / self._mod_steps)
                pup_tt = self._mod_amp * self.xp.sin(angle) * self._tilt_x + \
                         self._mod_amp * self.xp.cos(angle) * self._tilt_y
                self._ttexp[:, :, tt] = self.xp.exp(-iu * pup_tt, dtype=self.complex_dtype)

            self._flux_factor_vector = self.xp.ones(self._mod_steps, dtype=self.dtype)

    def trigger(self, t):
        in_ef = self.inputs['in_ef'].get(self._target_device_idx)
        if in_ef.generation_time != t:
            return

        if self._extended_source_in_on and self._extSourcePsf is not None:
            if self._extSourcePsf.generation_time == t:
                if self.xp.sum(self.xp.abs(self._extSourcePsf.value)) > 0:
                    self._extSource.updatePsf(self._extSourcePsf.value)
                    self._flux_factor_vector = self._extSource.coeff_flux

        s = in_ef.size

        if self._rotAnglePhInDeg != 0:
            A = (self.ROT_AND_SHIFT_IMAGE(in_ef.A, self._rotAnglePhInDeg, [0, 0], 1, use_interpolate=True) >= 0.5).astype(self.xp.uint8)
            phi_at_lambda = self.ROT_AND_SHIFT_IMAGE(in_ef.phi_at_lambda(self._wavelength_in_nm), self._rotAnglePhInDeg, [0, 0], 1, use_interpolate=True)
            ef = self.xp.complex64(self.xp.rebin(A, (s[0] * self._fov_res, s[1] * self._fov_res)) + 
                              self.xp.rebin(phi_at_lambda, (s[0] * self._fov_res, s[1] * self._fov_res)) * 1j)
        else:
            if self._fov_res != 1:
                ef = self.xp.complex64(self.xp.rebin(in_ef.A, (s[0] * self._fov_res, s[1] * self._fov_res)) + 
                                  self.xp.rebin(in_ef.phi_at_lambda(self._wavelength_in_nm), (s[0] * self._fov_res, s[1] * self._fov_res)) * 1j)
            else:
                ef = in_ef.ef_at_lambda(self._wavelength_in_nm)

        u_tlt_const = ef * self._tlt_f

        pup_pyr_tot = self.xp.zeros((self._fft_totsize, self._fft_totsize), dtype=self.dtype)
        psf_bfm = self.xp.zeros((self._fft_totsize, self._fft_totsize), dtype=self.dtype)
        psf_tot = self.xp.zeros((self._fft_totsize, self._fft_totsize), dtype=self.dtype)

        u_tlt = self.xp.zeros((self._fft_totsize, self._fft_totsize, self.mod_steps), dtype=self.complex_dtype)
        
        mean_value = self.xp.median(self._flux_factor_vector) * 1e-3
        fp_mask = self._fp_mask[:,:, self.xp.newaxis]
        my_exp = self._myexp[:,:, self.xp.newaxis]

        #plan1 = get_fft_plan(u_tlt, axes=(0, 1), value_type='C2C')            
        #plan2 = get_fft_plan(u_tlt, axes=(0, 1), value_type='C2C')            
        ffv = self.xp.where(self._flux_factor_vector > mean_value, self._flux_factor_vector, 0)
        tmp = self.xp.repeat(u_tlt_const[:, :, self.xp.newaxis], ffv.shape[0], axis=2)            
        tmp = tmp * self._ttexp
        ss = tmp.shape
        u_tlt[0:ss[0], 0:ss[1], :] = tmp
        #with plan1:
        u_fp = self.xp.fft.fftshift(self.xp.fft.fft2(u_tlt, axes=(0, 1)), axes=(0, 1))                                       
        if self._target_device_idx>-1:
            u_fp_pyr, fpsf = pyr1_fused(u_fp, ffv, my_exp, fp_mask)
        else:
            psf = self.xp.real(u_fp * self.xp.conj(u_fp))
            fpsf = psf * ffv
            u_fp *= fp_mask
            u_fp_pyr = u_fp * my_exp
        #with plan2:
        pup_pyr_tot = self.xp.sum( self.xp.abs(self.xp.fft.ifft2(u_fp_pyr, axes=(0, 1))) ** 2 * ffv, axis=2)            
        psf_bfm = self.xp.sum(fpsf , axis=2)
        psf_tot = self.xp.sum(fpsf*fp_mask, axis=2)
        # self.xp.cuda.runtime.deviceSynchronize()

        pup_pyr_tot = self.xp.roll(pup_pyr_tot, self.xp.array( [self._fft_padding//2, self._fft_padding//2], dtype=self.xp.int64), [0,1] )

        factor = 1.0 / self.xp.sum(self._flux_factor_vector)
        pup_pyr_tot *= factor
        psf_tot *= factor
        psf_bfm *= factor

        sum_psf = self.xp.sum(psf_tot)
        sum_bfm = self.xp.sum(psf_bfm)
        sum_pup = self.xp.sum(pup_pyr_tot)
        transmission = sum_psf / sum_bfm
        phot = in_ef.S0 * in_ef.masked_area()
        pup_pyr_tot *= (phot / sum_pup) * transmission

#        if phot == 0: slows down?
#            print('WARNING: total intensity at PYR entrance is zero')

        # TODO handle shifts as an input from a func generator (for time-varying shifts)
        if self._pup_shifts is not None and self._pup_shifts != (0.0, 0.0):
            image = self.xp.pad(pup_pyr_tot, 1, mode='constant')
            imscale = float(self._fft_totsize) / float(self._toccd_side)

            pup_shiftx = self._pup_shifts[0] * imscale
            pup_shifty = self._pup_shifts[1] * imscale

            image = self.interpolate(image, self.xp.arange(self._fft_totsize + 2) - pup_shiftx, 
                                     self.xp.arange(self._fft_totsize + 2) - pup_shifty, grid=True, missing=0)
            pup_pyr_tot = image[1:-1, 1:-1]


        self._toccd_side = int(self._toccd_side)
        ccd_internal = toccd(pup_pyr_tot, (self._toccd_side, self._toccd_side), xp=self.xp)

        if self._final_ccd_side > self._toccd_side:
            delta = (self._final_ccd_side - self._toccd_side) // 2
            ccd = self.xp.zeros((self._final_ccd_side, self._final_ccd_side), dtype=self.dtype)
            ccd[delta:delta + ccd_internal.shape[0], delta:delta + ccd_internal.shape[1]] = ccd_internal
        elif self._final_ccd_side < self._toccd_side:
            delta = (self._toccd_side - self._final_ccd_side) // 2
            ccd = ccd_internal[delta:delta + self._final_ccd_side, delta:delta + self._final_ccd_side]
        else:
            ccd = ccd_internal

        self._out_i.i = ccd
        self._out_i.generation_time = t
        self._psf_tot.value = psf_tot
        self._psf_tot.generation_time = t
        self._psf_bfm.value = psf_bfm
        self._psf_bfm.generation_time = t
        self._out_transmission.value = transmission
        self._out_transmission.generation_time = t

    def run_check(self, time_step):
        if self._extended_source_in_on:
            return 1
        elif self._mod_steps < self.xp.around(2 * self.xp.pi * self._mod_amp):
            raise Exception(f'Number of modulation steps is too small ({self._mod_steps}), it must be at least 2*pi times the modulation amplitude ({self.xp.around(2 * self.xp.pi * self._mod_amp)})!')
        return 1

    def hdr(self, hdr):
        hdr['MODAMP'] = self._mod_amp
        hdr['MODSTEPS'] = self._mod_steps
    
    def minmax(self, array):
        return self.xp.min(array), self.xp.max(array)

    # TODO needed for extended source
    @staticmethod
    def zern(mode, xx, yy):
        raise NotImplementedError

    # TODO needed for shifts
    @staticmethod
    def interpolate(image, x, y, grid=False, missing=0):
        raise NotImplementedError

    # TODO needed for image rotation
    @staticmethod
    def ROT_AND_SHIFT_IMAGE(image, angle, shift, scale, use_interpolate=False):
        raise NotImplementedError
