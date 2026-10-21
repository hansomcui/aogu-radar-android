"""Create VoiceForge v0.3.5.9 workflow from the v0.3.5.8 one (commit f404960).
Changes (QF182 long-text exit fix):
  1. Engine recycling between chunks when native heap exceeds a budget (memory evidence: vfmem bench).
  2. Long generation is a resumable job: WAV header + job sidecar checkpointed after every chunk,
     partial audio survives process death / cancel / error, and a dialog offers continue / save / delete.
  3. WavStreamWriter writes buffers instead of one syscall per byte.
  4. Breadcrumb records engine recycle count and per-chunk heap.
Every replacement must match exactly once, otherwise the script fails."""
import re, sys, pathlib

SRC = pathlib.Path(".github/workflows/VoiceForge_v0.3.5.8_bg-memory_build-apk.yml")
DST = pathlib.Path(".github/workflows/VoiceForge_v0.3.5.9_long-text_build-apk.yml")
s = SRC.read_text()

def sub(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        sys.exit(f"expected {count} match(es), found {n}: {old[:80]!r}")
    s = s.replace(old, new)

def ind(block, n=14):
    pad = " " * n
    return "\n".join((pad + l) if l.strip() else "" for l in block.strip("\n").split("\n"))

# ---------- version strings ----------
sub("name: Build VoiceForge v0.3.5.8 Background Memory APK", "name: Build VoiceForge v0.3.5.9 Long Text Recovery APK")
sub('".github/workflows/VoiceForge_v0.3.5.8_bg-memory_build-apk.yml"', '".github/workflows/VoiceForge_v0.3.5.9_long-text_build-apk.yml"')
sub("versionCode 43", "versionCode 44")
sub('versionName "0.3.5.8"', 'versionName "0.3.5.9"')
sub("诊断报告 v0.3.5.8", "诊断报告 v0.3.5.9")
sub("OFFLINE VOICE LIBRARY · v0.3.5.8", "OFFLINE VOICE LIBRARY · v0.3.5.9")
s = s.replace("VoiceForge-v0.3.5.8-BG-MEMORY", "VoiceForge-v0.3.5.9-LONG-TEXT")
sub("TAG=voiceforge-v0.3.5.8", "TAG=voiceforge-v0.3.5.9")
sub("dist/VoiceForge-v0.3.5.9-LONG-TEXT.apk dist/VoiceForge-v0.3.5.8.apk", "dist/VoiceForge-v0.3.5.9-LONG-TEXT.apk dist/VoiceForge-v0.3.5.9.apk")
sub('gh release create "$TAG" dist/VoiceForge-v0.3.5.8.apk', 'gh release create "$TAG" dist/VoiceForge-v0.3.5.9.apk')
sub('--title "声魄 VoiceForge v0.3.5.8"', '--title "声魄 VoiceForge v0.3.5.9"')
m = re.search(r'--notes "离线中英文声音克隆。v0\.3\.5\.8：[^"]*"', s)
if not m: sys.exit("notes not found")
s = s.replace(m.group(0), '--notes "离线中英文声音克隆。v0.3.5.9：长文本生成时按内存占用自动重建模型，避免连续多段后被系统杀死；每段完成即落盘，中断、取消或出错后可继续生成剩余段落或保存已完成部分。构建 run ${GITHUB_RUN_ID}，提交 ${GITHUB_SHA}。"')

# ---------- startup recovery hook ----------
sub("webView.postDelayed({ runCatching { showLastExitReportIfAny() } }, 1500)",
    "webView.postDelayed({ runCatching { showLastExitReportIfAny() } }, 1500)\n"
    "                  webView.postDelayed({ runCatching { offerRecoveryIfAny() } }, 2600)")

# ---------- engine build split out of prepareEngine ----------
old_build = s[s.index("                      val zip = OfflineTtsZipVoiceModelConfig("):s.index("                      tts = OfflineTts(assetManager = null, config = fullCfg)\n")]
sub(old_build + "                      tts = OfflineTts(assetManager = null, config = fullCfg)\n",
    "                      tts = buildEngine()\n")
build_fn = ("              private fun buildEngine(): OfflineTts {\n" +
    "\n".join(l[4:] if l.startswith(" " * 22) else l for l in old_build.rstrip("\n").split("\n")) +
    "\n                  return OfflineTts(assetManager = null, config = fullCfg)\n              }\n")
sub("              private fun copyAssetTree(assetPath: String, dest: File) {",
    build_fn + "\n" +
    "              private fun copyAssetTree(assetPath: String, dest: File) {")

# ---------- synthesizeOffline rewrite ----------
start = s.index("              private fun synthesizeOffline(")
end = s.index("              private fun pruneOldWorks(limit: Int) {")
NEW_SYNTH = r'''
// ---- v0.3.5.9 long-text job: memory-aware engine recycling + per-chunk checkpoints ----
private data class GenJob(
    val id: String, val voiceId: String, val style: String, val intensity: Int,
    val chunks: List<String>, var done: Int, var bytes: Long, val finalName: String, val created: Long
)
private fun jobFile(id: String) = File(worksDir, ".job-$id.json")
private fun jobPartFile(id: String) = File(worksDir, ".part-$id.wav")

private fun saveJob(j: GenJob) {
    val o = JSONObject().apply {
        put("v", 1); put("id", j.id); put("voiceId", j.voiceId); put("style", j.style); put("intensity", j.intensity)
        put("chunks", JSONArray(j.chunks)); put("done", j.done); put("bytes", j.bytes)
        put("finalName", j.finalName); put("created", j.created)
    }
    val tmp = File(worksDir, ".job-${j.id}.json.tmp")
    FileOutputStream(tmp).use { out -> out.write(o.toString().toByteArray(Charsets.UTF_8)); out.fd.sync() }
    if (!tmp.renameTo(jobFile(j.id))) { tmp.copyTo(jobFile(j.id), overwrite = true); tmp.delete() }
}

private fun loadJobs(): List<GenJob> = worksDir.listFiles()
    ?.filter { it.isFile && it.name.startsWith(".job-") && it.name.endsWith(".json") }
    ?.mapNotNull { f ->
        runCatching {
            val o = JSONObject(f.readText())
            val arr = o.getJSONArray("chunks")
            GenJob(o.getString("id"), o.getString("voiceId"), o.getString("style"), o.getInt("intensity"),
                List(arr.length()) { arr.getString(it) }, o.getInt("done"), o.getLong("bytes"),
                o.getString("finalName"), o.optLong("created", f.lastModified()))
        }.getOrNull()
    }
    ?.sortedByDescending { it.created } ?: emptyList()

private fun deleteJob(j: GenJob) { jobFile(j.id).delete(); jobPartFile(j.id).delete() }

private var engineRecycles = 0
private fun nativeHeapMb(): Long = android.os.Debug.getNativeHeapAllocatedSize() / 1048576

/** Budget for native heap between chunks. Measured on Linux with the same sherpa-onnx 1.13.8:
 *  heap left after a chunk keeps growing across chunks on one OfflineTts; recreating the engine
 *  returns it to the post-load level. */
private fun recycleBudgetMb(): Long {
    val am = getSystemService(ACTIVITY_SERVICE) as android.app.ActivityManager
    val mi = android.app.ActivityManager.MemoryInfo(); am.getMemoryInfo(mi)
    return (mi.totalMem / 1048576 * RECYCLE_FRACTION_PERCENT / 100).coerceIn(RECYCLE_MIN_MB, RECYCLE_MAX_MB)
}

private fun recycleEngine(reason: String): OfflineTts {
    writeBreadcrumb("重建模型（释放跨段累积的原生内存）", "reason=$reason recycles=${engineRecycles + 1} heapBeforeMB=${nativeHeapMb()}")
    val old = tts
    tts = null
    runCatching { old?.release() }
    val fresh = buildEngine()
    tts = fresh
    engineRecycles++
    return fresh
}

private fun synthesizeOffline(raw: String, style: String, intensity: Int, preview: Boolean, voice: VoiceProfile) {
    var source = if (preview) previewText(raw) else raw
    source = transformText(source, style, intensity)
    val chunks = splitText(source, if (preview) 120 else CHUNK_MAX_CHARS)
    if (chunks.isEmpty()) error("没有可生成的文字")
    val stamp = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date())
    if (preview) {
        val tempFile = File(previewDir, ".part-$stamp-${System.nanoTime()}.wav")
        val finalFile = File(previewDir, "Preview-$stamp.wav")
        try {
            renderChunks(chunks, 0, tempFile, 0L, voice, style, intensity, true) { _, _ -> }
            finishWav(tempFile, finalFile, chunks.size, style, true, voice)
        } catch (t: Throwable) {
            tempFile.delete()
            throw t
        }
        return
    }
    val job = GenJob("$stamp-${System.nanoTime() % 100000}", voice.id, style, intensity, chunks, 0, 44L,
        "VoiceForge-$stamp.wav", System.currentTimeMillis())
    saveJob(job)
    runJob(job, voice)
}

private fun runJob(job: GenJob, voice: VoiceProfile) {
    val part = jobPartFile(job.id)
    try {
        renderChunks(job.chunks, job.done, part, if (job.done > 0) job.bytes else 0L, voice, job.style, job.intensity, false) { done, bytes ->
            job.done = done; job.bytes = bytes; saveJob(job)
        }
        finishWav(part, File(worksDir, job.finalName), job.chunks.size, job.style, false, voice)
        jobFile(job.id).delete()
    } catch (t: Throwable) {
        if (job.done <= 0) deleteJob(job)
        else if (!shuttingDown) mainHandler.postDelayed({ runCatching { offerRecoveryIfAny() } }, 800)
        throw t
    }
}

private fun renderChunks(
    chunks: List<String>, startIndex: Int, file: File, resumeBytes: Long, voice: VoiceProfile,
    style: String, intensity: Int, preview: Boolean, onChunkDone: (Int, Long) -> Unit
) {
    var localTts = tts ?: error("本地模型尚未加载完成")
    val ref = readOwnWav(voiceFile(voice))
    val refSeconds = ref.samples.size.toDouble() / ref.sampleRate.coerceAtLeast(1)
    referenceProblem(refSeconds, voice.referenceText)?.let { error("音色「${voice.name}」无法使用：$it") }
    val cfg = styleFor(style, intensity)
    val budget = recycleBudgetMb()
    WavStreamWriter(file, SAMPLE_RATE, resumeBytes).use { writer ->
        for (index in startIndex until chunks.size) {
            val chunk = chunks[index]
            if (generationCancel.get() || shuttingDown) throw GenerationCancelledException()
            if (!preview && index > startIndex && nativeHeapMb() > budget) {
                js("window.onGenerationProgress&&window.onGenerationProgress(${index + 1},${chunks.size},${q("整理内存，重新加载模型")})")
                localTts = recycleEngine("heapMB>${budget} before chunk ${index + 1}")
            }
            js("window.onGenerationProgress&&window.onGenerationProgress(${index + 1},${chunks.size},${q("本地生成第 ${index + 1} 段")})")
            val gc = GenerationConfig(
                silenceScale = cfg.silenceScale,
                speed = cfg.speed,
                sid = 0,
                referenceAudio = ref.samples,
                referenceSampleRate = ref.sampleRate,
                referenceText = voice.referenceText,
                numSteps = cfg.numSteps,
                extra = mapOf("min_char_in_sentence" to "2")
            )
            writeBreadcrumb(
                "原生推理开始（若停在这里，说明进程在推理中死亡）",
                "voice=${voice.name} refSeconds=${String.format(Locale.US, "%.1f", refSeconds)} " +
                    "refSampleRate=${ref.sampleRate} refTextChars=${voice.referenceText.length} chunk=${index + 1}/${chunks.size} " +
                    "chunkChars=${chunk.length} numSteps=${cfg.numSteps} speed=${cfg.speed} preview=$preview " +
                    "threads=${Runtime.getRuntime().availableProcessors().coerceIn(2, 4)} " +
                    "engineRecycles=$engineRecycles recycleBudgetMB=$budget resumedFrom=$startIndex savedChunks=$index"
            )
            localTts.generateWithConfigAndCallback(text = chunk, config = gc) { pcmChunk ->
                if (generationCancel.get() || shuttingDown) {
                    0
                } else {
                    writer.append(postProcess(pcmChunk, cfg.gain, cfg.tone))
                    1
                }
            }
            if (generationCancel.get() || shuttingDown) throw GenerationCancelledException()
            writer.appendSilence(cfg.chunkGapMs)
            writer.checkpoint()
            onChunkDone(index + 1, writer.byteLength)
        }
    }
}

private fun finishWav(tempFile: File, finalFile: File, chunkCount: Int, style: String, preview: Boolean, voice: VoiceProfile) {
    val info = inspectPcm16Wav(tempFile)
    check(info.dataSize > 0L && info.sampleRate > 0) { "生成 WAV 无效" }
    if (generationCancel.get() || shuttingDown) throw GenerationCancelledException()
    if (finalFile.exists()) finalFile.delete()
    if (!tempFile.renameTo(finalFile)) {
        FileInputStream(tempFile).use { input ->
            FileOutputStream(finalFile).use { output -> input.copyTo(output, 64 * 1024) }
        }
        tempFile.delete()
    }
    currentGenerated = finalFile
    writeBreadcrumb("生成完成", "voice=${voice.name} chunks=$chunkCount file=${finalFile.name} engineRecycles=$engineRecycles")
    if (!preview) pruneOldWorks(50)
    js("window.onGenerationComplete&&window.onGenerationComplete($chunkCount,${q(style)})")
    if (!preview) js("window.onHistoryChanged&&window.onHistoryChanged()")
    playFile(finalFile)
}

@Volatile private var recoveryDialogShown = false

/** Shows at most one dialog for the newest interrupted long-text job. */
private fun offerRecoveryIfAny() {
    if (recoveryDialogShown || generationInProgress || shuttingDown) return
    Thread {
        val jobs = runCatching { loadJobs() }.getOrDefault(emptyList())
        val usable = mutableListOf<GenJob>()
        jobs.forEach { j ->
            val part = jobPartFile(j.id)
            if (j.done <= 0 || !part.isFile || part.length() < j.bytes) deleteJob(j)   // nothing recoverable
            else usable += j
        }
        val job = usable.firstOrNull() ?: return@Thread
        runCatching { WavStreamWriter.repair(jobPartFile(job.id), job.bytes, SAMPLE_RATE) }
        val minutes = (job.bytes - 44L) / 2.0 / SAMPLE_RATE / 60.0
        runOnUiThread {
            if (recoveryDialogShown || generationInProgress || shuttingDown) return@runOnUiThread
            recoveryDialogShown = true
            val total = job.chunks.size
            val left = total - job.done
            android.app.AlertDialog.Builder(this@MainActivity)
                .setTitle("有未完成的长文本")
                .setMessage("上次生成在第 ${job.done + 1}/$total 段中断（系统回收内存、取消或出错）。\n" +
                    "前 ${job.done} 段（约 ${String.format(Locale.US, "%.1f", minutes)} 分钟）已安全保存。" +
                    (if (usable.size > 1) "\n另有 ${usable.size - 1} 个更早的未完成任务，处理完这个后会再提示。" else ""))
                .setPositiveButton(if (left > 0) "继续生成剩余 $left 段" else "完成") { _, _ -> recoveryDialogShown = false; resumeJob(job) }
                .setNeutralButton("保存已完成部分") { _, _ -> recoveryDialogShown = false; savePartialJob(job) }
                .setNegativeButton("删除") { _, _ -> recoveryDialogShown = false; deleteJob(job); toast("已删除未完成的部分") }
                .setOnCancelListener { recoveryDialogShown = false }
                .show()
        }
    }.start()
}

private fun resumeJob(job: GenJob) {
    if (generationInProgress) { toast("已有生成任务正在运行"); return }
    val voice = loadVoiceProfiles().firstOrNull { it.id == job.voiceId }
    if (voice == null || !voiceFile(voice).isFile) {
        toast("原来使用的音色已不存在，只能保存已完成部分")
        return
    }
    generationCancel.set(false)
    generationInProgress = true
    js("window.onGenerationProgress&&window.onGenerationProgress(${job.done + 1},${job.chunks.size},${q("继续生成第 ${job.done + 1} 段")})")
    generationFuture = executor.submit {
        try {
            if (tts == null) prepareEngine()
            runJob(job, voice)
        } catch (_: GenerationCancelledException) {
            js("window.onGenerationCancelled&&window.onGenerationCancelled()")
        } catch (t: Throwable) {
            if (!shuttingDown) js("window.onGenerationError&&window.onGenerationError(${q(friendly(t))})")
        } finally {
            generationInProgress = false
            generationFuture = null
            generationCancel.set(false)
        }
    }
}

private fun savePartialJob(job: GenJob) {
    executor.execute {
        runCatching {
            val part = jobPartFile(job.id)
            WavStreamWriter.repair(part, job.bytes, SAMPLE_RATE)
            val dest = File(worksDir, job.finalName.removeSuffix(".wav") + "-前${job.done}段.wav")
            if (!part.renameTo(dest)) { part.copyTo(dest, overwrite = true); part.delete() }
            jobFile(job.id).delete()
            currentGenerated = dest
            js("window.onHistoryChanged&&window.onHistoryChanged()")
            toast("已保存：" + dest.name)
        }.onFailure { toast("保存失败：" + friendly(it)) }
    }
}
'''
s = s[:start] + ind(NEW_SYNTH) + "\n\n" + s[end:]

# ---------- constants ----------
sub('                  private const val PENDING_REF_FILE = "pending_voice_reference.wav"\n',
    '                  private const val PENDING_REF_FILE = "pending_voice_reference.wav"\n'
    '                  // v0.3.5.9 long-text memory policy (see vfmem bench evidence)\n'
    '                  private const val CHUNK_MAX_CHARS = __CHUNK_MAX__\n'
    '                  private const val RECYCLE_FRACTION_PERCENT = __RECYCLE_PCT__L\n'
    '                  private const val RECYCLE_MIN_MB = __RECYCLE_MIN__L\n'
    '                  private const val RECYCLE_MAX_MB = __RECYCLE_MAX__L\n')

# ---------- WavStreamWriter rewrite ----------
ws = s.index("              private class WavStreamWriter(")
we = s.index("              private fun splitText(text: String, maxChars: Int): List<String> {")
NEW_WRITER = r'''
private class WavStreamWriter(private val file: File, private val sampleRate: Int, resumeBytes: Long = 0L) : AutoCloseable {
    private val raf = RandomAccessFile(file, "rw")
    private var sampleCount = 0L
    init {
        if (resumeBytes >= 44L && raf.length() >= resumeBytes) {
            raf.setLength(resumeBytes)          // drop any half-written chunk after the last checkpoint
            sampleCount = (resumeBytes - 44L) / 2L
            raf.seek(resumeBytes)
        } else {
            raf.setLength(0)
            raf.write(ByteArray(44))
        }
    }
    val byteLength: Long get() = 44L + sampleCount * 2L
    fun append(samples: FloatArray) {
        val buf = ByteArray(samples.size * 2)
        var j = 0
        for (f in samples) {
            val s = (f.coerceIn(-1f, 1f) * 32767f).toInt()
            buf[j++] = (s and 0xff).toByte()
            buf[j++] = ((s shr 8) and 0xff).toByte()
        }
        raf.write(buf)
        sampleCount += samples.size
    }
    fun appendSilence(ms: Int) {
        val n = (sampleRate * ms / 1000.0).toInt()
        if (n > 0) { raf.write(ByteArray(n * 2)); sampleCount += n }
    }
    /** Make the file a valid WAV up to this point and flush it to storage. */
    fun checkpoint() {
        val end = raf.filePointer
        writeHeader(raf, sampleRate, sampleCount * 2L)
        raf.seek(end)
        raf.fd.sync()
    }
    override fun close() {
        writeHeader(raf, sampleRate, sampleCount * 2L)
        raf.close()
    }
    companion object {
        fun repair(file: File, bytes: Long, sampleRate: Int) {
            RandomAccessFile(file, "rw").use { r ->
                if (r.length() > bytes) r.setLength(bytes)
                writeHeader(r, sampleRate, r.length() - 44L)
                r.fd.sync()
            }
        }
        private fun writeHeader(r: RandomAccessFile, sampleRate: Int, dataBytes: Long) {
            val dataSize = dataBytes.toInt()
            r.seek(0)
            r.writeBytes("RIFF")
            writeLE32(r, 36 + dataSize)
            r.writeBytes("WAVEfmt ")
            writeLE32(r, 16)
            writeLE16(r, 1)
            writeLE16(r, 1)
            writeLE32(r, sampleRate)
            writeLE32(r, sampleRate * 2)
            writeLE16(r, 2)
            writeLE16(r, 16)
            r.writeBytes("data")
            writeLE32(r, dataSize)
        }
        private fun writeLE16(r: RandomAccessFile, v: Int) {
            r.write(v and 0xff); r.write((v shr 8) and 0xff)
        }
        private fun writeLE32(r: RandomAccessFile, v: Int) {
            r.write(v and 0xff); r.write((v shr 8) and 0xff)
            r.write((v shr 16) and 0xff); r.write((v shr 24) and 0xff)
        }
    }
}
'''
s = s[:ws] + ind(NEW_WRITER) + "\n\n" + s[we:]

# ---------- build-time invariants ----------
sub("          grep -q 'backgroundCleanup' app/src/main/java/com/hansom/voiceforge/MainActivity.kt\n",
    "          grep -q 'backgroundCleanup' app/src/main/java/com/hansom/voiceforge/MainActivity.kt\n"
    "          grep -q 'fun offerRecoveryIfAny' app/src/main/java/com/hansom/voiceforge/MainActivity.kt\n"
    "          grep -q 'fun recycleEngine' app/src/main/java/com/hansom/voiceforge/MainActivity.kt\n"
    "          grep -q 'fun checkpoint' app/src/main/java/com/hansom/voiceforge/MainActivity.kt\n")

params = dict(a.split("=") for a in sys.argv[1:])
for k, v in params.items():
    s = s.replace(f"__{k}__", v)
left = re.findall(r"__[A-Z_]+__", s)
if left: sys.exit(f"unfilled params: {set(left)}")
DST.write_text(s)
print("wrote", DST, len(s.splitlines()), "lines")
