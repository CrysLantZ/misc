"""
NOTES
-----
[1] Hartree atomic units are used throughout the code unless otherwise stated.

[2] The Hamiltonian of exciton should have six terms according to Nagaosa's 
paper. However, only the kinetic term (Tr) according to the relative motion
of electron-hole pair and the Coulomb attraction term (Veh) are dependent on
the variation parameter a. Therefore we neglect all the other terms and take
the variation of exciton binding energy (Tr + Veh) instead of the total
energy.

[3] The Coulomb attraction term of Nagaosa'paper has been replaced by the one
in doi:10.16854/j.cnki.1000-0712.2013.07.008, in order to generalize the model
to two barriers with different dielectric constants.

[4] For the derivation of the matrix elements, see PhysRevB.32.1043.

[5] Tests have proved that eps1 and eps3 are symmetric, i.e. swapping eps1 and
eps3 will yield the same exciton radius and binding energy. However, only eps1
is allowed to have the value as eps2.
"""
import numpy as np
import scipy.special as sp
import scipy.optimize as opt
from mpi4py import MPI


def G(a, gamma):
    x = 2 * abs(gamma) / a
    if x < 1.0e-9:
        return 1.0
    else:
        return x * (np.pi / 2 * (sp.struve(1, x) - sp.y1(x)) - 1)


def calc_eb(x):
    # Convert the unit of x from exciton Bohr radius to absolute Bohr
    x = comm.bcast(x, root=0)
    a = x * a_B

    # Evaluation the kinetic term
    kinetic_energy = 1.0 / (2.0 * mu * a**2)

    # Evaluate the Coulomb attraction term
    integral_ze = 0.0
    for i in jobs[rank]:
        ze = zgrid[i]
        integral_zh = 0.0
        for j, zh in enumerate(zgrid):
            kernel = G(a, ze - zh) + k * G(a, ze + zh)
            for n in range(1, num_series+1):
                qn = q**n
                zpn = -zh + 4 * n * l
                zmn =  zh + 4 * n * l
                kernel += qn * (k * G(a, ze - zpn) + G(a, ze + zpn) + 
                                    G(a, ze - zmn) + G(a, ze + zmn) / k)
            integral_zh += sin_zgrid[j] * kernel
        integral_ze += sin_zgrid[i] * integral_zh
    integral_ze = comm.allreduce(integral_ze)
    dS = (zgrid[1] - zgrid[0]) ** 2
    potential_energy = -2.0 / (eps2 * l**2 * a) * integral_ze * dS

    # Evaluate the binding energy in effective Rydberg energy
    binding_energy = (kinetic_energy + potential_energy) / R
    return binding_energy


def opt_eps2(x):
    global eps2, a_B, R, k, q, l, zgrid, sin_zgrid

    # Synchronize epsilon_2
    x = comm.bcast(x, root=0)
    eps2 = x

    residual = 0.0
    for i, qw_width in enumerate(qw_width_list):
        # Update global variables
        a_B = eps2 / mu
        R = mu / (2 * eps2**2)
        k = (eps2 - eps3) / (eps2 + eps3)
        q = (eps2 - eps1) / (eps2 + eps1) * k
        l = qw_width / bohr2ang / 2
        zgrid = np.linspace(-2*l, 0, num_grid)
        sin_zgrid = np.sin(np.pi * zgrid / (2 * l))**2

        # Calculate residual
        xopt, fopt, ninter, funcalls, warnflag = opt.fmin(calc_eb, x0=1.0, xtol=1.0e-6,
                                                 ftol=1.0e-6, full_output=True, disp=False)
        eb_meV = -fopt * R * har2eV * 1000
        residual += abs(eb_meV - eb_ref_list[i])

    return residual


def echo(x):
    if rank == 0:
        print(x)


# Physical constants
bohr2ang = 0.52917721092
har2eV = 27.211385

# Parameters of the quantum well
#
# mu: reduced effective mass of the electron-hole pair
# qw_width: width of the quantum well in angstroms
# eb_ref: exciton binding energy from experiments in meV
# eps1: relative dielectric constant of the bottom barrier
# eps3: relative dielectric constant of the top barrier
mu = 0.117
qw_width_list = [59, 78, 101, 143, 262]
eb_ref_list = [147.6, 123.5, 92.1, 71.4, 69.5]
eps1 = 6.0
eps3 = 1.0

# Parameters controlling the integral
#
# num_grid: number of discrete grid points to evaluate the Coulomb integral
#           over z-axis
# num_series: number of series to expand the Coulomb integral
num_grid = 100
num_series = 20

# Initialize MPI environment
comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()
jobs = [[i for i in range(num_grid) if i % size == k] for k in range(size)]

# Now we begin with the variation.
xopt, fopt, ninter, funcalls, warnflag = opt.fmin(opt_eps2, x0=3.5, xtol=1.0e-3,
                                         ftol=1.0e-3, full_output=True, disp=False,
                                         callback=echo)
if rank == 0:
   print(xopt, fopt)
