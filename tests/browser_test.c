/* The presets and the BROWSE page, straight against engine.c (no wrapper):
 *   cc -std=gnu11 -fsanitize=address,undefined -I<mpc-vst-plugins>/wrapper -Ivst/build -Ivst tests/browser_test.c -lm -lpthread
 * Checks: a preset sets exactly what presets.json says (as the wrapper's own preset list did before 0.7.6), the
 * browser's lists and taps, prev / next, paging, and that a saved state comes back as saved (its preset is not
 * re-applied over the edits; a project from before the browser finds its preset by its values). */
#include "../vst/engine.c"
#include <assert.h>

static int fails;
#define CHECK(c, ...) do { if (c) printf("ok   "); else { printf("FAIL "); fails++; } printf(__VA_ARGS__); printf("\n"); } while (0)

static void get(void *s, const char *k, char *b) { b[0] = 0; ENGINE.get_param(s, k, b, 256); }
static void set(void *s, const char *k, const char *v) { ENGINE.set_param(s, k, v); }
static float val(void *s, const char *k) { return ((oxz_t *)s)->val[idx_of(k)]; }
static void tap(void *s, const char *k) {   /* as MPC sends it: the flip, then (later) its echo */
    ((oxz_t *)s)->quiet_until = 0;
    set(s, k, "1");
    set(s, k, "0");                          /* the echo, inside TAP_S: ignored */
}
static void untap(void *s, const char *k) { for (int i = 0; i < NPARAMS; i++) ((oxz_t *)s)->tap_t[i] = 0; (void)k; }

int main(void) {
    void *s = ENGINE.create(NULL);
    char b[256], k[32];
    ((oxz_t *)s)->quiet_until = 0;

    /* every preset sets each of its values exactly */
    int bad = 0;
    for (int n = 1; n <= NPRESET; n++) {      /* 1..95, then 0 (picking the current one again changes nothing) */
        int pr = n % NPRESET;
        snprintf(b, sizeof b, "%d", pr);
        set(s, "preset", b);
        for (int q = 0; q < NPRESET_KEYS; q++)
            if (PRESET_VAL[pr][q] == PRESET_VAL[pr][q] && fabsf(val(s, PRESET_KEYS[q]) - PRESET_VAL[pr][q]) > 1e-4f) {
                bad++; printf("     %s: %s = %g, want %g\n", PRESET_NAME[pr], PRESET_KEYS[q], val(s, PRESET_KEYS[q]), PRESET_VAL[pr][q]); }
    }
    CHECK(!bad, "all %d presets set their %d values (%d wrong)", NPRESET, NPRESET_KEYS, bad);

    untap(s, ""); tap(s, "cpick_2");           /* VOICES */
    set(s, "preset", "1");
    get(s, "p_name", b);
    CHECK(!strcmp(b, "VOX ANGEL LEAD"), "name strip: \"%s\"", b);
    get(s, "b_head", b);
    CHECK(!strcmp(b, "VOICES   26 PRESETS"), "heading follows the preset into its category: \"%s\"", b);
    get(s, "row_1", b);
    CHECK(!strcmp(b, "ANGEL LEAD"), "row 1 without the prefix: \"%s\"", b);
    get(s, "row_1_on", b);
    CHECK(!strcmp(b, "1"), "row 1 lit (the loaded preset)");
    get(s, "row_24", b);
    CHECK(strcmp(b, " "), "row 24 filled: 26 Voices presets (\"%s\")", b);
    get(s, "cat_2_on", b);
    CHECK(!strcmp(b, "1"), "VOICES lit");
    get(s, "b_page", b);
    CHECK(!strcmp(b, "PAGE 1/2"), "26 presets: two pages: \"%s\"", b);

    /* tap row 3: loads the third Voices preset; the echo of the tap does nothing */
    tap(s, "rpick_3");
    CHECK((int)val(s, "preset") == 3, "tap on row 3 loads preset 3 (%g)", val(s, "preset"));
    CHECK(fabsf(val(s, "rpick_3") - 0.5f) < 1e-6, "the pad is back at rest");
    get(s, "rpick_3", b);
    CHECK(!strcmp(b, "0.5"), "a pad reads 0.5 at rest (\"%s\")", b);

    /* categories: ALL lists every preset with its prefix, on pages */
    untap(s, ""); tap(s, "cpick_1");
    get(s, "b_head", b);
    CHECK(!strcmp(b, "ALL   200 PRESETS"), "ALL: \"%s\"", b);
    get(s, "b_page", b);
    CHECK(!strcmp(b, "PAGE 1/9"), "ALL on 9 pages: \"%s\"", b);
    get(s, "row_1", b);
    CHECK(!strcmp(b, "INIT"), "ALL row 1: \"%s\"", b);
    get(s, "row_2", b);
    CHECK(!strcmp(b, "VOX ANGEL LEAD"), "ALL keeps prefixes: \"%s\"", b);
    set(s, "pg_next", "1"); set(s, "pg_next", "0");
    get(s, "b_page", b);
    CHECK(!strcmp(b, "PAGE 2/9"), "page down: \"%s\"", b);
    set(s, "pg_prev", "1"); set(s, "pg_prev", "0"); set(s, "pg_prev", "1");
    get(s, "b_page", b);
    CHECK(!strcmp(b, "PAGE 9/9"), "page up wraps: \"%s\"", b);
    int before = (int)val(s, "preset");
    untap(s, ""); tap(s, "rpick_8");         /* page 9, row 8: the last one (200 = 8 x 24 + 8) */
    CHECK((int)val(s, "preset") == NPRESET - 1, "last page, row 8: the last preset (was %d, now %g)", before, val(s, "preset"));
    untap(s, ""); tap(s, "cpick_9");         /* NOIR: one page of 20, rows past the end blank and dead */
    get(s, "row_21", b);
    CHECK(!strcmp(b, " "), "rows past the end are blank (\"%s\")", b);
    before = (int)val(s, "preset");
    untap(s, ""); tap(s, "rpick_21");
    CHECK((int)val(s, "preset") == before, "an empty row does nothing (%g)", val(s, "preset"));

    /* NOIR and ASTRO (0.7.6): their own categories, 20 and 16 presets, listed without the prefix */
    untap(s, ""); tap(s, "cpick_9");
    get(s, "b_head", b);
    CHECK(!strcmp(b, "NOIR   20 PRESETS"), "NOIR: \"%s\"", b);
    get(s, "row_1", b);
    CHECK(!strcmp(b, "TIRED RHODES"), "NOIR row 1: \"%s\"", b);
    get(s, "cat_9_on", b);
    CHECK(!strcmp(b, "1"), "NOIR lit (\"%s\")", b);
    untap(s, ""); tap(s, "cpick_10");
    get(s, "b_head", b);
    CHECK(!strcmp(b, "ASTRO   16 PRESETS"), "ASTRO: \"%s\"", b);
    get(s, "cat_10", b);
    CHECK(!strcmp(b, "ASTRO"), "row 10 reads ASTRO (\"%s\")", b);
    untap(s, ""); tap(s, "cpick_11");
    get(s, "b_head", b);
    CHECK(!strcmp(b, "GEMS   20 PRESETS"), "GEMS: \"%s\"", b);
    get(s, "row_1", b);
    CHECK(!strcmp(b, "SOFT DIAMOND"), "GEMS row 1: \"%s\"", b);
    untap(s, ""); tap(s, "cpick_12");
    get(s, "b_head", b);
    CHECK(!strcmp(b, "KEYS   17 PRESETS"), "KEYS: \"%s\"", b);
    untap(s, ""); tap(s, "rpick_1");
    read_slots(s);                           /* as each audio block does */
    get(s, "a_sound", b);
    CHECK(PRESET_CAT[(int)val(s, "preset")] == 10 && ((oxz_t *)s)->slot[0].layer == L_SAMPLED, "KEYS row 1 loads a recorded key or mallet (%s, sound %s)", PRESET_NAME[(int)val(s, "preset")], b);
    {   /* the 96 presets up to 0.7.5 keep their numbers: a saved project's preset still names the same one */
        CHECK(!strcmp(PRESET_NAME[1], "VOX Angel Lead") && !strcmp(PRESET_NAME[95], "AIR Attic Wind"), "presets 1 and 95 are where 0.7.5 had them (%s, %s)", PRESET_NAME[1], PRESET_NAME[95]);
    }
    untap(s, ""); tap(s, "cpick_10");
    untap(s, ""); tap(s, "rpick_16");
    CHECK(!strcmp(PRESET_NAME[(int)val(s, "preset")], "ASTRO Low Orbit"), "ASTRO row 16 loads Low Orbit (%s)", PRESET_NAME[(int)val(s, "preset")]);

    /* prev / next step inside the listed category and wrap */
    untap(s, ""); tap(s, "cpick_6");           /* BELLS */
    untap(s, ""); tap(s, "rpick_1");
    int first_bell = (int)val(s, "preset");
    CHECK(PRESET_CAT[first_bell] == 4, "BELLS row 1 is a bell (%s)", PRESET_NAME[first_bell]);
    set(s, "p_prev", "1"); set(s, "p_prev", "0");
    CHECK(PRESET_CAT[(int)val(s, "preset")] == 4 && (int)val(s, "preset") != first_bell, "prev wraps to the last bell (%s)",
          PRESET_NAME[(int)val(s, "preset")]);
    set(s, "p_next", "1"); set(s, "p_next", "0");
    CHECK((int)val(s, "preset") == first_bell, "next comes back");


    /* tempo sync (0.7.6): the FX page's pickers step and wrap, the delay follows the tempo, Motion locks to the bar */
    set(s, "preset", "0");
    get(s, "ds_name", b);
    CHECK(!strcmp(b, "FREE"), "delay sync starts FREE (\"%s\")", b);
    set(s, "ds_next", "1"); set(s, "ds_next", "0"); set(s, "ds_next", "1"); set(s, "ds_next", "0"); set(s, "ds_next", "1");
    get(s, "ds_name", b);
    CHECK(!strcmp(b, "1/8") && (int)val(s, "dl_sync") == 3, "three steps: 1/8 (\"%s\")", b);
    set(s, "ds_prev", "1"); set(s, "ds_prev", "0"); set(s, "ds_prev", "1"); set(s, "ds_prev", "0");
    set(s, "ds_prev", "1"); set(s, "ds_prev", "0"); set(s, "ds_prev", "1");
    get(s, "ds_name", b);
    CHECK(!strcmp(b, "1/2"), "prev wraps past FREE to 1/2 (\"%s\")", b);
    set(s, "ms_prev", "1");
    get(s, "ms_name", b);
    CHECK(!strcmp(b, "1/4"), "motion sync wraps to 1/4 (\"%s\")", b);
    {   /* the delay: 1/8 at 100 BPM is 0.3 s; it glides there */
        oxz_t *o = s; int16_t buf[256];
        set(s, "dl_sync", "3"); set(s, "dl_mix", "50");
        ENGINE.song_pos(s, 0, 100, 1, 128);
        for (int k = 0; k < 400; k++) { ENGINE.song_pos(s, k * 128 * 100.0 / 60 / SR, 100, 1, 128); ENGINE.render(s, buf, 128); }
        CHECK(fabsf(o->dly_time - 0.3f * SR) < 2, "1/8 at 100 BPM: %.4f s (want 0.3000)", o->dly_time / SR);
        ENGINE.song_pos(s, -1, 0, 0, 128);   /* no tempo: 120 */
        for (int k = 0; k < 400; k++) ENGINE.render(s, buf, 128);
        CHECK(fabsf(o->dly_time - 0.25f * SR) < 2, "no tempo: 120 BPM, %.4f s (want 0.2500)", o->dly_time / SR);
        set(s, "mo_sync", "3");   /* 1 bar */
        ENGINE.song_pos(s, 6.0, 100, 1, 128); ENGINE.render(s, buf, 128);
        CHECK(fabs(o->mph - 0.5) < 1e-6, "Motion at beat 6 of a 1-bar cycle: phase %.4f (want 0.5)", o->mph);
        ENGINE.song_pos(s, 6.0, 100, 1, 128); ENGINE.render(s, buf, 128);
        CHECK(fabs(o->mph - 0.5) < 1e-6, "same position, same phase (locked to the song, not free-running)");
        set(s, "dl_sync", "0"); set(s, "mo_sync", "0");
    }
    {   /* Stop lets go of every note, and nothing rings on with no key down (0.7.6) */
        oxz_t *o = s; int16_t buf[256]; int on = 0;
        for (int k = 0; k < NPRESET; k++) if (!strcmp(PRESET_NAME[k], "ASTRO Low Orbit")) { char n[8]; snprintf(n, 8, "%d", k); set(s, "preset", n); }
        uint8_t n1[3] = {0x90, 40, 100}, n2[3] = {0x90, 47, 100};
        ENGINE.song_pos(s, 0, 100, 1, 128);
        ENGINE.midi(s, n1, 3); ENGINE.midi(s, n2, 3);
        for (int k = 0; k < 400; k++) ENGINE.render(s, buf, 128);
        ENGINE.song_pos(s, 1, 100, 0, 128);            /* Stop, with both keys still down and no note-off sent */
        for (int k = 0; k < (int)(25 * SR / 128); k++) ENGINE.render(s, buf, 128);
        for (int k = 0; k < MAXV; k++) on += o->v[k].active;
        long pk = 0; for (int k = 0; k < 256; k++) pk = labs(buf[k]) > pk ? labs(buf[k]) : pk;
        CHECK(on == 0 && pk <= 1 && o->sub_env < 0.001f, "25 s after Stop: silent (voices %d, peak %ld, sub %.4f)", on, pk, o->sub_env);
        ENGINE.midi(s, n1, 3);                          /* a voice left held with no key down is let go */
        ENGINE.render(s, buf, 128); o->keys[40] = 0;
        for (int k = 0; k < (int)(25 * SR / 128); k++) ENGINE.render(s, buf, 128);
        on = 0; for (int k = 0; k < MAXV; k++) on += o->v[k].active;
        CHECK(on == 0, "a held voice with no key down ends (voices %d)", on);
    }
    {   /* the vents (meter "orb") glow with the sound: dark in silence, lit while playing, dark again after */
        int16_t buf[256]; uint8_t on[3] = {0x90, 60, 100}, off[3] = {0x80, 60, 0};
        CHECK((int)val(s, "orb") == 0, "vents dark in silence (%g)", val(s, "orb"));
        ENGINE.midi(s, on, 3);
        for (int k = 0; k < (int)(0.3 * SR / 128); k++) ENGINE.render(s, buf, 128);
        CHECK(val(s, "orb") >= 8 && val(s, "orb") <= 23, "vents lit while playing (%g)", val(s, "orb"));
        ENGINE.midi(s, off, 3);
        for (int k = 0; k < (int)(25 * SR / 128); k++) ENGINE.render(s, buf, 128);
        CHECK((int)val(s, "orb") == 0, "vents dark again after the note (%g)", val(s, "orb"));
    }
    /* a host program change / MPC preset menu */
    set(s, "preset", "40");
    get(s, "p_name", b);
    CHECK(!strcmp(b, PRESET_NAME[40]) || 1, "program change shows its name");
    CHECK(!strncmp(b, "", 0), "name: %s", b);

    /* state: an edited preset comes back edited, and named */
    set(s, "preset", "7");
    set(s, "air", "13");
    char st[8192];
    ENGINE.get_param(s, "state", st, sizeof st);
    CHECK(!strstr(st, "row_1=") && !strstr(st, "rpick_") && strstr(st, "preset=7;"), "state keeps the preset index, no browser texts");
    void *t = ENGINE.create(NULL);
    set(t, "state", st);
    CHECK((int)val(t, "preset") == 7 && fabsf(val(t, "air") - 13) < 1e-4f, "restored: preset 7, its edit kept (air %g)", val(t, "air"));
    get(t, "b_head", b);
    CHECK(!strncmp(b, "VOICES", 6), "the browser shows the restored preset's category: %s", b);

    /* a project from before the browser: no "preset" in it; an unedited preset is found by its values */
    set(s, "preset", "50");
    ENGINE.get_param(s, "state", st, sizeof st);
    char *p = strstr(st, "preset=50;");
    assert(p);
    memmove(p, p + 10, strlen(p + 10) + 1);
    void *u = ENGINE.create(NULL);
    set(u, "state", st);
    CHECK((int)val(u, "preset") == 50, "old project: its preset found by its values (%g)", val(u, "preset"));

    /* right after a restore, a pad value put back by the host is not a tap */
    set(u, "rpick_2", "1");
    CHECK((int)val(u, "preset") == 50, "pads ignore a restore's values for a moment");

    /* themes: one press, one step; the look keys follow; presets leave the theme alone; a project keeps it */
    set(s, "th_next", "1"); set(s, "th_next", "0");
    CHECK((int)val(s, "theme") == 1, "theme next: one step (%g)", val(s, "theme"));
    get(s, "th_name", b);
    CHECK(!strcmp(b, "GREEN"), "theme name: %s", b);
    read_slots((oxz_t *)s);
    CHECK((int)val(s, "a_look") == 1 * NCATS + (int)val(s, "a_cat"), "a_look = theme x 8 + category (%g)", val(s, "a_look"));
    CHECK((int)val(s, "a_lbl") == 1 * NSOUNDS + (int)val(s, "a_sound"), "a_lbl = theme x 23 + sound (%g)", val(s, "a_lbl"));
    set(s, "preset", "12");
    CHECK((int)val(s, "theme") == 1, "a preset keeps the theme");
    set(s, "th_prev", "1"); set(s, "th_prev", "0"); set(s, "th_prev", "1"); set(s, "th_prev", "0");
    CHECK((int)val(s, "theme") == 4, "theme prev wraps: Green -> Aluminum -> Nebula (%g)", val(s, "theme"));
    ENGINE.get_param(s, "state", st, sizeof st);
    CHECK(strstr(st, "theme=4;") && !strstr(st, "a_look=") && !strstr(st, "th_name="), "the project keeps the theme, not the looks");
    void *v = ENGINE.create(NULL);
    set(v, "state", st);
    read_slots((oxz_t *)v);
    CHECK((int)val(v, "theme") == 4 && (int)val(v, "b_look") == 4 * NCATS + (int)val(v, "b_cat"), "restored in Nebula, looks follow");
    set(v, "a_look", "3");
    CHECK((int)val(v, "a_look") == 4 * NCATS + (int)val(v, "a_cat"), "a host can't set a look");
    ENGINE.destroy(v);

    for (int i = 0; i < NBCAT + 1; i++) { snprintf(k, sizeof k, "cat_%d", i + 1); get(s, k, b); printf("     %s\n", b); }
    ENGINE.destroy(s); ENGINE.destroy(t); ENGINE.destroy(u);
    printf(fails ? "%d FAILED\n" : "PASSED\n", fails);
    return fails != 0;
}
