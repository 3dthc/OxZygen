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
4. [in progress] SD access test plugin (tests/sdtest): can a plugin read files from /sdcard? Decides whether an
   importable library on the SD card is practical.
5. Sound engine: sample playback for the recorded layers, formant synthesis for vowels, granular textures, FX chain.
6. Port the prototype UI to an MPC skin (1280x800, large knobs and text).
7. Presets, device test, release.

## Open
- Verify the dizi source.
- Plugin license for the release (the test plugin is MIT; decide for OxZygen itself before release).
