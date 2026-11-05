# OXZYGEN

A dark, cinematic VST2 instrument for Akai MPC standalone units: choirs, vowels and sung "doo"s, flutes, reeds, brass,
atmospheric strings, bells, Juno-style synths, soundscapes and textures, with a CRT crystal-ball orb that reacts as you play.

![OxZygen on the MPC: the Player page](docs/img/player.png)

| Sound page | FX page |
|---|---|
| ![Sound page: two slots, category and sound pickers, octave, four knobs](docs/img/sound.png) | ![FX page: reverb, delay, drive, sub and output](docs/img/fx.png) |

- Two sound slots: pick a category (Voices, Winds, Brass, Strings, Bells, Synth, Air), then one of 22 sounds
- Player page: Velocity, Breath, Attack, Release, Air, Filter (resonant), Lo-Fi, Motion; the mod wheel works on every sound
- FX: reverb, ping-pong delay, drive, and a gliding sub
- 96 presets tagged by category (VOX, WND, BRS, STR, BEL, SYN, AIR), including late-night R&B and horror/film-score sets
- Gen1 (MPC OS 3.x and 2.x) and Gen2; all samples CC0 ([CREDITS.md](CREDITS.md)), code MIT ([LICENSE](LICENSE))

Built with the [MPC VST toolchain](https://github.com/open-mpc/mpc-vst-plugins).

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

## Which zip?

`./build.sh` makes three, all the same plugin and sounds:

| Zip | For |
|---|---|
| `OxZygen-<ver>-mpc-armv7.zip` | Gen1: MPC Live, Live II, One, X, Force on MPC OS 3.x |
| `OxZygen-<ver>-mpc-armv7-os2.zip` | the same devices still on MPC OS 2.x (skin written in the 2.x file format) |
| `OxZygen-<ver>-mpc-aarch64.zip` | Gen2: MPC Live III and the other 64-bit models (they run MPC OS 3.x only) |
