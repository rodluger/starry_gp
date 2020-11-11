import numpy as np
from scipy.special import gamma as Gamma
from scipy.special import beta as B
from scipy.special import hyp2f1
from scipy.integrate import quad
from scipy.stats import beta as Beta
from wigner import R


def factorial(n):
    return Gamma(n + 1)


def Ul(l):
    """
    Return the transformation matrix from complex to real Ylms.
    
    """
    U = np.zeros((2 * l + 1, 2 * l + 1), dtype="complex128")
    for m in range(-l, l + 1):
        for mp in range(-l, l + 1):
            if mp < 0:
                term1 = 1j
            elif mp == 0:
                term1 = np.sqrt(2) / 2
            else:
                term1 = 1
            if (m > 0) and (mp < 0) and (mp % 2 == 0):
                term2 = -1
            elif (m > 0) and (mp > 0) and (mp % 2 != 0):
                term2 = -1
            else:
                term2 = 1
            U[l + m, l + mp] = (
                term1 * term2 * 1 / np.sqrt(2) * (int(m == mp) + int(m == -mp))
            )
    return U


def clmmpi(l, m, mp, i):
    if (m - mp - i) % 2 == 0:
        return (
            (-1) ** ((2 * l + 3 * m + mp - i) / 2)
            * np.sqrt(
                factorial(l - m)
                * factorial(l + m)
                * factorial(l - mp)
                * factorial(l + mp)
            )
            / (
                2 ** l
                * factorial((i - m - mp) / 2)
                * factorial((i + m + mp) / 2)
                * factorial((2 * l - i - m + mp) / 2)
                * factorial((2 * l - i + m - mp) / 2)
            )
        )
    else:
        return 0.0


def qli(l, i, alpha, beta):
    if i % 2 == 0:
        return B(alpha, l + beta - i / 2) * hyp2f1(
            -i / 2, alpha, l + alpha + beta - i / 2, -1
        )
    else:
        return 0.0


def rholm(l, m, alpha, beta, erl):
    term1 = 0
    for mp in range(-l, l + 1):
        term2 = 0
        for i in range(2 * l + 1):
            term2 += clmmpi(l, m, mp, i) * qli(l, i, alpha, beta)
        term1 += erl[l + mp] * np.exp(1j * np.pi / 2 * (m - mp)) * term2
    return term1 / B(alpha, beta)


def rhol(l, alpha, beta, erl):
    rho = np.zeros(2 * l + 1, dtype="complex128")
    for m in range(-l, l + 1):
        rho[l + m] = rholm(l, m, alpha, beta, erl)
    return rho


def elphi(l, alpha, beta, erl):
    U = Ul(l)
    return np.linalg.inv(U) @ rhol(l, alpha, beta, U @ erl)


def ephi(alpha, beta, er):
    lmax = int(np.sqrt(len(er)) - 1)
    e = []
    for l in range(lmax + 1):
        e.extend(elphi(l, alpha, beta, er[l ** 2 : (l + 1) ** 2]))
    e = np.array(e)
    assert np.max(np.abs(e.imag)) < 1e-15
    return e.real


def ephi_numerical(alpha, beta, er):

    lmax = int(np.sqrt(len(er)) - 1)
    N = (lmax + 1) ** 2
    e = np.zeros(N)

    for n in range(N):

        def func(phi):
            Rl = R(lmax, 0.5 * np.pi, phi, -0.5 * np.pi)
            Rs = np.zeros(N)
            for l in range(lmax + 1):
                i = slice(l ** 2, (l + 1) ** 2)
                Rs[i] = Rl[l] @ er[i]
            jac = 0.5 * np.abs(np.sin(phi))
            return Rs[n] * jac * Beta.pdf(np.cos(phi), alpha, beta)

        e[n] = quad(func, -np.pi / 2, np.pi / 2)[0]

    return e


def test_ephi(lmax=5, alpha=2.0, beta=5.0):
    np.random.seed(0)
    er = np.random.randn((lmax + 1) ** 2)
    assert np.allclose(ephi(alpha, beta, er), ephi_numerical(alpha, beta, er))