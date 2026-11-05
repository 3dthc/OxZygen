/* OxZygen engine, step 1: sample layers and reverb.
 *
 * Layers playing in this build:
 *   Choir  three singers (Claudia, Mirko, Sven), each on the notes it covers; the Vowel knob blends ah -> oh -> ih;
 *          Spread detunes and pans the singers apart; Attack sets the swell.
 *   Winds  flute, ocarina or alto sax (the Winds selector): soft/loud layers by velocity, recorded vibrato blended
 *          in by Vibrato, breath noise by Breath, brightness by Tone.
 * Vowels, Bells, Soundscape and Texture come in later steps, as do Delay, Drive and Sub.
 *
 * Macros (Player page):
 *   Voice  Winds level            Air     brightness lift (an "air" high band)
 *   Breath attack softness, breath  Dark  low-pass on everything
 *   Choir  Choir level            Space   reverb amount and size, longer release
 *   Bells  (later step)           Motion  vibrato depth, ensemble drift, orb speed
 *
 * Samples: <plugin folder>/samples (MODULE_SUBDIR), prepared by samples/prepare.py: mono 16-bit with baked loops,
 * listed in manifest.txt. They load once per process on a background thread and are shared by every instance.
 * The orb: display-only meter "orb" (2 energy levels x 17 frames), stepped here and reported via display_rev. */
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "engine.h"
#include "params.h"

#define SR 44100.0f
#define MAXV 16              /* voices (a note with choir and winds uses two) */
#define MAXSRC 6             /* sample players per voice: 3 singers x 2 vowels */
#define ORB_PHASES 17

/* ---------- sample bank: loaded once, shared by all instances ---------- */
enum { G_CLA_AH, G_CLA_OH, G_CLA_IH, G_MIR_AH, G_MIR_OH, G_MIR_IH, G_SVE_AH, G_SVE_OH, G_SVE_IH,
       G_FL_P, G_FL_F, G_FL_VIB, G_OC_STD, G_OC_VIB, G_SAX_P, G_SAX_F, NGROUPS };
static const char *GROUP_NAMES[NGROUPS] = {
    "choir/claudia_ah", "choir/claudia_oh", "choir/claudia_ih", "choir/mirko_ah", "choir/mirko_oh", "choir/mirko_ih",
    "choir/sven_ah", "choir/sven_oh", "choir/sven_ih", "flute/nv_p", "flute/nv_f", "flute/vib",
    "ocarina/std", "ocarina/vib", "sax/p", "sax/f"};

typedef struct { float pitch; int ls, le, frames; int16_t *pcm; } zone_t;   /* pitch = root + cents/100 */
typedef struct { zone_t *z; int n; } group_t;
typedef struct { group_t g[NGROUPS]; float lo[3], hi[3]; long bytes; int ok; char err[96]; } bank_t;

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static int g_refs;
static pthread_t g_loader;
static int g_loader_started;
static bank_t *g_bank;           /* set (atomically) once loaded */
static char g_dir[512];

static int16_t *load_wav(const char *path, int *frames) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    unsigned char h[12];
    int16_t *pcm = NULL;
    if (fread(h, 1, 12, f) == 12 && !memcmp(h, "RIFF", 4) && !memcmp(h + 8, "WAVE", 4)) {
        unsigned char ck[8];
        while (fread(ck, 1, 8, f) == 8) {
            unsigned len = ck[4] | ck[5] << 8 | ck[6] << 16 | (unsigned)ck[7] << 24;
            if (!memcmp(ck, "data", 4)) {
                pcm = malloc(len + 8);
                if (pcm && fread(pcm, 1, len, f) == len) { *frames = (int)(len / 2); pcm[*frames] = pcm[*frames + 1] = 0; }
                else { free(pcm); pcm = NULL; }
                break;
            }
            fseek(f, (long)(len + (len & 1)), SEEK_CUR);
        }
    }
    fclose(f);
    return pcm;
}

static int cmp_zone(const void *a, const void *b) {
    float d = ((const zone_t *)a)->pitch - ((const zone_t *)b)->pitch;
    return (d > 0) - (d < 0);
}

static void *loader(void *arg) {
    (void)arg;
    bank_t *b = calloc(1, sizeof *b);
    char path[1024], line[512];
    snprintf(path, sizeof path, "%s/manifest.txt", g_dir);
    FILE *m = fopen(path, "r");
    if (!m) { snprintf(b->err, sizeof b->err, "samples not found"); __atomic_store_n(&g_bank, b, __ATOMIC_RELEASE); return NULL; }
    int cap[NGROUPS] = {0};
    while (fgets(line, sizeof line, m)) {
        char inst[32], var[32], file[256];
        int root, ls, le, frames;
        float cents;
        if (line[0] == '#' || sscanf(line, "%31s %31s %d %f %d %d %d %255s", inst, var, &root, &cents, &ls, &le, &frames, file) != 8)
            continue;
        char gname[80];
        snprintf(gname, sizeof gname, "%s/%s", inst, var);
        int gi = -1;
        for (int i = 0; i < NGROUPS; i++) if (!strcmp(GROUP_NAMES[i], gname)) gi = i;
        if (gi < 0) continue;
        snprintf(path, sizeof path, "%s/%s", g_dir, file);
        int got = 0;
        int16_t *pcm = load_wav(path, &got);
        if (!pcm) continue;
        if (le > got) le = got;
        if (ls >= le) ls = 0;
        pcm[le] = pcm[ls]; pcm[le + 1] = pcm[ls + 1];   /* the interpolator reads 2 past the loop end: continue the loop */
        group_t *g = &b->g[gi];
        if (g->n == cap[gi]) { cap[gi] = cap[gi] ? cap[gi] * 2 : 16; g->z = realloc(g->z, cap[gi] * sizeof *g->z); }
        g->z[g->n++] = (zone_t){root + cents / 100.0f, ls, le, got, pcm};
        b->bytes += (long)got * 2;
    }
    fclose(m);
    for (int i = 0; i < NGROUPS; i++) if (b->g[i].n) qsort(b->g[i].z, b->g[i].n, sizeof(zone_t), cmp_zone);
    for (int s = 0; s < 3; s++) {   /* each singer's range over its vowels */
        b->lo[s] = 999; b->hi[s] = -999;
        for (int v = 0; v < 3; v++) {
            group_t *g = &b->g[s * 3 + v];
            if (!g->n) continue;
            if (g->z[0].pitch < b->lo[s]) b->lo[s] = g->z[0].pitch;
            if (g->z[g->n - 1].pitch > b->hi[s]) b->hi[s] = g->z[g->n - 1].pitch;
        }
    }
    b->ok = b->bytes > 0;
    if (!b->ok) snprintf(b->err, sizeof b->err, "no samples loaded");
    __atomic_store_n(&g_bank, b, __ATOMIC_RELEASE);
    return NULL;
}

static void bank_free(bank_t *b) {
    if (!b) return;
    for (int i = 0; i < NGROUPS; i++) { for (int k = 0; k < b->g[i].n; k++) free(b->g[i].z[k].pcm); free(b->g[i].z); }
    free(b);
}

static const zone_t *nearest(const bank_t *b, int gi, float pitch) {
    const group_t *g = &b->g[gi];
    if (!g->n) return NULL;
    int best = 0;
    float bd = 1e9f;
    for (int i = 0; i < g->n; i++) { float d = fabsf(g->z[i].pitch - pitch); if (d < bd) { bd = d; best = i; } }
    return &g->z[best];
}

/* ---------- reverb: 4 input allpasses into an 8-line feedback delay network ---------- */
#define FDN 8
#define AP 4
static const float FDN_MS[FDN] = {29.7f, 37.1f, 41.1f, 43.7f, 53.0f, 59.9f, 67.7f, 73.1f};
static const float AP_MS[AP] = {4.7f, 3.6f, 12.7f, 9.3f};
#define FDN_MAX 5600         /* longest line 73.1 ms x 1.7 size at 44.1 kHz, plus modulation */
#define PRE_MAX 2048

typedef struct {
    float line[FDN][FDN_MAX]; int wp[FDN]; float lp[FDN];
    float ap[AP][1024]; int apw[AP];
    float pre[PRE_MAX]; int prew;
    float lfo;
} reverb_t;

static inline float rd_frac(const float *buf, int n, int wp, float delay) {
    float p = (float)wp - delay;
    if (p < 0) p += n;
    int i = (int)p, j = i + 1 < n ? i + 1 : 0;
    float fr = p - i;
    return buf[i] + (buf[j] - buf[i]) * fr;
}

/* ---------- instance ---------- */
typedef struct { const zone_t *z; int i; float fr, inc_base, inc, g, gl, gr; } src_t;
enum { L_CHOIR, L_WINDS };
typedef struct {
    int active, note, layer, held, pedal;
    float vel, env, att, rel, t, lfo, tone_lp_l, tone_lp_r, bp1, bp2, breath_t, drift;
    int nsrc;
    src_t s[MAXSRC];
    unsigned age;
} voice_t;

typedef struct {
    float val[NPARAMS];
    voice_t v[MAXV];
    unsigned clock, noise;
    int pedal_down;
    float bend;                 /* semitones */
    float modwheel;
    float lp1_l, lp1_r, lp2_l, lp2_r, air_l, air_r;
    reverb_t *rv;
    float energy, orb_t;
    int orb_phase, orb_frame;
    unsigned rev;
} oxz_t;

static int idx_of(const char *key) {
    for (int i = 0; i < NPARAMS; i++) if (!strcmp(PARAMS[i].key, key)) return i;
    return -1;
}
#define P(name) (s->val[I_##name] * 0.01f)
static int I_master, I_voice, I_breath, I_choir, I_air, I_dark, I_space, I_motion, I_ch_vowel, I_ch_attack,
    I_ch_spread, I_ch_level, I_ch_mute, I_ch_solo, I_wi_breath, I_wi_vibrato, I_wi_tone, I_wi_level, I_wi_mute,
    I_wi_solo, I_wi_inst, I_rv_size, I_rv_decay, I_rv_mix, I_orb, I_solo_any[6];
static int g_idx_done;
static void init_idx(void) {
    if (g_idx_done) return;
#define X(n) I_##n = idx_of(#n)
    X(master); X(voice); X(breath); X(choir); X(air); X(dark); X(space); X(motion); X(ch_vowel); X(ch_attack);
    X(ch_spread); X(ch_level); X(ch_mute); X(ch_solo); X(wi_breath); X(wi_vibrato); X(wi_tone); X(wi_level);
    X(wi_mute); X(wi_solo); X(wi_inst); X(rv_size); X(rv_decay); X(rv_mix); X(orb);
#undef X
    const char *solos[6] = {"ch_solo", "vo_solo", "wi_solo", "be_solo", "sc_solo", "tx_solo"};
    for (int i = 0; i < 6; i++) I_solo_any[i] = idx_of(solos[i]);
    g_idx_done = 1;
}

static void *create(const char *data_dir) {
    init_idx();
    oxz_t *s = calloc(1, sizeof *s);
    if (!s) return NULL;
    s->rv = calloc(1, sizeof *s->rv);
    for (int i = 0; i < NPARAMS; i++)   /* params.h keeps defaults normalized 0..1; set_param() gets real units */
        s->val[i] = PARAMS[i].nopts ? floorf(PARAMS[i].def * (PARAMS[i].nopts - 1) + 0.5f)
                                    : PARAMS[i].min + PARAMS[i].def * (PARAMS[i].max - PARAMS[i].min);
    s->noise = 0x9e3779b9u;
    pthread_mutex_lock(&g_lock);
    if (g_refs++ == 0) {
        snprintf(g_dir, sizeof g_dir, "%s", data_dir ? data_dir : "samples");
        __atomic_store_n(&g_bank, (bank_t *)NULL, __ATOMIC_RELEASE);
        g_loader_started = pthread_create(&g_loader, NULL, loader, NULL) == 0;
    }
    pthread_mutex_unlock(&g_lock);
    return s;
}

static void destroy(void *inst) {
    oxz_t *s = inst;
    pthread_mutex_lock(&g_lock);
    if (--g_refs == 0) {
        if (g_loader_started) pthread_join(g_loader, NULL);
        g_loader_started = 0;
        bank_free(__atomic_load_n(&g_bank, __ATOMIC_ACQUIRE));
        __atomic_store_n(&g_bank, (bank_t *)NULL, __ATOMIC_RELEASE);
    }
    pthread_mutex_unlock(&g_lock);
    free(s->rv);
    free(s);
}

static int layer_on(oxz_t *s, int layer) {
    int any_solo = 0;
    for (int i = 0; i < 6; i++) if (I_solo_any[i] >= 0 && s->val[I_solo_any[i]] > 0.5f) any_solo = 1;
    int mute = layer == L_CHOIR ? I_ch_mute : I_wi_mute, solo = layer == L_CHOIR ? I_ch_solo : I_wi_solo;
    if (s->val[mute] > 0.5f) return 0;
    return !any_solo || s->val[solo] > 0.5f;
}

static voice_t *alloc_voice(oxz_t *s) {
    voice_t *best = NULL;
    for (int k = 0; k < MAXV; k++) if (!s->v[k].active) return &s->v[k];
    for (int k = 0; k < MAXV; k++)      /* steal: the quietest released voice, else the oldest */
        if (!s->v[k].held && !s->v[k].pedal && (!best || s->v[k].env < best->env)) best = &s->v[k];
    if (best) return best;
    for (int k = 0; k < MAXV; k++) if (!best || s->v[k].age < best->age) best = &s->v[k];
    return best;
}

static float attack_secs(float knob, float breath) {   /* knob 0..1 -> 5 ms .. 2.5 s, scaled by Breath */
    return (0.005f + 2.5f * knob * knob) * (0.45f + 1.1f * breath);
}

static void add_src(voice_t *v, const zone_t *z, int note, float g, float pan, float detune_cents) {
    if (!z || v->nsrc >= MAXSRC || g <= 0.0001f) return;
    src_t *x = &v->s[v->nsrc++];
    x->z = z;
    x->i = 0; x->fr = 0.0f;
    x->inc_base = powf(2.0f, (note - z->pitch + detune_cents / 100.0f) / 12.0f);
    x->g = g;
    float a = (pan + 1.0f) * 0.25f * (float)M_PI;   /* equal-power pan, -1..1 */
    x->gl = cosf(a); x->gr = sinf(a);
}

static void choir_sources(oxz_t *s, const bank_t *b, voice_t *v) {
    float vow = P(ch_vowel) * 2.0f;              /* 0 ah, 1 oh, 2 ih */
    int va = vow < 1.0f ? 0 : 1;
    float w = vow - va, wa = cosf(w * (float)M_PI / 2), wb = sinf(w * (float)M_PI / 2);
    float spread = P(ch_spread);
    static const float PAN[3] = {-0.45f, 0.45f, 0.0f}, DET[3] = {-7.0f, 6.0f, -2.0f};
    int n = 0;
    float gs[3];
    for (int sg = 0; sg < 3; sg++) {
        float lo = b->lo[sg] - 4, hi = b->hi[sg] + 4;
        gs[sg] = (v->note >= lo && v->note <= hi) ? 1.0f : 0.0f;
        n += gs[sg] > 0;
    }
    if (!n) {   /* outside every range: the nearest singer stretches */
        int best = v->note < b->lo[2] ? 2 : 0;
        gs[best] = 1.0f; n = 1;
    }
    float norm = 1.0f / sqrtf((float)n);
    for (int sg = 0; sg < 3; sg++) {
        if (!gs[sg]) continue;
        int ga = sg * 3 + va, gb = sg * 3 + va + 1;
        if (!b->g[gb].n) gb = ga;                  /* Mirko has no ih: hold his oh */
        float det = DET[sg] * spread * 2.0f;
        add_src(v, nearest(b, ga, v->note), v->note, wa * norm, PAN[sg] * spread * 1.6f, det);
        add_src(v, nearest(b, gb, v->note), v->note, wb * norm, PAN[sg] * spread * 1.6f, det);
    }
}

static void winds_sources(oxz_t *s, const bank_t *b, voice_t *v) {
    int inst = (int)(s->val[I_wi_inst] + 0.5f);    /* 0 flute, 1 ocarina, 2 sax */
    float vib = P(wi_vibrato), loud = fminf(1.0f, fmaxf(0.0f, (v->vel - 0.3f) / 0.55f));
    float rec_vib = fminf(1.0f, fmaxf(0.0f, (vib - 0.35f) * 2.5f));   /* recorded vibrato fades in above ~35% */
    if (inst == 0) {
        float plain = cosf(rec_vib * (float)M_PI / 2);
        add_src(v, nearest(b, G_FL_P, v->note), v->note, plain * cosf(loud * (float)M_PI / 2), 0, 0);
        add_src(v, nearest(b, G_FL_F, v->note), v->note, plain * sinf(loud * (float)M_PI / 2), 0, 0);
        add_src(v, nearest(b, G_FL_VIB, v->note), v->note, sinf(rec_vib * (float)M_PI / 2), 0, 0);
    } else if (inst == 1) {
        add_src(v, nearest(b, G_OC_STD, v->note), v->note, cosf(rec_vib * (float)M_PI / 2), 0, 0);
        add_src(v, nearest(b, G_OC_VIB, v->note), v->note, sinf(rec_vib * (float)M_PI / 2), 0, 0);
    } else {
        add_src(v, nearest(b, G_SAX_P, v->note), v->note, cosf(loud * (float)M_PI / 2), 0, 0);
        add_src(v, nearest(b, G_SAX_F, v->note), v->note, sinf(loud * (float)M_PI / 2), 0, 0);
    }
}

static void note_on(oxz_t *s, int note, float vel) {
    const bank_t *b = __atomic_load_n(&g_bank, __ATOMIC_ACQUIRE);
    s->energy = fminf(1.0f, s->energy + 0.35f + 0.4f * vel);
    if (!b || !b->ok) return;
    for (int layer = L_CHOIR; layer <= L_WINDS; layer++) {
        if (!layer_on(s, layer)) continue;
        float lvl = layer == L_CHOIR ? P(ch_level) * P(choir) : P(wi_level) * P(voice);
        if (lvl < 0.001f) continue;
        voice_t *v = alloc_voice(s);
        memset(v, 0, sizeof *v);
        v->active = 1; v->held = 1; v->note = note; v->layer = layer; v->vel = vel; v->age = ++s->clock;
        v->drift = ((s->clock * 2654435761u) >> 8 & 1023) / 1023.0f * 6.28f;
        if (layer == L_CHOIR) {
            v->att = 1.0f / (SR * attack_secs(P(ch_attack), P(breath)));
            choir_sources(s, b, v);
        } else {
            v->att = 1.0f / (SR * (0.012f + 0.35f * P(breath) * P(breath) + 0.1f * P(wi_breath)));
            winds_sources(s, b, v);
        }
    }
}

static void note_off(oxz_t *s, int note) {
    for (int k = 0; k < MAXV; k++)
        if (s->v[k].active && s->v[k].held && s->v[k].note == note) {
            s->v[k].held = 0;
            s->v[k].pedal = s->pedal_down;
        }
}

static void midi(void *inst, const uint8_t *m, int n) {
    oxz_t *s = inst;
    if (n < 2) return;
    int st = m[0] & 0xF0;
    if (st == 0xE0 && n >= 3) { s->bend = (((m[2] << 7) | m[1]) - 8192) / 8192.0f * 2.0f; return; }
    if (n < 3) return;
    if (st == 0x90 && m[2] > 0) note_on(s, m[1], m[2] / 127.0f);
    else if (st == 0x80 || st == 0x90) note_off(s, m[1]);
    else if (st == 0xB0) {
        if (m[1] == 1) s->modwheel = m[2] / 127.0f;
        else if (m[1] == 64) {
            s->pedal_down = m[2] >= 64;
            if (!s->pedal_down) for (int k = 0; k < MAXV; k++) s->v[k].pedal = 0;
        } else if (m[1] == 120 || m[1] == 123) {
            for (int k = 0; k < MAXV; k++) { s->v[k].held = 0; s->v[k].pedal = 0; if (m[1] == 120) s->v[k].active = 0; }
        }
    }
}

static void set_param(void *inst, const char *key, const char *val) {
    oxz_t *s = inst;
    if (!strcmp(key, "state")) {           /* "key=value;..." from get_param("state") */
        char buf[64];
        const char *p = val;
        while (*p) {
            const char *e = strchr(p, ';');
            size_t len = e ? (size_t)(e - p) : strlen(p);
            if (len < sizeof buf) {
                memcpy(buf, p, len); buf[len] = 0;
                char *eq = strchr(buf, '=');
                if (eq) { *eq = 0; int i = idx_of(buf); if (i >= 0 && i != I_orb) s->val[i] = (float)atof(eq + 1); }
            }
            if (!e) break;
            p = e + 1;
        }
        s->rev++;
        return;
    }
    int i = idx_of(key);
    if (i < 0) return;
    if (i == I_orb) { s->energy = fminf(1.0f, s->energy + 0.6f); s->rev++; return; }   /* a tap on the orb */
    s->val[i] = (float)atof(val);
}

static int get_param(void *inst, const char *key, char *b, int n) {
    oxz_t *s = inst;
    if (!strcmp(key, "display_rev")) return snprintf(b, n, "%u", s->rev);
    if (!strcmp(key, "state")) {
        int len = 0;
        for (int i = 0; i < NPARAMS && len < n - 32; i++)
            if (i != I_orb) len += snprintf(b + len, n - len, "%s=%g;", PARAMS[i].key, s->val[i]);
        return len;
    }
    int i = idx_of(key);
    if (i < 0) return 0;
    if (i == I_orb) return snprintf(b, n, "%d", s->orb_frame);
    if (PARAMS[i].nopts) {
        int o = (int)(s->val[i] + 0.5f);
        if (o < 0) o = 0;
        if (o >= PARAMS[i].nopts) o = PARAMS[i].nopts - 1;
        return snprintf(b, n, "%s", PARAMS[i].opts[o]);
    }
    return snprintf(b, n, "%d", (int)(s->val[i] + 0.5f));
}

static inline float hermite(const int16_t *d, int i, float t) {
    float xm = d[i > 0 ? i - 1 : 0], x0 = d[i], x1 = d[i + 1], x2 = d[i + 2];
    float c1 = 0.5f * (x1 - xm), c2 = xm - 2.5f * x0 + 2.0f * x1 - 0.5f * x2, c3 = 0.5f * (x2 - xm) + 1.5f * (x0 - x1);
    return ((c3 * t + c2) * t + c1) * t + x0;
}

static void reverb_block(oxz_t *s, float *L, float *R, int frames) {
    reverb_t *r = s->rv;
    if (!r) return;
    float space = P(space);
    float size = 0.55f + 1.1f * (0.5f * P(rv_size) + 0.5f * space);            /* 0.55 .. 1.65 */
    float rt60 = (0.6f + 11.0f * P(rv_decay) * P(rv_decay)) * (0.7f + 0.6f * space);
    float mix = fminf(0.9f, P(rv_mix) * (0.35f + 1.3f * space));
    float damp = 1.0f - expf(-2.0f * (float)M_PI * (2500.0f + 6000.0f * (1.0f - P(dark))) / SR);
    float dl[FDN], g[FDN];
    for (int k = 0; k < FDN; k++) {
        dl[k] = FDN_MS[k] * size * 44.1f;
        g[k] = powf(10.0f, -3.0f * dl[k] / (rt60 * SR));
    }
    const int pre = (int)(0.018f * SR);
    /* the two modulated lines: their offsets move linearly across the block (no trig per sample) */
    float lfo_end = r->lfo + 0.7f / SR * 6.2831853f * frames;
    float m0a = sinf(r->lfo) * 12.0f, m1a = cosf(r->lfo) * 12.0f;
    float m0b = sinf(lfo_end) * 12.0f, m1b = cosf(lfo_end) * 12.0f;
    r->lfo = lfo_end > 6.2831853f ? lfo_end - 6.2831853f : lfo_end;
    float dm0 = (m0b - m0a) / frames, dm1 = (m1b - m1a) / frames;
    for (int f = 0; f < frames; f++) {
        float in = (L[f] + R[f]) * 0.5f;
        r->pre[r->prew] = in;
        int pr = r->prew - pre; if (pr < 0) pr += PRE_MAX;
        float x = r->pre[pr];
        if (++r->prew == PRE_MAX) r->prew = 0;
        for (int a = 0; a < AP; a++) {             /* diffusion */
            int len = (int)(AP_MS[a] * 44.1f), rp = r->apw[a] - len; if (rp < 0) rp += 1024;
            float d = r->ap[a][rp], y = -0.6f * x + d;
            r->ap[a][r->apw[a]] = x + 0.6f * y;
            r->apw[a] = (r->apw[a] + 1) & 1023;
            x = y;
        }
        float o[FDN], sum = 0;
        for (int k = 0; k < FDN; k++) {
            float mod = k == 0 ? m0a + dm0 * f : k == 1 ? m1a + dm1 * f : 0.0f;   /* slow chorus on two lines */
            o[k] = rd_frac(r->line[k], FDN_MAX, r->wp[k], dl[k] + mod + 14.0f);
            r->lp[k] += damp * (o[k] - r->lp[k]);
            o[k] = r->lp[k] * g[k];
            sum += o[k];
        }
        sum *= 2.0f / FDN;                         /* Householder feedback */
        for (int k = 0; k < FDN; k++) {
            r->line[k][r->wp[k]] = o[k] - sum + ((k & 1) ? -x : x);
            if (++r->wp[k] == FDN_MAX) r->wp[k] = 0;
        }
        float wl = (o[0] - o[2] + o[4] - o[6] + 0.5f * (o[1] + o[5])) * 0.5f;
        float wr = (o[1] - o[3] + o[5] - o[7] + 0.5f * (o[2] + o[6])) * 0.5f;
        L[f] = L[f] * (1.0f - 0.5f * mix) + wl * mix;
        R[f] = R[f] * (1.0f - 0.5f * mix) + wr * mix;
    }
}

static void render(void *inst, int16_t *out, int frames) {
    oxz_t *s = inst;
    float L[128], R[128];
    memset(L, 0, sizeof L); memset(R, 0, sizeof R);
    if (frames > 128) frames = 128;
    float dt = frames / SR, motion = P(motion), space = P(space);
    float rel_secs = 0.25f + 3.8f * powf(space, 1.4f);
    float rel_mul = expf(-1.0f / (SR * rel_secs / 4.6f));     /* -40 dB over rel_secs */
    float ch_gain = P(ch_level) * P(choir) * 1.4f, wi_gain = P(wi_level) * P(voice) * 2.0f;
    float vib_depth = (P(wi_vibrato) * 0.35f + motion * 0.25f + s->modwheel * 0.5f) * 0.6f;   /* semitones peak */
    float tone_a = 1.0f - expf(-2.0f * (float)M_PI * (1500.0f + 16000.0f * P(wi_tone) * P(wi_tone)) / SR);
    float breath_amt = P(wi_breath) * (0.4f + 0.8f * P(breath));
    int held_any = 0;

    for (int k = 0; k < MAXV; k++) {
        voice_t *v = &s->v[k];
        if (!v->active) continue;
        held_any |= v->held || v->pedal;
        int choir = v->layer == L_CHOIR;
        float lg = choir ? ch_gain : wi_gain;
        if (!layer_on(s, v->layer)) { v->held = 0; v->pedal = 0; }
        /* control rate: pitch modulation for this block */
        v->t += dt;
        float pm = s->bend;
        if (choir) {
            v->drift += dt * (0.3f + 0.4f * motion);
            pm += sinf(v->drift) * 0.06f * (0.3f + motion);      /* slow ensemble drift */
        } else {
            v->lfo += dt * 6.2831853f * (4.6f + 1.2f * motion);
            float onset = fminf(1.0f, fmaxf(0.0f, (v->t - 0.25f) / 0.6f));   /* vibrato grows after the attack */
            pm += sinf(v->lfo) * vib_depth * onset * 0.25f;
        }
        float pmul = exp2f(pm / 12.0f);
        float bp_f = 2.0f * sinf((float)M_PI * fminf(0.45f, 3.0f * 440.0f * exp2f((v->note - 69) / 12.0f) / SR));
        for (int q = 0; q < v->nsrc; q++) v->s[q].inc = v->s[q].inc_base * pmul;
        for (int f = 0; f < frames; f++) {
            if (v->held || v->pedal) { v->env += v->att; if (v->env > 1.0f) v->env = 1.0f; }
            else v->env *= rel_mul;
            float l = 0, r = 0;
            for (int q = 0; q < v->nsrc; q++) {
                src_t *x = &v->s[q];
                const zone_t *z = x->z;
                const int16_t *d = z->pcm + x->i;
                /* choir zones sit a semitone apart, so the shift is tiny: linear is enough there */
                float smp = (choir ? d[0] + (d[1] - d[0]) * x->fr : hermite(z->pcm, x->i, x->fr)) * x->g;
                l += smp * x->gl; r += smp * x->gr;
                x->fr += x->inc;
                if (x->fr >= 1.0f) { int k = (int)x->fr; x->i += k; x->fr -= (float)k; }
                if (x->i >= z->le) x->i -= (z->le - z->ls);
            }
            float a = v->env * (0.45f + 0.55f * v->vel) * lg * (1.0f / 32768.0f);
            l *= a; r *= a;
            if (!choir) {
                /* breath: band-passed noise around the note, strongest at the onset */
                s->noise = s->noise * 1664525u + 1013904223u;
                float nz = ((int)(s->noise >> 9) - (1 << 22)) * (1.0f / (1 << 22));
                v->bp1 += bp_f * v->bp2; float hp = nz - v->bp1 - 0.7f * v->bp2; v->bp2 += bp_f * hp;
                float tr = 1.0f + 2.5f * expf(-v->t * 9.0f);
                float br = v->bp2 * breath_amt * 0.05f * tr * v->env * lg;
                l += br; r += br;
                v->tone_lp_l += tone_a * (l - v->tone_lp_l); v->tone_lp_r += tone_a * (r - v->tone_lp_r);
                l = v->tone_lp_l; r = v->tone_lp_r;
            }
            L[f] += l; R[f] += r;
        }
        if (!v->held && !v->pedal && v->env < 0.0003f) v->active = 0;
    }

    /* tone: Dark (12 dB low-pass) and Air (lift above ~5 kHz) */
    float dark = P(dark), air = P(air);
    float cut = 20000.0f * powf(0.045f, powf(dark, 1.5f));
    float a1 = 1.0f - expf(-2.0f * (float)M_PI * cut / SR);
    float aa = 1.0f - expf(-2.0f * (float)M_PI * 5000.0f / SR);
    for (int f = 0; f < frames; f++) {
        s->lp1_l += a1 * (L[f] - s->lp1_l); s->lp2_l += a1 * (s->lp1_l - s->lp2_l);
        s->lp1_r += a1 * (R[f] - s->lp1_r); s->lp2_r += a1 * (s->lp1_r - s->lp2_r);
        float l = s->lp2_l, r = s->lp2_r;
        s->air_l += aa * (l - s->air_l); s->air_r += aa * (r - s->air_r);
        L[f] = l + (l - s->air_l) * air * 0.9f;
        R[f] = r + (r - s->air_r) * air * 0.9f;
    }
    reverb_block(s, L, R, frames);

    float lvl = P(master) * 1.25f;
    lvl *= lvl;
    for (int f = 0; f < frames; f++) {
        float l = L[f] * lvl, r = R[f] * lvl;
        l = l * (27.0f + l * l) / (27.0f + 9.0f * l * l);   /* soft clip */
        r = r * (27.0f + r * r) / (27.0f + 9.0f * r * r);
        if (l > 1) l = 1; else if (l < -1) l = -1;
        if (r > 1) r = 1; else if (r < -1) r = -1;
        out[2 * f] = (int16_t)(l * 32000.0f);
        out[2 * f + 1] = (int16_t)(r * 32000.0f);
    }

    /* orb: energy from playing, phase on a timer (Motion), report frame changes */
    if (held_any) s->energy = fmaxf(s->energy, 0.6f);
    s->energy *= expf(-dt / 1.5f);
    s->orb_t += dt;
    float step = (0.30f - 0.20f * motion) * (s->energy > 0.3f ? 0.7f : 1.0f);
    if (s->orb_t >= step) { s->orb_t = 0.0f; s->orb_phase = (s->orb_phase + 1) % ORB_PHASES; }
    int frame = (s->energy > 0.3f ? ORB_PHASES : 0) + s->orb_phase;
    if (frame != s->orb_frame) { s->orb_frame = frame; s->val[I_orb] = (float)frame; s->rev++; }
}

static const mpc_engine_t ENGINE = { create, destroy, midi, set_param, get_param, render, NULL, NULL };
const mpc_engine_t *mpc_engine(void) { return &ENGINE; }
