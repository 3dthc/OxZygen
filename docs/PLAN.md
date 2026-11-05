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
5. Sound engine, in steps:
   a. [done, 0.2.0, offline] Choir (Claudia, Mirko, Sven; Vowel blends ah/oh/ih) and Winds (flute, ocarina, alto
      sax) from 306 looped zones (62 MB RAM, shared between instances, loaded on a background thread), Dark/Air
      tone, 8-line FDN reverb, project save/restore. Host CPU 71 us per block at 16 voices; device bench pending.
   b. [done, 0.3.0, offline] Vowels: formant synthesis (two glottal oscillators, four formants, u-o-a-e-i).
   c. [done, 0.3.0, offline] Bells: eight-partial modal synthesis. Soundscape: pitched wind resonances plus a
      granular choir cloud. Texture: granular voices with musical pitch steps and reverse grains.
   d. [done, 0.3.0, offline] Drive, ping-pong Delay, Sub (follows the lowest note, Drop glide); 16 presets in
      MPC's PRESET menu (vst/make_presets.py), levelled to within ~1 dB.
   Per-layer polyphony caps (10/8/6/12/6/6), 32 voices total. Host CPU, median per block: 56-90 us across presets.
   Device bench still pending.
6. [in progress] MPC skin (vst/skin): Player (orb + 8 macros), Edit (6 layer cards), FX (4 modules). Built and
   checked offline, not yet seen on the device. The orb is a 34-frame meter filmstrip (2 energy levels x 17
   frames) the engine steps about every 0.1 to 0.3 s. Plugin area is 1280x628; MPC draws the tabs and preset menu.
7. Presets, device test, release.

## Open
- Verify the dizi source.
- Plugin license for the release (the test plugin is MIT; decide for OxZygen itself before release).

## 0.4.0: two sound slots (2026-11-05)
The six always-on layers (36 controls, Mute/Solo, two Q-Link sub-pages that drew the same screen) were replaced by
two slots, A and B. Each picks one sound (Off, Choir, Vowels, Flute, Ocarina, Sax, Bells, Wind, Texture) and has an
Octave, three knobs that relabel for that sound, and a Level. Player macros: Blend, Breath, Attack, Release, Air,
Dark, Space, Motion. 34 parameters (was 59); the order was reset once, before any release.
Presets rebuilt for range: solo leads, high choirs, bells, air and texture, and a dark group that is the only one
using the Sub. Measured offline: brightness spans 317-1827 Hz; energy below 150 Hz is ~0% outside the dark presets
and Monastery. Wrapper gotcha: an option label that starts with a digit is read as an index, so the middle octave
option is "Mid", not "0".

## 0.4.1: velocity (2026-11-05)
One velocity curve for every sound: 18 dB from softest to hardest (was ~7 dB). Measured, velocity 40 -> 127:
Choir 15 dB, Vowels 12, Flute 18, Ocarina 13, Sax 16, Bells 12, Wind 17, Texture 12. Timbre follows too: the choir
tilts its highs (x0.77 soft to x2.5 hard around 1.2 kHz; a low-pass did nothing, its energy sits below 1 kHz),
vowels get a brighter glottal source, ocarina and winds open their Tone filter, Wind gets breathier, flute and sax
crossfade soft/loud recordings, bells strike brighter. Choir, Vowels, Wind and Texture speak faster when hit harder.
No Velocity control: MPC's own pad sensitivity and Full Level cover that. Presets re-levelled for the new curve.

## 0.5.0: categories and new sounds (2026-11-05)
- Each slot picks a category (Voices, Winds, Brass, Strings, Bells, Synth, Air), then a sound in it: 22 sounds.
- New sampled sounds (CC0, VSCO 2 CE and VCSL): clarinet, oboe, horn, mute trumpet, trombone, sustained and tremolo
  strings, tubular bells, vibes, bowed vibes, wine glasses.
- New synth engine (Juno-style): Pad (PWM), mono Lead with glide, Brass with filter bloom, per-slot chorus.
- 15 new presets (34 total), levelled. Library about 131 MB. Parameters reset: 0.4 projects don't carry over.

## 0.5.1: sung "doo" and metal skin (2026-11-05)
- Vowels: with Attack under 25% each note starts with a sung "d" (closure, tongue burst, formant glide), so
  Morph picks doo / doh / dah / deh / dee. Stronger on harder hits. New preset Scat Doos.
- Skin: brushed graphite panels with screws, machined steel buttons, accent brightened to ice blue (#5cc8ff).

## 0.5.2: CRT orb (2026-11-05)
- The orb picture runs through a CRT pass: tube bulge, RGB fringe, scanlines, phosphor triads, rolling refresh band, flicker.

## 0.5.3: mod wheel on every sound (2026-11-05)
- Winds, brass, Vowels, synth lead: vibrato up to ±0.5 semitone, at once. Choir, strings, Texture drift: wider, faster.
- Synth pad and brass: filter opens. Bells: more shimmer. Wind: more Drift. Texture: more Smear.

## 0.5.4: 65 presets, tagged by category (2026-11-05)
- 30 new presets. Names start with a category tag (VOX, WND, BRS, STR, BEL, SYN, AIR) and the list is grouped in that order.

## 0.5.5: late-night R&B presets (2026-11-05)
- 16 dark R&B presets (81 total): low octaves, murky filters, long delays and reverb, sub and drive.

## 0.5.6: horror / film score and cold R&B presets (2026-11-05)
- 9 horror and film-score presets, 6 sparse ghost-vocal R&B presets (96 total).
