# VoiceForge v0.3.5.9 long-text exit — memory evidence (清云, 2026-10-21)

Task: QF182 / QH-021. Baseline: commit f404960 (v0.3.5.8), build run 38281984078.

## Bench (Linux x86_64, 2 vCPU, 7 GB, same sherpa-onnx v1.13.8 C API as the Android AAR)
- Model: sherpa-onnx-zipvoice-distill-int8-zh-en-emilia + vocos_24khz, num_threads=2 (phone 4), num_steps=4, speed 0.88, max_num_sentences=2.
- Reference: 19.4 s synthetic Kokoro voice (sid 47), 64-char text (ref.txt). No personal audio.
- Text: synthetic (make_text.py, seed 20261021), split with a port of MainActivity.splitText(…,300).
- bench.c prints after each chunk: chars, audio seconds, seconds, RSS MB, peak RSS MB, malloc in-use MB.

## Results (raw logs: run_ab.log, run_small.log)
| run | after chunk 1 | after chunk 2 | after chunk 8 |
|---|---|---|---|
| one engine, ~200–290-char chunks | 2555 MB in use | 4741 MB | 4743 MB (plateau) |
| recreate engine every 2 chunks | 2555 | 4741 → recreate RSS 290 MB → chunk 3: 5788 | stopped after chunk 4 (5797) |
| one engine, 59–74-char chunks | 2554 | 2554 | chunk 4–5: 4667 |
| one engine, 112–140-char chunks | 2554 | 4667 | stopped after chunk 3 (4733) |

Findings (only what the data show):
1. One ZipVoice inference leaves ~2.5 GB of native memory allocated; after a few chunks ~4.7 GB stays allocated. Chunk length (60–290 chars) barely changes this.
2. Recreating the engine frees the memory (RSS 290 MB), but the next chunk allocated 5.8 GB, so recreation is not a reliable reduction.
3. On the phone the breadcrumb showed nativeHeapMB=5875 before chunk 9 and LOW_MEMORY/SIGNALED kills during chunk 9. Android allocator behaviour was not measured here.
Not proven: the exact allocator (ORT arena or scudo), a leak, or that the two phone exits have the same cause.

## Fix in v0.3.5.9
- After every chunk: WAV header rewritten + fsync, job sidecar (.job-<id>.json: chunks, done, bytes) saved atomically.
- Process killed / cancelled / error: completed chunks are kept. On next start (or right after cancel/error) a dialog offers:
  continue remaining chunks (fresh process memory), save completed part as a work, or delete.
- Engine recycled when native heap > 35% of device RAM (clamped 2.5–4.5 GB) — safety net only.
- WAV writing buffered (was one syscall per byte). Breadcrumb now records engineRecycles, budget, resume index.
