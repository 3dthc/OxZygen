/* OxZygen engine: two sound slots, effects, the orb.
 *
 * Slots A and B each pick one sound and have an Octave, three knobs that mean what that sound needs, and a Level:
 *   Choir    Vowel (ah -> oh -> ih), Spread (singers apart in pitch and stereo), Attack (the swell)
 *            three recorded singers (Claudia, Mirko, Sven) on the notes each covers
 *   Vowels   Morph (u-o-a-e-i), Formant (voice size), Attack: formant synthesis, two glottal oscillators
 *   Flute, Ocarina, Sax   Vibrato (recorded vibrato fades in), Breath (noise), Tone: recorded winds, soft/loud by velocity
 *   Bells    Strike (brightness, mallet), Decay, Shimmer (beating): eight church-bell partials (modal synthesis)
 *   Wind     Density, Drift, Width: pitched wind on the note's harmonics plus a granular cloud of choir whispers
 *   Texture  Grain (20-400 ms), Pitch (-24..+24 in musical steps), Smear: granular voices
 * Player macros: Blend (A <-> B), Breath (breathiness), Attack and Release (scale every sound's envelope),
 * Air (top lift), Dark (low-pass), Space (reverb), Motion (vibrato, drift, vowel sway, orb speed).
 * Effects (FX page): Drive -> Dark/Air -> ping-pong Delay -> 8-line reverb; the Sub follows the lowest held key
 * (Drop glides it into pitch) and is added after the reverb so it stays dry. Output level last.
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
#define MAXV 32              /* voices: one per slot per note */
#define MAXSRC 6             /* sample players per voice: 3 singers x 2 vowels */
#define ORB_PHASES 17

/* ---------- sample bank: loaded once, shared by all instances ---------- */
enum { G_CLA_AH, G_CLA_OH, G_CLA_IH, G_MIR_AH, G_MIR_OH, G_MIR_IH, G_SVE_AH, G_SVE_OH, G_SVE_IH,
       G_FL_P, G_FL_F, G_FL_VIB, G_OC_STD, G_OC_VIB, G_SAX_P, G_SAX_F,
       G_CL_P, G_CL_F, G_OB_P, G_OB_F, G_OB_VIB, G_HORN_P, G_HORN_F, G_MTR_P, G_MTR_F, G_TBN_P, G_TBN_F,
       G_STR_VLN, G_STR_VLA, G_STR_VC, G_TRM_VLN, G_TRM_VLA, G_TRM_VC,
       G_TUB_P, G_TUB_F, G_VIB_P, G_VIB_F, G_BVIB, G_GLASS, NGROUPS };
static const char *GROUP_NAMES[NGROUPS] = {
    "choir/claudia_ah", "choir/claudia_oh", "choir/claudia_ih", "choir/mirko_ah", "choir/mirko_oh", "choir/mirko_ih",
    "choir/sven_ah", "choir/sven_oh", "choir/sven_ih", "flute/nv_p", "flute/nv_f", "flute/vib",
    "ocarina/std", "ocarina/vib", "sax/p", "sax/f",
    "clarinet/p", "clarinet/f", "oboe/nv_p", "oboe/nv_f", "oboe/vib", "horn/p", "horn/f", "mtrumpet/p", "mtrumpet/f",
    "trombone/p", "trombone/f", "strings/vln", "strings/vla", "strings/vc", "trem/vln", "trem/vla", "trem/vc",
    "tubular/p", "tubular/f", "vibes/p", "vibes/f", "bowedvibes/std", "glass/std"};

/* pitch = root + cents/100; a one-shot (struck) zone plays to its end and stops instead of looping */
#define LF_MAX 1024           /* Lo-Fi wobble line: up to ~23 ms */
typedef struct { float pitch; int ls, le, frames, oneshot; int16_t *pcm; } zone_t;
typedef struct { zone_t *z; int n; } group_t;
typedef struct { group_t g[NGROUPS]; float lo[3], hi[3], glo[NGROUPS], ghi[NGROUPS]; long bytes; int ok; char err[96]; } bank_t;

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
        int oneshot = ls >= le;                          /* manifest: loop_start == loop_end for struck sounds */
        if (oneshot) { ls = le = got; }
        else pcm[le] = pcm[ls], pcm[le + 1] = pcm[ls + 1];   /* the interpolator reads 2 past the loop end: continue the loop */
        group_t *g = &b->g[gi];
        if (g->n == cap[gi]) { cap[gi] = cap[gi] ? cap[gi] * 2 : 16; g->z = realloc(g->z, cap[gi] * sizeof *g->z); }
        g->z[g->n++] = (zone_t){root + cents / 100.0f, ls, le, got, oneshot, pcm};
        b->bytes += (long)got * 2;
    }
    fclose(m);
    for (int i = 0; i < NGROUPS; i++) {
        if (b->g[i].n) qsort(b->g[i].z, b->g[i].n, sizeof(zone_t), cmp_zone);
        b->glo[i] = b->g[i].n ? b->g[i].z[0].pitch : 999;
        b->ghi[i] = b->g[i].n ? b->g[i].z[b->g[i].n - 1].pitch : -999;
    }
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
enum { L_CHOIR, L_VOWELS, L_WINDS, L_BELLS, L_SCAPE, L_TEXTURE, L_STRINGS, L_SAMPLED, L_SYNTH, NLAYERS };

typedef struct { const zone_t *z; int i, done; float fr, inc_base, inc, g, gl, gr; } src_t;
typedef struct { const zone_t *z; float pos, inc, ph, dph, gl, gr; int on; } grain_t;

typedef struct {
    int active, note, key, slot, inst, layer, held, pedal;   /* note: key + the slot's octave */
    float vel, vg, env, att, t, lfo, drift, pan;   /* vg: velocity gain */
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
    float cons, bhp, blp, blp2;          /* Vowels: strength of the sung "d" onset, and its burst filter */
    /* soundscape and texture */
    grain_t gr[NGRAIN];
    int next_grain;
    svf_t wind[3], airband;
    float gust, gust_ph, wdrift[3];
    /* sampled extras: tremolo phase (Shimmer), damping (Decay) */
    float trem_ph;
    /* synth */
    float sph[3], pwm_ph, glide, fenv;
    svf_t flt[2];
    int fstage;
} voice_t;

/* the Juno-style chorus: two modulated delays per slot, one triangle LFO */
#define CH_MAX 2048
typedef struct { float l[CH_MAX], r[CH_MAX]; int w; float ph; } chorus_t;

/* one slot's settings, read once per block */
/* every sound, in the order of the a_sound/b_sound options */
enum { S_OFF, S_CHOIR, S_VOWELS, S_FLUTE, S_OCARINA, S_SAX, S_CLARINET, S_OBOE, S_HORN, S_MTRUMPET, S_TROMBONE,
       S_STRINGS, S_TREMOLO, S_CHURCH, S_TUBULAR, S_VIBES, S_BOWEDVIBES, S_GLASS, S_SYNPAD, S_SYNLEAD, S_SYNBRASS,
       S_WIND, S_TEXTURE, NSOUNDS };
#define NCATS 8
/* category -> its first sound; a category's selector picks an offset from there */
static const int CAT_FIRST[NCATS] = {S_OFF, S_CHOIR, S_FLUTE, S_HORN, S_STRINGS, S_CHURCH, S_SYNPAD, S_WIND};
static const int CAT_COUNT[NCATS] = {1, 2, 5, 3, 2, 5, 3, 2};
typedef struct { int type, layer, inst, oct; float k1, k2, k3, gain; } slot_t;   /* type: the sound (S_*) */

typedef struct {
    float val[NPARAMS];
    slot_t slot[2];
    voice_t v[MAXV];
    unsigned clock, noise;
    int pedal_down;
    float bend, modwheel;
    unsigned char keys[128];          /* held keys, for the sub */
    float lp1_l, lp1_r, lp2_l, lp2_r, air_l, air_r;
    reverb_t *rv;
    chorus_t *ch[2];
    float bus_l[2][128], bus_r[2][128];      /* synth voices per slot, before their chorus */
    unsigned key_time[128];                  /* when each key went down, for the mono lead's note priority */
    /* delay */
    float *dly_l, *dly_r, dly_time, dly_lp_l, dly_lp_r;
    int dly_w;
    /* drive */
    float drv_lp_l, drv_lp_r;
    float vel_extra;          /* Velocity above 50: extra depth for the note being started */
    float lf_buf[2][LF_MAX]; int lf_w; float lf_ph, lf_ph2, lf_hold_l, lf_hold_r, lf_cnt, lf_lp_l, lf_lp_r, lf_lp2_l, lf_lp2_r;
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
static int I_master, I_velocity, I_breath, I_attack, I_release, I_air, I_dark, I_lofi, I_motion,
    I_rv_size, I_rv_decay, I_rv_mix, I_dl_time, I_dl_feedback, I_dl_mix, I_dr_amount, I_dr_tone, I_dr_mix,
    I_sb_level, I_sb_tune, I_sb_drop, I_orb;
static int I_cat[2], I_sel[2][NCATS], I_sound[2], I_oct[2], I_k1[2], I_k2[2], I_k3[2], I_level[2];
static int g_idx_done;
static void init_idx(void) {
    if (g_idx_done) return;
#define X(n) I_##n = idx_of(#n)
    X(master); X(velocity); X(breath); X(attack); X(release); X(air); X(dark); X(lofi); X(motion);
    X(rv_size); X(rv_decay); X(rv_mix); X(dl_time); X(dl_feedback); X(dl_mix); X(dr_amount); X(dr_tone); X(dr_mix);
    X(sb_level); X(sb_tune); X(sb_drop); X(orb);
#undef X
    static const char *CATKEY[NCATS] = {"", "voices", "winds", "brass", "strings", "bells", "synth", "air"};
    for (int sl = 0; sl < 2; sl++) {
        char k[24];
        const char *pre = sl ? "b" : "a";
        snprintf(k, sizeof k, "%s_cat", pre); I_cat[sl] = idx_of(k);
        I_sel[sl][0] = -1;
        for (int c = 1; c < NCATS; c++) { snprintf(k, sizeof k, "%s_%s", pre, CATKEY[c]); I_sel[sl][c] = idx_of(k); }
        snprintf(k, sizeof k, "%s_sound", pre); I_sound[sl] = idx_of(k);
        snprintf(k, sizeof k, "%s_oct", pre); I_oct[sl] = idx_of(k);
        snprintf(k, sizeof k, "%s_k1", pre); I_k1[sl] = idx_of(k);
        snprintf(k, sizeof k, "%s_k2", pre); I_k2[sl] = idx_of(k);
        snprintf(k, sizeof k, "%s_k3", pre); I_k3[sl] = idx_of(k);
        snprintf(k, sizeof k, "%s_level", pre); I_level[sl] = idx_of(k);
    }
    for (int i = 0; i <= 256; i++) HANN[i] = 0.5f - 0.5f * cosf(2.0f * (float)M_PI * i / 256.0f);
    g_idx_done = 1;
}

/* per sound: which engine plays it, the instrument within that engine, and a level so sounds at the same Level
 * knob come out about equally loud */
static const int SOUND_LAYER[NSOUNDS] = {-1, L_CHOIR, L_VOWELS, L_WINDS, L_WINDS, L_WINDS, L_WINDS, L_WINDS,
    L_WINDS, L_WINDS, L_WINDS, L_STRINGS, L_STRINGS, L_BELLS, L_SAMPLED, L_SAMPLED, L_SAMPLED, L_SAMPLED,
    L_SYNTH, L_SYNTH, L_SYNTH, L_SCAPE, L_TEXTURE};
/* winds: 0 flute 1 ocarina 2 sax 3 clarinet 4 oboe 5 horn 6 mute trumpet 7 trombone; strings: 0 sustain 1 tremolo;
 * sampled: 0 tubular 1 vibes 2 bowed vibes 3 glass; synth: 0 pad 1 lead 2 brass */
static const int SOUND_INST[NSOUNDS] = {0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 0, 0, 1, 2, 3, 0, 1, 2, 0, 0};
static const float SOUND_GAIN[NSOUNDS] = {0, 0.98f, 1.79f, 1.40f, 1.25f, 0.92f, 0.61f, 0.97f, 0.56f, 0.92f, 0.34f,
    1.53f, 1.46f, 2.57f, 1.15f, 0.73f, 2.48f, 1.09f, 1.19f, 1.17f, 0.94f, 2.09f, 2.54f};   /* measured: 4-note chords level */

static void read_slots(oxz_t *s) {
    for (int i = 0; i < 2; i++) {
        slot_t *x = &s->slot[i];
        int cat = (int)(s->val[I_cat[i]] + 0.5f);
        if (cat < 0 || cat >= NCATS) cat = 0;
        int snd = S_OFF;
        if (cat > 0) {
            int sel = (int)(s->val[I_sel[i][cat]] + 0.5f);
            if (sel < 0) sel = 0;
            if (sel >= CAT_COUNT[cat]) sel = CAT_COUNT[cat] - 1;
            snd = CAT_FIRST[cat] + sel;
        }
        if ((int)(s->val[I_sound[i]] + 0.5f) != snd) {   /* the derived Sound the skin's labels follow */
            s->val[I_sound[i]] = (float)snd;
            s->rev++;
        }
        x->type = snd;
        x->layer = SOUND_LAYER[snd];
        x->inst = SOUND_INST[snd];
        x->oct = (int)(s->val[I_oct[i]] + 0.5f) - 2;
        x->k1 = s->val[I_k1[i]] * 0.01f; x->k2 = s->val[I_k2[i]] * 0.01f; x->k3 = s->val[I_k3[i]] * 0.01f;
        x->gain = SOUND_GAIN[snd] * s->val[I_level[i]] * 0.01f;
    }
}

/* what the three knobs mean for each sound, for MPC's parameter names (the skin's labels match) */
static const char *KNOB_NAMES[NSOUNDS][3] = {
    {"Knob 1", "Knob 2", "Knob 3"}, {"Vowel", "Spread", "Attack"}, {"Morph", "Formant", "Attack"},
    {"Vibrato", "Breath", "Tone"}, {"Vibrato", "Breath", "Tone"}, {"Vibrato", "Breath", "Tone"},
    {"Vibrato", "Breath", "Tone"}, {"Vibrato", "Breath", "Tone"}, {"Vibrato", "Breath", "Tone"},
    {"Vibrato", "Breath", "Tone"}, {"Vibrato", "Breath", "Tone"},
    {"Ensemble", "Swell", "Tone"}, {"Ensemble", "Swell", "Tone"},
    {"Strike", "Decay", "Shimmer"}, {"Decay", "Shimmer", "Tone"}, {"Decay", "Shimmer", "Tone"},
    {"Swell", "Shimmer", "Tone"}, {"Swell", "Shimmer", "Tone"},
    {"Cutoff", "Shape", "Chorus"}, {"Cutoff", "Glide", "Chorus"}, {"Cutoff", "Bloom", "Chorus"},
    {"Density", "Drift", "Width"}, {"Grain", "Pitch", "Smear"}};

static void *create(const char *data_dir) {
    init_idx();
    oxz_t *s = calloc(1, sizeof *s);
    if (!s) return NULL;
    s->rv = calloc(1, sizeof *s->rv);
    s->ch[0] = calloc(1, sizeof(chorus_t));
    s->ch[1] = calloc(1, sizeof(chorus_t));
    s->dly_l = calloc(DLY_MAX, sizeof(float));
    s->dly_r = calloc(DLY_MAX, sizeof(float));
    for (int i = 0; i < NPARAMS; i++)   /* params.h keeps defaults normalized 0..1; set_param() gets real units */
        s->val[i] = PARAMS[i].nopts ? floorf(PARAMS[i].def * (PARAMS[i].nopts - 1) + 0.5f)
                                    : PARAMS[i].min + PARAMS[i].def * (PARAMS[i].max - PARAMS[i].min);
    s->noise = 0x9e3779b9u;
    s->sub_target = -1;
    read_slots(s);
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
    free(s->rv); free(s->ch[0]); free(s->ch[1]); free(s->dly_l); free(s->dly_r);
    free(s);
}

/* per-slot polyphony: a full slot reuses its own quietest released voice (else its oldest) instead of
 * growing, which keeps long release tails from piling up on the MPC's CPU */
static voice_t *alloc_voice(oxz_t *s, int slot, int layer) {
    voice_t *best = NULL;
    int cap = layer == L_BELLS || layer == L_SAMPLED ? 14 : layer == L_SCAPE || layer == L_TEXTURE ? 8 : 12, count = 0;
    for (int k = 0; k < MAXV; k++) count += s->v[k].active && s->v[k].slot == slot;
    if (count >= cap) {
        for (int k = 0; k < MAXV; k++) {
            voice_t *v = &s->v[k];
            if (!v->active || v->slot != slot) continue;
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

/* velocity -> gain: 18 dB from softest to hardest, about -2 dB at velocity 100 (the old curve spanned ~7 dB) */
static float vel_gain(float vel) { return 1.3f * powf(10.0f, -0.9f * (1.0f - vel)); }   /* times oxz_t.vel_extra */

static float attack_mult(oxz_t *s) { return powf(4.0f, 2.0f * P(attack) - 1.0f); }   /* 0.25x .. 4x, 1x at 50 */

static float attack_secs(float knob, float breath) {   /* knob 0..1 -> 5 ms .. 2.5 s, scaled by Breath */
    return (0.005f + 2.5f * knob * knob) * (0.45f + 1.1f * breath);   /* breath is fixed at 0.5 now */
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
    const slot_t *sl = &s->slot[v->slot];
    float vow = sl->k1 * 2.0f;                   /* 0 ah, 1 oh, 2 ih */
    int va = vow < 1.0f ? 0 : 1;
    float w = vow - va, wa = cosf(w * (float)M_PI / 2), wb = sinf(w * (float)M_PI / 2);
    float spread = sl->k2;
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

/* a soft/loud pair crossfaded by velocity */
static void pair_sources(const bank_t *b, voice_t *v, int gp, int gf, float loud) {
    add_src(v, nearest(b, gp, v->note), v->note, cosf(loud * (float)M_PI / 2), 0, 0);
    add_src(v, nearest(b, gf, v->note), v->note, sinf(loud * (float)M_PI / 2), 0, 0);
}

static void winds_sources(oxz_t *s, const bank_t *b, voice_t *v) {
    int inst = v->inst;                            /* 0 flute 1 ocarina 2 sax 3 clarinet 4 oboe 5 horn 6 mute trumpet 7 trombone */
    float vib = s->slot[v->slot].k1, loud = fminf(1.0f, fmaxf(0.0f, (v->vel - 0.3f) / 0.55f));
    float rec_vib = fminf(1.0f, fmaxf(0.0f, (vib - 0.35f) * 2.5f));   /* recorded vibrato fades in above ~35% */
    if (inst == 0) {
        float plain = cosf(rec_vib * (float)M_PI / 2);
        add_src(v, nearest(b, G_FL_P, v->note), v->note, plain * cosf(loud * (float)M_PI / 2), 0, 0);
        add_src(v, nearest(b, G_FL_F, v->note), v->note, plain * sinf(loud * (float)M_PI / 2), 0, 0);
        add_src(v, nearest(b, G_FL_VIB, v->note), v->note, sinf(rec_vib * (float)M_PI / 2), 0, 0);
    } else if (inst == 1) {
        add_src(v, nearest(b, G_OC_STD, v->note), v->note, cosf(rec_vib * (float)M_PI / 2), 0, 0);
        add_src(v, nearest(b, G_OC_VIB, v->note), v->note, sinf(rec_vib * (float)M_PI / 2), 0, 0);
    } else if (inst == 4) {                        /* oboe: like the flute, with a recorded-vibrato layer */
        float plain = cosf(rec_vib * (float)M_PI / 2);
        add_src(v, nearest(b, G_OB_P, v->note), v->note, plain * cosf(loud * (float)M_PI / 2), 0, 0);
        add_src(v, nearest(b, G_OB_F, v->note), v->note, plain * sinf(loud * (float)M_PI / 2), 0, 0);
        add_src(v, nearest(b, G_OB_VIB, v->note), v->note, sinf(rec_vib * (float)M_PI / 2), 0, 0);
    } else {
        static const int GP[8] = {0, 0, G_SAX_P, G_CL_P, 0, G_HORN_P, G_MTR_P, G_TBN_P};
        pair_sources(b, v, GP[inst], GP[inst] + 1, loud);
    }
}

/* strings: violins, violas and cellos, each on the notes its section covers (like the choir's singers);
 * Ensemble spreads them across the stereo field (violins left, cellos right) and detunes them a little */
static void strings_sources(oxz_t *s, const bank_t *b, voice_t *v) {
    const slot_t *sl = &s->slot[v->slot];
    int g0 = v->inst ? G_TRM_VLN : G_STR_VLN;
    static const float PAN[3] = {-0.55f, 0.0f, 0.55f}, DET[3] = {5.0f, -3.0f, -6.0f};
    float ens = sl->k1, gs[3];
    int n = 0;
    for (int k = 0; k < 3; k++) {
        gs[k] = v->note >= b->glo[g0 + k] - 3 && v->note <= b->ghi[g0 + k] + 3;
        n += gs[k] > 0;
    }
    if (!n) { gs[v->note > b->ghi[g0] ? 0 : 2] = 1; n = 1; }
    for (int k = 0; k < 3; k++)
        if (gs[k]) add_src(v, nearest(b, g0 + k, v->note), v->note, 1.0f / sqrtf((float)n), PAN[k] * ens * 1.5f, DET[k] * ens * 1.6f);
}

/* tubular bells and vibes (struck, soft/loud by velocity), bowed vibes and glass (sustained) */
static void sampled_sources(oxz_t *s, const bank_t *b, voice_t *v) {
    (void)s;
    float loud = fminf(1.0f, fmaxf(0.0f, (v->vel - 0.3f) / 0.55f));
    switch (v->inst) {
    case 0: pair_sources(b, v, G_TUB_P, G_TUB_F, loud); break;
    case 1: pair_sources(b, v, G_VIB_P, G_VIB_F, loud); break;
    case 2: add_src(v, nearest(b, G_BVIB, v->note), v->note, 1.0f, 0, 0); break;
    default: add_src(v, nearest(b, G_GLASS, v->note), v->note, 1.0f, 0, 0); break;
    }
}

/* bells: minor-third church-bell partials (hum, prime, tierce, quint, nominal and above) */
static const float BELL_RATIO[NP] = {0.5f, 1.0f, 1.183f, 1.506f, 2.0f, 2.514f, 2.662f, 3.011f};
static const float BELL_AMP[NP] = {0.45f, 1.0f, 0.62f, 0.38f, 0.75f, 0.28f, 0.22f, 0.16f};

static void bells_start(oxz_t *s, voice_t *v) {
    const slot_t *sl = &s->slot[v->slot];
    float strike = sl->k1 * (0.6f + 0.6f * v->vel);
    float t60 = 0.6f + 11.0f * sl->k2 * sl->k2;
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

static void note_on(oxz_t *s, int key, float vel) {
    const bank_t *b = __atomic_load_n(&g_bank, __ATOMIC_ACQUIRE);
    s->energy = fminf(1.0f, s->energy + 0.35f + 0.4f * vel);
    /* Velocity: 0 = every hit full, 50 = as designed, 100 = soft hits a further 12 dB down */
    float vsens = P(velocity);
    s->vel_extra = vsens > 0.5f ? powf(10.0f, -0.6f * (2.0f * vsens - 1.0f) * (1.0f - vel)) : 1.0f;
    vel = 1.0f - (1.0f - vel) * fminf(1.0f, 2.0f * vsens);
    read_slots(s);
    float am = attack_mult(s), br = 0.5f;   /* timing no longer follows Breath (0.5 = its old default) */
    for (int si = 0; si < 2; si++) {
        const slot_t *sl = &s->slot[si];
        if (sl->type == S_OFF || sl->gain < 0.001f) continue;
        int layer = sl->layer;
        int needs_bank = layer != L_BELLS && layer != L_VOWELS && layer != L_SYNTH;
        if (needs_bank && (!b || !b->ok)) continue;
        int note = key + 12 * sl->oct;
        if (note < 12 || note > 120) continue;
        if (layer == L_SYNTH && sl->inst == 1) {   /* the lead is mono: a held lead glides to the new note */
            voice_t *mono = NULL;
            for (int k = 0; k < MAXV; k++)
                if (s->v[k].active && s->v[k].slot == si && s->v[k].layer == L_SYNTH && s->v[k].inst == 1) mono = &s->v[k];
            if (mono && (mono->held || mono->pedal)) {
                mono->key = key; mono->note = note; mono->held = 1; mono->vel = vel; mono->vg = vel_gain(vel) * s->vel_extra;
                continue;
            }
        }
        voice_t *v = alloc_voice(s, si, layer);
        memset(v, 0, sizeof *v);
        v->active = 1; v->held = 1; v->key = key; v->note = note; v->slot = si; v->inst = sl->inst; v->layer = layer;
        v->vel = vel; v->vg = vel_gain(vel) * s->vel_extra; v->age = ++s->clock;
        v->seed = 0x2545F491u ^ (s->clock * 2654435761u) ^ (unsigned)(note * 7919);
        rnd(&v->seed);
        v->drift = frand(&v->seed) * 6.2831853f;
        v->pan = nrand(&v->seed);
        float secs;
        switch (layer) {
        case L_CHOIR:  secs = attack_secs(sl->k3, br); choir_sources(s, b, v); break;
        case L_WINDS:  secs = 0.012f + 0.2f * br * br + 0.04f * sl->k2; winds_sources(s, b, v); break;
        case L_VOWELS: secs = attack_secs(sl->k3, br); v->ph[0] = frand(&v->seed); v->ph[1] = frand(&v->seed);
                       /* a short Attack sings a "d" first (doo, dah, dee): stronger with lower Attack and harder hits */
                       v->cons = sl->k3 < 0.25f ? (1.0f - sl->k3 / 0.25f) * (0.55f + 0.45f * v->vel) : 0.0f;
                       v->bhp = v->blp = v->blp2 = 0.0f;
                       if (v->cons > 0.0f) secs = 0.004f;
                       break;
        case L_BELLS:  secs = 0.0f; bells_start(s, v); break;     /* struck: full at once */
        case L_SCAPE:  secs = 0.5f + 1.5f * br;
                       v->gust_ph = frand(&v->seed) * 6.2831853f;
                       for (int k = 0; k < 3; k++) v->wdrift[k] = frand(&v->seed) * 6.2831853f;
                       break;
        case L_STRINGS: secs = 0.03f + 2.2f * sl->k2 * sl->k2; strings_sources(s, b, v); break;   /* Swell */
        case L_SAMPLED: secs = v->inst < 2 ? 0.0f : 0.05f + 2.5f * sl->k1 * sl->k1; sampled_sources(s, b, v); break;
        case L_SYNTH:   secs = v->inst == 0 ? 0.25f + 1.2f * br : v->inst == 1 ? 0.004f : 0.05f + 0.1f * br;
                        v->glide = (float)note; v->sph[0] = frand(&v->seed); v->sph[1] = frand(&v->seed);
                        v->pwm_ph = frand(&v->seed); v->fenv = 1.0f;
                        break;
        default:       secs = 0.05f + 1.2f * br * br; break;
        }
        v->att = secs <= 0.0f ? 1.0f : 1.0f / (SR * secs * am);
        if (layer != L_BELLS && layer != L_WINDS && layer != L_SAMPLED && layer != L_SYNTH)
            v->att *= 0.6f + 0.8f * vel;            /* harder: the swell speaks sooner */
    }
}

static void note_off(oxz_t *s, int key) {
    for (int k = 0; k < MAXV; k++) {
        voice_t *v = &s->v[k];
        if (!v->active || !v->held || v->key != key) continue;
        if (v->layer == L_SYNTH && v->inst == 1) {   /* mono lead: fall back to the newest key still held */
            int back = -1;
            for (int n = 0; n < 128; n++)
                if (n != key && s->keys[n] == 1 && (back < 0 || s->key_time[n] > s->key_time[back])) back = n;
            if (back >= 0) { v->key = back; v->note = back + 12 * s->slot[v->slot].oct; continue; }
        }
        v->held = 0;
        v->pedal = s->pedal_down;
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
        s->keys[m[1]] = 1;
        s->key_time[m[1]] = ++s->clock;
        note_on(s, m[1], m[2] / 127.0f);
        int low = lowest_key(s);
        if (low != was || was < 0) {                 /* the sub follows the lowest held note, dropping in */
            s->sub_target = low;
            s->sub_glide = (float)(was < 0 ? low + P(sb_drop) * 12.0f : (s->sub_note > 0 ? s->sub_note : low));
            if (was < 0) s->sub_ph = 0.0f;
        }
    } else if (st == 0x80 || st == 0x90) {
        if (!s->pedal_down) s->keys[m[1]] = 0; else s->keys[m[1]] = 2;   /* 2: held by the pedal */
        note_off(s, m[1]);
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
    size_t kl = strlen(key);
    if (kl > 5 && !strcmp(key + kl - 5, "_name") && (key[0] == 'a' || key[0] == 'b') && key[1] == '_' && key[2] == 'k') {
        int sl = key[0] == 'b', k = key[3] - '1';            /* "a_k2_name" -> slot A, knob 2 */
        read_slots(s);
        int t = s->slot[sl].type;
        if (k < 0 || k > 2 || t < 0 || t >= NSOUNDS) return 0;
        return snprintf(b, n, "%s %s", sl ? "B" : "A", KNOB_NAMES[t][k]);
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
    int choir = v->layer == L_CHOIR, winds = v->layer == L_WINDS, sampled = v->layer == L_SAMPLED;
    int strings = v->layer == L_STRINGS, linear = choir || strings;
    const slot_t *sl = &s->slot[v->slot];
    /* brightness follows velocity: the choir has one recorded dynamic, so harder playing opens a filter on it; the
     * winds keep their Tone knob, scaled by velocity (most for the ocarina, which has no soft/loud recordings) */
    float vb = v->vel;
    /* the choir: a tilt around 1.2 kHz, ~-5 dB up top when soft, ~+6 dB when hard (its energy sits low, so a plain
     * low-pass would change little); the winds: the Tone low-pass, opened by velocity, most for the ocarina */
    float cutoff = choir ? 1200.0f
                 : winds ? (1500.0f + 16000.0f * sl->k3 * sl->k3) * (v->inst == 1 ? 0.25f + 0.75f * powf(vb, 1.5f) : 0.7f + 0.3f * vb)
                 :         (900.0f + 17000.0f * sl->k3 * sl->k3) * (0.45f + 0.55f * powf(vb, 1.2f));   /* strings, sampled: Tone */
    float tone_a = 1.0f - expf(-2.0f * (float)M_PI * cutoff / SR);
    float tilt = 0.4f + 2.1f * powf(vb, 1.5f);     /* highs: x0.4 at velocity 0, x0.77 at 40, x2.5 at 127 */
    /* sampled extras: Shimmer = amplitude tremolo (a vibraphone's motor), Decay = extra damping on struck sounds */
    float shimmer = sampled ? fminf(1.0f, sl->k2 + s->modwheel) : 0.0f;   /* mod wheel adds shimmer */
    float trem_inc = 6.2831853f * (2.0f + 4.5f * shimmer) / SR;
    float damp = (sampled && v->inst < 2 && sl->k1 < 0.97f) ? expf(-1.0f / (SR * (0.15f + 7.0f * sl->k1 * sl->k1))) : 1.0f;
    float breath_amt = winds ? sl->k2 * (0.4f + 0.8f * P(breath)) : P(breath) * P(breath) * 0.5f;   /* choir: Breath alone */
    svfc_t bc = svf_coef(3.0f * note_hz((float)v->note), 1.4f);
    for (int q = 0; q < v->nsrc; q++) v->s[q].inc = v->s[q].inc_base * pmul;
    for (int f = 0; f < frames; f++) {
        if (v->held || v->pedal) { v->env += v->att; if (v->env > 1.0f) v->env = 1.0f; }
        else v->env *= rel_mul;
        v->env *= damp;
        float l = 0, r = 0;
        for (int q = 0; q < v->nsrc; q++) {
            src_t *x = &v->s[q];
            if (x->done) continue;
            const zone_t *z = x->z;
            const int16_t *d = z->pcm + x->i;
            /* choir and string zones sit close together, so the shift is small: linear is enough there */
            float smp = (linear ? d[0] + (d[1] - d[0]) * x->fr : hermite(z->pcm, x->i, x->fr)) * x->g;
            l += smp * x->gl; r += smp * x->gr;
            x->fr += x->inc;
            if (x->fr >= 1.0f) { int k = (int)x->fr; x->i += k; x->fr -= (float)k; }
            if (x->i >= z->le - 2) {
                if (z->oneshot) { x->done = 1; x->i = z->le - 2; }   /* struck: rang out */
                else if (x->i >= z->le) x->i -= (z->le - z->ls);
            }
        }
        if (shimmer > 0.001f) {
            v->trem_ph += trem_inc; if (v->trem_ph > 6.2831853f) v->trem_ph -= 6.2831853f;
            float tr = 1.0f - shimmer * shimmer * 0.55f * (1.0f - cosf(v->trem_ph));   /* gentle at 50, deep at 100 */
            l *= tr; r *= tr;
        }
        float a = v->env * v->vg * lg * (1.0f / 32768.0f);
        l *= a; r *= a;
        if (winds || choir) {    /* breath: band-passed noise around the note, strongest at the onset */
            float nz = nrand(&s->noise);
            float tr = 1.0f + 2.5f * expf(-v->t * 9.0f);
            float br = svf_bp(&v->breath, &bc, nz) * breath_amt * 0.06f * tr * v->env * lg;
            l += br; r += br;
        }
        v->tone_l += tone_a * (l - v->tone_l); v->tone_r += tone_a * (r - v->tone_r);
        if (choir) { l = v->tone_l + (l - v->tone_l) * tilt; r = v->tone_r + (r - v->tone_r) * tilt; }
        else { l = v->tone_l; r = v->tone_r; }
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
    const slot_t *sl = &s->slot[v->slot];
    v->drift += dt * (0.15f + 0.35f * motion);
    float morph = sl->k1 * 4.0f + sinf(v->drift) * (0.15f + 0.6f * motion);   /* Motion sways the vowel */
    if (morph < 0) morph = 0;
    if (morph > 3.999f) morph = 3.999f;
    int a = (int)morph;
    float w = morph - a;
    float scale = 0.72f + 0.62f * sl->k2;                    /* Formant: larger to smaller voice */
    svfc_t c[4];
    float amp[4];
    static const float DLOC[4] = {220, 1750, 2700, 3600};          /* where the tongue tip puts the formants on "d" */
    float tb = v->t - dt;                                           /* time since note-on at this block's start */
    float glide = v->cons * expf(-fmaxf(0.0f, tb - 0.012f) / 0.028f);
    for (int k = 0; k < 4; k++) {
        float fz = (VF[a][k] + (VF[a + 1][k] - VF[a][k]) * w) * scale;
        fz += (DLOC[k] * scale - fz) * glide;
        float bw = (VB[a][k] + (VB[a + 1][k] - VB[a][k]) * w) * (0.8f + 0.4f * scale);
        float db = VA[a][k] + (VA[a + 1][k] - VA[a][k]) * w;
        c[k] = svf_coef(fz, fz / bw);
        amp[k] = powf(10.0f, db / 20.0f);
    }
    float f0 = note_hz((float)v->note) * pmul;
    float dt0 = f0 / SR, dt1 = f0 * 1.0046f / SR;                    /* two glottal sources, 8 cents apart */
    float glot_a = 1.0f - expf(-2.0f * (float)M_PI * (1100.0f + 3200.0f * v->vel) / SR);   /* harder: brighter voice */
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
        float burst = 0.0f;
        if (v->cons > 0.0f) {
            float tt = tb + f / SR;
            /* closure (voice bar only), release burst at ~12 ms, then the voice opens into the vowel */
            float open = fminf(1.0f, fmaxf(0.0f, (tt - 0.010f) / 0.022f));
            src *= 0.12f + 0.88f * open * open;
            if (tt > 0.010f && tt < 0.040f) {
                float n = nrand(&s->noise);
                v->bhp += 0.35f * (n - v->bhp);                        /* hiss above ~3 kHz ... */
                v->blp += 0.55f * ((n - v->bhp) - v->blp);              /* ... and below ~6 kHz: a "d", not a click */
                v->blp2 += 0.55f * (v->blp - v->blp2);
                burst = v->blp2 * v->cons * 0.55f * expf(-(tt - 0.010f) / 0.007f);
            }
        }
        float y = burst;
        for (int k = 0; k < 4; k++) y += svf_bp(&v->fm[k], &c[k], src) * amp[k];
        y *= v->env * v->vg * lg * 1.75f;
        L[f] += y * gl; R[f] += y * gr;
    }
}

static void render_bells(oxz_t *s, voice_t *v, float *L, float *R, int frames, float lg, float pmul, float rel_mul) {
    float f0 = note_hz((float)v->note) * pmul, dt = frames / SR, shimmer = fminf(1.0f, s->slot[v->slot].k3 + s->modwheel);
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
        y *= v->vg * lg * 0.24f;
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
    const slot_t *sl = &s->slot[v->slot];
    float dt = frames / SR, density = sl->k1, drift = fminf(1.0f, sl->k2 + s->modwheel), width = sl->k3;   /* wheel: more wander */
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
        float air = svf_bp(&v->airband, &ac, (nl + nr) * 0.5f) * 0.025f * (0.4f + 1.4f * v->vel);   /* harder: breathier */
        float e = v->env * v->gust * lg * v->vg;
        /* Width: the harmonics move apart, the fundamental stays centred */
        float l = (w0 + w1 * (1.0f - width) + w2 * width + air) * e + gl * e * (0.55f / 32768.0f);
        float r = (w0 + w1 * width + w2 * (1.0f - width) + air) * e + gr * e * (0.55f / 32768.0f);
        L[f] += l; R[f] += r;
    }
}

static const float TX_STEPS[8] = {-24, -12, -5, 0, 7, 12, 19, 24};

static void render_texture(oxz_t *s, voice_t *v, float *L, float *R, int frames, float lg, float pmul, float rel_mul,
                           const bank_t *b) {
    const slot_t *sl = &s->slot[v->slot];
    float smear = fminf(1.0f, sl->k3 + s->modwheel);         /* wheel: more smear */
    float size = 0.02f * powf(20.0f, sl->k1);               /* 20 ms .. 400 ms */
    int step = (int)(sl->k2 * 7.0f + 0.5f);
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
        float e = v->env * v->vg * lg * (0.6f / 32768.0f) / sqrtf(overlap * 0.5f);
        L[f] += gl * e; R[f] += gr * e;
    }
}


/* ---------- the Juno-style synth: two oscillators and a sub into a 24 dB low-pass, then the slot's chorus ----------
 * Pad: Cutoff, Shape (saw -> pulse with slow PWM), Chorus. Lead (mono): Cutoff, Glide, Chorus.
 * Brass: Cutoff, Bloom (how far and how slowly the filter opens), Chorus. Velocity opens the filter too. */
static inline float saw_blep(float ph, float dt) { return 2.0f * ph - 1.0f - polyblep(ph, dt); }

static void render_synth(oxz_t *s, voice_t *v, float *bl, float *br, int frames, float lg, float pmul, float rel_mul) {
    const slot_t *sl = &s->slot[v->slot];
    float dt = frames / SR;
    int inst = v->inst;
    /* glide (the lead only) */
    float tau = inst == 1 ? 0.002f + 0.45f * sl->k2 * sl->k2 : 0.0f;
    v->glide = tau > 0.0025f ? v->note + (v->glide - v->note) * expf(-dt / tau) : (float)v->note;
    float f0 = note_hz(v->glide) * pmul;
    float d0 = f0 / SR, d1 = f0 * (inst == 1 ? 1.0015f : 1.0048f) / SR, dsub = f0 * 0.5f / SR;
    /* filter: Cutoff knob, key tracking, velocity, and the filter envelope */
    float bloom = inst == 2 ? sl->k2 : 0.0f;
    float env_oct = inst == 0 ? 1.0f : inst == 1 ? 2.2f : 1.5f + 4.0f * bloom;
    float fatk = inst == 2 ? 0.01f + 0.5f * bloom : inst == 0 ? 0.6f : 0.005f;
    float fdec = inst == 2 ? 0.4f + 1.2f * bloom : inst == 0 ? 2.0f : 0.35f;
    float fsus = inst == 1 ? 0.35f : 0.25f;
    if (v->fstage == 0) { v->fenv += dt / fatk; if (v->fenv >= 1.0f) { v->fenv = 1.0f; v->fstage = 1; } }
    else v->fenv = fsus + (v->fenv - fsus) * expf(-dt / fdec);
    float base = 55.0f * exp2f(fminf(1.0f, sl->k1 + (v->inst != 1 ? s->modwheel * 0.5f : 0.0f)) * 8.5f)   /* wheel opens pad/brass */ * exp2f((v->glide - 60.0f) / 24.0f) * exp2f(v->vel * 1.2f - 0.6f);
    float fc = base * exp2f(env_oct * v->fenv);
    svfc_t c = svf_coef(fc, inst == 1 ? 1.6f : inst == 0 ? 0.62f : 0.8f);
    /* oscillator mix */
    float shape = inst == 0 ? sl->k2 : inst == 1 ? 0.45f : 0.0f;
    float sub = inst == 0 ? 0.3f : inst == 1 ? 0.4f : 0.25f;
    v->pwm_ph += dt * 6.2831853f * 0.55f;
    float pw = 0.5f + 0.38f * sinf(v->pwm_ph) * (inst == 0 ? 1.0f : 0.0f);
    float amp = v->vg * lg * 0.22f;
    for (int f = 0; f < frames; f++) {
        if (v->held || v->pedal) { v->env += v->att; if (v->env > 1.0f) v->env = 1.0f; }
        else v->env *= rel_mul;
        float sa = saw_blep(v->sph[0], d0);
        float p2 = v->sph[0] + pw; if (p2 >= 1.0f) p2 -= 1.0f;
        float pulse = sa - saw_blep(p2, d0);
        float sb = saw_blep(v->sph[1], d1);
        float sq = v->sph[2] < 0.5f ? 1.0f : -1.0f;
        v->sph[0] += d0; if (v->sph[0] >= 1.0f) v->sph[0] -= 1.0f;
        v->sph[1] += d1; if (v->sph[1] >= 1.0f) v->sph[1] -= 1.0f;
        v->sph[2] += dsub; if (v->sph[2] >= 1.0f) v->sph[2] -= 1.0f;
        float x = (sa * (1.0f - shape) + pulse * shape * 0.7f) + sb * (inst == 1 ? 0.25f : 0.6f) + sq * sub;
        x = svf_lp(&v->flt[1], &c, svf_lp(&v->flt[0], &c, x));
        x *= v->env * amp;
        bl[f] += x; br[f] += x;
    }
}

/* chorus: a delay swept by a triangle LFO, opposite on the two sides; Chorus knob sets depth, rate and mix */
static void chorus_block(chorus_t *c, float amount, const float *inl, const float *inr, float *L, float *R, int frames) {
    float mix = fminf(1.0f, amount * 1.6f), rate = 0.45f + 0.45f * amount, depth = (1.2f + 3.0f * amount) * 44.1f;
    float base = 3.2f * 44.1f;
    for (int f = 0; f < frames; f++) {
        float x = (inl[f] + inr[f]) * 0.5f;
        c->l[c->w] = x;
        c->ph += rate / SR; if (c->ph >= 1.0f) c->ph -= 1.0f;
        float tri = c->ph < 0.5f ? c->ph * 2.0f : 2.0f - c->ph * 2.0f;
        float wl = rd_frac(c->l, CH_MAX, c->w, base + depth * tri);
        float wr = rd_frac(c->l, CH_MAX, c->w, base + depth * (1.0f - tri));
        if (++c->w == CH_MAX) c->w = 0;
        L[f] += inl[f] * (1.0f - 0.45f * mix) + wl * mix * 0.8f;
        R[f] += inr[f] * (1.0f - 0.45f * mix) + wr * mix * 0.8f;
    }
}

static void reverb_block(oxz_t *s, float *L, float *R, int frames) {
    reverb_t *r = s->rv;
    if (!r) return;
    float size = 0.55f + 1.1f * P(rv_size);                                    /* 0.55 .. 1.65 */
    float rt60 = 0.6f + 13.2f * P(rv_decay) * P(rv_decay);                     /* 0.6 .. 13.8 s */
    float mix = 0.9f * P(rv_mix);
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
/* Lo-Fi: worn tape and an old sampler in one knob. Wow and flutter (a wobbling short delay), a gentle low-pass that
   closes as it goes up, sample-rate and bit reduction past the middle, and a little hiss. 0 = off, untouched. */
static void lofi_block(oxz_t *s, float *L, float *R, int frames) {
    float amt = P(lofi);
    if (amt < 0.005f) return;
    float wow = (0.6f + 5.0f * amt) * 44.1f * 0.5f;                    /* wobble depth in samples */
    float cut = 16000.0f * powf(0.22f, amt);                            /* 16 kHz .. 3.5 kHz */
    float la = 1.0f - expf(-2.0f * (float)M_PI * cut / SR);
    float crush = amt > 0.45f ? (amt - 0.45f) / 0.55f : 0.0f;          /* second half: the sampler */
    float hold = 1.0f + crush * 3.0f;                                   /* 44.1 kHz down to ~11 kHz */
    float steps = crush > 0.0f ? powf(2.0f, 12.0f - 5.0f * crush) : 0.0f;   /* 12 bits down to 7 */
    float hiss = amt * amt * 0.004f;
    for (int f = 0; f < frames; f++) {
        s->lf_ph += 0.55f / SR * 6.2831853f; if (s->lf_ph > 6.2831853f) s->lf_ph -= 6.2831853f;
        s->lf_ph2 += 6.3f / SR * 6.2831853f; if (s->lf_ph2 > 6.2831853f) s->lf_ph2 -= 6.2831853f;
        s->lf_buf[0][s->lf_w] = L[f]; s->lf_buf[1][s->lf_w] = R[f];
        float d = wow * (1.6f + sinf(s->lf_ph) + 0.25f * sinf(s->lf_ph2));
        float rp = (float)s->lf_w - d; if (rp < 0) rp += LF_MAX;
        int i = (int)rp, j = i + 1 < LF_MAX ? i + 1 : 0; float fr = rp - i;
        float l = s->lf_buf[0][i] + (s->lf_buf[0][j] - s->lf_buf[0][i]) * fr;
        float r = s->lf_buf[1][i] + (s->lf_buf[1][j] - s->lf_buf[1][i]) * fr;
        if (++s->lf_w == LF_MAX) s->lf_w = 0;
        if (crush > 0.0f) {
            s->lf_cnt += 1.0f;
            if (s->lf_cnt >= hold) { s->lf_cnt -= hold; s->lf_hold_l = roundf(l * steps) / steps; s->lf_hold_r = roundf(r * steps) / steps; }
            l += (s->lf_hold_l - l) * crush; r += (s->lf_hold_r - r) * crush;
        }
        float n = nrand(&s->noise) * hiss;
        s->lf_lp_l += la * (l + n - s->lf_lp_l); s->lf_lp2_l += la * (s->lf_lp_l - s->lf_lp2_l);
        s->lf_lp_r += la * (r + n - s->lf_lp_r); s->lf_lp2_r += la * (s->lf_lp_r - s->lf_lp2_r);
        float wet = fminf(1.0f, amt * 30.0f);                           /* in fully by 3%: a dry/wobble mix would comb-filter */
        L[f] += (softclip(s->lf_lp2_l * 1.15f) - L[f]) * wet;
        R[f] += (softclip(s->lf_lp2_r * 1.15f) - R[f]) * wet;
    }
}

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
        float x = softclip(sinf(s->sub_ph * 6.2831853f) * 1.25f) * s->sub_env * lvl * 0.3f;
        L[f] += x; R[f] += x;
    }
    s->sub_note = s->sub_glide;
}

static void render(void *inst, int16_t *out, int frames) {
    oxz_t *s = inst;
    const bank_t *b = __atomic_load_n(&g_bank, __ATOMIC_ACQUIRE);
    float L[128], R[128];
    memset(L, 0, sizeof L); memset(R, 0, sizeof R);
    memset(s->bus_l, 0, sizeof s->bus_l); memset(s->bus_r, 0, sizeof s->bus_r);
    if (frames > 128) frames = 128;
    float dt = frames / SR, motion = P(motion);
    read_slots(s);
    float rel_secs = 0.12f + 5.5f * powf(P(release), 1.6f);  /* Release: 0.12 s .. 5.6 s */
    float rel_mul = expf(-1.0f / (SR * rel_secs / 4.6f));     /* -40 dB over rel_secs */
    int held_any = 0;

    for (int k = 0; k < MAXV; k++) {
        voice_t *v = &s->v[k];
        if (!v->active) continue;
        int L_ = v->layer;
        const slot_t *sl = &s->slot[v->slot];
        if (L_ != L_BELLS && L_ != L_VOWELS && L_ != L_SYNTH && (!b || !b->ok)) { v->active = 0; continue; }
        held_any |= v->held || v->pedal;
        if (sl->layer != L_ || sl->inst != v->inst) { v->held = 0; v->pedal = 0; }   /* the slot changed sound: let it go */
        float lgain = sl->layer == L_ ? sl->gain : 0.0f;
        v->t += dt;
        float pm = s->bend;
        if (L_ == L_CHOIR || L_ == L_TEXTURE || L_ == L_STRINGS) {
            v->drift += dt * (0.3f + 0.4f * motion + 3.0f * s->modwheel);
            pm += sinf(v->drift) * (0.06f * (0.3f + motion) + 0.22f * s->modwheel);   /* slow ensemble drift; wheel: wider and faster */
        } else if (L_ == L_WINDS || L_ == L_VOWELS || (L_ == L_SYNTH && v->inst == 1)) {
            v->lfo += dt * 6.2831853f * (4.6f + 1.2f * motion);
            float onset = fminf(1.0f, fmaxf(0.0f, (v->t - 0.25f) / 0.6f));   /* vibrato grows after the attack */
            float depth = (L_ == L_WINDS ? sl->k1 * 0.35f + motion * 0.25f : 0.12f + 0.3f * motion) * 0.6f
                          ;   /* semitones peak (x0.25 below) */
            pm += sinf(v->lfo) * (depth * onset * 0.25f + s->modwheel * 0.5f);   /* wheel: up to half a semitone, at once */
        }
        float pmul = exp2f(pm / 12.0f);
        switch (L_) {
        case L_CHOIR: case L_WINDS: case L_STRINGS: case L_SAMPLED:
                        render_samples(s, v, L, R, frames, lgain, pmul, rel_mul); break;
        case L_SYNTH:   render_synth(s, v, s->bus_l[v->slot], s->bus_r[v->slot], frames, lgain, pmul, rel_mul); break;
        case L_VOWELS:  render_vowels(s, v, L, R, frames, lgain, pmul, rel_mul); break;
        case L_BELLS:   render_bells(s, v, L, R, frames, lgain, pmul, rel_mul); break;
        case L_SCAPE:   render_scape(s, v, L, R, frames, lgain, pmul, rel_mul, b); break;
        default:        render_texture(s, v, L, R, frames, lgain, pmul, rel_mul, b); break;
        }
        if (L_ == L_BELLS) { if (v->env < 0.0005f) v->active = 0; }
        else if (L_ == L_SAMPLED && v->inst < 2) {   /* struck: done once every source has rung out, or damped away */
            int live = 0;
            for (int q = 0; q < v->nsrc; q++) live |= !v->s[q].done;
            if (!live || v->env < 0.0005f) v->active = 0;
        }
        else if (!v->held && !v->pedal && v->env < 0.001f) v->active = 0;     /* -60 dB: the reverb carries the rest */
    }

    for (int i = 0; i < 2; i++)                 /* each slot's synth voices through its own chorus */
        if (s->slot[i].layer == L_SYNTH) chorus_block(s->ch[i], s->slot[i].k3, s->bus_l[i], s->bus_r[i], L, R, frames);
    drive_block(s, L, R, frames);
    lofi_block(s, L, R, frames);
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
