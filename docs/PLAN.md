# OxZygen plan

Dark, cinematic instrument for the MPC: choir, vowels, winds (flute, ocarina, sax), bells, soundscapes and textures.
Commercial quality, redistributable sources only. One product, named OxZygen; more sounds can come later as an
importable library.

## Device budget (MPC Live II, Gen1)
- RAM: 2 GB total, about 1,130 MB usable. Sample RAM target: about 400 MB per instance.
- Built-in sound set: 163 MB trimmed (samples/MANIFEST.md), loads fully into RAM.
- SD card: mounted at /sdcard (ext4, writable from the shell). The user's card had 2.2 GB free when checked.

## Steps
1. [done] Source and license check (CREDITS.md).
2. [done] Trim the sources to the v1 set (samples/trim.sh): 163 MB.
3. [done] UI prototype (ui/prototype.html): Player page with the orb, Edit page per layer, FX page.
4. [done] SD access test plugin (tests/sdtest): a plugin running inside MPC read /sdcard/OxZygen/library_test.txt
   on an MPC Live II (2026-11-05). An importable library on the SD card is practical.
5. Sound engine: sample playback for the recorded layers, formant synthesis for vowels, granular textures, FX chain.
6. [in progress] MPC skin (vst/skin): Player (orb + 8 macros), Edit (6 layer cards), FX (4 modules). Built and
   checked offline, not yet seen on the device. The orb is a 34-frame meter filmstrip (2 energy levels x 17
   frames) the engine steps about every 0.1 to 0.3 s. Plugin area is 1280x628; MPC draws the tabs and preset menu.
7. Presets, device test, release.

## Open
- Project state saving: the engine has no "state" chunk yet; add one before presets.
- Verify the dizi source.
- Plugin license for the release (the test plugin is MIT; decide for OxZygen itself before release).
