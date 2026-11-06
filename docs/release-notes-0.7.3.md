**What's new in 0.7.3:** an **A4 Tune** knob on the FX page (in the Drive / Tuning panel) sets the reference pitch from 415 to 466 Hz (440 is standard; 432, 442 and 443 are common). Every sound follows it. Saved projects and presets carry over and stay at 440 Hz.

**Also since 0.7.1:** the sub is now off in every preset except the seven built around it, and sits lower (18–25) in those.

**OXZYGEN 0.7.3**: a dark, cinematic instrument for MPC standalone: choirs, vowels and sung "doo"s, flutes, reeds, brass, atmospheric strings, bells, Juno-style synths, wind and textures, with a CRT crystal-ball orb that reacts as you play.

- Two sound slots, each picking a category (Voices, Winds, Brass, Strings, Bells, Synth, Air) and one of 22 sounds
- FX page: A4 Tune, 415–466 Hz
- Player page: Velocity, Breath, Attack, Release, Air, Filter (resonant), Lo-Fi, Motion; the mod wheel works on every sound
- FX: reverb, ping-pong delay, drive, and a gliding sub
- 96 presets, tagged by category (VOX, WND, BRS, STR, BEL, SYN, AIR), including late-night R&B and horror/film-score sets
- All samples are CC0 (see CREDITS.md); code is MIT

## Which zip

| Zip | Device |
|---|---|
| `OxZygen-0.7.3-mpc-armv7.zip` | **Gen1**: MPC Live, Live II, One, X, Force on **MPC OS 3.x** |
| `OxZygen-0.7.3-mpc-armv7-os2.zip` | the same Gen1 devices still on **MPC OS 2.x** |
| `OxZygen-0.7.3-mpc-aarch64.zip` | **Gen2**: MPC Live III and the other 64-bit models (MPC OS 3.x) |

## Requirements
- An MPC OS standalone device (see above); about 130 MB free on the internal drive. The plugin uses about 131 MB of RAM once loaded.
- Tested on an MPC Live II (MPC OS 3.10). The OS 2.x and Gen2 builds have not been tried on those units yet: reports welcome.

## Install
Install with your plugin manager, or unzip and follow `INSTALL.md` inside the zip (`install.sh`, or the manual steps).
