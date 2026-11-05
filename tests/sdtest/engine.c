/* OxZygen SD access test: a throwaway engine to check whether an MPC plugin can read a file from the SD card.
 * On create it opens /sdcard/OxZygen/library_test.txt and reports the result in the "status" text parameter.
 * "tone" turns on a 440 Hz sine, so a played note confirms audio runs at the same time.
 * This hardcodes the SD path on purpose (it is the thing under test). Not for release. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <errno.h>
#include "engine.h"

#define TEST_FILE "/sdcard/OxZygen/library_test.txt"

typedef struct { int tone; double phase; char status[160]; } oxs_t;

static void *create(const char *d) {
    (void)d;
    oxs_t *s = calloc(1, sizeof *s);
    FILE *f = fopen(TEST_FILE, "r");
    if (f) {
        char line[120] = "";
        if (fgets(line, sizeof line, f)) line[strcspn(line, "\r\n")] = 0;
        fclose(f);
        snprintf(s->status, sizeof s->status, "FOUND: %s", line);
    } else {
        snprintf(s->status, sizeof s->status, "NOT FOUND (%s)", strerror(errno));
    }
    return s;
}
static void destroy(void *i) { free(i); }
static void midi(void *i, const uint8_t *m, int n) { (void)i; (void)m; (void)n; }
static void set_param(void *i, const char *k, const char *v) {
    oxs_t *s = i;
    if (!strcmp(k, "tone")) s->tone = atoi(v) != 0;
}
static int get_param(void *i, const char *k, char *b, int n) {
    oxs_t *s = i;
    if (!strcmp(k, "status")) return snprintf(b, n, "%s", s->status);
    if (!strcmp(k, "tone")) return snprintf(b, n, "%d", s->tone);
    return 0;
}
static void render(void *i, int16_t *o, int f) {
    oxs_t *s = i;
    for (int k = 0; k < f; k++) {
        int16_t v = 0;
        if (s->tone) {
            v = (int16_t)(sin(s->phase) * 6000.0);
            s->phase += 2.0 * M_PI * 440.0 / 44100.0;
            if (s->phase > 2.0 * M_PI) s->phase -= 2.0 * M_PI;
        }
        o[2 * k] = v; o[2 * k + 1] = v;
    }
}

static const mpc_engine_t ENGINE = { create, destroy, midi, set_param, get_param, render, NULL, NULL };
const mpc_engine_t *mpc_engine(void) { return &ENGINE; }
