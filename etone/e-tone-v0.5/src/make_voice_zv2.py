#!/usr/bin/env python3
"""E-tone v0.4：逐短句 ZipVoice + 多候选自动质检（清云原创）。
修 v0.3 问题：低速(0.57)拉伸导致句中声音骤轻、变调。改为接近正常语速合成，慢主要靠句读停顿；
每个短句生成 N 个候选，按「音量骤降、音高偏离、语速异常」打分选最稳的一个；各短句响度对齐。
"""
import argparse, hashlib, json, os, re, subprocess, time, wave, platform
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); CFG = json.load(open(os.path.join(HERE, 'paths.json'))); SR = 24000
from make_voice_zv import sh, rd, wr, kokoro, zipvoice, trim
def f0_track(p):
    s = f's = Read from file: "{p}"\nr = Resample: 48000, 50\np = To Pitch: 0.01, 120, 600\nn = Get number of frames\nfor i to n\n  f = Get value in frame: i, "Hertz"\n  appendInfo: fixed$(f, 1), " "\nendfor\n'
    open('/tmp/_trk.praat', 'w').write(s)
    v = sh([CFG['praat'], '--run', '/tmp/_trk.praat']).stdout.split()
    return np.array([float(x) if x != '--undefined--' else np.nan for x in v])
def score(x, f0, ref_med, nchar):
    fr = 0.02; n = int(SR * fr); m = len(x) // n
    db = 20 * np.log10(np.sqrt(np.mean(x[:m * n].reshape(m, n) ** 2, 1)) + 1e-9)
    sp = db > db.max() - 35; idx = np.where(sp)[0]
    core = db[idx[0]: idx[-1] + 1] if len(idx) else db
    med = np.median(core)
    # 句中持续 ≥0.3 s 比中位低 12 dB 以上的段（不含句间自然停顿判定：只看有声帧前后）
    low = core < med - 12; run = mx = 0
    for v in low: run = run + 1 if v else 0; mx = max(mx, run)
    dip = mx * fr
    vf = f0[~np.isnan(f0)]
    pitch_dev = abs(12 * np.log2(np.median(vf) / ref_med)) if len(vf) > 5 else 9
    jumps = np.mean(np.abs(np.diff(12 * np.log2(vf))) > 4) if len(vf) > 5 else 1
    rate = nchar / (len(x) / SR)
    rate_pen = max(0, 3.0 - rate) + max(0, rate - 6.0)
    return dip * 3 + pitch_dev + jumps * 10 + rate_pen, {'dip_s': round(dip, 2), 'pitch_dev_st': round(pitch_dev, 2), 'jump_ratio': round(float(jumps), 3), 'rate_cps': round(rate, 2)}
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('style'); ap.add_argument('--tag', default='run1'); ap.add_argument('--out', default=os.path.join(HERE, '..', 'out_zv2'))
    a = ap.parse_args(); st = json.load(open(os.path.join(HERE, 'styles_zv2.json')))[a.style]
    work = os.path.join(a.out, f'work_{a.style}_{a.tag}'); os.makedirs(work, exist_ok=True); t0 = time.time()
    ref = os.path.join(a.out, f'prompt_{a.style}.wav')
    if not os.path.exists(ref):
        parts = []
        for i, s in enumerate(st['prompt_sentences']):
            p = os.path.join(work, f'prompt_{i}.wav'); kokoro(s, st['prompt_sid'], p, st.get('prompt_length_scale', 1.0)); parts += [trim(rd(p)), np.zeros(int(SR * 0.3), np.float32)]
        wr(ref, np.concatenate(parts)[:-int(SR * 0.3)])
    ref_text = ''.join(st['prompt_sentences']); rf = f0_track(ref); ref_med = np.nanmedian(rf)
    text = open(os.path.join(HERE, st['text_file']), encoding='utf-8').read().strip()
    clauses = re.findall(r'[^，。？！；]+[，。？！；]', text)
    log = {'style': a.style, 'params': st, 'prompt_sha256': hashlib.sha256(open(ref, 'rb').read()).hexdigest(), 'prompt_f0_median': round(float(ref_med), 1), 'clauses': []}
    pieces = [np.zeros(int(SR * 0.25), np.float32)]
    for i, c in enumerate(clauses):
        nchar = len(re.findall(r'[一-鿿]', c)); best = None; cands = []
        for k in range(st['candidates']):
            o = os.path.join(work, f'{i:02d}_c{k}.wav'); zipvoice(c, ref, ref_text, st['speed'], st['num_steps'], o)
            x = trim(rd(o)); wr(o + '.trim.wav', x); f0 = f0_track(o + '.trim.wav')
            sc, info = score(x, f0, ref_med, nchar); info['score'] = round(sc, 3); cands.append(info)
            if best is None or sc < best[0]: best = (sc, x, k)
        x = best[1]; act = np.abs(x) > 0.01; x = x / (np.sqrt(np.mean(x[act] ** 2)) + 1e-9) * 0.1
        pieces.append(x)
        pause = st['pause_ms'][c[-1]] if c[-1] in st['pause_ms'] else 300
        if i == len(clauses) - 1: pause = 300
        pieces.append(np.zeros(int(SR * pause / 1000), np.float32))
        log['clauses'].append({'i': i, 'text': c, 'chosen': best[2], 'candidates': cands, 'seconds': round(len(x) / SR, 3), 'pause_ms': pause})
        print(i, c, 'chosen', best[2], cands[best[2]], flush=True)
    y = np.concatenate(pieces); tmp = os.path.join(work, 'mix.wav'); wr(tmp, y / (np.max(np.abs(y)) + 1e-9) * 0.7)
    eq = os.path.join(work, 'eq.wav')
    sh(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', tmp, '-af', f"treble=g={st['treble_db']}:f=4000:t=s:w=0.7,lowpass=f={st['lowpass_hz']}", '-ar', str(SR), '-ac', '1', '-c:a', 'pcm_s16le', eq])
    y = rd(eq); act = np.abs(y) > 0.01; y = y / (np.sqrt(np.mean(y[act] ** 2)) + 1e-9) * st['ref_rms'] * st['gain']
    if np.max(np.abs(y)) > 0.89: y = y / np.max(np.abs(y)) * 0.89
    f = int(SR * 0.05); y[-f:] *= np.linspace(1, 0, f)
    wav = os.path.join(a.out, f'Etone_{a.style}_{a.tag}.wav'); wr(wav, y); sh(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', wav, '-b:a', '128k', wav[:-4] + '.mp3'])
    log.update({'output_wav': os.path.basename(wav), 'output_sha256': hashlib.sha256(open(wav, 'rb').read()).hexdigest(), 'seconds': round(len(y) / SR, 3),
                'elapsed_s': round(time.time() - t0, 1), 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t0)), 'host': platform.platform()})
    json.dump(log, open(wav[:-4] + '.log.json', 'w'), ensure_ascii=False, indent=1); print('DONE', log['seconds'], log['elapsed_s'])
if __name__ == '__main__': main()
