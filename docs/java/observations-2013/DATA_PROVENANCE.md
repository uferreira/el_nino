# Java observation data through June 2026

The Java applet reads `sva.2_filter_10_9_1950.1_2026.06.dat`.

Its first 3,781 lines are the complete original
`sva.2_filter_10_9_1950.1_2013.01.dat` file, unchanged byte for byte. The
SHA-256 of that preserved prefix is:

```text
2f5f6e8a793ef70d218c60cf64d386cdb9740183d4c5af2028ab671745e14d9e
```

The continuation uses the repository's NOAA NINO1+2 download and Fourier
filter pipeline. Recomputing the entire record would revise the old phase-space
values because the filter depends on the full record length and the upstream
monthly series can be revised. For that reason, the builder deliberately keeps
the old prefix and appends the modern result only from February 2013 onward.
Four cubic-Hermite samples connect the preserved January 2013 endpoint to the
February 2013 endpoint without a discontinuity.

Generate and verify the file with:

```bash
python scripts/run_all.py --sst-only --no-animate
python scripts/build_java_observations.py
pytest tests/test_java_observations.py
```
