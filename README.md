# OxZygen

A dark, cinematic VST2 instrument for Akai MPC standalone units: choirs, vowels, flutes, ocarina, sax, bells,
soundscapes and textures, with a crystal-ball orb that reacts as you play.

Work in progress. Built with the [MPC VST toolchain](https://github.com/open-mpc/mpc-vst-plugins).

## Build (Ubuntu / WSL)

Needs the toolchain checked out at `~/mpc-vst-plugins` (or set `MPC_VST`) and Docker running.

```bash
./build.sh            # OxZygen
./build.sh sdtest     # the SD card access test plugin
```

This builds, runs the offline test, and writes the install zip to `dist/`. In WSL it also copies the zip to your
Windows Desktop. Install the zip with the MPC plugin installer app. The first OxZygen build downloads the
toolchain's skin renderer image (Chromium), which takes a few minutes once.

The skin artwork is pre-rendered and committed. To change the design, edit `vst/skin/make_skin.py` and run
`python3 vst/skin/make_skin.py` (needs Python with Playwright and Pillow), then build.

## Layout
- `vst/`: the plugin: `engine.c` (two sound slots and the effects), `make_presets.py` (writes `presets.json`), `params.json` (parameter order is fixed; saved
  projects depend on it; new parameters go at the end), `skin/make_skin.py` (all skin artwork and `layout.conf`)
- `vst/data/`: the prepared samples the plugin ships with (62 MB, CC0; made by `samples/prepare.py`), so a build
  needs no 15 GB source download
- `tests/sdtest/`: SD card access test plugin (passed on an MPC Live II, 2026-11-05)
- `samples/`: fetch the CC0 sources, trim them (`trim.sh`) and prepare them for the engine (`prepare.py`: pitch,
  seamless loops, levels)
- `ui/prototype.html`: clickable UI prototype (open in a browser)
- `docs/PLAN.md`: plan and device budget
- `CREDITS.md`: every sample source and its license
