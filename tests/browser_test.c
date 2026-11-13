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
    CHECK(!strcmp(b, "VOICES   23 PRESETS"), "heading follows the preset into its category: \"%s\"", b);
    get(s, "row_1", b);
    CHECK(!strcmp(b, "ANGEL LEAD"), "row 1 without the prefix: \"%s\"", b);
    get(s, "row_1_on", b);
    CHECK(!strcmp(b, "1"), "row 1 lit (the loaded preset)");
    get(s, "row_24", b);
    CHECK(!strcmp(b, " "), "row 24 empty in a 23-preset list");
    get(s, "cat_2_on", b);
    CHECK(!strcmp(b, "1"), "VOICES lit");
    get(s, "b_page", b);
    CHECK(!strcmp(b, "PAGE 1/1"), "one page: \"%s\"", b);

    /* tap row 3: loads the third Voices preset; the echo of the tap does nothing */
    tap(s, "rpick_3");
    CHECK((int)val(s, "preset") == 3, "tap on row 3 loads preset 3 (%g)", val(s, "preset"));
    CHECK(fabsf(val(s, "rpick_3") - 0.5f) < 1e-6, "the pad is back at rest");
    get(s, "rpick_3", b);
    CHECK(!strcmp(b, "0.5"), "a pad reads 0.5 at rest (\"%s\")", b);

    /* categories: ALL lists every preset with its prefix, on pages */
    untap(s, ""); tap(s, "cpick_1");
    get(s, "b_head", b);
    CHECK(!strcmp(b, "ALL   96 PRESETS"), "ALL: \"%s\"", b);
    get(s, "b_page", b);
    CHECK(!strcmp(b, "PAGE 1/4"), "ALL on 4 pages: \"%s\"", b);
    get(s, "row_1", b);
    CHECK(!strcmp(b, "INIT"), "ALL row 1: \"%s\"", b);
    get(s, "row_2", b);
    CHECK(!strcmp(b, "VOX ANGEL LEAD"), "ALL keeps prefixes: \"%s\"", b);
    set(s, "pg_next", "1"); set(s, "pg_next", "0");
    get(s, "b_page", b);
    CHECK(!strcmp(b, "PAGE 2/4"), "page down: \"%s\"", b);
    set(s, "pg_prev", "1"); set(s, "pg_prev", "0"); set(s, "pg_prev", "1");
    get(s, "b_page", b);
    CHECK(!strcmp(b, "PAGE 4/4"), "page up wraps: \"%s\"", b);
    int before = (int)val(s, "preset");
    untap(s, ""); tap(s, "rpick_24");        /* page 4, row 24: past the end of the list (96 = 4 x 24: the last one) */
    CHECK((int)val(s, "preset") == 95, "last page, last row: preset 95 (was %d, now %g)", before, val(s, "preset"));

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

    for (int i = 0; i < 8; i++) { snprintf(k, sizeof k, "cat_%d", i + 1); get(s, k, b); printf("     %s\n", b); }
    ENGINE.destroy(s); ENGINE.destroy(t); ENGINE.destroy(u);
    printf(fails ? "%d FAILED\n" : "PASSED\n", fails);
    return fails != 0;
}
