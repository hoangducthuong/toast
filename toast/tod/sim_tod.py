# Copyright (c) 2015 by the parties listed in the AUTHORS file.
# All rights reserved.  Use of this source code is governed by 
# a BSD-style license that can be found in the LICENSE file.


import os
if 'TOAST_NO_MPI' in os.environ.keys():
    from .. import fakempi as MPI
else:
    from mpi4py import MPI

import unittest

import numpy as np

import scipy.fftpack as sft
import scipy.interpolate as si
import scipy.sparse as sp

import healpy as hp

from . import qarray as qa

from .tod import TOD

from .noise import Noise

from ..operator import Operator


def slew_precession_axis(nsim=1000, firstsamp=0, samplerate=100.0, degday=1.0):
    """
    Generate quaternions for constantly slewing precession axis.

    This constructs quaternions which rotates the Z coordinate axis
    to the X/Y plane, and then slowly rotates this.  This can be used
    to generate quaternions for the precession axis used in satellite
    scanning simulations.

    Args:
        nsim (int): The number of samples to simulate.
        firstsamp (int): The offset in samples from the start
            of rotation.
        samplerate (float): The sampling rate in Hz.
        degday (float): The rotation rate in degrees per day.

    Returns:
        Array of quaternions stored as an ndarray of
        shape (nsim, 4).
    """
    # this is the increment in radians per sample
    angincr = degday * (np.pi / 180.0) / (24.0 * 3600.0 * samplerate)

    # Compute the time-varying quaternions representing the rotation
    # from the coordinate frame to the precession axis frame.  The
    # angle of rotation is fixed (PI/2), but the axis starts at the Y
    # coordinate axis and sweeps.

    satang = np.arange(nsim, dtype=np.float64)
    satang *= angincr
    satang += angincr * firstsamp + (np.pi / 2)

    cang = np.cos(satang)
    sang = np.sin(satang)

    # this is the time-varying rotation axis
    sataxis = np.concatenate((cang.reshape(-1,1), sang.reshape(-1,1), np.zeros((nsim, 1))), axis=1)

    # the rotation about the axis is always pi/2
    csatrot = np.cos(0.25 * np.pi)
    ssatrot = np.sin(0.25 * np.pi)

    # now construct the axis-angle quaternions for the precession
    # axis
    sataxis = np.multiply(np.repeat(ssatrot, nsim).reshape(-1,1), sataxis)
    satquat = np.concatenate((sataxis, np.repeat(csatrot, nsim).reshape(-1,1)), axis=1)

    return satquat


def satellite_scanning(nsim=1000, firstsamp=0, samplerate=100.0, qprec=None, spinperiod=1.0, spinangle=85.0, precperiod=0.0, precangle=0.0):
    """
    Generate boresight quaternions for a generic satellite.

    Given scan strategy parameters and the relevant angles
    and rates, generate an array of quaternions representing
    the rotation of the ecliptic coordinate axes to the
    boresight.

    Args:
        nsim (int) : The number of samples to simulate.
        qprec (ndarray): If None (the default), then the
            precession axis will be fixed along the
            X axis.  If a 1D array of size 4 is given,
            This will be the fixed quaternion used
            to rotate the Z coordinate axis to the 
            precession axis.  If a 2D array of shape
            (nsim, 4) is given, this is the time-varying
            rotation of the Z axis to the precession axis.
        samplerate (float): The sampling rate in Hz.
        spinperiod (float): The period (in minutes) of the
            rotation about the spin axis.
        spinangle (float): The opening angle (in degrees) 
            of the boresight from the spin axis.
        precperiod (float): The period (in minutes) of the
            rotation about the precession axis.
        precangle (float): The opening angle (in degrees)
            of the spin axis from the precession axis.

    Returns:
        Array of quaternions stored as an ndarray of
        shape (nsim, 4).
    """

    if spinperiod > 0.0:
        spinrate = 1.0 / (60.0 * spinperiod)
    else:
        spinrate = 0.0
    spinangle = spinangle * np.pi / 180.0

    if precperiod > 0.0:
        precrate = 1.0 / (60.0 * precperiod)
    else:
        precrate = 0.0
    precangle = precangle * np.pi / 180.0

    xaxis = np.array([1,0,0], dtype=np.float64)
    yaxis = np.array([0,1,0], dtype=np.float64)
    zaxis = np.array([0,0,1], dtype=np.float64)

    satrot = None
    if qprec is None:
        # in this case, we just have a fixed precession axis, pointing
        # along the ecliptic X axis.
        satrot = np.tile(qa.rotation(np.array([0.0, 1.0, 0.0]), np.pi/2), nsim).reshape(-1,4)
    elif qprec.flatten().shape[0] == 4:
        # we have a fixed precession axis.
        satrot = np.tile(qprec, nsim).reshape(-1,4)
    elif qprec.shape == (nsim, 4):
        # we have full vector of quaternions
        satrot = qprec
    else:
        raise RuntimeError("qprec has wrong dimensions")

    # Time-varying rotation about precession axis.  
    # Increment per sample is
    # (2pi radians) X (precrate) / (samplerate)
    # Construct quaternion from axis / angle form.

    #print("satrot = ", satrot[-1])

    precang = np.arange(nsim, dtype=np.float64)
    precang += float(firstsamp)
    precang *= 2.0 * np.pi * precrate / samplerate
    #print("precang = ", precang[-1])

    cang = np.cos(0.5 * precang)
    sang = np.sin(0.5 * precang)

    precaxis = np.multiply(sang.reshape(-1,1), np.tile(zaxis, nsim).reshape(-1,3))
    #print("precaxis = ", precaxis[-1])
    
    precrot = np.concatenate((precaxis, cang.reshape(-1,1)), axis=1)
    #print("precrot = ", precrot[-1])

    # Rotation which performs the precession opening angle

    precopen = qa.rotation(np.array([1.0, 0.0, 0.0]), precangle)
    #print("precopen = ", precopen)

    # Time-varying rotation about spin axis.  Increment 
    # per sample is
    # (2pi radians) X (spinrate) / (samplerate)
    # Construct quaternion from axis / angle form.

    spinang = np.arange(nsim, dtype=np.float64)
    spinang += float(firstsamp)
    spinang *= 2.0 * np.pi * spinrate / samplerate
    #print("spinang = ", spinang[-1])

    cang = np.cos(0.5 * spinang)
    sang = np.sin(0.5 * spinang)

    spinaxis = np.multiply(sang.reshape(-1,1), np.tile(zaxis, nsim).reshape(-1,3))
    #print("spinaxis = ", spinaxis[-1])
    
    spinrot = np.concatenate((spinaxis, cang.reshape(-1,1)), axis=1)
    #print("spinrot = ", spinrot[-1])

    # Rotation which performs the spin axis opening angle

    spinopen = qa.rotation(np.array([1.0, 0.0, 0.0]), spinangle)
    #print("spinopen = ", spinopen)

    # compose final rotation

    boresight = qa.mult(satrot, qa.mult(precrot, qa.mult(precopen, qa.mult(spinrot, spinopen))))
    #print("boresight = ", boresight[-1])

    return boresight


class TODHpixSpiral(TOD):
    """
    Provide a simple generator of fake detector pointing.

    Detector focalplane offsets are specified as a dictionary of 4-element
    ndarrays.  The boresight pointing is a simple looping over HealPix 
    ring ordered pixel centers.

    Args:
        mpicomm (mpi4py.MPI.Comm): the MPI communicator over which the data is distributed.
        detectors (dictionary): each key is the detector name, and each value
            is a quaternion tuple.
        detindx (dict): the detector indices for use in simulations.  Default is 
            { x[0] : x[1] for x in zip(detectors, range(len(detectors))) }.
        samples (int): maximum allowed samples.
        firsttime (float): starting time of data.
        rate (float): sample rate in Hz.
        sizes (list): specify the indivisible chunks in which to split the samples.
    """

    def __init__(self, mpicomm=MPI.COMM_WORLD, detectors=None, detindx=None, samples=0, firsttime=0.0, rate=100.0, nside=512, sizes=None):
        if detectors is None:
            self._fp = {'boresight' : np.array([0.0, 0.0, 1.0, 0.0])}
        else:
            self._fp = detectors

        self._detlist = sorted(list(self._fp.keys()))
        
        super().__init__(mpicomm=mpicomm, timedist=True, detectors=self._detlist, detindx=detindx, samples=samples, sizes=sizes)

        self._firsttime = firsttime
        self._rate = rate
        self._nside = nside
        self._npix = 12 * self._nside * self._nside


    def _get(self, detector, start, n):
        # This class just returns data streams of zeros
        return np.zeros(n, dtype=np.float64)


    def _put(self, detector, start, data, flags):
        raise RuntimeError('cannot write data to simulated data streams')
        return


    def _get_flags(self, detector, start, n):
        return (np.zeros(n, dtype=np.uint8), np.zeros(n, dtype=np.uint8))


    def _put_det_flags(self, detector, start, flags):
        raise RuntimeError('cannot write flags to simulated data streams')
        return


    def _get_common_flags(self, start, n):
        return np.zeros(n, dtype=np.uint8)


    def _put_common_flags(self, start, flags):
        raise RuntimeError('cannot write flags to simulated data streams')
        return


    def _get_times(self, start, n):
        start_abs = self.local_samples[0] + start
        start_time = self._firsttime + float(start_abs) / self._rate
        stop_time = start_time + float(n) / self._rate
        stamps = np.linspace(start_time, stop_time, num=n, endpoint=False, dtype=np.float64)
        return stamps


    def _put_times(self, start, stamps):
        raise RuntimeError('cannot write timestamps to simulated data streams')
        return


    def _get_pntg(self, detector, start, n):
        # compute the absolute sample offset
        start_abs = self.local_samples[0] + start

        detquat = np.asarray(self._fp[detector])

        # pixel offset
        start_pix = int(start_abs % self._npix)
        pixels = np.linspace(start_pix, start_pix + n, num=n, endpoint=False)
        pixels = np.mod(pixels, self._npix*np.ones(n, dtype=np.int64)).astype(np.int64)

        # the result of this is normalized
        x, y, z = hp.pix2vec(self._nside, pixels, nest=False)

        # z axis is obviously normalized
        zaxis = np.array([0,0,1], dtype=np.float64)
        ztiled = np.tile(zaxis, x.shape[0]).reshape((-1,3))

        # ... so dir is already normalized
        dir = np.ravel(np.column_stack((x, y, z))).reshape((-1,3))

        # get the rotation axis
        v = np.cross(ztiled, dir)
        v = v / np.sqrt(np.sum(v * v, axis=1)).reshape((-1,1))

        # this is the vector-wise dot product
        zdot = np.sum(ztiled * dir, axis=1).reshape((-1,1))
        ang = 0.5 * np.arccos(zdot)

        # angle element
        s = np.cos(ang)

        # axis
        v *= np.sin(ang)

        # build the un-normalized quaternion
        boresight = np.concatenate((v, s), axis=1)

        boresight = qa.norm(boresight)

        # boredir = qa.rotate(boresight, zaxis)
        # boredir = boredir / np.sum(boredir * boredir, axis=1).reshape(-1,1)

        # check = hp.vec2pix(self._nside, boredir[:,0], boredir[:,1], boredir[:,2], nest=False)
        # if not np.array_equal(pixels, check):
        #     print(list(enumerate(zip(dir,boredir))))
        #     print(pixels)
        #     print(check)
        #     raise RuntimeError('FAIL on TODFake')

        data = qa.mult(boresight, detquat)

        return data


    def _put_pntg(self, detector, start, data):
        raise RuntimeError('cannot write data to simulated pointing')
        return


    def _get_position(self, start, n):
        return np.zeros((n,3), dtype=np.float64)


    def _put_position(self, start, pos):
        raise RuntimeError('cannot write data to simulated position')
        return


    def _get_velocity(self, start, n):
        return np.zeros((n,3), dtype=np.float64)

    
    def _put_velocity(self, start, vel):
        raise RuntimeError('cannot write data to simulated velocity')
        return



class TODSatellite(TOD):
    """
    Provide a simple generator of satellite detector pointing.

    Detector focalplane offsets are specified as a dictionary of 4-element
    ndarrays.  The boresight pointing is a generic 2-angle model.

    Args:
        mpicomm (mpi4py.MPI.Comm): the MPI communicator over which the data is distributed.
        detectors (dictionary): each key is the detector name, and each value
            is a quaternion tuple.
        detindx (dict): the detector indices for use in simulations.  Default is 
            { x[0] : x[1] for x in zip(detectors, range(len(detectors))) }.
        samples (int): maximum allowed samples.
        firsttime (float): starting time of data.
        rate (float): sample rate in Hz.
        spinperiod (float): The period (in minutes) of the
            rotation about the spin axis.
        spinangle (float): The opening angle (in degrees) 
            of the boresight from the spin axis.
        precperiod (float): The period (in minutes) of the
            rotation about the precession axis.
        precangle (float): The opening angle (in degrees)
            of the spin axis from the precession axis.
        sizes (list): specify the indivisible chunks in which to split the samples.
    """

    def __init__(self, mpicomm=MPI.COMM_WORLD, detectors=None, detindx=None, samples=0, firsttime=0.0, rate=100.0, spinperiod=1.0, spinangle=85.0, precperiod=0.0, precangle=0.0, sizes=None):

        if detectors is None:
            self._fp = {'boresight' : np.array([0.0, 0.0, 1.0, 0.0])}
        else:
            self._fp = detectors

        self._detlist = sorted(list(self._fp.keys()))
        
        # call base class constructor to distribute data
        super().__init__(mpicomm=mpicomm, timedist=True, detectors=self._detlist, detindx=detindx, samples=samples, sizes=sizes)

        self._firsttime = firsttime
        self._rate = rate
        self._spinperiod = spinperiod
        self._spinangle = spinangle
        self._precperiod = precperiod
        self._precangle = precangle
        self._boresight = None

        self._AU = 149597870.7
        self._radperday = 0.01720209895
        self._radpersec = self._radperday / 86400.0
        self._radinc = self._radpersec / self._rate
        self._earthspeed = self._radpersec * self._AU


    def set_prec_axis(self, qprec=None):
        """
        Set the fixed or time-varying precession axis.

        This function sets the precession axis for the locally assigned samples.
        It also triggers the generation and caching of the boresight pointing.

        Args:
            qprec (ndarray): If None (the default), then the
                precession axis will be fixed along the
                X axis.  If a 1D array of size 4 is given,
                This will be the fixed quaternion used
                to rotate the Z coordinate axis to the 
                precession axis.  If a 2D array of shape
                (local samples, 4) is given, this is the time-varying
                rotation of the Z axis to the precession axis.
        """
        if qprec is not None:
            if (qprec.shape != (4,)) and (qprec.shape != (self.local_samples[1], 4)):
                raise RuntimeError("precession quaternion has incorrect dimensions")

        # generate and cache the boresight pointing
        self._boresight = satellite_scanning(nsim=self.local_samples[1], firstsamp=self.local_samples[0], qprec=qprec, samplerate=self._rate, spinperiod=self._spinperiod, spinangle=self._spinangle, precperiod=self._precperiod, precangle=self._precangle)


    def _get(self, detector, start, n):
        # This class just returns data streams of zeros
        return np.zeros(n, dtype=np.float64)


    def _put(self, detector, start, data, flags):
        raise RuntimeError('cannot write data to simulated data streams')
        return


    def _get_flags(self, detector, start, n):
        return (np.zeros(n, dtype=np.uint8), np.zeros(n, dtype=np.uint8))


    def _put_det_flags(self, detector, start, flags):
        raise RuntimeError('cannot write flags to simulated data streams')
        return


    def _get_common_flags(self, start, n):
        return np.zeros(n, dtype=np.uint8)


    def _put_common_flags(self, start, flags):
        raise RuntimeError('cannot write flags to simulated data streams')
        return


    def _get_times(self, start, n):
        start_abs = self.local_samples[0] + start
        start_time = self._firsttime + float(start_abs) / self._rate
        stop_time = start_time + float(n) / self._rate
        stamps = np.linspace(start_time, stop_time, num=n, endpoint=False, dtype=np.float64)
        return stamps


    def _put_times(self, start, stamps):
        raise RuntimeError('cannot write timestamps to simulated data streams')
        return


    def _get_pntg(self, detector, start, n):
        if self._boresight is None:
            raise RuntimeError("you must set the precession axis before reading detector pointing")
        detquat = self._fp[detector]
        data = qa.mult(self._boresight, detquat)
        return data


    def _put_pntg(self, detector, start, data):
        raise RuntimeError('cannot write data to simulated pointing')
        return


    def _get_position(self, start, n):
        # For this simple class, assume that the Earth is located
        # along the X axis at time == 0.0s.  We also just use the
        # mean values for distance and angular speed.  Classes for 
        # real experiments should obviously use ephemeris data.
        rad = np.fmod( (start - self._firsttime) * self._radpersec, 2.0 * np.pi )
        ang = self._radinc * np.arange(n, dtype=np.float64) + rad
        x = self._AU * np.cos(ang)
        y = self._AU * np.sin(ang)
        z = np.zeros_like(x)
        return np.ravel(np.column_stack((x, y, z))).reshape((-1,3))


    def _put_position(self, start, pos):
        raise RuntimeError('cannot write data to simulated position')
        return


    def _get_velocity(self, start, n):
        # For this simple class, assume that the Earth is located
        # along the X axis at time == 0.0s.  We also just use the
        # mean values for distance and angular speed.  Classes for 
        # real experiments should obviously use ephemeris data.
        rad = np.fmod( (start - self._firsttime) * self._radpersec, 2.0 * np.pi )
        ang = self._radinc * np.arange(n, dtype=np.float64) + rad + (0.5*np.pi)
        x = self._earthspeed * np.cos(ang)
        y = self._earthspeed * np.sin(ang)
        z = np.zeros_like(x)
        return np.ravel(np.column_stack((x, y, z))).reshape((-1,3))

    
    def _put_velocity(self, start, vel):
        raise RuntimeError('cannot write data to simulated velocity')
        return


