from pyssata import xp

main = {
 'root_dir':          './calib/SCAO',         # Root directory for calibration manager
 'store_dir':         './output',             # Data result directory: 'store_dir'/TN/
 'pixel_pupil':       160,                    # Linear dimension of pupil phase array
 'pixel_pitch':       0.05,                   # [m] Pitch of the pupil phase array
 'total_time':        0.205,                  # [s] Total simulation running time
 'time_step':         0.001,                  # [s] Simulation time step
 'store': {                                   # Dict of data products to store, 'name': 'output'
     'sr': 'psf.out_sr',
     'res_ef': 'pyramid.in_ef'}
}

seeing = {
 'class':             'FuncGenerator',
 'constant':          0.8,                  # ["] seeing value
 'func_type':         'SIN'                 # TODO necessary for factory.py line 217
}

wind_speed = {
 'class':             'FuncGenerator',
 'constant':          [20.]#,10.,20.,10.]      # [m/s] Wind speed value
}

wind_direction = {
 'class':             'FuncGenerator',
 'constant':          [0.]#,270.,270.,90.]   # [degrees] Wind direction value
}

on_axis_source = {
 'class':             'Source',
 'polar_coordinate':  [0.0, 0.0],           # [arcsec, degrees] source polar coordinates
 'magnitude':         8,                    # source magnitude
 'wavelengthInNm':    750                   # [nm] wavelength
}

pupilstop = {                                 # Default parameters (circular pupil)
    'class': 'Pupilstop'
}

atmo = {
 'class':             'AtmoEvolution',
 'L0':                40,                   # [m] Outer scale
 'heights':           xp.array([119.]), #,837,3045,12780]), # [m] layer heights at 0 zenith angle
 'Cn2':               xp.array([0.70]), #,0.06,0.14,0.10]), # Cn2 weights (total must be eq 1)
 'source_list_ref':       ['on_axis_source'],
 'inputs': {
    'seeing' : 'seeing.output',
    'wind_speed': 'wind_speed.output',
    'wind_direction': 'wind_direction.output',
     }
}

prop = {
 'class':             'AtmoPropagation',
 'source_dict_ref':       ['on_axis_source'],
 'inputs': {
   'layer_list': ['atmo.layer_list',
                  'pupilstop',
                  'dm.out_layer']
  }
}

pyramid = {
 'pup_diam':          30.,                     # Pupil diameter in subaps.
 'pup_dist':          36.,                     # Separation between pupil centers in subaps.
 'fov':               2.0,                     # Requested field-of-view [arcsec]
 'mod_amp':           3.0,                     # Modulation radius (in lambda/D units)
 'output_resolution': 80,                      # Output sampling [usually corresponding to
 										    # CCD pixels]
 'wavelengthInNm':    750,                     # [nm] Pyramid wavelength
 'inputs': {
     'in_ef': 'prop.on_axis_source'
 }
}

detector = {
 'size':              [80,80],                # Detector size in pixels
 'dt':                0.001,                 # [s] Detector integration time
 'bandw':             300,                    # [nm] Sensor bandwidth
 'photon_noise':      True,                     # activate photon noise
 'readout_noise':     True,                     # activate readout noise
 'readout_level':     1.0,                    # readout noise in [e-/pix/frame]
 'quantum_eff':       0.32,                   # quantum efficiency * total transmission
 'inputs': { 
    'in_i': 'pyramid.out_i',
 }
}

slopec = {
 'class':             'PyrSlopec',
 'pupdata_object':    'scao_pup',             # tag of the pyramid WFS pupils
 'sn_object':         'scao_sn',               # tag of the slope reference vector
 'inputs' : {
   'in_pixels': 'detector.out_pixels',
 }
}

rec = {
 'class':             'Modalrec',
 'recmat_object':        'scao_recmat',         # reconstruction matrix tag
 'inputs': {
    'in_slopes':  'slopec.out_slopes'
 }
}

control = {
 'class':             'IntControl',
 'delay':             2,                      # Total temporal delay in time steps
 'int_gain':          0.5 * xp.ones(54)       # Integrator gain (for 'INT' control)
}

dm = {
 'class':             'DM',
 'type':              'zernike',              # modes type
 'nmodes':            54,                     # number of modes
 'npixels':           160,                    # linear dimension of DM phase array
 'obsratio':          0.1,                    # obstruction dimension ratio w.r.t. diameter
 'height':            0,                      # DM height [m]
 'inputs': {
   'in_command': 'rec.out_modes'              # TODO skip control object for now
 }
}

psf = {
 'class':             'PSF',
 'wavelengthInNm':    1650,                 # [nm] Imaging wavelength
 'nd':                8,                    # padding coefficient for PSF computation
 'start_time':        0.05,                # PSF integration start time
 'inputs': {
    'in_ef':  'pyramid.in_ef'
 }
}

