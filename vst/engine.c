/* OxZygen, skin-test engine.
 *
 * This build exists to put the OxZygen interface on the device. The sound is a placeholder: a soft
 * eight-voice pad (three detuned sines, breath noise, a darkening low-pass), so the keys play something
 * and drive the orb. The real choir, vowel, wind and texture engine replaces render() later; the
 * parameter list (params.json) and its order stay.
 *
 * The orb is a display-only meter ("orb", frames 0..33): 2 energy levels x 17 animation phases.
 * The engine steps the phase on a timer (Motion sets the speed) and picks the level from the notes
 * sounding, then bumps "display_rev" so the wrapper reports the new frame (HAS_DISPLAY_REV). */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "engine.h"
#include "params.h"

#define SR 44100.0f
#define VOICES 8
#define TAB 2048
#define ORB_PHASES 17
#define ORB_LEVELS 2

static float sine_tab[TAB + 1];

typedef struct {
    int note, on;          /* on: key held */
    float vel, env, ph[3], inc[3];
    unsigned age;
} voice_t;

typedef struct {
    float val[NPARAMS];    /* parameter values in their own units (0..100 knobs, option index) */
    voice_t v[VOICES];
    unsigned clock;
    unsigned noise;
    float lp_l, lp_r;      /* low-pass state */
    float energy;          /* 0..1, rises with notes, falls back slowly */
    float orb_t;           /* seconds since the last orb step */
    int orb_phase, orb_frame;
    unsigned rev;
} oxz_t;

static int idx_of(const char *key) {
    for (int i = 0; i < NPARAMS; i++)
        if (!strcmp(PARAMS[i].key, key)) return i;
    return -1;
}
static float pv(oxz_t *s, const char *key) {   /* a 0..100 knob as 0..1 */
    int i = idx_of(key);
    return i < 0 ? 0.5f : s->val[i] / 100.0f;
}

static void *create(const char *d) {
    (void)d;
    if (sine_tab[TAB / 4] == 0.0f)
        for (int i = 0; i <= TAB; i++) sine_tab[i] = sinf(2.0f * (float)M_PI * i / TAB);
    oxz_t *s = calloc(1, sizeof *s);
    for (int i = 0; i < NPARAMS; i++)   /* params.h keeps defaults normalized 0..1; set_param() gets real units */
        s->val[i] = PARAMS[i].nopts ? floorf(PARAMS[i].def * (PARAMS[i].nopts - 1) + 0.5f)
                                    : PARAMS[i].min + PARAMS[i].def * (PARAMS[i].max - PARAMS[i].min);
    s->noise = 0x12345678u;
    return s;
}
static void destroy(void *i) { free(i); }

static void midi(void *inst, const uint8_t *m, int n) {
    oxz_t *s = inst;
    if (n < 3) return;
    int st = m[0] & 0xF0, note = m[1], vel = m[2];
    if (st == 0x90 && vel > 0) {
        int pick = 0;   /* a free voice, else the oldest */
        for (int k = 0; k < VOICES; k++) {
            if (s->v[k].env < 0.0001f && !s->v[k].on) { pick = k; break; }
            if (s->v[k].age < s->v[pick].age) pick = k;
        }
        voice_t *v = &s->v[pick];
        float f = 440.0f * powf(2.0f, (note - 69) / 12.0f);
        const float det[3] = {1.0f, 1.0035f, 0.5f};
        v->note = note; v->on = 1; v->vel = vel / 127.0f; v->age = ++s->clock;
        for (int k = 0; k < 3; k++) v->inc[k] = f * det[k] * TAB / SR;
        s->energy = fminf(1.0f, s->energy + 0.35f + 0.4f * v->vel);
    } else if (st == 0x80 || (st == 0x90 && vel == 0)) {
        for (int k = 0; k < VOICES; k++)
            if (s->v[k].on && s->v[k].note == note) s->v[k].on = 0;
    } else if (st == 0xB0 && (note == 120 || note == 123)) {   /* all sound / all notes off */
        for (int k = 0; k < VOICES; k++) s->v[k].on = 0;
    }
}

static void set_param(void *inst, const char *key, const char *val) {
    oxz_t *s = inst;
    int i = idx_of(key);
    if (i < 0) return;
    if (!strcmp(key, "orb")) {   /* a tap on the orb: a burst of energy (the engine owns the frame) */
        s->energy = fminf(1.0f, s->energy + 0.6f);
        s->rev++;
        return;
    }
    s->val[i] = (float)atof(val);
}

static int get_param(void *inst, const char *key, char *b, int n) {
    oxz_t *s = inst;
    if (!strcmp(key, "display_rev")) return snprintf(b, n, "%u", s->rev);
    if (!strcmp(key, "orb")) return snprintf(b, n, "%d", s->orb_frame);
    int i = idx_of(key);
    if (i < 0) return 0;
    if (PARAMS[i].nopts) {
        int o = (int)(s->val[i] + 0.5f);
        if (o < 0) o = 0;
        if (o >= PARAMS[i].nopts) o = PARAMS[i].nopts - 1;
        return snprintf(b, n, "%s", PARAMS[i].opts[o]);
    }
    return snprintf(b, n, "%d", (int)(s->val[i] + 0.5f));
}

static inline float tab_sin(float *ph, float inc) {
    int i = (int)*ph;
    float fr = *ph - i, a = sine_tab[i], o = a + (sine_tab[i + 1] - a) * fr;
    *ph += inc;
    if (*ph >= TAB) *ph -= TAB;
    return o;
}

static void render(void *inst, int16_t *out, int frames) {
    oxz_t *s = inst;
    float level = pv(s, "master"), breath = pv(s, "breath"), air = pv(s, "air"), dark = pv(s, "dark");
    float space = pv(s, "space"), motion = pv(s, "motion"), voice = pv(s, "voice");
    float att = 1.0f / (SR * (0.04f + breath * 1.2f));           /* attack time 0.04..1.24 s */
    float rel = expf(-1.0f / (SR * (0.25f + space * 2.5f)));    /* release time constant */
    float cut = 9000.0f * powf(0.07f, dark);                     /* 9 kHz down to about 630 Hz */
    float a = 1.0f - expf(-2.0f * (float)M_PI * cut / SR);
    float oct = 0.15f + 0.5f * voice;                            /* Voice: more of the low octave */

    for (int f = 0; f < frames; f++) {
        float l = 0.0f, r = 0.0f;
        for (int k = 0; k < VOICES; k++) {
            voice_t *v = &s->v[k];
            if (v->on) { v->env += att; if (v->env > 1.0f) v->env = 1.0f; }
            else v->env *= rel;
            if (v->env < 0.0001f) continue;
            float g = v->env * (0.35f + 0.65f * v->vel) * 0.11f;
            float s0 = tab_sin(&v->ph[0], v->inc[0]), s1 = tab_sin(&v->ph[1], v->inc[1]);
            float s2 = tab_sin(&v->ph[2], v->inc[2]);
            l += g * (s0 + oct * s2);
            r += g * (s1 + oct * s2);
        }
        s->noise = s->noise * 1664525u + 1013904223u;          /* breath noise rides on the notes */
        float nz = ((int)(s->noise >> 9) - (1 << 22)) / (float)(1 << 22);
        float any = s->energy > 0.0f ? s->energy : 0.0f;
        l += nz * air * 0.025f * any; r -= nz * air * 0.025f * any;
        s->lp_l += a * (l - s->lp_l); s->lp_r += a * (r - s->lp_r);
        float ol = s->lp_l * level * 1.4f, or_ = s->lp_r * level * 1.4f;
        if (ol > 1.0f) ol = 1.0f; else if (ol < -1.0f) ol = -1.0f;
        if (or_ > 1.0f) or_ = 1.0f; else if (or_ < -1.0f) or_ = -1.0f;
        out[2 * f] = (int16_t)(ol * 32000.0f);
        out[2 * f + 1] = (int16_t)(or_ * 32000.0f);
    }

    /* orb: energy follows the held notes, the phase steps on a timer, the frame changes are reported */
    int held = 0;
    for (int k = 0; k < VOICES; k++) held += s->v[k].on;
    float dt = frames / SR;
    if (held) s->energy = fmaxf(s->energy, 0.6f);
    s->energy *= expf(-dt / 1.5f);
    s->orb_t += dt;
    float step = (0.30f - 0.20f * motion) * (s->energy > 0.3f ? 0.7f : 1.0f);   /* 0.1..0.3 s per frame */
    if (s->orb_t >= step) {
        s->orb_t = 0.0f;
        s->orb_phase = (s->orb_phase + 1) % ORB_PHASES;
    }
    int lvl = s->energy > 0.3f ? 1 : 0;
    int frame = lvl * ORB_PHASES + s->orb_phase;
    if (frame != s->orb_frame) {
        s->orb_frame = frame;
        s->val[idx_of("orb")] = (float)frame;
        s->rev++;
    }
}

static const mpc_engine_t ENGINE = { create, destroy, midi, set_param, get_param, render, NULL, NULL };
const mpc_engine_t *mpc_engine(void) { return &ENGINE; }
