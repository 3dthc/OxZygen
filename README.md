# OxZygen

A dark, cinematic VST2 instrument for Akai MPC standalone units: choirs, vowels, flutes, ocarina, sax, bells,
soundscapes and textures, with a crystal-ball orb that reacts as you play.

Work in progress. Built with the [MPC VST toolchain](https://github.com/open-mpc/mpc-vst-plugins).

## Build (Ubuntu / WSL)

Needs the toolchain checked out at `~/mpc-vst-plugins` (or set `MPC_VST`) and Docker running.

```bash
./build.sh sdtest
```

This builds, runs the offline test, and writes the install zip to `dist/`. In WSL it also copies the zip to your
Windows Desktop. Install the zip with the MPC plugin installer app.

## Layout
- `tests/sdtest/`: SD card access test plugin
- `samples/`: scripts to fetch the CC0 sources and trim them to the built-in set (`MANIFEST.md`)
- `ui/prototype.html`: clickable UI prototype (open in a browser)
- `docs/PLAN.md`: plan and device budget
- `CREDITS.md`: every sample source and its license
