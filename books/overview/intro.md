# MRR Processing Intercomparison — Overview

For the first part of our workflow, we will process the 20 May 2025 case from the CROCUS Urban Canyons field camaign. CROCUS was a DOE-funded Urban Integrated Field Laboratory focused on improving the predicability of extreme weather events, such as flooding, in the Chicago region. The Chicago region, with its unique set up of a major city on the coast of Lake Michigan, commonly experiences Mesoscale Convective Systems (MCS). The cooler air over the lake sometimes influences the development of MCSes, as the more stable airmass inhibits convective growth, leading to storms weakening as they approach Lake Michigan. However, the urban heat island of Chicago can provide a warmer, more unstable airmass that can also lead to convective invigoration. Therefore, the CROCUS Urban Canyons campaign focused on high frequency sampling of thermodynamic and kinematic profiles from rawinsonde launches during flooding events. These launches were co-located with both the CROCUS Micronet measurements of meteorological parameters and precipitation and the Argonne Deployable Mast.

The Argonne Deployable Mast (ADM), until the last week of May 2025, was located at the Argonne Testbed for Multiscale Observational Studies. The ADM consisted of a portable hand crank tower with the following instrumentation installed:

* A Vaisala Weather Transmitter for recording temperature, winds, and dewpoint at 2 m
* A $Parsivel^2$ disdrometer
* A Micro Rain Radar 2

At ATMOS, further instrumentation for intercomparison was located within 20 m of the ADM:
* FD70 Disdrometer
* A Micro Rain Radar PRO

This setup provided a unique opportunity to compare the performance of the MRR2 and MRR-PRO for rainfall events over Chicago. In addition, this also provides an opportunity to compare common processing techniques for MRR and MRR-PRO data.

## Micro Rain Radar Parameters

The Micro Rain Radar 2 and PRO are vertically pointing Ka-band radars that record full Doppler spectra over a column. They are designed with low power consumption in mind, only using about 100 W of power, making it portable and easy to install compared to more power hungry zenith pointing radars. It also provides the capability to record full Doppler spectra, from which rainfall drop size distributions can be retrieved. The Micro Rain Radar PRO supports higher spatial and temporal resolutions than the MRR2.

| Instrument | Number of Gates |   Vertical Resolution    |    Time resolution
-------------|-----------------|--------------------------|------------------------
| MRR-2      |      32 (fixed) |   10-200 m (set by user) |   Typically 60 s
| MRR-PRO    |     variable    |  10-200 m | Typically 10-30 s|

## Comparison of MRR Processing Packages

The Micro Rain Radar's raw output is a Doppler power spectrum at each range gate, sampled over 64 velocity bins between roughly 0 and 12 m/s. Turning that spectrum into geophysical quantities (reflectivity, mean Doppler velocity, spectral width, drop size distribution, rain or snow rate) requires several decisions: how to estimate and subtract the noise floor, how to detect and bound precipitation peaks, whether and how to dealias spectra that wrap around the Nyquist velocity, how to correct for path-integrated attenuation, and which v(D) relationship to invert. Three open-source Python packages have been used for this processing: **IMProToo**, **RaProM**, and **ERUO**. Each makes different choices, and each was built for a different primary use case.

### IMProToo (Improved MRR Processing Tool)

IMProToo, developed by Maximilian Maahn and described in Maahn and Kollias (2012), was the first widely adopted alternative to Metek's factory processing. It targets the **MRR-2** and was designed specifically to make the instrument usable for **snowfall**, where the factory processing performs poorly because it assumes liquid drops and a v(D) relation valid only for rain. In addition, the factory processing does not dealias power spectra, which can cause issues in retrieving vertical velocities in strong downdrafts or hail.

Key features:
* **Hildebrand–Sekhon noise removal** applied for each spectrial bin. This has the potential to recover weak signals that would be below a specified global threshold.
* **Multi-peak detection** in the dealiased spectrum, with a heuristic that selects the most likely precipitation peak.
* **Doppler dealiasing** by stitching the spectrum to itself and tracking peak continuity in time and height, extending the effective unambiguous velocity well beyond the nominal ±6 m/s Nyquist window. This is the package's signature contribution and is what makes it valuable for hail and strong downdrafts.
* Outputs reflectivity (`Ze`), mean Doppler velocity (`W`), spectral width, and the dealiased spectrum itself (`eta`), along with quality masks (`etaMask`, `qualityFlags`).

### RaProM (Radar Processing Methodology)

RaProM, developed by Albert Garcia-Benadí at UPC Barcelona (Garcia-Benadí et al. 2020), is the most comprehensive of the three. It supports both the **MRR-2** and **MRR-PRO** and was designed to retrieve rainfall rate and hydrometeor ID rather than provide dealiased, cleaned spectra.

Key features:
* **Hildebrand–Sekhon noise removal** plus an additional spectral coherence test across adjacent gates.
* **Hydrometeor classification** into rain, drizzle, mixed, snow, hail, and unknown categories using moments of the Doppler spectrum (mean velocity, spectral width, skewness, kurtosis).
* **Bright band detection** (`BB_bottom`, `BB_top`) from gradients in `Ze` and `W`.
* **Path-integrated attenuation (PIA) correction** at C-band-equivalent assumptions, output per gate as `PIA` / `PIA_all`.
* **Full drop size distribution retrieval** stored as `N(D) in function of time and height` (log₁₀ N(D)), with bulk parameters `Dm` (mass-weighted mean diameter) and `Nw` (normalized intercept).
* **Rain rate** (`RR`) computed directly from the retrieved DSD, by class.
* Supports a user-supplied **calibration offset**, which can be used to recalibrate the MRR data from the raw spectrum.
* Outputs are NetCDF, gate-aligned to time × Height, and easily opened in xarray.

The retrieved rainfall rates from RaProM make several assumptions. One, the updraft velocity is assumed to be zero, similar to the factory processing. While this is suitable for stratiform rain where updrafts and downdrafts are weak, this can produce large errors in the DSDs during convective events. Two, raindrops and snowflakes are assumed to fall at speeds provided in Atlas et al. (1973) for a given radar reflectivity factor. Therefore, if there is any calibration error in Ze, this can impact the retrieved drop sizes.

### ERUO (Enhancement and Reconstruction of the spectrUm for MRR-PRO Observations)

ERUO, developed by Alfonso Ferrone and colleagues at EPFL / University of Lausanne (Ferrone et al. 2022, AMT), is the newest of the three and is specific to the **MRR-PRO**. It was developed in the context of polar snowfall campaigns (Antarctica, Davos), where the MRR-PRO's known firmware artifacts cause serious problems: a persistent interference pattern that had an unknown source.

Key features:
* **Interference line removal**: identifies and masks the velocity bins where the interference line contaminates the spectrum, then reconstructs the underlying precipitation signal by interpolation.
* **Spectrum reconstruction in the lowest gates**, where the factory-corrected spectrum is distorted by the transmit pulse — ERUO replaces these with a model-fit reconstruction so that surface-adjacent retrievals become usable.
* **Noise removal** with a more aggressive method tuned for the very low SNR typical of dry snow.
* **Doppler dealiasing** similar in spirit to IMProToo but adapted for MRR-PRO spectra.
* Outputs reflectivity, mean Doppler velocity, and spectral width on the same grid as the factory product, so it can be substituted into downstream snowfall retrievals (e.g., Snowfall Rate from Ze–S relations).
* Does **not** support the MRR-2 and does **not** produce a DSD or rain rate directly.

### Summary

| Aspect | IMProToo | RaProM | ERUO |
|---|---|---|---|
| Instrument | MRR-2 | MRR-2 and MRR-PRO | MRR-PRO only |
| Primary target | Snowfall (dealiasing) | All precipitation (full retrieval) | Polar snowfall (artifact removal) |
| Noise removal | Hildebrand–Sekhon | Hildebrand–Sekhon + coherence | Aggressive, low-SNR tuned |
| Doppler dealiasing | Yes (signature feature) | Yes | Yes |
| Interference / artifact removal | No | Limited | Yes (PSU line + ringdown) |
| Hydrometeor classification | No | Yes | No |
| DSD retrieval | No (external) | Yes | No |
| Bulk rain rate | No (external) | Yes | No |
| PIA correction | No | Yes | No |
| Output | NetCDF spectra + moments | NetCDF full retrieval | NetCDF moments |
| Reference | Maahn & Kollias (2012) | Garcia-Benadí et al. (2020–2022) | Ferrone et al. (2022) |

These packages were designed with different applications in mind, with ImProToo and ERUO designed for snowfall while RaProM was designed for all weather conditions. However, we will show in later chapters that RaProM may not be correctly subtracting the ground clutter signal in the raw spectrum, causing a drizzle peak that is not detected by the Parsivel nor present in the factory processing. Therefore, further evaluation of all of these retrieval techniques is an ongoing line of reserarch.

# References

* Atlas, D., R. C.Srivastava, and R. S.Sekhon (1973), Doppler radar characteristics of precipitation at vertical incidence, Rev. Geophys., 11(1), 1–35, doi:10.1029/RG011i001p00001.
* Ferrone, A., Billault-Roux, A.-C., and Berne, A.: ERUO: a spectral processing routine for the Micro Rain Radar PRO (MRR-PRO), *Atmospheric Measurement Techniques*, 15, 3569–3592, https://doi.org/10.5194/amt-15-3569-2022, 2022.
* Garcia-Benadí, A., Bech, J., Gonzalez, S., Udina, M., Codina, B., and Georgis, J.-F.: Precipitation Type Classification of Micro Rain Radar Data Using an Improved Doppler Spectral Processing Methodology, *Remote Sensing*, 12, 4113, https://doi.org/10.3390/rs12244113, 2020.
* Maahn, M. and Kollias, P.: Improved Micro Rain Radar snow measurements using Doppler spectra post-processing, *Atmospheric Measurement Techniques*, 5, 2661–2673, https://doi.org/10.5194/amt-5-2661-2012, 2012.
