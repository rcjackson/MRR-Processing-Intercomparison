"""Compute rainfall rate from an IMProToo MRR-2 NetCDF.

For each (time, range) gate, invert the dealiased Doppler spectrum into a
drop-size distribution and integrate it to a rainfall rate, assuming the
radar points at zenith (Doppler velocity == drop terminal fall speed).

Chain:
  v_doppler -> D (inverted Atlas et al. 1973, with height density correction)
  eta(v)    -> N(D) dD  via N(D) dD = eta / sigma_b(D)
  R         = 6 pi * 1e5 * sum( D^3 * v * N(D) dD )        [mm/h, SI inside]

IMProToo's `eta` is the volume reflectivity per Doppler bin in m^-1 (SI),
despite a misleading units attribute of "mm^6 m^-3" in the file.
Sign convention: positive Doppler velocity = downward (falling).
"""

import numpy as np
import xarray as xr
import miepython as mp

LAM_M = 0.012413766376811594          # MRR-2 wavelength, m (24.15 GHz)
M_WATER = 6.417 - 2.758j               # water refractive index used in raprom.py
RHO0 = 1.225                           # sea-level air density, kg/m^3
SCALE_HEIGHT = 8400.0                  # isothermal atmosphere scale height, m


def air_density(h_m):
    return RHO0 * np.exp(-np.asarray(h_m) / SCALE_HEIGHT)


def diameter_from_velocity(v_ms, h_m):
    """Invert Atlas et al. (1973) with Foote & du Toit (1969) density correction.

    v_obs(h) = v_atlas(D) * (rho0/rho(h))^0.4
    Returns NaN where v is outside the physical range (0, 9.65) m/s.
    """
    rho = air_density(h_m)
    v_sl = v_ms * (rho / RHO0) ** 0.4         # sea-level-equivalent fall speed
    with np.errstate(invalid="ignore", divide="ignore"):
        arg = (9.65 - v_sl) / 10.3
        D = np.where(arg > 0, -np.log(arg) / 0.6, np.nan)
    return D                                  # mm


def backscatter_xsection_grid(D_mm, lam_m=LAM_M, m=M_WATER):
    """Mie backscatter cross-section [mm^2] on a 1-D diameter grid."""
    lam_mm = lam_m * 1000.0
    sigma = np.empty_like(D_mm, dtype=float)
    for i, D in enumerate(D_mm):
        if not np.isfinite(D) or D <= 0:
            sigma[i] = np.nan
            continue
        r_mm = D / 2.0
        x = 2 * np.pi * r_mm / lam_mm
        _, _, qback, _ = mp.efficiencies_mx(m, x)
        sigma[i] = qback * np.pi * r_mm ** 2
    return sigma


def rainrate_from_improtoo(ds, vmin=0.1, vmax=9.6):
    """Rainfall rate [mm/h] on the (time, range) grid of an IMProToo dataset.

    Parameters
    ----------
    ds : xarray.Dataset
        IMProToo output, must contain eta, etaMask, velocity, height.
    vmin, vmax : float
        Doppler velocity bounds for rain bins (Atlas inversion is only
        well-defined for 0 < v < 9.65 m/s).
    """
    v = ds["velocity"].values.astype(float)            # (Nv,) m/s
    h = ds["height"].values.astype(float)              # (T, R) m
    eta = ds["eta"].values.astype(float)               # (T, R, Nv) m^-1 (SI!)
    mask = ds["etaMask"].values.astype(bool)           # True = masked/invalid
    eta = np.where(mask, np.nan, eta)

    # Only positive (downward) Doppler bins within Atlas validity range
    rain_bins = (v > vmin) & (v < vmax)

    # D(v, h): same Doppler bin maps to slightly different D at different heights
    D_mm = diameter_from_velocity(v[None, None, :], h[:, :, None])   # (T, R, Nv)

    # Pre-compute sigma_b on a fine D grid, then interpolate to D(v,h)
    D_grid = np.linspace(0.05, 7.0, 1400)                            # mm
    sigma_grid_mm2 = backscatter_xsection_grid(D_grid)               # mm^2
    sigma_mm2 = np.interp(D_mm, D_grid, sigma_grid_mm2,
                          left=np.nan, right=np.nan)
    sigma_m2 = sigma_mm2 * 1e-6                                      # m^2

    # N(D) dD per Doppler bin, in m^-3 (no wavelength factor: SI eta = sigma * NdD)
    NdD = eta / sigma_m2

    # Restrict to rain bins; zero-out everything else for the sum
    NdD = np.where(rain_bins[None, None, :], NdD, 0.0)
    NdD = np.where(np.isfinite(NdD), NdD, 0.0)

    # Zenith MRR: observed Doppler = terminal fall speed at this height
    v_b = np.broadcast_to(v[None, None, :], D_mm.shape)
    D_m = np.where(np.isfinite(D_mm), D_mm * 1e-3, 0.0)              # m
    integrand = D_m ** 3 * v_b * NdD                                 # m^3 * m/s * m^-3 = m/s

    # m/s -> mm/h: factor 3.6e6; with (pi/6) sphere volume: 6e5 * pi
    R = 6.0e5 * np.pi * integrand.sum(axis=-1)                       # mm/h

    # Mark gates with no valid rain bins as NaN rather than 0
    valid_any = np.isfinite(eta) & rain_bins[None, None, :]
    no_valid_gate = ~valid_any.any(axis=-1)
    R = np.where(no_valid_gate, np.nan, R)

    return xr.DataArray(
        R,
        dims=("time", "range"),
        coords={
            "time": ds["time"],
            "range": ds["range"],
            "height": (("time", "range"), h),
        },
        attrs={
            "units": "mm h-1",
            "long_name": "Rainfall rate from inverted Doppler spectrum",
            "description": (
                "Zenith-pointing MRR retrieval: Atlas (1973) v(D) inverted with "
                "Foote & du Toit (1969) density correction; Mie sigma_b at "
                "24.15 GHz with m=6.417-2.758j."
            ),
        },
    )


if __name__ == "__main__":
    import sys
    import matplotlib.pyplot as plt

    path = sys.argv[1] if len(sys.argv) > 1 else "0520.improtoo.nc"
    ds = xr.open_dataset(path)
    R = rainrate_from_improtoo(ds)

    out_nc = path.rsplit(".", 1)[0] + ".rainrate.nc"
    R.to_dataset(name="rainrate").to_netcdf(out_nc)
    print(f"Wrote {out_nc}")
    print(f"R: min={np.nanmin(R.values):.4f}  max={np.nanmax(R.values):.4f}  "
          f"mean={np.nanmean(R.values):.4f} mm/h")

    fig, ax = plt.subplots(figsize=(11, 4))
    pcm = ax.pcolormesh(R["time"].values, R["range"].values, R.values.T,
                        shading="auto", cmap="viridis",
                        vmin=0, vmax=np.nanpercentile(R.values, 99))
    fig.colorbar(pcm, ax=ax, label="Rainfall rate [mm h$^{-1}$]")
    ax.set_xlabel("Time")
    ax.set_ylabel("Range gate")
    ax.set_title(f"Rainfall rate from {path}")
    fig.autofmt_xdate()
    fig.tight_layout()
    out_png = path.rsplit(".", 1)[0] + ".rainrate.png"
    fig.savefig(out_png, dpi=120)
    print(f"Wrote {out_png}")
