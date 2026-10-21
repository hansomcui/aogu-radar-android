// VoiceForge long-text memory bench (Linux, sherpa-onnx v1.13.8 C API, same as the
// Android AAR version). Mirrors MainActivity.synthesizeOffline: one OfflineTts,
// ZipVoice, maxNumSentences=2, one GenerateWithConfig per chunk.
// Usage: bench <chunks.txt> <ref.wav> <ref.txt> <threads> <num_steps> <recreate_every|0> <rss_abort_mb>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <malloc.h>
#include "sherpa-onnx/c-api/c-api.h"

static const char *Z = "/home/claude/vf/model/sherpa-onnx-zipvoice-distill-int8-zh-en-emilia";

static long status_kb(const char *key) {
  FILE *f = fopen("/proc/self/status", "r"); char line[256]; long v = -1; size_t n = strlen(key);
  while (fgets(line, sizeof line, f)) if (!strncmp(line, key, n)) { v = atol(line + n + 1); break; }
  fclose(f); return v;
}
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec / 1e9; }
static char *slurp(const char *p) {
  FILE *f = fopen(p, "rb"); fseek(f, 0, SEEK_END); long n = ftell(f); rewind(f);
  char *b = malloc(n + 1); fread(b, 1, n, f); b[n] = 0; fclose(f); return b;
}
static const SherpaOnnxOfflineTts *create(int threads) {
  char p[6][512];
  snprintf(p[0], 512, "%s/tokens.txt", Z); snprintf(p[1], 512, "%s/encoder.int8.onnx", Z);
  snprintf(p[2], 512, "%s/decoder.int8.onnx", Z); snprintf(p[3], 512, "%s/vocos_24khz.onnx", Z);
  snprintf(p[4], 512, "%s/espeak-ng-data", Z); snprintf(p[5], 512, "%s/lexicon.txt", Z);
  SherpaOnnxOfflineTtsConfig c; memset(&c, 0, sizeof c);
  c.model.zipvoice.tokens = p[0]; c.model.zipvoice.encoder = p[1]; c.model.zipvoice.decoder = p[2];
  c.model.zipvoice.vocoder = p[3]; c.model.zipvoice.data_dir = p[4]; c.model.zipvoice.lexicon = p[5];
  c.model.zipvoice.feat_scale = 0.1f; c.model.zipvoice.t_shift = 0.5f; c.model.zipvoice.target_rms = 0.1f;
  c.model.zipvoice.guidance_scale = 1.0f;
  c.model.num_threads = threads; c.model.provider = "cpu";
  c.max_num_sentences = 2; c.silence_scale = 1.0f;
  return SherpaOnnxCreateOfflineTts(&c);
}

int main(int argc, char **argv) {
  if (argc < 8) { fprintf(stderr, "usage\n"); return 2; }
  int threads = atoi(argv[4]), steps = atoi(argv[5]), every = atoi(argv[6]); long abort_mb = atol(argv[7]);
  const SherpaOnnxWave *ref = SherpaOnnxReadWave(argv[2]);
  char *ref_text = slurp(argv[3]);
  char *all = slurp(argv[1]);
  char *chunks[256]; int nc = 0;
  for (char *s = strtok(all, "\n"); s && nc < 256; s = strtok(NULL, "\n")) chunks[nc++] = s;
  printf("# chunks=%d threads=%d steps=%d recreate_every=%d ref_s=%.1f\n", nc, threads, steps, every, ref->num_samples / (double)ref->sample_rate);
  printf("# idx chars audio_s secs rss_mb hwm_mb heap_mb\n"); fflush(stdout);
  const SherpaOnnxOfflineTts *tts = create(threads);
  printf("load rss_mb=%ld hwm_mb=%ld\n", status_kb("VmRSS:") / 1024, status_kb("VmHWM:") / 1024); fflush(stdout);
  for (int i = 0; i < nc; ++i) {
    if (every > 0 && i > 0 && i % every == 0) {
      SherpaOnnxDestroyOfflineTts(tts); malloc_trim(0); tts = create(threads);
      printf("recreate rss_mb=%ld\n", status_kb("VmRSS:") / 1024);
    }
    SherpaOnnxGenerationConfig g; memset(&g, 0, sizeof g);
    g.silence_scale = 1.0f; g.speed = 0.88f; g.sid = 0; g.reference_audio = ref->samples;
    g.reference_audio_len = ref->num_samples; g.reference_sample_rate = ref->sample_rate;
    g.reference_text = ref_text; g.num_steps = steps; g.extra = "{\"min_char_in_sentence\":\"2\"}";
    double t0 = now();
    const SherpaOnnxGeneratedAudio *a = SherpaOnnxOfflineTtsGenerateWithConfig(tts, chunks[i], &g, NULL, NULL);
    double dt = now() - t0;
    long hwm = status_kb("VmHWM:") / 1024;
    double audio = a ? a->n / (double)a->sample_rate : 0;
    if (a) SherpaOnnxDestroyOfflineTtsGeneratedAudio(a);
    struct mallinfo2 mi = mallinfo2();
    printf("%d %zu %.1f %.1f %ld %ld %zu\n", i + 1, strlen(chunks[i]) / 3, audio, dt, status_kb("VmRSS:") / 1024, hwm, (mi.uordblks + mi.hblkhd) >> 20);
    fflush(stdout);
    if (hwm > abort_mb) { printf("ABORT hwm>%ld\n", abort_mb); return 3; }
  }
  SherpaOnnxDestroyOfflineTts(tts);
  return 0;
}
