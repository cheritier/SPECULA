import numpy as np
from specula import show_in_profiler

from astropy.io import fits

from specula.base_processing_obj import BaseProcessingObj
from specula.base_value import BaseValue
from specula.data_objects.layer import Layer
from specula.lib.cv_coord import cv_coord
from specula.lib.phasescreen_manager import phasescreens_manager
from specula.connections import InputValue
from specula import cpuArray, ASEC2RAD, RAD2ASEC

#atmo:
#  class:                'AtmoEvolution'
#  L0:                   40                   # [m] Outer scale
#  heights:              [119.] #,837,3045,12780]), # [m] layer heights at 0 zenith angle
#  Cn2:                  [1.0] #,0.06,0.14,0.10]), # Cn2 weights (total must be eq 1)
#  source_dict_ref:      ['on_axis_source']
#  inputs:
#    seeing: 'seeing.output'
#    wind_speed: 'wind_speed.output'
#    wind_direction: 'wind_direction.output'
#  outputs: ['layer_list']


from scipy.special import gamma, kv
from symao.turbolence import createTurbolenceFormulary, ft_phase_screen, ft_ft2

turbolenceFormulas = createTurbolenceFormulary()

def seeing_to_r0(seeing, wvl=500.E-9):
    return 0.9759*wvl/(seeing* ASEC2RAD)

def cn2_to_r0(cn2, wvl=500.E-9):
    r0=(0.423*(2*np.pi/wvl)**2*cn2)**(-3./5.)
    return r0

def r0_to_seeing(r0, wvl=500.E-9):
    return (0.9759*wvl/r0)*RAD2ASEC

def cn2_to_seeing(cn2, wvl=500.E-9):
    r0 = cn2_to_r0(cn2,wvl)
    seeing = r0_to_seeing(r0,wvl)
    return seeing


class InfinitePhaseScreen(BaseProcessingObj):

    def __init__(self, mx_size, pixel_scale, r0, L0, l0, xp=np, random_seed=None, stencil_size_factor=1, target_device_idx=0, precision=0):
        super().__init__(target_device_idx=target_device_idx, precision=precision)
        self.requested_mx_size = mx_size
        self.mx_size = 2 ** (int( np.ceil(np.log2(mx_size)))) + 1
        self.pixel_scale = pixel_scale
        self.r0 = r0
        self.L0 = L0
        self.l0 = l0
        self.xp = xp
        self.stencil_size_factor = stencil_size_factor
        self.stencil_size = stencil_size_factor * self.mx_size        
        if random_seed is not None:
            self.xp.random.seed(random_seed)
        #self.set_stencil_coords_basic()
        self.set_stencil_coords()
        self.setup()

    def phase_covariance(self, r, r0, L0):
        # Make sure everything is a float to avoid nasty surprises in division!
        r = self.xp.asnumpy(r)
        r0 = float(r0)
        L0 = float(L0)
        # Get rid of any zeros
        r += 1e-40
        A = (L0 / r0) ** (5. / 3)
        B1 = (2 ** (-5. / 6)) * gamma(11. / 6) / (self.xp.pi ** (8. / 3))
        B2 = ((24. / 5) * gamma(6. / 5)) ** (5. / 6)
        C = (((2 * self.xp.pi * r) / L0) ** (5. / 6)) * kv(5. / 6, (2 * self.xp.pi * r) / L0)
        cov = A * B1 * B2 * C
        cov = self.xp.asarray(cov)
        return cov

    def set_stencil_coords_basic(self):
        self.stencil = self.xp.zeros((self.stencil_size, self.stencil_size))
        self.stencil[:2,:] = 1
        self.stencil_coords = self.xp.array(self.xp.where(self.stencil==1)).T
        self.stencil_positions = self.stencil_coords * self.pixel_scale
        self.n_stencils = self.stencil_coords.shape[0]

    def set_stencil_coords(self):
        self.stencil = np.zeros((self.stencil_size, self.stencil_size))
        self.stencilF = np.zeros((self.stencil_size, self.stencil_size))
        max_n = int( np.floor(np.log2(self.stencil_size)))
        # the head of stencil (basiaccaly all of it for us)
        for n in range(0, max_n + 1):
            col = int((2 ** (n - 1)) + 1)
            n_points = (2 ** (max_n - n)) + 1
            coords = np.round(np.linspace(0, self.stencil_size - 1, n_points)).astype('int32')
            self.stencil[col - 1][coords] = 1
            self.stencilF[self.stencil_size - col][coords] = 1
        # the tail of stencil
        for n in range(1, self.stencil_size_factor + 1):
            col = n * self.mx_size - 1
            self.stencil[col, self.stencil_size // 2] = 1
            self.stencilF[self.stencil_size-col-1, self.stencil_size // 2] = 1
        self.stencil = self.xp.asarray(self.stencil)
        self.stencilF = self.xp.asarray(self.stencilF)
        self.stencil_coords = []
        self.stencil_coords.append(self.xp.array(self.xp.where(self.stencil == 1)).T)
        self.stencil_coords.append(self.xp.array(self.xp.where(self.stencilF == 1)).T)
        self.stencil_positions = []
        self.stencil_positions.append(self.stencil_coords[0] * self.pixel_scale)
        self.stencil_positions.append(self.stencil_coords[1] * self.pixel_scale)        
        self.n_stencils = self.stencil_coords[0].shape[0]

    def AB_from_positions(self, positions):
        seperations = self.xp.zeros((len(positions), len(positions)))
        px, py = positions[:,0], positions[:,1]
        delta_x_gridA, delta_x_gridB = self.xp.meshgrid(px, px)
        delta_y_gridA, delta_y_gridB = self.xp.meshgrid(py, py)
        delta_x_grid = delta_x_gridA - delta_x_gridB
        delta_y_grid = delta_y_gridA - delta_y_gridB
        seperations = self.xp.sqrt(delta_x_grid ** 2 + delta_y_grid ** 2)
        self.cov_mat = self.phase_covariance(seperations, self.r0, self.L0)
        self.cov_mat_zz = self.cov_mat[:self.n_stencils, :self.n_stencils]
        self.cov_mat_xx = self.cov_mat[self.n_stencils:, self.n_stencils:]
        self.cov_mat_zx = self.cov_mat[:self.n_stencils, self.n_stencils:]
        self.cov_mat_xz = self.cov_mat[self.n_stencils:, :self.n_stencils]
        # Cholesky solve can fail - so do brute force inversion
        cf = self._lu_factor(self.cov_mat_zz)
        inv_cov_zz = self._lu_solve(cf, self.xp.identity(self.cov_mat_zz.shape[0]))
        A_mat = self.cov_mat_xz.dot(inv_cov_zz)
        # Can make initial BBt matrix first
        BBt = self.cov_mat_xx - A_mat.dot(self.cov_mat_zx)
        # Then do SVD to get B matrix
        u, W, ut = self.xp.linalg.svd(BBt)
        L_mat = self.xp.zeros((self.stencil_size, self.stencil_size))
        self.xp.fill_diagonal(L_mat, self.xp.sqrt(W))
        # Now use sqrt(eigenvalues) to get B matrix
        B_mat = u.dot(L_mat)
        return A_mat, B_mat
    
    def setup(self):
        # set X coords
        self.new_col_coords1 = self.xp.zeros((self.stencil_size, 2))
        self.new_col_coords1[:, 0] = -1
        self.new_col_coords1[:, 1] = self.xp.arange(self.stencil_size)
        self.new_col_positions1 = self.new_col_coords1 * self.pixel_scale
        # calc separations
        positions1 = self.xp.concatenate((self.stencil_positions[0], self.new_col_positions1), axis=0)
        self.A_mat, self.B_mat = [], []
        A_mat, B_mat = self.AB_from_positions(positions1)
        self.A_mat.append(A_mat)
        self.B_mat.append(B_mat)
        self.A_mat.append(self.xp.fliplr(self.xp.flipud(A_mat)))
        self.B_mat.append(B_mat)
        # make initial screen
        self.full_scrn = self.xp.asarray(ft_phase_screen( turbolenceFormulas, self.r0, self.stencil_size, self.pixel_scale, self.L0, self.l0 ))
        # print(self.full_scrn.shape)  

    def get_new_line(self, row, after):
        random_data = self.xp.random.normal(size=self.stencil_size) / ((2*self.xp.pi)**2)
        if row:
            stencil_data = self.xp.asarray(self.full_scrn[self.stencil_coords[after][:, 1], self.stencil_coords[after][:, 0]])
        else:
            stencil_data = self.xp.asarray(self.full_scrn[self.stencil_coords[after][:, 0], self.stencil_coords[after][:, 1]])            
        new_line = self.A_mat[after].dot(stencil_data) + self.B_mat[after].dot(random_data)        
        return new_line

    def add_line(self, row, after):
        new_line = self.get_new_line(row, after)
        if row:
            new_line = new_line[:,self.xp.newaxis]
            if after:
                self.full_scrn = self.xp.concatenate((self.full_scrn, new_line), axis=row)[:self.stencil_size, 1:]
            #    self.shift(self.full_scrn, [-1, 0], self.full_scrn, order=0, mode='constant', cval=0.0, prefilter=False)
            #    self.full_scrn[-1, :] = new_line
            else:
                self.full_scrn = self.xp.concatenate((new_line, self.full_scrn), axis=row)[:self.stencil_size, :self.stencil_size]
            #    self.shift(self.full_scrn, [1, 0], self.full_scrn, order=0, mode='constant', cval=0.0, prefilter=False)
            #    self.full_scrn[0, :] = new_line
        else:
            new_line = new_line[self.xp.newaxis, :]
            if after:
                self.full_scrn = self.xp.concatenate((self.full_scrn, new_line), axis=row)[1:, :self.stencil_size]
            #    self.shift(self.full_scrn, [0, -1], self.full_scrn, order=0, mode='constant', cval=0.0, prefilter=False)
            #    self.full_scrn[:, -1] = new_line
            else:
                self.full_scrn = self.xp.concatenate((new_line, self.full_scrn), axis=row)[:self.stencil_size, :self.stencil_size]
            #    self.shift(self.full_scrn, [0, 1], self.full_scrn, order=0, mode='constant', cval=0.0, prefilter=False)
            #    self.full_scrn[:, 0] = new_line

    @property
    def scrn(self):
        return self.full_scrn[:self.requested_mx_size, :self.requested_mx_size].get()

    @property
    def scrnRaw(self):
        return self.full_scrn[:self.requested_mx_size, :self.requested_mx_size]

    @property
    def scrnRawAll(self):
        return self.full_scrn


class AtmoInfiniteEvolution(BaseProcessingObj):
    def __init__(self, L0, pixel_pitch, heights, Cn2, pixel_pupil, data_dir, source_dict,
                 zenithAngleInDeg=None, mcao_fov=None, seed: int=1, target_device_idx=None, precision=None,
                 verbose=None, force_mcao_fov=False, make_cycle=None,
                 fov_in_m=None, pupil_position=None):

        super().__init__(target_device_idx=target_device_idx, precision=precision)
        
        self.n_infinite_phasescreens = len(heights)
        self.last_position = np.zeros(self.n_infinite_phasescreens)
        self.last_t = 0
        self.delta_time = 1
        # fixed at generation time, then is a input -> rescales the screen?
        self.seeing = 1
        self.l0 = 0.005
        self.wind_speed = 1
        self.wind_direction = 1
        self.airmass = 1
        self.ref_wavelengthInNm = 500
        self.pixel_pitch = pixel_pitch         
        
        self.inputs['seeing'] = InputValue(type=BaseValue)
        self.inputs['wind_speed'] = InputValue(type=BaseValue)
        self.inputs['wind_direction'] = InputValue(type=BaseValue)

        if pupil_position is None:
            pupil_position = [0, 0]
        
        if zenithAngleInDeg is not None:
            self.airmass = 1.0 / np.cos(np.radians(zenithAngleInDeg), dtype=self.dtype)
            print(f'Atmo_Evolution: zenith angle is defined as: {zenithAngleInDeg} deg')
            print(f'Atmo_Evolution: airmass is: {self.airmass}')
        else:
            self.airmass = np.array(1.0, dtype=self.dtype)
        self.heights = np.array(heights, dtype=self.dtype) * self.airmass

        if force_mcao_fov:
            print(f'\nATTENTION: MCAO FoV is forced to diameter={mcao_fov} arcsec\n')
            alpha_fov = mcao_fov / 2.0
        else:
            alpha_fov = 0.0
            for source in source_dict.values():
                alpha_fov = max(alpha_fov, *abs(cv_coord(from_polar=[source.phi, source.r_arcsec],
                                                       to_rect=True, degrees=False, xp=np)))
            if mcao_fov is not None:
                alpha_fov = max(alpha_fov, mcao_fov / 2.0)
        
        # Max star angle from arcseconds to radians
        rad_alpha_fov = alpha_fov * ASEC2RAD

        # Compute layers dimension in pixels
        self.pixel_layer_size = np.ceil((pixel_pupil + 2 * np.sqrt(np.sum(np.array(pupil_position, dtype=self.dtype) * 2)) / self.pixel_pitch + 
                               2.0 * abs(self.heights) / self.pixel_pitch * rad_alpha_fov) / 2.0) * 2.0
        if fov_in_m is not None:
            self.pixel_layer_size = np.full_like(self.heights, int(fov_in_m / self.pixel_pitch / 2.0) * 2)
        
        self.L0 = L0
        self.Cn2 = np.array(Cn2, dtype=self.dtype)
        self.pixel_pupil = pixel_pupil
        self.data_dir = data_dir
        self.seeing = None
        self.wind_speed = None
        self.wind_direction = None

        self.verbose = verbose if verbose is not None else False
        
        # Initialize layer list with correct heights
        self.layer_list = []
        for i in range(self.n_infinite_phasescreens):
            layer = Layer(self.pixel_layer_size[i], self.pixel_layer_size[i], self.pixel_pitch, self.heights[i], precision=self.precision, target_device_idx=self.target_device_idx)
            self.layer_list.append(layer)
        self.outputs['layer_list'] = self.layer_list
        
        self.initScreens(seed)

        self.last_position = np.zeros(self.n_infinite_phasescreens, dtype=self.dtype)
        
        if not np.isclose(np.sum(self.Cn2), 1.0, atol=1e-6):
            raise ValueError(f' Cn2 total must be 1. Instead is: {np.sum(self.Cn2)}.')

    def initScreens(self, seed):
        self.seed = seed
        if self.seed <= 0:
            raise ValueError('seed must be >0')
        # Phase screens list
        self.infinite_phasescreens = []
        seed = self.seed + self.xp.arange(self.n_infinite_phasescreens)
        if len(seed) != len(self.L0):
            raise ValueError('Number of elements in seed and L0 must be the same!')
        # Square infinite_phasescreens
        for i in range(self.n_infinite_phasescreens):
            print('Creating phase screen..')
            self.ref_r0 = cn2_to_r0(self.Cn2[i], self.ref_wavelengthInNm*1e-3) # fattore 1e-3 messo a caso per aver un valore decente
            print('self.ref_r0:', self.ref_r0)
            temp_infinite_screen = InfinitePhaseScreen(self.pixel_layer_size[i], self.pixel_pitch, 
                                                       self.ref_r0,
                                                       self.L0[i], self.l0, xp=self.xp, target_device_idx=self.target_device_idx, precision=self.precision )
            self.infinite_phasescreens.append(temp_infinite_screen)

    def prepare_trigger(self, t):
        super().prepare_trigger(t)
        self.delta_time = self.t_to_seconds(self.current_time - self.last_t)
    
    @show_in_profiler('atmo_evolution.trigger_code')
    def trigger_code(self):
        seeing = cpuArray(self.local_inputs['seeing'].value)
        wind_speed = cpuArray(self.local_inputs['wind_speed'].value)
        wind_direction = cpuArray(self.local_inputs['wind_direction'].value)

        #seeing = 0.75
        r0 = 0.9759 * 0.5 / (seeing * 4.848) * self.airmass**(-3./5.)
        #print('r0', r0)
        # # r0wavelength = r0 * (self.wavelengthInNm*1e-9 / self.ref_wavelengthInNm)**(6./5.)        
        scale_r0 = (self.ref_r0 / r0)**(5./6.) 
        scale_wvl = self.ref_wavelengthInNm  / np.pi
        scale_coeff = scale_r0 * scale_wvl
        # print('scale_coeff', scale_coeff)
        # ascreen = temp_infinite_screen.scrn
        # print('mean', np.mean(ascreen))
        # print('std', np.std(ascreen))
        # print('power', np.sqrt(np.mean(ascreen**2)))
        # temp_infinite_screen.full_scrn += np.pi/2
        # temp_infinite_screen.full_scrn *= scale_coeff*8
        # self.infinite_phasescreens.append(temp_infinite_screen)
        # from matplotlib import pyplot as plt
        # ascreen = temp_infinite_screen.scrn
        # print('mean', np.mean(ascreen))
        # print('std', np.std(ascreen))
        # print('power', np.sqrt(np.mean(ascreen**2)))
        # psd_stat = np.absolute(ft_ft2(ascreen, 1))**2
        # plt.plot( np.log( psd_stat[160//2, 160//2+1:] ) )
        # plt.show()
        
        # Compute the delta position in pixels
        delta_position =  wind_speed * self.delta_time / self.pixel_pitch  # [pixel]
        new_position = self.last_position + delta_position
        eps = 1e-4

        for ii, phaseScreen in enumerate(self.infinite_phasescreens):
            w_y_comp = np.sin(2*np.pi*wind_direction[ii]/360.0)
            w_x_comp = np.cos(2*np.pi*wind_direction[ii]/360.0)
            frac_rows, rows_to_add = np.modf( delta_position[ii] * w_y_comp )
            sr = int( (np.sign(rows_to_add) + 1) / 2 )
            frac_cols, cols_to_add = np.modf( delta_position[ii] * w_x_comp )
            sc = int( (-np.sign(cols_to_add) + 1) / 2 )
            if np.abs(w_y_comp)>eps:
                for r in range(int(np.abs(rows_to_add))):
                    phaseScreen.add_line(1, sr)
            if np.abs(w_x_comp)>eps:
                for r in range(int(np.abs(cols_to_add))):
                    phaseScreen.add_line(0, sc)
            phaseScreen0 = phaseScreen.scrnRawAll
            if np.abs(frac_rows)>eps:
                phaseScreen.add_line(1, sr)
            if np.abs(frac_cols)>eps:
                phaseScreen.add_line(0, sc)
            phaseScreen1 = phaseScreen.scrnRawAll
            interpfactor = np.sqrt(frac_rows**2 + frac_cols**2 )
            layer_phase = interpfactor * phaseScreen1 + (1.0-interpfactor) * phaseScreen0
            phaseScreen.full_scrn = layer_phase
            layer_phase += np.pi/2
            self.layer_list[ii].phaseInNm = layer_phase * scale_coeff * 8
            self.layer_list[ii].generation_time = self.current_time
        self.last_position = new_position
        self.last_t = self.current_time
        
    def save(self, filename):
        hdr = fits.Header()
        hdr['VERSION'] = 1
        hdr['INTRLVD'] = int(self.interleave)
        hdr['PUPD_TAG'] = self.pupdata_tag
        super().save(filename, hdr)

        with fits.open(filename, mode='append') as hdul:
            hdul.append(fits.ImageHDU(data=self.infinite_phasescreens))

    def read(self, filename):
        super().read(filename)
        self.infinite_phasescreens = fits.getdata(filename, ext=1)

    def set_last_position(self, last_position):
        self.last_position = last_position

    def set_last_t(self, last_t):
        self.last_t = last_t



