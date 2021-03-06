# Copyright (c) 2015 by the parties listed in the AUTHORS file.
# All rights reserved.  Use of this source code is governed by 
# a BSD-style license that can be found in the LICENSE file.


import sys
import os

if 'TOAST_NO_MPI' in os.environ.keys():
    from toast import fakempi as MPI
else:
    from mpi4py import MPI

import numpy as np
import numpy.testing as nt

from toast.dist import *
from toast.tod.interval import *
from toast.tod.sim_interval import *

from toast.mpirunner import MPITestCase


class IntervalTest(MPITestCase):


    def setUp(self):
        self.outdir = "tests_output"
        if self.comm.rank == 0:
            if not os.path.isdir(self.outdir):
                os.mkdir(self.outdir)
        self.rate = 123.456
        self.duration = 24 * 3601.23
        self.gap = 3600.0
        self.start = 5432.1
        self.first = 10
        self.nint = 3


    def test_regular(self):
        start = MPI.Wtime()
        
        intrvls = regular_intervals(self.nint, self.start, self.first, self.rate, self.duration, self.gap)

        goodsamp = self.nint * ( int(0.5 + self.duration * self.rate) + 1 )

        check = 0

        for it in intrvls:
            print(it.first," ",it.last," ",it.start," ",it.stop)
            check += it.last - it.first + 1

        nt.assert_equal(check, goodsamp)

        stop = MPI.Wtime()
        elapsed = stop - start
        #print('Proc {}:  test took {:.4f} s'.format( MPI.COMM_WORLD.rank, elapsed ))

