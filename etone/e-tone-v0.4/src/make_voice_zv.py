#!/usr/bin/env python3
"""E/F-tone v0.3：ZipVoice 零样本合成（清云原创脚本）。
提示音 = Kokoro 原始合成句（未经 Praat 处理，非真人），ZipVoice 负责自然韵律；后期只做响度与柔化 EQ，不做 PSOLA、不加噪声。
用法: python3 make_voice_zv.py STYLE [--tag run1]
"""
import argparse, hashlib, json, os, re, subprocess, time, wave, platform
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, 'paths.json')))
SR = 24000
def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0: raise RuntimeError(f"{cmd}\n{r.stderr[-1500:]}")
    return r
def rd(p):
    w = wave.open(p); assert w.getframerate() == SR, p
    return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
def wr(p, x):
    w = wave.open(p, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()
def kokoro(text, sid, out, ls=1.0):
    m = CFG['kokoro_dir']; b = CFG['sherpa_dir']
    sh([f'{b}/bin/sherpa-onnx-offline-tts', f'--kokoro-model={m}/model.onnx', f'--kokoro-voices={m}/voices.bin', f'--kokoro-tokens={m}/tokens.txt',
        f'--kokoro-data-dir={m}/espeak-ng-data', f'--kokoro-lexicon={m}/lexicon-us-en.txt,{m}/lexicon-zh.txt', '--num-threads=1', f'--sid={sid}', f'--kokoro-length-scale={ls}', f'--output-filename={out}', text],
       env=dict(os.environ, LD_LIBRARY_PATH=f'{b}/lib'))
def zipvoice(text, ref, ref_text, speed, steps, out):
    z = CFG['zipvoice_dir']; b = CFG['sherpa_dir']
    sh([f'{b}/bin/sherpa-onnx-offline-tts', f'--zipvoice-encoder={z}/encoder.int8.onnx', f'--zipvoice-decoder={z}/decoder.int8.onnx',
        f'--zipvoice-data-dir={z}/espeak-ng-data', f'--zipvoice-lexicon={z}/lexicon.txt', f'--zipvoice-tokens={z}/tokens.txt', f'--zipvoice-vocoder={z}/vocos_24khz.onnx',
        f'--reference-audio={ref}', f'--reference-text={ref_text}', f'--num-steps={steps}', f'--speed={speed}', '--num-threads=2', f'--output-filename={out}', text],
       env=dict(os.environ, LD_LIBRARY_PATH=f'{b}/lib'))
def trim(x, thr=0.004):
    i = np.where(np.abs(x) > thr)[0]
    return x[max(0, i[0] - 240): i[-1] + 720] if len(i) else x
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('style'); ap.add_argument('--tag', default='run1')
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'out_zv')); a = ap.parse_args()
    st = json.load(open(os.path.join(HERE, 'styles_zv.json')))[a.style]
    work = os.path.join(a.out, f'work_{a.style}_{a.tag}'); os.makedirs(work, exist_ok=True); t0 = time.time()
    # 1) 提示音：Kokoro 原始合成（固定一次生成后缓存，保证跨次一致）
    ref = os.path.join(a.out, f'prompt_{a.style}.wav')
    if not os.path.exists(ref):
        parts = []
        for i, s in enumerate(st['prompt_sentences']):
            p = os.path.join(work, f'prompt_{i}.wav'); kokoro(s, st['prompt_sid'], p); parts += [trim(rd(p)), np.zeros(int(SR * 0.3), np.float32)]
        wr(ref, np.concatenate(parts)[:-int(SR * 0.3)])
    ref_text = ''.join(st['prompt_sentences'])
    # 2) 正文：按 chunk（约两句）合成
    text = open(os.path.join(HERE, st['text_file']), encoding='utf-8').read().strip()
    sents = re.findall(r'[^。？！；]+[。？！；]', text)
    chunks, cur = [], ''
    for s in sents:
        cur += s
        if len(cur) >= st.get('chunk_chars', 24): chunks.append(cur); cur = ''
    if cur: chunks.append(cur)
    pieces = []; log = {'style': a.style, 'params': st, 'prompt_wav_sha256': hashlib.sha256(open(ref, 'rb').read()).hexdigest(), 'chunks': []}
    for i, c in enumerate(chunks):
        o = os.path.join(work, f'{i:02d}.wav'); zipvoice(c, ref, ref_text, st['speed'], st['num_steps'], o)
        x = trim(rd(o)); pieces += [x, np.zeros(int(SR * st['chunk_pause_ms'] / 1000), np.float32)]
        log['chunks'].append({'i': i, 'text': c, 'seconds': round(len(x) / SR, 3)})
    y = np.concatenate([np.zeros(int(SR * 0.25), np.float32)] + pieces)
    tmp = os.path.join(work, 'mix.wav'); wr(tmp, y / (np.max(np.abs(y)) + 1e-9) * 0.7)
    # 3) 柔化：只用 ffmpeg 均衡（高频搁架衰减 + 轻低通），不做变调
    eq = os.path.join(work, 'eq.wav')
    af = f"treble=g={st['treble_db']}:f=4000:t=s:w=0.7,lowpass=f={st['lowpass_hz']}"
    sh(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', tmp, '-af', af, '-ar', str(SR), '-ac', '1', '-c:a', 'pcm_s16le', eq])
    y = rd(eq); act = np.abs(y) > 0.01
    y = y / (np.sqrt(np.mean(y[act] ** 2)) + 1e-9) * st['ref_rms'] * st['gain']
    if np.max(np.abs(y)) > 0.89: y = y / np.max(np.abs(y)) * 0.89
    f = int(SR * 0.05); y[-f:] *= np.linspace(1, 0, f)
    os.makedirs(a.out, exist_ok=True); wav = os.path.join(a.out, f'Etone_{a.style}_{a.tag}.wav'); wr(wav, y)
    sh(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', wav, '-b:a', '128k', wav[:-4] + '.mp3'])
    log.update({'output_wav': os.path.basename(wav), 'output_sha256': hashlib.sha256(open(wav, 'rb').read()).hexdigest(), 'seconds': round(len(y) / SR, 3),
                'elapsed_s': round(time.time() - t0, 1), 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t0)), 'host': platform.platform()})
    json.dump(log, open(wav[:-4] + '.log.json', 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: log[k] for k in ['style', 'output_wav', 'seconds', 'elapsed_s']}, ensure_ascii=False))
if __name__ == '__main__': main()
