# Original Java simulations

This directory preserves the Java source programs imported from the local
`ALADO_website` archive:

- `double-well`: theoretical forced double-well oscillator.
- `observations-2013`: historical observational phase-space animation.

The browser-ready JAR files are generated with Java 8 bytecode by:

```sh
./scripts/build_legacy_java.sh
```

The GitHub Pages wrapper uses CheerpJ 4.3 to run these unmodified AWT applets
inside modern browsers. GitHub Pages itself remains a static host.
