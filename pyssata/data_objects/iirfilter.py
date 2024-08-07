import numpy as np
from astropy.io import fits

class IIRFilter:
    def __init__(self):
        self._nfilter = 0
        self._ordnum = None
        self._ordden = None
        self._num = None
        self._den = None
        self._zeros = None
        self._poles = None
        self._gain = None
        self.init()

    def init(self):
        self._ordnum = np.array([], dtype=float)
        self._ordden = np.array([], dtype=float)
        self._num = np.array([], dtype=float)
        self._den = np.array([], dtype=float)
        self._zeros = np.array([], dtype=float)
        self._poles = np.array([], dtype=float)
        self._gain = np.array([], dtype=float)
        return True

    def set_property(self, nfilter=None, ordnum=None, ordden=None, num=None, den=None, zeros=None, poles=None, gain=None, **extra):
        if nfilter is not None:
            self._nfilter = nfilter
        if ordnum is not None:
            self._ordnum = np.array(ordnum)
        if ordden is not None:
            self._ordden = np.array(ordden)
        if num is not None:
            self.set_num(num)
        if den is not None:
            self.set_den(den)
        if zeros is not None:
            self.set_zeros(zeros)
        if poles is not None:
            self.set_poles(poles)
        if gain is not None:
            self.set_gain(gain)

    def get_property(self):
        return {
            'nfilter': self._nfilter,
            'ordnum': self._ordnum,
            'ordden': self._ordden,
            'num': self._num,
            'den': self._den,
            'zeros': self._zeros,
            'poles': self._poles,
            'gain': self._gain,
        }

    def set_num(self, num):
        self._num = np.array(num)
        zeros = np.zeros((self._nfilter, self._num.shape[1] - 1))
        gain = np.zeros(self._nfilter)
        for i in range(self._nfilter):
            if self._ordnum[i] > 1:
                zeros[i, :self._ordnum[i] - 1] = np.roots(self._num[i, :self._ordnum[i]])
            gain[i] = self._num[i, self._ordnum[i] - 1]
        self._zeros = zeros
        self._gain = gain

    def set_den(self, den):
        self._den = np.array(den)
        poles = np.zeros((self._nfilter, self._den.shape[1] - 1))
        for i in range(self._nfilter):
            if self._ordden[i] > 1:
                poles[i, :self._ordden[i] - 1] = np.roots(self._den[i, :self._ordden[i]])
        self._poles = poles

    def set_zeros(self, zeros):
        self._zeros = np.array(zeros)
        num = np.zeros((self._nfilter, self._zeros.shape[1] + 1))
        for i in range(self._nfilter):
            if self._ordnum[i] > 1:
                num[i, :self._ordnum[i]] = np.poly(self._zeros[i, :self._ordnum[i] - 1])
        self._num = num

    def set_poles(self, poles):
        self._poles = np.array(poles)
        den = np.zeros((self._nfilter, self._poles.shape[1] + 1))
        for i in range(self._nfilter):
            if self._ordden[i] > 1:
                den[i, :self._ordden[i]] = np.poly(self._poles[i, :self._ordden[i] - 1])
        self._den = den

    def set_gain(self, gain, verbose=False):
        if verbose:
            print('original gain:', self._gain)
        if len(gain) < self._nfilter:
            nfilter = len(gain)
        else:
            nfilter = self._nfilter
        if self._gain is None:
            for i in range(nfilter):
                if np.isfinite(gain[i]):
                    if self._ordnum[i] > 1:
                        self._num[i, :] *= gain[i]
                    else:
                        self._num[i, self._ordden - 1] = gain[i]
                else:
                    gain[i] = self._num[i, self._ordden - 1]
        else:
            for i in range(nfilter):
                if np.isfinite(gain[i]):
                    if self._ordnum[i] > 1:
                        self._num[i, :] *= (gain[i] / self._gain[i])
                    else:
                        self._num[i, self._ordden - 1] = gain[i] / self._gain[i]
                else:
                    gain[i] = self._gain[i]
        self._gain = np.array(gain)
        if verbose:
            print('new gain:', self._gain)

    def complexRTF(self, mode, fs, delay, freq=None, verbose=False):
        if delay > 1:
            dm = np.array([0.0, 1.0])
            nm = np.array([1.0, 0.0])
            wTf = self.discrete_delay_tf(delay - 1)
        else:
            dm = np.array([1.0])
            nm = np.array([1.0])
            wTf = self.discrete_delay_tf(delay)
        nw = wTf[:, 0]
        dw = wTf[:, 1]
        complex_yt_tf = self.plot_iirfilter_tf(self._num[mode, :], self._den[mode, :], fs, dm=dm, nw=nw, dw=dw, freq=freq, noplot=True, verbose=verbose)
        return complex_yt_tf

    def RTF(self, mode, fs, freq=None, tf=None, dm=None, nw=None, dw=None, verbose=False, title=None, overplot=False, **extra):
        plotTitle = title if title else '!17Rejection Transfer Function'
        tf = self.plot_iirfilter_tf(self._num[mode, :], self._den[mode, :], fs, dm=dm, nw=nw, dw=dw, freq=freq, noplot=True, verbose=verbose)
        if overplot:
            color = extra.get('color', 255)
            plt.plot(freq, tf, color=color, **extra)
        else:
            plt.plot(freq, tf, label=plotTitle)
            plt.xlabel('!17frequency !4[!17Hz!4]!17')
            plt.ylabel('!17magnitude')
            plt.title(plotTitle)
            plt.show()

    def NTF(self, mode, fs, freq=None, tf=None, dm=None, nw=None, dw=None, verbose=False, title=None, overplot=False, **extra):
        plotTitle = title if title else '!17Noise Transfer Function'
        tf = self.plot_iirfilter_tf(self._num[mode, :], self._den[mode, :], fs, dm=dm, nw=nw, dw=dw, freq=freq, noplot=True, verbose=verbose)
        if overplot:
            color = extra.get('color', 255)
            plt.plot(freq, tf, color=color, **extra)
        else:
            plt.plot(freq, tf, label=plotTitle)
            plt.xlabel('!17frequency !4[!17Hz!4]!17')
            plt.ylabel('!17magnitude')
            plt.title(plotTitle)
            plt.show()

    def is_stable(self, mode, nm=None, dm=None, nw=None, dw=None, gain=None, no_margin=False, verbose=False):
        nm = nm if nm is not None else np.array([1, 0])
        nw = nw if nw is not None else np.array([1, 0])
        dm = dm if dm is not None else np.array([0, 1])
        dw = dw if dw is not None else np.array([0, 1])

        temp1 = np.polymul(dm, dw)
        while temp1[-1] == 0:
            temp1 = temp1[:-1]
        DDD = np.polymul(temp1, self._den[mode, :])
        while DDD[-1] == 0:
            DDD = DDD[:-1]

        temp2 = np.polymul(nm, nw)
        while temp2[-1] == 0:
            temp2 = temp2[:-1]
        NNN = np.polymul(temp2, self._num[mode, :])
        if np.sum(np.abs(NNN)) != 0:
            while NNN[-1] == 0:
                NNN = NNN[:-1]

        if gain is not None:
            NNN *= gain / self._gain[mode]

        stable, ph_margin, g_margin, mroot, m_one_dist = self.nyquist(NNN, DDD, no_margin=no_margin)

        if verbose:
            print('max root (closed loop) =', mroot)
            print('phase margin =', ph_margin)
            print('gain margin =', g_margin)
            print('min. distance from (-1;0) =', m_one_dist)
        return stable

    def save(self, filename, hdr=None):
        hdr = hdr if hdr is not None else fits.Header()
        hdr['VERSION'] = 1

        hdu = fits.PrimaryHDU(header=hdr)
        hdul = fits.HDUList([hdu])
        hdul.append(fits.ImageHDU(data=self._ordnum, name='ORDNUM'))
        hdul.append(fits.ImageHDU(data=self._ordden, name='ORDDEN'))
        hdul.append(fits.ImageHDU(data=self._num, name='NUM'))
        hdul.append(fits.ImageHDU(data=self._den, name='DEN'))
        hdul.writeto(filename, overwrite=True)

    def read(self, filename, hdr=None, exten=0):
        hdul = fits.open(filename)
        hdr = hdul[0].header
        self._ordnum = hdul['ORDNUM'].data
        self._ordden = hdul['ORDDEN'].data
        self._nfilter = len(self._ordnum)
        self.set_num(hdul['NUM'].data)
        self.set_den(hdul['DEN'].data)

    def restore(self, filename):
        obj = IIRFilter()
        obj.read(filename)
        return obj

    def revision_track(self):
        return '$Rev$'

    def cleanup(self):
        del self._ordnum
        del self._ordden
        del self._num
        del self._den
        del self._zeros
        del self._poles
        del self._gain

    def discrete_delay_tf(self, delay):
        # Placeholder for the actual discrete delay transfer function
        pass

    def plot_iirfilter_tf(self, num, den, fs, dm, nw, dw, freq, noplot, verbose):
        # Placeholder for the actual plotting of IIR filter transfer function
        pass

    def nyquist(self, NNN, DDD, no_margin):
        # Placeholder for the actual Nyquist stability criterion implementation
        pass