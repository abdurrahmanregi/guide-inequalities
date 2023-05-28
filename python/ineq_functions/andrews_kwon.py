import numpy as np

from .moment import m_function, m_hat


def rhat(
    W_data: np.ndarray,
    A_matrix: np.ndarray,
    theta: np.ndarray,
    J0_vec: np.ndarray,
    Vbar: float,
    IV_matrix: np.ndarray | None = None,
    grid0: int | str = "all",
    adjust: np.ndarray = np.array([0]),
) -> float:
    """Find the points of the rhat vector as in Andrews and Kwon (2023)

    Parameters
    ----------
    W_data : array_like
        n x J0 matrix of product portfolio.
    A_matrix : array_like
        n x (J0 + 1) matrix of estimated revenue differential.
    theta : array_like
        d_theta x 1 parameter of interest.
    J0_vec : array_like
        J0 x 2 matrix of ownership by two firms.
    Vbar : float
        Tuning parameter as in Assumption 4.2
    IV_matrix : array_like, optional
        n x d_IV matrix of instruments or None if no instruments are used.
    grid0 : {1, 2, 'all'}, default='all'
        Grid direction to use for the estimation of the model.
    adjust : array_like, optional
        Adjustment to the m_hat vector. Default is 0.

    Returns
    -------
    float
        Value of rhat for a given parameter theta.
    """
    # note we use -m_function
    X_data = -1 * m_function(W_data, A_matrix, theta, J0_vec, Vbar, IV_matrix, grid0)
    m_hat0 = m_hat(X_data)
    return np.max(-1 * (m_hat0 + adjust).clip(max=0))


def an_vec(
    aux1_var: np.ndarray,
    hat_r_inf: float,
    W_data: np.ndarray,
    A_matrix: np.ndarray,
    theta_grid: np.ndarray,
    J0_vec: np.ndarray,
    Vbar: float,
    IV_matrix,
    grid0: int,
    bootstrap_replications: int | None = None,
    rng_seed: int | None = None,
    bootstrap_indices: np.ndarray | None = None,
) -> np.ndarray:
    n = A_matrix.shape[0]
    tau_n = np.sqrt(np.log(n))
    kappa_n = np.sqrt(np.log(n))

    boole_of_interest = (aux1_var <= tau_n / np.sqrt(n)) | (aux1_var == 1)
    theta_of_interest = theta_grid[boole_of_interest]

    if bootstrap_indices is None:
        BB = bootstrap_replications
    else:
        BB = bootstrap_indices.shape[0]

    an_mat = np.zeros((BB, theta_of_interest.shape[0]))

    for i, t in enumerate(theta_of_interest):
        the_theta = np.zeros(2)
        the_theta[grid0 - 1] = t

        X_data = -1 * m_function(
            W_data, A_matrix, the_theta, J0_vec, Vbar, IV_matrix, grid0
        )
        b0_vec = std_b_vec(X_data, bootstrap_replications, rng_seed, bootstrap_indices)
        std_b2 = b0_vec[1, :]
        std_b3 = b0_vec[2, :]
        an_mat[:, i] = an_star(
            X_data,
            std_b2,
            std_b3,
            kappa_n,
            hat_r_inf,
            bootstrap_replications,
            rng_seed,
            bootstrap_indices,
        )

    return np.min(an_mat, axis=1)


def an_star(
    X_data: np.ndarray,
    std_b2: np.ndarray,
    std_b3: np.ndarray,
    kappa_n: float,
    hat_r_inf: float,
    bootstrap_replications: int | None = None,
    rng_seed: int | None = None,
    bootstrap_indices: np.ndarray | None = None,
) -> np.ndarray:
    n = X_data.shape[0]
    k = X_data.shape[1]

    # Obtain random numbers for the bootstrap
    if bootstrap_indices is None:
        if bootstrap_replications is None:
            raise ValueError(
                "bootstrap_replications must be specified if bootstrap_indices is not."
            )
        else:
            if rng_seed is not None:
                np.random.seed(rng_seed)
            bootstrap_indices = np.random.randint(
                0, n, size=(bootstrap_replications, n)
            )

    # Step 1: Obtain hat_j_r(theta) as in (4.24) in Andrews and Kwon (2023)
    m_hat0 = m_hat(X_data)
    r_hat_vec = -1 * (m_hat0).clip(max=0)
    r_hat0 = np.max(r_hat_vec)

    # Obtain set of indicies for which this inequality holds
    hat_j_r = (r_hat_vec >= r_hat0 - std_b3 * kappa_n / np.sqrt(n)).nonzero()[0]

    # Step 2: Compute the objective function
    hat_b = np.sqrt(n) * (r_hat_vec - hat_r_inf) - std_b3 * kappa_n
    xi_a = (np.sqrt(n) * (r_hat_vec - hat_r_inf)) / (std_b3 * kappa_n)

    phi_n = np.zeros_like(xi_a)
    phi_n[xi_a > 1] = np.inf

    # Use the bootstrap
    vstar = np.sqrt(n) * (m_hat(X_data[bootstrap_indices, :], axis=1) - m_hat0)

    # Obtain plus-minus variable based on sign of vstar (negative if vstar >= 0)
    pm = 1 - 2 * (vstar >= 0)

    hat_hi_star = (
        -1 * (np.sqrt(n) * m_hat0 + pm * std_b2 * kappa_n + vstar).clip(max=0)
    ) - (-1 * (np.sqrt(n) * m_hat0 + pm * std_b2 * kappa_n).clip(max=0))

    aux_vec2 = np.zeros((vstar.shape[0], hat_j_r.shape[0]))

    for i, j in enumerate(hat_j_r):
        hat_bnew = hat_b
        hat_bnew[j] = phi_n[j]
        aux_vec2[:, i] = np.max(hat_bnew + hat_hi_star, axis=1)

    return np.min(aux_vec2, axis=1)


def cvalue_SPUR1(
    X_data: np.ndarray,
    alpha: float,
    an_vec: np.ndarray,
    bootstrap_replications: int | None = None,
    rng_seed: int | None = None,
    bootstrap_indices: np.ndarray | None = None,
) -> float:
    """Calculate the c-value for the SPUR1 test statistic presented in
    Section 4 in Andrews and Kwon (2023).

    Parameters
    ----------
    X_data : array_like
        Matrix of the moment functions with n rows (output of
        :func:`ineq_functions.m_function`).
    alpha : float
        Significance level for the first stage test.
    an_vec : array_like
        Vector as in eq. (4.25) in Andrews and Kwon (2023).
    bootstrap_replications : int, optional
        Number of bootstrap replications. Required if bootstrap_indices
        is not specified.
    rng_seed : int, optional
        Random number generator seed (for replication purposes). If not
        specified, the system seed will be used as-is.
    bootstrap_indices : array_like, optional
        Integer array of shape (bootstrap_replications, n) for the bootstrap
        replications. If this is specified, bootstrap_replications and rng_seed
        will be ignored. If this is not specified, bootstrap_replications is
        required.

    Returns
    -------
    float
        The c-value for the SPUR1 test statistic.
    """
    n = X_data.shape[0]  # sample size
    kappa_n = np.sqrt(np.log(n))  # tuning parameter

    # Step 1: Computation of Bootstrap statistic

    std_b0 = std_b_vec(X_data, bootstrap_replications, rng_seed, bootstrap_indices)
    std_b1 = std_b0[0, :]
    tn_vec = tn_star(
        X_data, std_b1, kappa_n, bootstrap_replications, rng_seed, bootstrap_indices
    )

    sn_star_vec = np.max(-1 * (tn_vec + an_vec[:, np.newaxis]).clip(max=0), axis=1)

    # Step 2: Computation of critical value
    # We use the midpoint interpolation method for consistency with MATLAB
    c_value = np.quantile(sn_star_vec, 1 - alpha, interpolation="midpoint")

    return c_value


def std_b_vec(
    X_data: np.ndarray,
    bootstrap_replications: int | None = None,
    rng_seed: int | None = None,
    bootstrap_indices: np.ndarray | None = None,
) -> np.ndarray:
    """Compute scaling factors (std_1, std_2, std_3) as in (4.19), (4.21),
    and (4.22) as in Andrews and Kwon (2023).

    Parameters
    ----------
    X_data : array_like
        Matrix of the moment functions with n rows (output of
        :func:`ineq_functions.m_function`).
    bootstrap_replications : int, optional
        Number of bootstrap replications. Required if bootstrap_indices
        is not specified.
    rng_seed : int, optional
        Random number generator seed (for replication purposes). If not
        specified, the system seed will be used as-is.
    bootstrap_indices : array_like, optional
        Integer array of shape (bootstrap_replications, n) for the bootstrap
        replications. If this is specified, bootstrap_replications and rng_seed
        will be ignored. If this is not specified, bootstrap_replications is
        required.

    Returns
    -------
    array_like
        Array of shape (3, k) with the scaling factors.
    """
    iota = 1e-6  # small number as in eq (4.16) and Section 4.7.1
    n = X_data.shape[0]  # sample size

    # Obtain random numbers for the bootstrap
    if bootstrap_indices is None:
        if bootstrap_replications is None:
            raise ValueError(
                "bootstrap_replications must be specified if bootstrap_indices is not."
            )
        else:
            if rng_seed is not None:
                np.random.seed(rng_seed)
            bootstrap_indices = np.random.randint(
                0, n, size=(bootstrap_replications, n)
            )

    # Axis 0 is the bootstrap replications. So we specify axis=1
    mhat_star_vec = m_hat(X_data[bootstrap_indices, :], axis=1)

    # Get repeated terms
    mhat_star_clip = mhat_star_vec.clip(max=0)
    mn_star_vec = np.min(mhat_star_clip, axis=1)

    # Compute the scaling factors to be clipped below at iota
    vec_1 = np.sqrt(n) * (mhat_star_vec - mn_star_vec[:, np.newaxis])
    vec_2 = np.sqrt(n) * mhat_star_vec
    vec_3 = np.sqrt(n) * (mn_star_vec[:, np.newaxis] - mhat_star_clip)

    std_b = np.vstack(
        (
            np.std(vec_1, axis=0).clip(min=iota),
            np.std(vec_2, axis=0).clip(min=iota),
            np.std(vec_3, axis=0).clip(min=iota),
        )
    )

    return std_b


def tn_star(
    X_data: np.ndarray,
    std_b1: np.ndarray,
    kappa_n: float,
    bootstrap_replications: int | None = None,
    rng_seed: int | None = None,
    bootstrap_indices: np.ndarray | None = None,
) -> np.ndarray:
    """Compute the tn* statistic as in (4.24) as in Andrews and Kwon (2023).

    Parameters
    ----------
    X_data : array_like
        Matrix of the moment functions with n rows (output of
        :func:`ineq_functions.m_function`).
    std_b1 : array_like
        Array of shape (1, k, 1) with the first scaling factor.
    kappa_n : float
        Tuning parameter as in (4.23).
    bootstrap_replications : int, optional
        Number of bootstrap replications. Required if bootstrap_indices
        is not specified.
    rng_seed : int, optional
        Random number generator seed (for replication purposes). If not
        specified, the system seed will be used as-is.
    bootstrap_indices : array_like, optional
        Integer array of shape (bootstrap_replications, n) for the bootstrap
        replications. If this is specified, bootstrap_replications and rng_seed
        will be ignored. If this is not specified, bootstrap_replications is
        required.

    Returns
    -------
    array_like
        Array of shape (bootstrap_replications, k) with the tn* statistics.
    """
    n = X_data.shape[0]  # sample size

    # Obtain random numbers for the bootstrap
    if bootstrap_indices is None:
        if bootstrap_replications is None:
            raise ValueError(
                "bootstrap_replications must be specified if bootstrap_indices is not."
            )
        else:
            if rng_seed is not None:
                np.random.seed(rng_seed)
            bootstrap_indices = np.random.randint(
                0, n, size=(bootstrap_replications, n)
            )

    m_hat0 = m_hat(X_data)
    r_hat_vec = -1 * m_hat0.clip(max=0)
    r_hat = np.max(r_hat_vec)

    xi_n = (np.sqrt(n) * (m_hat0 + r_hat)) / (std_b1 * kappa_n)
    phi_n = np.zeros_like(xi_n)
    phi_n[xi_n > 1] = np.inf

    # Combining (4.17) and (4.18) from Andrews and Kwon (2023)
    tn_star_vec = (
        np.sqrt(n) * (m_hat(X_data[bootstrap_indices, :], axis=1) - m_hat0) + phi_n
    )

    return tn_star_vec
