

import specula
specula.init(0)  # Default target device

import unittest

from specula import cp, np
from specula import cpuArray

from specula.data_objects.electric_field import ElectricField
from specula.processing_objects.sh import SH
from test.specula_testlib import cpu_and_gpu


class TestSH(unittest.TestCase):

    @cpu_and_gpu
    def test_sh_flux(self, target_device_idx, xp):
        
        ref_S0 = 100
        t = 1
        
        sh = SH(wavelengthInNm=500,
                subap_wanted_fov=3,
                sensor_pxscale=0.5,
                subap_on_diameter=20,
                subap_npx=6,
                convolGaussSpotSize=1.0,
                target_device_idx=target_device_idx)
        
        ef = ElectricField(120,120,0.05, S0=ref_S0, target_device_idx=target_device_idx)
        ef.generation_time = t

        sh.inputs['in_ef'].set(ef)

        sh.setup(1, 1)
        sh.check_ready(t)
        sh.trigger()
        sh.post_trigger()
        intensity = sh.outputs['out_i']
        
        np.testing.assert_almost_equal(xp.sum(intensity.i), ref_S0 * ef.masked_area())

    @cpu_and_gpu
    def test_pixelscale(self, target_device_idx, xp):
        '''
        Test that pixelscale is correctly handled, by comparing spots from a flat 
        wavefront and from a tilted one. The introduced tilt corresponds to exactly 1 pixel,
        and we verify that the resulting intensity field is indeed shifted by 1 pixel
        in the correct direction
        '''
        t = 1
        pxscale_arcsec = 0.5
        pixel_pupil = 120
        pixel_pitch = 0.05
        sh_npix = 6

        sh = SH(wavelengthInNm=500,
                subap_wanted_fov= sh_npix * pxscale_arcsec,
                sensor_pxscale=pxscale_arcsec,
                subap_on_diameter=20,
                subap_npx=sh_npix,
                convolGaussSpotSize=1.0,
                target_device_idx=target_device_idx)

        # Flat wavefront
        ef = ElectricField(pixel_pupil, pixel_pupil, pixel_pitch, S0=1, target_device_idx=target_device_idx)
        ef.generation_time = t
        sh.inputs['in_ef'].set(ef)

        sh.setup(1, 1)
        sh.check_ready(t)
        sh.trigger()
        sh.post_trigger()
        flat = sh.outputs['out_i'].i.copy()
        
        # tilt corresponding to pxscale_arcsec
        tilt_value = np.radians(pixel_pupil * pixel_pitch * 1/(60*60) * pxscale_arcsec)
        tilt = np.linspace(-tilt_value / 2, tilt_value / 2, pixel_pupil)

        # Tilted wavefront
        ef.phaseInNm[:] = xp.array(np.broadcast_to(tilt, (pixel_pupil, pixel_pupil))) * 1e9
        ef.generation_time = t+1

        sh.check_ready(t+1)
        sh.trigger()
        sh.post_trigger()
        tilted = sh.outputs['out_i'].i.copy()
        
        flat_shifted = np.roll(flat, (0, 1))

        # Remove the left column edges on each subap (comparison is invalid after roll)
        flat_shifted[:, ::sh_npix] = 0
        tilted[:, ::sh_npix] = 0
        
        np.testing.assert_array_almost_equal(cpuArray(tilted), cpuArray(flat_shifted), decimal=3) 
        

 