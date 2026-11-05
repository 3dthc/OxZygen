/* OxZygen engine: six layers, effects, the orb.
 *
 * Layers (Edit page), each with Level, Mute and Solo:
 *   Choir       three singers (Claudia, Mirko, Sven) on the notes each covers; Vowel blends ah -> oh -> ih;
 *               Spread detunes and pans them; Attack sets the swell.
 *   Vowels      formant synthesis: two glottal oscillators through four vowel formants. Morph sweeps u-o-a-e-i,
 *               Formant sets the voice size, Motion sways the vowel.
 *   Winds       flute, ocarina or alto sax from samples: soft/loud by velocity, recorded vibrato by Vibrato, breath
 *               noise by Breath, brightness by Tone.
 *   Bells       modal synthesis, eight church-bell partials: Strike (brightness, mallet), Decay, Shimmer (beating).
 *   Soundscape  pitched wind (resonances on the note's harmonics, gusting) plus a granular cloud of choir whispers:
 *               Density, Drift, Width.
 *   Texture     granular voices: Grain size, Pitch (-24..+24 in musical steps), Smear (scatter, reverse grains).
 * Effects (FX page): Drive -> Dark/Air tone -> ping-pong Delay -> 8-line reverb; the Sub (follows the lowest held
 * note, Drop glides it into pitch) is added after the reverb so it stays dry. Output level last.
 * Player macros: Voice = Winds level, Choir = Choir and Vowels levels, Bells = Bells level, Breath = attack softness
 * and breath, Air = brightness and Soundscape level, Dark = low-pass, Space = reverb and release, Motion = vibrato,
 * drift, vowel sway, Texture level and the orb's speed.
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
#define MAXV 32              /* voices: one per layer per note */
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


/* ---------- small DSP helpers ---------- */
typedef struct { float ic1, ic2; } svf_t;                       /* TPT state-variable filter (Zavalishin) */
typedef struct { float a1, a2, a3, k; } svfc_t;
static inline svfc_t svf_coef(float f, float q) {
    if (f > 0.45f * SR) f = 0.45f * SR;
    if (f < 10.0f) f = 10.0f;
    svfc_t c;
    float g = tanf((float)M_PI * f / SR);
    c.k = 1.0f / q;
    c.a1 = 1.0f / (1.0f + g * (g + c.k)); c.a2 = g * c.a1; c.a3 = g * c.a2;
    return c;
}
static inline float svf_bp(svf_t *s, const svfc_t *c, float x) {   /* band-pass, unity gain at the centre */
    float v3 = x - s->ic2, v1 = c->a1 * s->ic1 + c->a2 * v3, v2 = s->ic2 + c->a2 * s->ic1 + c->a3 * v3;
    s->ic1 = 2 * v1 - s->ic1; s->ic2 = 2 * v2 - s->ic2;
    return v1 * c->k;
}
static inline float svf_lp(svf_t *s, const svfc_t *c, float x) {
    float v3 = x - s->ic2, v1 = c->a1 * s->ic1 + c->a2 * v3, v2 = s->ic2 + c->a2 * s->ic1 + c->a3 * v3;
    s->ic1 = 2 * v1 - s->ic1; s->ic2 = 2 * v2 - s->ic2;
    return v2;
}
static inline float polyblep(float t, float dt) {
    if (t < dt) { t /= dt; return t + t - t * t - 1.0f; }
    if (t > 1.0f - dt) { t = (t - 1.0f) / dt; return t * t + t + t + 1.0f; }
    return 0.0f;
}
static inline float softclip(float x) {
    if (x > 3.0f) return 1.0f;
    if (x < -3.0f) return -1.0f;
    return x * (27.0f + x * x) / (27.0f + 9.0f * x * x);
}
static inline unsigned rnd(unsigned *st) { *st ^= *st << 13; *st ^= *st >> 17; *st ^= *st << 5; return *st; }
static inline float frand(unsigned *st) { return (rnd(st) >> 8) * (1.0f / 16777216.0f); }        /* 0..1 */
static inline float nrand(unsigned *st) { return frand(st) * 2.0f - 1.0f; }                      /* -1..1 */
static float HANN[257];
static float note_hz(float n) { return 440.0f * exp2f((n - 69.0f) / 12.0f); }

/* ---------- voices ---------- */
#define NP 8                 /* bell partials */
#define NGRAIN 6             /* grains per voice */
enum { L_CHOIR, L_VOWELS, L_WINDS, L_BELLS, L_SCAPE, L_TEXTURE, NLAYERS };

typedef struct { const zone_t *z; int i; float fr, inc_base, inc, g, gl, gr; } src_t;
typedef struct { const zone_t *z; float pos, inc, ph, dph, gl, gr; int on; } grain_t;

typedef struct {
    int active, note, layer, held, pedal;
    float vel, env, att, t, lfo, drift, pan;
    unsigned age, seed;
    /* sample layers (choir, winds) */
    int nsrc;
    src_t s[MAXSRC];
    float tone_l, tone_r;
    svf_t breath;
    /* vowels */
    float ph[2], glot;
    svf_t fm[4];
    /* bells */
    float pc[NP], ps[NP], pa[NP], pdec[NP], beat[NP], click;
    /* soundscape and texture */
    grain_t gr[NGRAIN];
    int next_grain;
    svf_t wind[3], airband;
    float gust, gust_ph, wdrift[3];
} voice_t;

typedef struct {
    float val[NPARAMS];
    voice_t v[MAXV];
    unsigned clock, noise;
    int pedal_down;
    float bend, modwheel;
    unsigned char keys[128];          /* held keys, for the sub */
    float lp1_l, lp1_r, lp2_l, lp2_r, air_l, air_r;
    reverb_t *rv;
    /* delay */
    float *dly_l, *dly_r, dly_time, dly_lp_l, dly_lp_r;
    int dly_w;
    /* drive */
    float drv_lp_l, drv_lp_r;
    /* sub */
    float sub_ph, sub_env, sub_note, sub_glide, sub_hz;
    int sub_target;
    /* orb */
    float energy, orb_t;
    int orb_phase, orb_frame;
    unsigned rev;
} oxz_t;

#define DLY_MAX 70560          /* 1.6 s */

static int idx_of(const char *key) {
    for (int i = 0; i < NPARAMS; i++) if (!strcmp(PARAMS[i].key, key)) return i;
    return -1;
}
#define P(name) (s->val[I_##name] * 0.01f)
static int I_master, I_voice, I_breath, I_choir, I_bells, I_air, I_dark, I_space, I_motion,
    I_ch_vowel, I_ch_attack, I_ch_spread, I_ch_level,
    I_vo_morph, I_vo_attack, I_vo_formant, I_vo_level,
    I_wi_breath, I_wi_vibrato, I_wi_tone, I_wi_level, I_wi_inst,
    I_be_strike, I_be_decay, I_be_shimmer, I_be_level,
    I_sc_density, I_sc_drift, I_sc_width, I_sc_level,
    I_tx_grain, I_tx_pitch, I_tx_smear, I_tx_level,
    I_rv_size, I_rv_decay, I_rv_mix, I_dl_time, I_dl_feedback, I_dl_mix, I_dr_amount, I_dr_tone, I_dr_mix,
    I_sb_level, I_sb_tune, I_sb_drop, I_orb;
static int I_mute[NLAYERS], I_solo[NLAYERS];
static int g_idx_done;
static void init_idx(void) {
    if (g_idx_done) return;
#define X(n) I_##n = idx_of(#n)
    X(master); X(voice); X(breath); X(choir); X(bells); X(air); X(dark); X(space); X(motion);
    X(ch_vowel); X(ch_attack); X(ch_spread); X(ch_level); X(vo_morph); X(vo_attack); X(vo_formant); X(vo_level);
    X(wi_breath); X(wi_vibrato); X(wi_tone); X(wi_level); X(wi_inst);
    X(be_strike); X(be_decay); X(be_shimmer); X(be_level); X(sc_density); X(sc_drift); X(sc_width); X(sc_level);
    X(tx_grain); X(tx_pitch); X(tx_smear); X(tx_level);
    X(rv_size); X(rv_decay); X(rv_mix); X(dl_time); X(dl_feedback); X(dl_mix); X(dr_amount); X(dr_tone); X(dr_mix);
    X(sb_level); X(sb_tune); X(sb_drop); X(orb);
#undef X
    static const char *PRE[NLAYERS] = {"ch", "vo", "wi", "be", "sc", "tx"};
    for (int l = 0; l < NLAYERS; l++) {
        char k[16];
        snprintf(k, sizeof k, "%s_mute", PRE[l]); I_mute[l] = idx_of(k);
        snprintf(k, sizeof k, "%s_solo", PRE[l]); I_solo[l] = idx_of(k);
    }
    for (int i = 0; i <= 256; i++) HANN[i] = 0.5f - 0.5f * cosf(2.0f * (float)M_PI * i / 256.0f);
    g_idx_done = 1;
}

static void *create(const char *data_dir) {
    init_idx();
    oxz_t *s = calloc(1, sizeof *s);
    if (!s) return NULL;
    s->rv = calloc(1, sizeof *s->rv);
    s->dly_l = calloc(DLY_MAX, sizeof(float));
    s->dly_r = calloc(DLY_MAX, sizeof(float));
    for (int i = 0; i < NPARAMS; i++)   /* params.h keeps defaults normalized 0..1; set_param() gets real units */
        s->val[i] = PARAMS[i].nopts ? floorf(PARAMS[i].def * (PARAMS[i].nopts - 1) + 0.5f)
                                    : PARAMS[i].min + PARAMS[i].def * (PARAMS[i].max - PARAMS[i].min);
    s->noise = 0x9e3779b9u;
    s->sub_target = -1;
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
    free(s->rv); free(s->dly_l); free(s->dly_r);
    free(s);
}

static int layer_on(oxz_t *s, int layer) {
    int any_solo = 0;
    for (int l = 0; l < NLAYERS; l++) if (s->val[I_solo[l]] > 0.5f) any_solo = 1;
    if (s->val[I_mute[layer]] > 0.5f) return 0;
    return !any_solo || s->val[I_solo[layer]] > 0.5f;
}

/* each layer's level: its own Level knob times the Player macro that owns it */
static float layer_gain(oxz_t *s, int l) {
    switch (l) {
    case L_CHOIR:   return P(ch_level) * P(choir) * 1.4f;
    case L_VOWELS:  return P(vo_level) * P(choir) * 1.3f;
    case L_WINDS:   return P(wi_level) * P(voice) * 2.0f;
    case L_BELLS:   return P(be_level) * P(bells) * 2.4f;
    case L_SCAPE:   return P(sc_level) * (0.35f + 1.1f * P(air));
    default:        return P(tx_level) * (0.5f + 0.8f * P(motion));
    }
}

/* per-layer polyphony: a full layer reuses its own quietest released voice (else its oldest) instead of
 * growing, which keeps long release tails from piling up on the MPC's CPU */
static const int LAYER_CAP[NLAYERS] = {10, 8, 6, 12, 6, 6};

static voice_t *alloc_voice(oxz_t *s, int layer) {
    voice_t *best = NULL;
    int count = 0;
    for (int k = 0; k < MAXV; k++) count += s->v[k].active && s->v[k].layer == layer;
    if (count >= LAYER_CAP[layer]) {
        for (int k = 0; k < MAXV; k++) {
            voice_t *v = &s->v[k];
            if (!v->active || v->layer != layer) continue;
            int rel = !v->held && !v->pedal, brel = best && !best->held && !best->pedal;
            if (!best || (rel && !brel) || (rel == brel && (rel ? v->env < best->env : v->age < best->age))) best = v;
        }
        return best;
    }
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
    x->inc_base = exp2f((note - z->pitch + detune_cents / 100.0f) / 12.0f);
    x->g = g;
    float a = (pan + 1.0f) * 0.25f * (float)M_PI;   /* equal-power pan, -1..1 */
    x->gl = cosf(a); x->gr = sinf(a);
}

/* which singers cover a note (the nearest one stretches when none does) */
static int singers_for(const bank_t *b, float note, float gs[3]) {
    int n = 0;
    for (int sg = 0; sg < 3; sg++) { gs[sg] = (note >= b->lo[sg] - 4 && note <= b->hi[sg] + 4); n += gs[sg] > 0; }
    if (!n) { gs[note < b->lo[2] ? 2 : 0] = 1.0f; n = 1; }
    return n;
}

static void choir_sources(oxz_t *s, const bank_t *b, voice_t *v) {
    float vow = P(ch_vowel) * 2.0f;              /* 0 ah, 1 oh, 2 ih */
    int va = vow < 1.0f ? 0 : 1;
    float w = vow - va, wa = cosf(w * (float)M_PI / 2), wb = sinf(w * (float)M_PI / 2);
    float spread = P(ch_spread);
    static const float PAN[3] = {-0.45f, 0.45f, 0.0f}, DET[3] = {-7.0f, 6.0f, -2.0f};
    float gs[3];
    float norm = 1.0f / sqrtf((float)singers_for(b, v->note, gs));
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

/* bells: minor-third church-bell partials (hum, prime, tierce, quint, nominal and above) */
static const float BELL_RATIO[NP] = {0.5f, 1.0f, 1.183f, 1.506f, 2.0f, 2.514f, 2.662f, 3.011f};
static const float BELL_AMP[NP] = {0.45f, 1.0f, 0.62f, 0.38f, 0.75f, 0.28f, 0.22f, 0.16f};

static void bells_start(oxz_t *s, voice_t *v) {
    float strike = P(be_strike) * (0.6f + 0.6f * v->vel);
    float t60 = 0.6f + 11.0f * P(be_decay) * P(be_decay);
    float f0 = note_hz((float)v->note);
    for (int k = 0; k < NP; k++) {
        float f = f0 * BELL_RATIO[k];
        if (f > 0.45f * SR) { v->pa[k] = 0; continue; }
        float bright = k < 2 ? 1.0f : 0.25f + 1.1f * strike;           /* Strike brings out the upper partials */
        v->pa[k] = BELL_AMP[k] * bright;
        float tk = t60 / powf(BELL_RATIO[k] / 0.5f, 0.55f);           /* higher partials die sooner */
        v->pdec[k] = expf(-6.9078f / (tk * SR));                       /* -60 dB over tk */
        v->pc[k] = 1.0f; v->ps[k] = 0.0f;
        v->beat[k] = frand(&v->seed) * 6.2831853f;
    }
    v->click = 0.35f * strike;
}

static void note_on(oxz_t *s, int note, float vel) {
    const bank_t *b = __atomic_load_n(&g_bank, __ATOMIC_ACQUIRE);
    s->energy = fminf(1.0f, s->energy + 0.35f + 0.4f * vel);
    for (int layer = 0; layer < NLAYERS; layer++) {
        if (!layer_on(s, layer) || layer_gain(s, layer) < 0.001f) continue;
        int needs_bank = layer == L_CHOIR || layer == L_WINDS || layer == L_SCAPE || layer == L_TEXTURE;
        if (needs_bank && (!b || !b->ok)) continue;
        voice_t *v = alloc_voice(s, layer);
        memset(v, 0, sizeof *v);
        v->active = 1; v->held = 1; v->note = note; v->layer = layer; v->vel = vel; v->age = ++s->clock;
        v->seed = 0x2545F491u ^ (s->clock * 2654435761u) ^ (unsigned)(note * 7919);
        rnd(&v->seed);
        v->drift = frand(&v->seed) * 6.2831853f;
        v->pan = nrand(&v->seed);
        switch (layer) {
        case L_CHOIR:
            v->att = 1.0f / (SR * attack_secs(P(ch_attack), P(breath)));
            choir_sources(s, b, v);
            break;
        case L_WINDS:
            v->att = 1.0f / (SR * (0.012f + 0.25f * P(breath) * P(breath) + 0.05f * P(wi_breath)));
            winds_sources(s, b, v);
            break;
        case L_VOWELS:
            v->att = 1.0f / (SR * attack_secs(P(vo_attack), P(breath)));
            v->ph[0] = frand(&v->seed); v->ph[1] = frand(&v->seed);
            break;
        case L_BELLS:
            v->att = 1.0f;          /* struck: full at once, the partials decay on their own */
            bells_start(s, v);
            break;
        case L_SCAPE:
            v->att = 1.0f / (SR * (0.4f + 2.0f * P(breath)));
            v->gust_ph = frand(&v->seed) * 6.2831853f;
            for (int k = 0; k < 3; k++) v->wdrift[k] = frand(&v->seed) * 6.2831853f;
            break;
        default:
            v->att = 1.0f / (SR * (0.05f + 1.5f * P(breath) * P(breath)));
            break;
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

static int lowest_key(oxz_t *s) {
    for (int n = 0; n < 128; n++) if (s->keys[n]) return n;
    return -1;
}

static void midi(void *inst, const uint8_t *m, int n) {
    oxz_t *s = inst;
    if (n < 2) return;
    int st = m[0] & 0xF0;
    if (st == 0xE0 && n >= 3) { s->bend = (((m[2] << 7) | m[1]) - 8192) / 8192.0f * 2.0f; return; }
    if (n < 3) return;
    if (st == 0x90 && m[2] > 0) {
        int was = lowest_key(s);
        s->keys[m[1]] = 1 | (s->pedal_down ? 0 : 0);
        note_on(s, m[1], m[2] / 127.0f);
        int low = lowest_key(s);
        if (low != was || was < 0) {                 /* the sub follows the lowest held note, dropping in */
            s->sub_target = low;
            s->sub_glide = (float)(was < 0 ? low + P(sb_drop) * 12.0f : (s->sub_note > 0 ? s->sub_note : low));
            if (was < 0) s->sub_ph = 0.0f;
        }
    } else if (st == 0x80 || st == 0x90) {
        note_off(s, m[1]);
        if (!s->pedal_down) s->keys[m[1]] = 0; else s->keys[m[1]] = 2;   /* 2: held by the pedal */
        int low = lowest_key(s);
        if (low >= 0) s->sub_target = low;
    } else if (st == 0xB0) {
        if (m[1] == 1) s->modwheel = m[2] / 127.0f;
        else if (m[1] == 64) {
            s->pedal_down = m[2] >= 64;
            if (!s->pedal_down) {
                for (int k = 0; k < MAXV; k++) s->v[k].pedal = 0;
                for (int k = 0; k < 128; k++) if (s->keys[k] == 2) s->keys[k] = 0;
            }
        } else if (m[1] == 120 || m[1] == 123) {
            for (int k = 0; k < MAXV; k++) { s->v[k].held = 0; s->v[k].pedal = 0; if (m[1] == 120) s->v[k].active = 0; }
            memset(s->keys, 0, sizeof s->keys);
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

/* ---------- per-layer renderers: add one voice's block into L/R ---------- */
static void render_samples(oxz_t *s, voice_t *v, float *L, float *R, int frames, float lg, float pmul, float rel_mul) {
    int choir = v->layer == L_CHOIR;
    float tone_a = 1.0f - expf(-2.0f * (float)M_PI * (1500.0f + 16000.0f * P(wi_tone) * P(wi_tone)) / SR);
    float breath_amt = P(wi_breath) * (0.4f + 0.8f * P(breath));
    svfc_t bc = svf_coef(3.0f * note_hz((float)v->note), 1.4f);
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
        if (!choir) {   /* breath: band-passed noise around the note, strongest at the onset */
            float nz = nrand(&s->noise);
            float tr = 1.0f + 2.5f * expf(-v->t * 9.0f);
            float br = svf_bp(&v->breath, &bc, nz) * breath_amt * 0.06f * tr * v->env * lg;
            l += br; r += br;
            v->tone_l += tone_a * (l - v->tone_l); v->tone_r += tone_a * (r - v->tone_r);
            l = v->tone_l; r = v->tone_r;
        }
        L[f] += l; R[f] += r;
    }
}

/* vowels: formant frequencies (Hz), levels (dB) and bandwidths for u, o, a, e, i (an alto voice) */
static const float VF[5][4] = {{325, 700, 2530, 3500}, {450, 800, 2830, 3500}, {800, 1150, 2800, 3500},
                               {400, 1600, 2700, 3300}, {350, 1700, 2700, 3700}};
static const float VA[5][4] = {{0, -12, -30, -40}, {0, -9, -16, -28}, {0, -4, -20, -36}, {0, -24, -30, -35}, {0, -20, -30, -36}};
static const float VB[5][4] = {{50, 60, 170, 180}, {70, 80, 100, 130}, {80, 90, 120, 130}, {60, 80, 120, 150}, {50, 100, 120, 150}};

static void render_vowels(oxz_t *s, voice_t *v, float *L, float *R, int frames, float lg, float pmul, float rel_mul) {
    float dt = frames / SR, motion = P(motion);
    v->drift += dt * (0.15f + 0.35f * motion);
    float morph = P(vo_morph) * 4.0f + sinf(v->drift) * (0.15f + 0.6f * motion);   /* Motion sways the vowel */
    if (morph < 0) morph = 0;
    if (morph > 3.999f) morph = 3.999f;
    int a = (int)morph;
    float w = morph - a;
    float scale = 0.72f + 0.62f * P(vo_formant);                    /* Formant: larger to smaller voice */
    svfc_t c[4];
    float amp[4];
    for (int k = 0; k < 4; k++) {
        float fz = (VF[a][k] + (VF[a + 1][k] - VF[a][k]) * w) * scale;
        float bw = (VB[a][k] + (VB[a + 1][k] - VB[a][k]) * w) * (0.8f + 0.4f * scale);
        float db = VA[a][k] + (VA[a + 1][k] - VA[a][k]) * w;
        c[k] = svf_coef(fz, fz / bw);
        amp[k] = powf(10.0f, db / 20.0f);
    }
    float f0 = note_hz((float)v->note) * pmul;
    float dt0 = f0 / SR, dt1 = f0 * 1.0046f / SR;                    /* two glottal sources, 8 cents apart */
    float glot_a = 1.0f - expf(-2.0f * (float)M_PI * 2200.0f / SR);
    float asp = 0.05f + 0.12f * P(breath);                           /* breathiness */
    float gl = cosf((v->pan * 0.35f + 1.0f) * 0.25f * (float)M_PI), gr = sinf((v->pan * 0.35f + 1.0f) * 0.25f * (float)M_PI);
    for (int f = 0; f < frames; f++) {
        if (v->held || v->pedal) { v->env += v->att; if (v->env > 1.0f) v->env = 1.0f; }
        else v->env *= rel_mul;
        float x0 = 2.0f * v->ph[0] - 1.0f - polyblep(v->ph[0], dt0);
        float x1 = 2.0f * v->ph[1] - 1.0f - polyblep(v->ph[1], dt1);
        v->ph[0] += dt0; if (v->ph[0] >= 1.0f) v->ph[0] -= 1.0f;
        v->ph[1] += dt1; if (v->ph[1] >= 1.0f) v->ph[1] -= 1.0f;
        v->glot += glot_a * ((x0 + x1) * 0.5f - v->glot);
        float src = v->glot + nrand(&s->noise) * asp;
        float y = 0;
        for (int k = 0; k < 4; k++) y += svf_bp(&v->fm[k], &c[k], src) * amp[k];
        y *= v->env * (0.5f + 0.5f * v->vel) * lg * 1.75f;
        L[f] += y * gl; R[f] += y * gr;
    }
}

static void render_bells(oxz_t *s, voice_t *v, float *L, float *R, int frames, float lg, float pmul, float rel_mul) {
    float f0 = note_hz((float)v->note) * pmul, dt = frames / SR, shimmer = P(be_shimmer);
    float rot_c[NP], rot_s[NP], dec[NP], beat_amt[NP];
    for (int k = 0; k < NP; k++) {
        float w = 2.0f * (float)M_PI * f0 * BELL_RATIO[k] / SR;
        rot_c[k] = cosf(w); rot_s[k] = sinf(w);
        dec[k] = v->pdec[k] * ((v->held || v->pedal) ? 1.0f : rel_mul);   /* let go: damp toward the release */
        v->beat[k] += dt * 6.2831853f * (0.6f + 2.2f * shimmer) * (0.5f + 0.25f * k);   /* slow beating, faster up high */
        beat_amt[k] = 1.0f - shimmer * 0.45f * (1.0f - cosf(v->beat[k]));
    }
    float gl = cosf((v->pan * 0.5f + 1.0f) * 0.25f * (float)M_PI), gr = sinf((v->pan * 0.5f + 1.0f) * 0.25f * (float)M_PI);
    float total = 0;
    for (int f = 0; f < frames; f++) {
        float y = 0;
        for (int k = 0; k < NP; k++) {
            float c = v->pc[k] * rot_c[k] - v->ps[k] * rot_s[k];
            float sn = v->pc[k] * rot_s[k] + v->ps[k] * rot_c[k];
            v->pc[k] = c * dec[k]; v->ps[k] = sn * dec[k];
            y += v->ps[k] * v->pa[k] * beat_amt[k];
        }
        if (v->click > 0.0005f) { y += nrand(&s->noise) * v->click; v->click *= 0.985f; }   /* mallet */
        y *= (0.4f + 0.6f * v->vel) * lg * 0.24f;
        L[f] += y * gl; R[f] += y * gr;
    }
    for (int k = 0; k < NP; k++) total += fabsf(v->pc[k]) * v->pa[k] + fabsf(v->ps[k]) * v->pa[k];
    v->env = total;   /* the voice ends once every partial has died away */
}

/* grains: a Hann-windowed slice of a sample zone */
static void grain_spawn(voice_t *v, const zone_t *z, float target_note, float size_s, float pos_rand, int reverse,
                        float pan, float detune_cents) {
    if (!z) return;
    int slot = -1;
    for (int g = 0; g < NGRAIN; g++) if (!v->gr[g].on) { slot = g; break; }
    if (slot < 0) return;
    grain_t *g = &v->gr[slot];
    float inc = exp2f((target_note - z->pitch + detune_cents / 100.0f) / 12.0f);
    float len = size_s * SR;
    float span = len * inc;
    float avail = (float)z->le - 8.0f;
    if (span > avail * 0.8f) { span = avail * 0.8f; len = span / inc; }
    float lo = fminf((float)z->ls, avail - span), hi = avail - span;
    if (hi < lo) hi = lo;
    float start = lo + (hi - lo) * (0.5f + (pos_rand - 0.5f));
    if (start < 2) start = 2;
    g->z = z; g->inc = reverse ? -inc : inc; g->pos = reverse ? start + span : start;
    g->ph = 0.0f; g->dph = 256.0f / fmaxf(16.0f, len);
    float a = (pan + 1.0f) * 0.25f * (float)M_PI;
    g->gl = cosf(a); g->gr = sinf(a);
    g->on = 1;
}

static inline void grains_run(voice_t *v, float *l, float *r) {
    for (int k = 0; k < NGRAIN; k++) {
        grain_t *g = &v->gr[k];
        if (!g->on) continue;
        int i = (int)g->pos;
        float fr = g->pos - i, w = HANN[(int)g->ph];
        const int16_t *d = g->z->pcm + i;
        float x = (d[0] + (d[1] - d[0]) * fr) * w;
        *l += x * g->gl; *r += x * g->gr;
        g->pos += g->inc; g->ph += g->dph;
        if (g->ph >= 256.0f || g->pos < 1.0f || g->pos >= (float)g->z->le) g->on = 0;
    }
}

static const zone_t *choir_zone(const bank_t *b, voice_t *v, float note) {
    float gs[3];
    singers_for(b, note, gs);
    int pick[3], n = 0;
    for (int sg = 0; sg < 3; sg++) if (gs[sg]) pick[n++] = sg;
    int sg = pick[rnd(&v->seed) % n];
    int vow = rnd(&v->seed) % 3;
    if (!b->g[sg * 3 + vow].n) vow = 0;
    return nearest(b, sg * 3 + vow, note);
}

static void render_scape(oxz_t *s, voice_t *v, float *L, float *R, int frames, float lg, float pmul, float rel_mul,
                         const bank_t *b) {
    float dt = frames / SR, drift = P(sc_drift), width = P(sc_width), density = P(sc_density);
    float note = v->note + 12.0f * log2f(pmul);
    /* pitched wind: three narrow resonances on the note's harmonics, each wandering with Drift */
    svfc_t wc[3];
    float wg[3];
    for (int k = 0; k < 3; k++) {
        v->wdrift[k] += dt * (0.07f + 0.25f * drift) * (1.0f + 0.37f * k);
        float cents = sinf(v->wdrift[k]) * drift * 45.0f;
        float fz = note_hz(note + cents / 100.0f) * (k + 1), q = 26.0f + 30.0f * (1.0f - density);
        wc[k] = svf_coef(fz, q);
        wg[k] = 0.11f * sqrtf(0.5f * SR * q / fz) / (1.0f + 0.6f * k);   /* a narrow band carries little energy: lift it */
    }
    v->gust_ph += dt * (0.08f + 0.25f * drift);
    v->gust = 0.55f + 0.45f * sinf(v->gust_ph) * sinf(v->gust_ph * 0.61f + 1.3f);   /* slow, uneven gusts */
    svfc_t ac = svf_coef(1600.0f + 900.0f * sinf(v->gust_ph * 0.7f), 2.2f);        /* a faint airy band */
    /* granular air: whispers of the choir, on the note, scattered in the stereo field */
    float rate = 2.0f + 22.0f * density;                     /* grains per second */
    int every = (int)(SR / rate);
    for (int f = 0; f < frames; f++) {
        if (v->held || v->pedal) { v->env += v->att; if (v->env > 1.0f) v->env = 1.0f; }
        else v->env *= rel_mul;
        if (--v->next_grain <= 0) {
            v->next_grain = every + (int)(frand(&v->seed) * every);
            grain_spawn(v, choir_zone(b, v, note), note + (rnd(&v->seed) & 1 ? 12.0f : 0.0f), 0.09f + 0.2f * frand(&v->seed),
                        frand(&v->seed), 0, nrand(&v->seed) * width, nrand(&v->seed) * 25.0f * drift);
        }
        float gl = 0, gr = 0;
        grains_run(v, &gl, &gr);
        float nl = nrand(&s->noise), nr = nrand(&s->noise);
        float w0 = svf_bp(&v->wind[0], &wc[0], nl) * wg[0];
        float w1 = svf_bp(&v->wind[1], &wc[1], nr) * wg[1];
        float w2 = svf_bp(&v->wind[2], &wc[2], (nl - nr) * 0.7f) * wg[2];
        float air = svf_bp(&v->airband, &ac, (nl + nr) * 0.5f) * 0.025f;
        float e = v->env * v->gust * lg;
        /* Width: the harmonics move apart, the fundamental stays centred */
        float l = (w0 + w1 * (1.0f - width) + w2 * width + air) * e + gl * e * (0.55f / 32768.0f);
        float r = (w0 + w1 * width + w2 * (1.0f - width) + air) * e + gr * e * (0.55f / 32768.0f);
        L[f] += l; R[f] += r;
    }
}

static const float TX_STEPS[8] = {-24, -12, -5, 0, 7, 12, 19, 24};

static void render_texture(oxz_t *s, voice_t *v, float *L, float *R, int frames, float lg, float pmul, float rel_mul,
                           const bank_t *b) {
    float smear = P(tx_smear);
    float size = 0.02f * powf(20.0f, P(tx_grain));          /* 20 ms .. 400 ms */
    int step = (int)(P(tx_pitch) * 7.0f + 0.5f);
    float note = v->note + TX_STEPS[step] + 12.0f * log2f(pmul);
    float overlap = 1.5f + 3.0f * smear;                    /* grains sounding at once */
    int every = (int)(size * SR / overlap);
    if (every < 64) every = 64;
    for (int f = 0; f < frames; f++) {
        if (v->held || v->pedal) { v->env += v->att; if (v->env > 1.0f) v->env = 1.0f; }
        else v->env *= rel_mul;
        if (--v->next_grain <= 0) {
            v->next_grain = every + (int)(nrand(&v->seed) * every * 0.3f * smear);
            int reverse = frand(&v->seed) < smear * 0.45f;
            grain_spawn(v, choir_zone(b, v, note), note, size * (0.8f + 0.4f * frand(&v->seed)),
                        0.5f + (frand(&v->seed) - 0.5f) * (0.2f + 0.8f * smear), reverse,
                        nrand(&v->seed) * (0.2f + 0.7f * smear), nrand(&v->seed) * 18.0f * smear);
        }
        float gl = 0, gr = 0;
        grains_run(v, &gl, &gr);
        float e = v->env * (0.5f + 0.5f * v->vel) * lg * (0.6f / 32768.0f) / sqrtf(overlap * 0.5f);
        L[f] += gl * e; R[f] += gr * e;
    }
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


/* ---------- effects ---------- */
static void drive_block(oxz_t *s, float *L, float *R, int frames) {
    float mix = P(dr_mix);
    if (mix < 0.001f) return;
    float amt = P(dr_amount), pre = 1.0f + 9.0f * amt * amt, make = 1.0f / (1.0f + 1.8f * amt);
    float ta = 1.0f - expf(-2.0f * (float)M_PI * (1200.0f + 14000.0f * P(dr_tone) * P(dr_tone)) / SR);
    for (int f = 0; f < frames; f++) {
        float l = softclip(L[f] * pre) * make, r = softclip(R[f] * pre) * make;
        s->drv_lp_l += ta * (l - s->drv_lp_l); s->drv_lp_r += ta * (r - s->drv_lp_r);
        L[f] += (s->drv_lp_l - L[f]) * mix;
        R[f] += (s->drv_lp_r - R[f]) * mix;
    }
}

static void delay_block(oxz_t *s, float *L, float *R, int frames) {
    float mix = P(dl_mix);
    if (mix < 0.001f && s->dly_time == 0) return;
    float target = (0.06f * powf(25.0f, P(dl_time))) * SR;          /* 60 ms .. 1.5 s */
    if (s->dly_time == 0) s->dly_time = target;
    float fb = 0.92f * P(dl_feedback);
    float la = 1.0f - expf(-2.0f * (float)M_PI * (2500.0f + 5000.0f * (1.0f - P(dark))) / SR);
    for (int f = 0; f < frames; f++) {
        s->dly_time += (target - s->dly_time) * 0.0004f;           /* glide, no zipper on time changes */
        float rp = (float)s->dly_w - s->dly_time;
        if (rp < 0) rp += DLY_MAX;
        int i = (int)rp, j = i + 1 < DLY_MAX ? i + 1 : 0;
        float fr = rp - i;
        float dl = s->dly_l[i] + (s->dly_l[j] - s->dly_l[i]) * fr;
        float dr = s->dly_r[i] + (s->dly_r[j] - s->dly_r[i]) * fr;
        s->dly_lp_l += la * (dl - s->dly_lp_l); s->dly_lp_r += la * (dr - s->dly_lp_r);
        /* ping-pong: the input enters on the left, each repeat crosses sides */
        s->dly_l[s->dly_w] = (L[f] + R[f]) * 0.5f + s->dly_lp_r * fb;
        s->dly_r[s->dly_w] = s->dly_lp_l * fb;
        if (++s->dly_w == DLY_MAX) s->dly_w = 0;
        L[f] += dl * mix; R[f] += dr * mix;
    }
}

static void sub_block(oxz_t *s, float *L, float *R, int frames) {
    float lvl = P(sb_level);
    int held = s->sub_target >= 0 && lowest_key(s) >= 0;
    if (lvl < 0.001f && s->sub_env < 0.0001f) return;
    float target = s->sub_target >= 0 ? s->sub_target + (-24.0f + roundf(P(sb_tune) * 24.0f)) : 0;
    float glide = expf(-1.0f / (SR * (0.03f + 0.35f * P(sb_drop))));    /* Drop: how slowly it falls into pitch */
    float glide_target = s->sub_target >= 0 ? (float)s->sub_target : 0;
    float att = 1.0f / (0.006f * SR), rel = expf(-1.0f / (0.12f * SR));
    for (int f = 0; f < frames; f++) {
        s->sub_glide = glide_target + (s->sub_glide - glide_target) * glide;
        float n = s->sub_glide + (target - glide_target);
        float hz = note_hz(n);
        s->sub_ph += hz / SR;
        if (s->sub_ph >= 1.0f) s->sub_ph -= 1.0f;
        if (held) { s->sub_env += att; if (s->sub_env > 1.0f) s->sub_env = 1.0f; }
        else s->sub_env *= rel;
        float x = softclip(sinf(s->sub_ph * 6.2831853f) * 1.25f) * s->sub_env * lvl * 0.55f;
        L[f] += x; R[f] += x;
    }
    s->sub_note = s->sub_glide;
}

static void render(void *inst, int16_t *out, int frames) {
    oxz_t *s = inst;
    const bank_t *b = __atomic_load_n(&g_bank, __ATOMIC_ACQUIRE);
    float L[128], R[128];
    memset(L, 0, sizeof L); memset(R, 0, sizeof R);
    if (frames > 128) frames = 128;
    float dt = frames / SR, motion = P(motion), space = P(space);
    float rel_secs = 0.25f + 3.8f * powf(space, 1.4f);
    float rel_mul = expf(-1.0f / (SR * rel_secs / 4.6f));     /* -40 dB over rel_secs */
    float vib_depth = (P(wi_vibrato) * 0.35f + motion * 0.25f + s->modwheel * 0.5f) * 0.6f;   /* semitones peak */
    float lg[NLAYERS];
    int on[NLAYERS];
    for (int l = 0; l < NLAYERS; l++) { lg[l] = layer_gain(s, l); on[l] = layer_on(s, l); }
    int held_any = 0;

    for (int k = 0; k < MAXV; k++) {
        voice_t *v = &s->v[k];
        if (!v->active) continue;
        int L_ = v->layer;
        if (L_ != L_BELLS && L_ != L_VOWELS && (!b || !b->ok)) { v->active = 0; continue; }
        held_any |= v->held || v->pedal;
        if (!on[L_]) { v->held = 0; v->pedal = 0; }
        v->t += dt;
        float pm = s->bend;
        if (L_ == L_CHOIR || L_ == L_TEXTURE) {
            v->drift += dt * (0.3f + 0.4f * motion);
            pm += sinf(v->drift) * 0.06f * (0.3f + motion);      /* slow ensemble drift */
        } else if (L_ == L_WINDS || L_ == L_VOWELS) {
            v->lfo += dt * 6.2831853f * (4.6f + 1.2f * motion);
            float onset = fminf(1.0f, fmaxf(0.0f, (v->t - 0.25f) / 0.6f));   /* vibrato grows after the attack */
            float depth = L_ == L_WINDS ? vib_depth : (0.12f + 0.3f * motion + s->modwheel * 0.5f) * 0.6f;
            pm += sinf(v->lfo) * depth * onset * 0.25f;
        }
        float pmul = exp2f(pm / 12.0f);
        switch (L_) {
        case L_CHOIR: case L_WINDS: render_samples(s, v, L, R, frames, lg[L_], pmul, rel_mul); break;
        case L_VOWELS:  render_vowels(s, v, L, R, frames, lg[L_], pmul, rel_mul); break;
        case L_BELLS:   render_bells(s, v, L, R, frames, lg[L_], pmul, rel_mul); break;
        case L_SCAPE:   render_scape(s, v, L, R, frames, lg[L_], pmul, rel_mul, b); break;
        default:        render_texture(s, v, L, R, frames, lg[L_], pmul, rel_mul, b); break;
        }
        if (L_ == L_BELLS) { if (v->env < 0.0005f) v->active = 0; }
        else if (!v->held && !v->pedal && v->env < 0.001f) v->active = 0;     /* -60 dB: the reverb carries the rest */
    }

    drive_block(s, L, R, frames);
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
    delay_block(s, L, R, frames);
    reverb_block(s, L, R, frames);
    sub_block(s, L, R, frames);          /* after the reverb: the sub stays dry and centred */

    float lvl = P(master) * 1.25f;
    lvl *= lvl;
    for (int f = 0; f < frames; f++) {
        float l = softclip(L[f] * lvl), r = softclip(R[f] * lvl);
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
