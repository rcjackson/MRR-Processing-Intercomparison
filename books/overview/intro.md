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

The Micro Rain Radar (2 and PRO versions) is a vertically pointing Ka-band radar that records full Doppler spectra over a column. It is designed with low power consumption in mind, only using about 100 W of power, making it portable and easy to install compared to more power hungry zenith pointing radars. It also provides the capability to record full Doppler spectra, from which rainfall drop size distributions can be retrieved.

## Comparison of MRR Processing Packages

The Micro Rain Radar's raw output is a complex-valued Doppler power spectrum at each range gate, sampled over 64 velocity bins between roughly 0 and 12 m/s. Turning that spectrum into geophysical quantities (reflectivity, mean Doppler velocity, spectral width, drop size distribution, rain or snow rate) requires several decisions: how to estimate and subtract the noise floor, how to detect and bound precipitation peaks, whether and how to dealias spectra that wrap around the Nyquist velocity, how to correct for path-integrated attenuation, and which v(D) relationship to invert. Three open-source Python packages dominate the community: **IMProToo**, **RaProM**, and **ERUO**. Each makes different choices, and each was built for a different primary use case.

### IMProToo (Improved MRR Processing Tool)

IMProToo, developed by Maximilian Maahn and described in Maahn and Kollias (2012), was the first widely adopted alternative to Metek's factory processing. It targets the **MRR-2** and was designed specifically to make the instrument usable for **snowfall**, where the factory processing performs poorly because it assumes liquid drops and a v(D) relation valid only for rain.

Key features:
* **Hildebrand–Sekhon noise removal** applied bin by bin, which is more conservative than Metek's threshold-based approach and recovers weak signals.
* **Multi-peak detection** in the dealiased spectrum, with a heuristic that selects the most likely precipitation peak.
* **Doppler dealiasing** by stitching the spectrum to itself and tracking peak continuity in time and height, extending the effective unambiguous velocity well beyond the nominal ±6 m/s Nyquist window. This is the package's signature contribution and is what makes it valuable for hail, strong downdrafts, and fast-falling rimed particles.
* Outputs reflectivity (`Ze`), mean Doppler velocity (`W`), spectral width, and the dealiased spectrum itself (`eta`), along with quality masks (`etaMask`, `qualityFlags`).
* Does **not** retrieve a drop size distribution, rain rate, or hydrometeor type — the user must derive these downstream (which is what `rainrate_from_improtoo` does in this notebook).

### RaProM (Radar Processing Methodology)

RaProM, developed by Albert Garcia-Benadí at UPC Barcelona (Garcia-Benadí et al. 2020, 2021, 2022), is the most comprehensive of the three. It supports both the **MRR-2** and **MRR-PRO** and was designed end-to-end as a geophysical retrieval pipeline rather than a spectrum cleanup tool.

Key features:
* **Hildebrand–Sekhon noise removal** plus an additional spectral coherence test across adjacent gates.
* **Hydrometeor classification** into rain, drizzle, mixed, snow, hail, and unknown categories using moments of the Doppler spectrum (mean velocity, spectral width, skewness, kurtosis).
* **Bright band detection** (`BB_bottom`, `BB_top`) from gradients in `Ze` and `W`.
* **Path-integrated attenuation (PIA) correction** at C-band-equivalent assumptions, output per gate as `PIA` / `PIA_all`.
* **Full drop size distribution retrieval** stored as `N(D) in function of time and height` (log₁₀ N(D)), with bulk parameters `Dm` (mass-weighted mean diameter) and `Nw` (normalized intercept).
* **Rain rate** (`RR`) computed directly from the retrieved DSD, by class.
* Supports a user-supplied **calibration offset** (see the second `process_file` call in the processing notebook, with `calibration=0.403`).
* Outputs are NetCDF, gate-aligned to time × Height, and easily opened in xarray — which is why most of the comparison plots in the processing notebook are built around the RaProM dataset.

The trade-off is that RaProM bakes a lot of assumptions into its DSD inversion (Atlas-style v(D), Rayleigh scattering, Marshall–Palmer-like priors), so the retrieved DSD and the bulk RR inherit those assumptions and are not always directly comparable to disdrometer-derived DSDs over the same diameter range — which motivates the band-restricted re-integration done in the `rr_from_nd` cell of the processing notebook.

### ERUO (Enhancement and Reconstruction of the spectrUm for MRR-PRO Observations)

ERUO, developed by Alfonso Ferrone and colleagues at EPFL / University of Lausanne (Ferrone et al. 2022, AMT), is the newest of the three and is specific to the **MRR-PRO**. It was developed in the context of polar snowfall campaigns (Antarctica, Davos), where the MRR-PRO's known firmware artifacts cause serious problems: a persistent low-altitude interference pattern from the instrument's own power supply, and distorted spectra in the first few range gates from antenna ringdown.

Key features:
* **Interference line removal**: identifies and masks the velocity bins where the PSU artifact contaminates the spectrum, then reconstructs the underlying precipitation signal by interpolation.
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

In practice these packages are complementary rather than competing: IMProToo and ERUO clean up the spectrum so that downstream retrievals are trustworthy, while RaProM bundles cleanup and retrieval together. The intercomparison in the processing notebook focuses on IMProToo, RaProM, and the factory Metek processing (read via the `xradar` `metek` engine) because the MRR-2 deployed on the ADM is not an MRR-PRO and is therefore outside ERUO's scope; ERUO would enter the comparison if we extended this analysis to the MRR-PRO at ATMOS.

## References

* Ferrone, A., Billault-Roux, A.-C., and Berne, A.: ERUO: a spectral processing routine for the Micro Rain Radar PRO (MRR-PRO), *Atmospheric Measurement Techniques*, 15, 3569–3592, https://doi.org/10.5194/amt-15-3569-2022, 2022.
* Garcia-Benadí, A., Bech, J., Gonzalez, S., Udina, M., Codina, B., and Georgis, J.-F.: Precipitation Type Classification of Micro Rain Radar Data Using an Improved Doppler Spectral Processing Methodology, *Remote Sensing*, 12, 4113, https://doi.org/10.3390/rs12244113, 2020.
* Maahn, M. and Kollias, P.: Improved Micro Rain Radar snow measurements using Doppler spectra post-processing, *Atmospheric Measurement Techniques*, 5, 2661–2673, https://doi.org/10.5194/amt-5-2661-2012, 2012.
