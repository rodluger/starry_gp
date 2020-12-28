from .size import SizeIntegral
from .latitude import LatitudeIntegral, gauss2beta
from .longitude import LongitudeIntegral
from .contrast import ContrastIntegral
from .flux import FluxIntegral
from .math import cho_factor, cho_solve, cast
from .defaults import defaults
from .ops import CheckBoundsOp, AlphaBetaOp
import theano.tensor as tt
from theano.ifelse import ifelse
import numpy as np


__all__ = ["StarryProcess"]


class StarryProcess(object):
    def __init__(
        self,
        r=defaults["r"],
        d=defaults["d"],
        c=defaults["c"],
        n=defaults["n"],
        u=defaults["u"],
        marginalize_over_inclination=defaults["marginalize_over_inclination"],
        normalized=defaults["normalized"],
        covpts=defaults["covpts"],
        **kwargs,
    ):
        """
        An interpretable Gaussian process for stellar light curves.

        Args:
            r (scalar, optional): The mean star spot radius in degrees.
                Default is %%defaults["r"]%%. Care should be taken when
                modeling very small spots, as the spherical
                harmonic expansion can typically only model features
                with radius on the order of ``180 / ydeg`` or larger.
                For the default spherical harmonic degree, the minimum
                radius is about 10 degrees. Values below this will
                typically lead to poor approximations, although the
                process will in general still be valid and numerically
                stable.
            d (scalar, optional): The half-width of the uniform prior
                on the spot radius in degrees. Default is %%defaults["d"]%%.
                If this value is zero, a delta-function prior centered at
                ``r`` is assumed.
            a (scalar, optional): Shape parameter of the spot latitude
                distribution. This is equal to the log of the ``alpha``
                parameter characterizing the Beta distribution in the
                cosine of the latitude, scaled to the range ``[0, 1]``.
                Default is %%defaults["a"]%%. Cannot be set if ``mu``
                and ``sigma`` are provided.
            b (scalar, optional): Shape parameter of the spot latitude
                distribution. This is equal to the log of the ``beta``
                parameter characterizing the Beta distribution in the
                cosine of the latitude, scaled to the range ``[0, 1]``.
                Default is %%defaults["b"]%%. Cannot be set if ``mu``
                and ``sigma`` are provided.
            mu (scalar, optional): Mode of the spot latitude
                distribution in degrees. Default is ``None``. If this parameter
                is set, ``sigma`` must also be set, and ``a`` and
                ``b`` cannot be provided.
            sigma (scalar, optional): Standard deviation of the spot latitude
                distribution in degrees. Default is ``None``. If this parameter
                is set, ``mu`` must also be set, and ``a`` and
                ``b`` cannot be provided.
            c (scalar, optional): The mean spot contrast as a fraction of
                the photospheric intensity. Default is %%defaults["c"]%%.
            n (scalar, optional): The total number of spots. Note that since a
                ``StarryProcess`` does not model spots as discrete features,
                this parameter will not generally have the expected behavior
                when sampling from the prior. In other words, it is unlikely
                that a draw with ``n=10`` will have ten distinct spots when
                visualizing the corresponding stellar surface, nor will it
                necessarily have more spots than a draw with (say) ``n=5``.
                However, this parameter *does* behave correctly in an
                inference setting: the posterior over ``n`` when doing 
                inference on an ensemble of light curves is meaningful and
                should have a mean (on average) equal to the true number of
                spots (assuming all other model assumptions are valid).
                Default is %%defaults["n"]%%.
            u (vector, optional): The limb darkening coefficients for the
                star. In the case of no limb darkening, set this to
                ``None``. Default is %%defaults["u"]%%.
            marginalize_over_inclination (bool, optional): Whether or not to
                marginalize over the inclination under the assumption of an
                isotropic prior. Recommended if there are no constraints on
                the inclination of the object. If this is set to ``True``,
                the value of the ``i`` keyword to several of the methods in 
                this class will be ignored. Default is 
                %%defaults["marginalize_over_inclination"]%%.
            normalized (bool, optional): Whether or not the flux observations 
                (passed in calls to ``log_likelihood`` and 
                ``sample_ylm_conditional``) are normalized. Usually, the
                true baseline in stellar photometry is unknown, as it
                requires knowledge of how bright the star would be in the
                absence of star spots. If the baseline is unknown
                (which is almost certainly the case), we recommend setting 
                this keyword to ``True`` and make sure observations are 
                mean- (or median-) normalized. 
                Alternatively, particularly when the amplitude of variability
                is large, you may set this to ``False`` and explicitly
                model the unknown baseline with a latent parameter *for
                each star* when doing inference. 
                Default is %%defaults["normalized"]%%.
            covpts (int, optional): The number of grid points on which to
                compute the kernel when ``marginalize_over_inclination`` is
                set to ``True``. Since the full covariance is expensive to
                compute, ``StarryProcess`` instead computes it on a uniform
                grid in phase lag and performs a cubic spline interpolation
                to obtain the covariance matrix. Increasing this number will
                improve the accuracy of the computation at the expense of
                greater runtime. Default is %%defaults["covpts"]%%.

        The following under-the-hood keyword arguments are also accepted,
        although changing them is not recommended unless you really understand
        what you are doing:

        Parameters:
            ydeg (int, optional): The spherical harmonic  degree of the 
                process. Default is %%defaults["ydeg"]%%. Decreasing this
                value will speed up computations but decrease the ability
                to model small features on the surface. Increasing this
                above the default value is not recommended, as it can lead
                to numerical instabilities.
            udeg (int, optional): The degree of limb darkening.
                Default is %%defaults["udeg"]%%. Changing this is currently
                supported, but it is likely that future releases will
                deprecate this in favor of always using quadratic limb 
                darkening, which can be analytically marginalized over.
            normalization_order (int, optional): Order of the series
                expansion for the normalized covariance. Default is
                %%defaults["normalization_order"]%%.
            normalization_zmax (float, optional): Maximum value of the
                expansion parameter ``z`` when computing the normalized
                covariance. Values above this threshold will result in 
                infinite variance and a log probability of ``-np.inf``. 
                Default is %%defaults["normalization_zmax"]%%.
            log_alpha_max (float, optional): The maximum value of 
                ``log(alpha)``. Default is %%defaults["log_alpha_max"]%%.
            log_beta_max (float, optional): The maximum value of ``log(beta)``. 
                Default is %%defaults["log_alpha_max"]%%.
            sigma_max (float, optional): The maximum value of the latitude 
                standard deviation in degrees. The latitude distribution 
                becomes extremely non-gaussian for high values of ``sigma``. 
                This value is used to penalize such distributions when 
                computing the jacobian of the transformation.
                Default is %%defaults["sigma_max"]%%.
            compile_args (list, optional): Additional arguments to be passed to
                the C compiler when compiling the ops for this class. Each
                entry in the list should be a tuple of ``(name, value)`` pairs.
                For possible options, see the macros under ``USER CONSTANTS``
                in the header file
                `starry_process/ops/include/constants.h 
                <https://github.com/rodluger/starry_process/blob/master/starry_process/ops/include/constants.h>`_.
            epsy (float, optional): A small number added to the diagonal of the
                spherical harmonic covariance matrix for stability.
                Default is %%defaults["epsy"]%%.
            epsy15 (float, optional): A small number added to terms in the 
                diagonal of the spherical harmonic covariance matrix 
                above degree ``15``, which become particularly unstable.
                Default is %%defaults["epsy15"]%%.
        """
        # Latitude hyperparameters
        mu = kwargs.pop("mu", None)
        sigma = kwargs.pop("sigma", None)
        if mu is None and sigma is None:
            # User did not provide either `mu` or `sigma`
            # User may have provided `a` and/or `b`
            a = kwargs.pop("a", defaults["a"])
            b = kwargs.pop("b", defaults["b"])
        elif (
            kwargs.get("a", None) is None and kwargs.get("b", None) is None
        ) and (mu is not None and sigma is not None):
            # User did not provide `a` and did not provide `b`
            # User provided `mu` and `sigma`
            a, b = gauss2beta(mu, sigma)
        else:
            # Invalid or ambiguous combination
            raise ValueError(
                "Must provide either `a` and `b` *or* `mu` and `sigma`."
            )

        # Spherical harmonic degree of the process
        self._ydeg = int(kwargs.get("ydeg", defaults["ydeg"]))
        assert self._ydeg >= 5, "Degree of map must be >= 5."
        self._udeg = int(kwargs.get("udeg", defaults["udeg"]))
        assert self._udeg >= 0, "Degree of limb darkening must be >= 0."
        self._nylm = (self._ydeg + 1) ** 2
        self._covpts = int(covpts)
        self._kwargs = kwargs

        # Is the flux normalized?
        self._normalized = normalized
        self._normN = kwargs.get(
            "normalization_order", defaults["normalization_order"]
        )
        self._normzmax = kwargs.get(
            "normalization_zmax", defaults["normalization_zmax"]
        )
        self._get_alpha_beta = AlphaBetaOp(self._normN)

        # Initialize the Ylm integral ops
        self._size = SizeIntegral(r, d, **kwargs)
        self._latitude = LatitudeIntegral(a, b, child=self._size, **kwargs)
        self._longitude = LongitudeIntegral(child=self._latitude, **kwargs)
        self._contrast = ContrastIntegral(
            c, n, child=self._longitude, **kwargs
        )

        # Mean and covariance of the Ylm process
        self._mean_ylm = self._contrast.mean()
        self._cov_ylm = self._contrast.cov()
        self._cho_cov_ylm = cho_factor(self._cov_ylm)
        self._LInv = cho_solve(
            self._cho_cov_ylm, tt.eye((self._ydeg + 1) ** 2)
        )
        self._LInvmu = cho_solve(self._cho_cov_ylm, self._mean_ylm)

        # Initialize the flux integral op
        self._marginalize_over_inclination = marginalize_over_inclination
        self._flux = FluxIntegral(
            self._mean_ylm,
            self._cov_ylm,
            u=u,
            marginalize_over_inclination=self._marginalize_over_inclination,
            covpts=self._covpts,
            **self._kwargs,
        )

        # Seed the randomizer
        self.random = tt.shared_randomstreams.RandomStreams(
            kwargs.get("seed", 0)
        )

    @property
    def ydeg(self):
        """The spherical harmonic degree of the surface map expansion."""
        return self._ydeg

    @property
    def covpts(self):
        """
        The number of interpolation points for the covariance matrix
        when ``marginalize_over_inclination`` is ``True``.

        """
        return self._covpts

    @property
    def normalized(self):
        """
        Whether or not the process is modeling light curves that have
        been normalized to the (sample) mean (or median).

        """
        return self._normalized

    @property
    def marginalize_over_inclination(self):
        """
        Whether or not the process marginalizes over inclination under
        an isotropic prior.

        """
        return self._marginalize_over_inclination

    @property
    def latitude(self):
        """
        The latitude distribution integral.

        This integral is used internally to compute the mean and covariance
        of the Gaussian process, but some of its methods may be of interest
        to the user:

        .. autofunction:: starry_process.latitude.pdf
        .. autofunction:: starry_process.latitude.sample

        """
        return self._latitude

    @property
    def longitude(self):
        """
        The longitude distribution integral.

        This integral is used internally to compute the mean and covariance
        of the Gaussian process, but some of its methods may be of interest
        to the user:

        .. autofunction:: starry_process.longitude.pdf
        .. autofunction:: starry_process.longitude.sample

        """
        return self._longitude

    @property
    def contrast(self):
        """The contrast distribution integral (not *really* user-facing)."""
        return self._contrast

    @property
    def flux(self):
        """The flux integral  (not *really* user-facing)."""
        return self._flux

    @property
    def mean_ylm(self):
        """
        The mean spherical harmonic coefficient vector.

        """
        return self._mean_ylm

    @property
    def cov_ylm(self):
        """
        The spherical harmonic covariance matrix.
        
        """
        return self._cov_ylm

    @property
    def cho_cov_ylm(self):
        """
        The lower Cholesky factorization of the spherical harmonic covariance.
        
        """
        return self._cho_cov_ylm

    def sample_ylm(self, nsamples=1):
        """
        Draw samples from the prior.

        Args:
            nsamples (int, optional): The number of samples to draw. Default 1.

        """
        u = self.random.normal((self._nylm, nsamples))
        return tt.transpose(
            self.mean_ylm[:, None] + tt.dot(self.cho_cov_ylm, u)
        )

    def sample_ylm_conditional(
        self,
        t,
        flux,
        data_cov,
        i=defaults["i"],
        p=defaults["p"],
        baseline_mean=defaults["baseline_mean"],
        baseline_var=defaults["baseline_var"],
        nsamples=1,
    ):
        """
        Draw samples from the process conditioned on observed flux values.

        Args:
            t (vector): The time array in arbitrary units.
            flux (vector): The array of observed flux values in arbitrary 
                units. In general, the flux should be either mean- or
                median-normalized with zero baseline. If the raw photometry
                is measured in ``counts``, users should compute the ``flux``
                from

                    .. code-block:: python
                    
                        flux = counts / np.mean(counts) - 1

                If the baseline is something else (such as unity), users
                may alternatively set the ``baseline_mean`` parameter to
                reflect that.
                Note that if the ``normalized`` keyword passed to this class
                is ``False`` (not recommended for real data), then the flux
                should instead be normalized to the true baseline (i.e., the
                counts one would measure if the star had no spots). 
            data_cov (scalar, vector, or matrix): The data covariance 
                matrix. This may be a scalar equal to the (homoscedastic) 
                variance of the data, a vector equal to the variance of each 
                observation, or a matrix equal to the full covariance of the 
                dataset.
            i (scalar, optional): The inclination of the star in degrees.
                Default is %%defaults["i"]%%. If ``marginalize_over_inclination``
                is set, this argument is ignored.
            p (scalar, optional): The rotational period of the star in the same
                units as ``t``. Default is %%defaults["p"]%%.
            baseline_mean (scalar or vector, optional): The flux baseline to
                subtract when computing the GP likelihood. Default is 
                %%defaults["baseline_mean"]%%.
            baseline_var (scalar or matrix): The variance (square of the
                uncertainty) on the true value of the baseline. This is added
                to every element of the GP covariance matrix in order to
                marginalize over the baseline uncertainty. This may also be a
                matrix specifying the covariance due to additional correlated
                noise unrelated to star spot variability. Default is
                %%defaults["baseline_var"]%%.
            nsamples (int, optional): The number of samples to draw. Default 1.
            
        """
        # TODO
        if self._marginalize_over_inclination:
            raise NotImplementedError(
                "Not yet implemented when marginalizing over inclination."
            )

        # TODO
        if self._normalized:
            raise NotImplementedError(
                "Not yet implemented when the flux is normalized."
            )

        # Get the full data covariance
        flux = cast(flux)
        data_cov = cast(data_cov)
        if data_cov.ndim == 0:
            C = data_cov * tt.eye(flux.shape[0])
        elif data_cov.ndim == 1:
            C = tt.diag(data_cov)
        else:
            C = data_cov

        # TODO: If we're not marginalizing over the baseline,
        # we don't need to instantiate the full covariance matrix!

        # Marginalize over the baseline; note we're adding
        # `baseline_var` to *every* entry in the covariance matrix
        C += baseline_var

        # Compute C^-1 . A
        A = self._flux._design_matrix(t, i, p)
        cho_C = cho_factor(C)
        CInvA = cho_solve(cho_C, A)

        # Compute W = A^T . C^-1 . A + L^-1
        W = tt.dot(tt.transpose(A), CInvA) + self._LInv

        # Compute the conditional mean and covariance
        cho_W = cho_factor(W)
        M = cho_solve(cho_W, tt.transpose(CInvA))
        ymu = tt.dot(M, flux - baseline_mean) + cho_solve(cho_W, self._LInvmu)
        ycov = cho_solve(cho_W, tt.eye(cho_W.shape[0]))
        cho_ycov = cho_factor(ycov)

        # Sample from it
        u = self.random.normal((self._nylm, nsamples))
        return tt.transpose(ymu[:, None] + tt.dot(cho_ycov, u))

    def mean(self, t, i=defaults["i"], p=defaults["p"]):
        """
        The GP flux mean vector.

        Args:
            t (vector): The time array in arbitrary units.
            i (scalar, optional): The inclination of the star in degrees.
                Default is %%defaults["i"]%%. If ``marginalize_over_inclination``
                is set, this argument is ignored.
            p (scalar, optional): The rotational period of the star in the same
                units as ``t``. Default is %%defaults["p"]%%.           
        """
        if self._normalized:
            return tt.zeros_like(cast(t, vectorize=True))
        else:
            return self._flux.mean(t, i, p)

    def cov(self, t, i=defaults["i"], p=defaults["p"]):
        """
        The GP flux covariance matrix.

        Args:
            t (vector): The time array in arbitrary units.
            i (scalar, optional): The inclination of the star in degrees.
                Default is %%defaults["i"]%%. If ``marginalize_over_inclination``
                is set, this argument is ignored.
            p (scalar, optional): The rotational period of the star in the same
                units as ``t``. Default is %%defaults["p"]%%.           
        """
        if self._normalized:
            cov = self._flux.cov(t, i, p)
            mean = self._flux.mean(t, i, p)[0]
            return self._normalize(1.0 + mean, cov)
        else:
            return self._flux.cov(t, i, p)

    def _normalize(self, mu, Sig):
        """
        Return the series expansion of the normalized covariance matrix.

        See Luger (2020) for details.

        """
        # Terms
        K = Sig.shape[0]
        j = tt.ones((K, 1))
        m = tt.mean(Sig)
        q = tt.dot(Sig, j) / (K * m)
        z = m / mu ** 2
        p = j - q
        alpha, beta, _, _ = self._get_alpha_beta(z)

        # We're done
        ppT = tt.dot(p, tt.transpose(p))
        qqT = tt.dot(q, tt.transpose(q))
        normSig = (alpha / mu ** 2) * Sig + z * (
            (alpha + beta) * ppT - alpha * qqT
        )
        return ifelse(tt.gt(z, self._normzmax), Sig * np.inf, normSig)

    def sample(
        self,
        t,
        i=defaults["i"],
        p=defaults["p"],
        nsamples=1,
        eps=defaults["eps"],
    ):
        """
        Draw samples from the prior distribution over light curves.

        Args:
            t (vector): The time array in arbitrary units.
            i (scalar, optional): The inclination of the star in degrees.
                Default is %%defaults["i"]%%. If ``marginalize_over_inclination``
                is set, this argument is ignored.
            p (scalar, optional): The rotational period of the star in the same
                units as ``t``. Default is %%defaults["p"]%%.
            nsamples (int, optional): The number of samples to draw. Default 1.
            eps (float, optional): A small number added to the diagonal of the
                flux covariance matrix when marginalizing over inclination
                for extra stability. Default is %%defaults["eps"]%%.
        """
        if self._marginalize_over_inclination:
            t = cast(t)
            u = self.random.normal((t.shape[0], nsamples))
            cho_cov = cho_factor(self.cov(t, i, p) + eps * tt.eye(t.shape[0]))
            return tt.transpose(
                self.mean(t, i, p)[:, None] + tt.dot(cho_cov, u)
            )
        else:
            ylm = self.sample_ylm(nsamples=nsamples)
            return tt.transpose(
                tt.dot(self._flux._design_matrix(t, i, p), tt.transpose(ylm))
            )

    def log_jac(self):
        """
        The log of the absolute value of the determinant of the Jacobian matrix.

        The spot latitude is Beta-distributed with shape parameters
        ``a`` and ``b``, equal to the log of the traditional ``alpha`` 
        and ``beta`` parameters of the Beta distribution, normalized and scaled
        to the range ``[0, 1]``. From Bayes' theorem, the joint posterior in 
        these two quantities is

            .. math::

                p\\big(a, b \\big| data\\big) \\sim 
                p\\big(data \\big| a, b\\big) \\times  p(a, b)

        However, this is a rather awkward parametrization, since it's hard to
        visualize how exactly ``a`` and ``b`` (or ``alpha`` and ``beta``) 
        determine quantities we actually care about, such as the mean ``mu`` and 
        standard deviation ``sigma`` of the distribution. This parameterization 
        is especially clumsy when it comes to specifying the prior ``p(a, b)``, 
        since any prior on these quantities will imply a very different prior 
        on ``mu`` and ``sigma``. In most cases, we probably want to place a prior 
        on ``mu`` and ``sigma`` directly. We can do this by noting that
        
            .. math::

                p(a, b) = p(\\mu, \\sigma) \\times J

        where

            .. math::

                J = \\bigg| \\frac{\\partial{\\mu}}{\\partial{a}} \\times 
                           \\frac{\\partial{\\sigma}}{\\partial{b}} -
                           \\frac{\\partial{\\mu}}{\\partial{b}} \\times 
                           \\frac{\\partial{\\sigma}}{\\partial{a}} \\bigg|

        is the absolute value of the determinant of the Jacobian matrix.

        Thus, to enforce a uniform prior on ``mu`` and ``sigma``, sample
        in ``a`` and ``b`` with a uniform prior in the range ``[0, 1]``
        and multiply the PDF by ``J``. Since we're in log space, you'll want 
        to add ``log J`` (the value returned by this function) to the
        log likelihood.

        """
        return self._latitude.log_jac()

    def log_likelihood(
        self,
        t,
        flux,
        data_cov,
        i=defaults["i"],
        p=defaults["p"],
        baseline_mean=defaults["baseline_mean"],
        baseline_var=defaults["baseline_var"],
    ):
        """
        Compute the log marginal likelihood of a light curve.

        Args:
            t (vector): The time array in arbitrary units.
            flux (vector): The array of observed flux values in arbitrary 
                units. In general, the flux should be either mean- or
                median-normalized with zero baseline. If the raw photometry
                is measured in ``counts``, users should compute the ``flux``
                from

                    .. code-block:: python
                    
                        flux = counts / np.mean(counts) - 1

                If the baseline is something else (such as unity), users
                may alternatively set the ``baseline_mean`` parameter to
                reflect that.
                Note that if the ``normalized`` keyword passed to this class
                is ``False`` (not recommended for real data), then the flux
                should instead be normalized to the true baseline (i.e., the
                counts one would measure if the star had no spots). 
            data_cov (scalar, vector, or matrix): The data covariance 
                matrix. This may be a scalar equal to the (homoscedastic) 
                variance of the data, a vector equal to the variance of each 
                observation, or a matrix equal to the full covariance of the 
                dataset.
            i (scalar, optional): The inclination of the star in degrees.
                Default is %%defaults["i"]%%. If ``marginalize_over_inclination``
                is set, this argument is ignored.
            p (scalar, optional): The rotational period of the star in the same
                units as ``t``. Default is %%defaults["p"]%%.
            baseline_mean (scalar or vector, optional): The flux baseline to
                subtract when computing the GP likelihood. Default is 
                %%defaults["baseline_mean"]%%.
            baseline_var (scalar or matrix): The variance (square of the
                uncertainty) on the true value of the baseline. This is added
                to every element of the GP covariance matrix in order to
                marginalize over the baseline uncertainty. This may also be a
                matrix specifying the covariance due to additional correlated
                noise unrelated to star spot variability. Default is
                %%defaults["baseline_var"]%%.

        Returns:
            The log marginal likelihood of the `flux` vector conditioned on
            the current properties of the model. This is the likelihood 
            marginalized over all possible spherical harmonic vectors.

        """
        # Get the flux gp mean and covariance
        gp_mean = self.mean(t, i=i, p=p)
        gp_cov = self.cov(t, i=i, p=p)
        K = gp_mean.shape[0]

        # Get the full data covariance
        data_cov = cast(data_cov)
        if data_cov.ndim == 0:
            C = data_cov * tt.eye(K)
        elif data_cov.ndim == 1:
            C = tt.diag(data_cov)
        else:
            C = data_cov

        # Covariances add!
        gp_cov += C

        # Marginalize over the baseline; note that we are adding
        # `baseline_var` to *every* entry in the covariance matrix
        # To see why, c.f. Equation (4) in Luger et al. (2017),
        # where `A` is a column vector of ones (our baseline regressor)
        # and `Lambda` is our prior baseline variance
        gp_cov += baseline_var

        # Cholesky factorization
        cho_gp_cov = cho_factor(gp_cov)

        # Compute the marginal likelihood
        r = tt.reshape(flux - gp_mean - baseline_mean, (-1, 1))
        lnlike = -0.5 * tt.dot(tt.transpose(r), cho_solve(cho_gp_cov, r))
        lnlike -= tt.sum(tt.log(tt.diag(cho_gp_cov)))
        lnlike -= 0.5 * K * tt.log(2 * np.pi)

        # NANs --> -inf
        return ifelse(tt.isnan(lnlike[0, 0]), -np.inf, lnlike[0, 0])

    def __add__(self, other):
        return StarryProcessSum(self, other)

    def __radd__(self, other):
        if other == 0:
            return self
        else:
            return self.__add__(other)


class StarryProcessSum(StarryProcess):
    def __init__(self, first, second):
        # Verify props
        assert isinstance(
            second, (StarryProcess, StarryProcessSum)
        ), "Can only add instances of `StarryProcess` to each other."
        assert first._ydeg == second._ydeg, "Mismatch in `ydeg`."
        assert (
            first._normalized == second._normalized
        ), "Mismatch in `normalized`."
        assert (
            first._marginalize_over_inclination
            == second._marginalize_over_inclination
        ), "Mismatch in `marginalize_over_inclination`."
        assert first._covpts == second._covpts, "Mismatch in `covpts`."
        self._ydeg = first._ydeg
        self._nylm = first._nylm
        self._normalized = first._normalized
        self._marginalize_over_inclination = (
            first._marginalize_over_inclination
        )
        self._covpts = first._covpts
        self._normN = first._normN
        self._normzmax = first._normzmax
        self._get_alpha_beta = first._get_alpha_beta
        self._kwargs = first._kwargs
        self.random = first.random

        # Sum the random variables
        self._mean_ylm = first._mean_ylm + second._mean_ylm
        self._cov_ylm = first._cov_ylm + second._cov_ylm
        self._cho_cov_ylm = cho_factor(self._cov_ylm)
        self._LInv = cho_solve(
            self._cho_cov_ylm, tt.eye((self._ydeg + 1) ** 2)
        )
        self._LInvmu = cho_solve(self._cho_cov_ylm, self._mean_ylm)

        # Initialize the flux integral op
        self._flux = FluxIntegral(
            self._mean_ylm,
            self._cov_ylm,
            marginalize_over_inclination=self._marginalize_over_inclination,
            covpts=self._covpts,
            **self._kwargs,
        )
