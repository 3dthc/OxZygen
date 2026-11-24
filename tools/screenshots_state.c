/* Engine state for tools/screenshots.py: every param (key, normalized, raw, text, unit) after loading the first NOIR
 * preset, plus the BROWSE list texts. Built and run by screenshots.py. */
#include "engine.c"
/* print every param: key \t normalized \t text \t unit, after loading a NOIR preset and browsing NOIR */
int main(void) {
    void *s = ENGINE.create(NULL); char b[256];
    int pick = -1;
    for (int p = 0; p < NPRESET; p++) { b[0]=0; get_param(s, (snprintf(b,64,"preset_category:%d",p), b), b, 256); if (!strcmp(b,"NOIR")) { pick = p; break; } }
    char v[32]; snprintf(v, 32, "%d", pick); ENGINE.set_param(s, "preset", v);
    int16_t buf[256]; for (int k = 0; k < 40; k++) ENGINE.render(s, buf, 128);
    for (int i = 0; i < NPARAMS; i++) {
        oxz_t *o = s; float x = o->val[i], n = PARAMS[i].max > PARAMS[i].min ? (x - PARAMS[i].min) / (PARAMS[i].max - PARAMS[i].min) : 0;
        b[0] = 0; get_param(s, PARAMS[i].key, b, 256);
        printf("%s\t%g\t%g\t%s\t%s\n", PARAMS[i].key, n, x, b, PARAMS[i].unit ? PARAMS[i].unit : "");
    }
    for (int i = 1; i <= 24; i++) { char k[16]; snprintf(k,16,"row_%d",i); b[0]=0; get_param(s,k,b,256); printf("%s\t0\t0\t%s\t\n",k,b); }
    for (int i = 1; i <= 12; i++) { char k[16]; snprintf(k,16,"cat_%d",i); b[0]=0; get_param(s,k,b,256); printf("%s\t0\t0\t%s\t\n",k,b); }
}
