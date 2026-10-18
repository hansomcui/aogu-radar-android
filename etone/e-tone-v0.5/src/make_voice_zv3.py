#!/usr/bin/env python3
"""E-tone v0.5：加强人声感（清云原创）。
1) 提示音换成 v0.4 里质检最稳的 ZipVoice 输出（比 Kokoro 原声更自然），一轮「自举」；
2) 按整句合成（保留句内连贯语调），每句多候选自动质检；
3) 停顿加入 ±15% 自然抖动（固定种子），各句响度对齐但保留原有轻重；
4) 加极轻的小房间早期反射，去掉「干录音棚/机器」感；柔化 EQ 同 v0.4。
"""
import argparse, hashlib, json, os, re, time, platform
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
from make_voice_zv import sh, rd, wr, zipvoice, trim, SR, CFG
from make_voice_zv2 import f0_track, score
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('style'); ap.add_argument('--tag', default='run1'); ap.add_argument('--out', default=os.path.join(HERE, '..', 'out_zv3'))
    a = ap.parse_args(); st = json.load(open(os.path.join(HERE, 'styles_zv3.json')))[a.style]
    work = os.path.join(a.out, f'work_{a.style}_{a.tag}'); os.makedirs(work, exist_ok=True); t0 = time.time()
    ref = os.path.join(a.out, f'prompt_{a.style}.wav')
    if not os.path.exists(ref):
        parts = []
        for f in st['prompt_files']: parts += [trim(rd(os.path.join(HERE, '..', f))), np.zeros(int(SR * 0.32), np.float32)]
        y = np.concatenate(parts)[:-int(SR * 0.32)]; wr(ref, y / np.max(np.abs(y)) * 0.8)
    ref_text = st['prompt_text']; ref_med = np.nanmedian(f0_track(ref))
    text = open(os.path.join(HERE, st['text_file']), encoding='utf-8').read().strip()
    sents = re.findall(r'[^。？！；]+[。？！；]', text)
    rng = np.random.default_rng(st.get('seed', 20261018))
    log = {'style': a.style, 'params': st, 'prompt_sha256': hashlib.sha256(open(ref, 'rb').read()).hexdigest(), 'prompt_f0_median': round(float(ref_med), 1), 'sentences': []}
    pieces = [np.zeros(int(SR * 0.3), np.float32)]
    for i, s in enumerate(sents):
        nchar = len(re.findall(r'[一-鿿]', s)); best = None; cands = []
        for k in range(st['candidates']):
            o = os.path.join(work, f'{i:02d}_c{k}.wav'); zipvoice(s, ref, ref_text, st['speed'], st['num_steps'], o)
            x = trim(rd(o)); wr(o + '.trim.wav', x); f0 = f0_track(o + '.trim.wav')
            sc, info = score(x, f0, ref_med, nchar); info['score'] = round(float(sc), 3); cands.append(info)
            if best is None or sc < best[0]: best = (sc, x, k)
        x = best[1]; act = np.abs(x) > 0.01; x = x / (np.sqrt(np.mean(x[act] ** 2)) + 1e-9) * 0.1
        pieces.append(x)
        base = st['pause_ms'].get(s[-1], 600) if i < len(sents) - 1 else 350
        pause = int(base * (1 + rng.uniform(-0.15, 0.15)))
        pieces.append(np.zeros(int(SR * pause / 1000), np.float32))
        log['sentences'].append({'i': i, 'text': s, 'chosen': best[2], 'candidates': cands, 'seconds': round(len(x) / SR, 3), 'pause_ms': pause})
        print(i, s, 'chosen', best[2], cands[best[2]], flush=True)
    y = np.concatenate(pieces); tmp = os.path.join(work, 'mix.wav'); wr(tmp, y / (np.max(np.abs(y)) + 1e-9) * 0.7)
    eq = os.path.join(work, 'eq.wav')
    af = f"treble=g={st['treble_db']}:f=4000:t=s:w=0.7,lowpass=f={st['lowpass_hz']},aecho=1.0:1.0:{st['room_delays_ms']}:{st['room_decays']}"
    sh(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', tmp, '-af', af, '-ar', str(SR), '-ac', '1', '-c:a', 'pcm_s16le', eq])
    y = rd(eq); act = np.abs(y) > 0.01; y = y / (np.sqrt(np.mean(y[act] ** 2)) + 1e-9) * st['ref_rms'] * st['gain']
    if np.max(np.abs(y)) > 0.89: y = y / np.max(np.abs(y)) * 0.89
    f = int(SR * 0.08); y[-f:] *= np.linspace(1, 0, f)
    wav = os.path.join(a.out, f'Etone_{a.style}_{a.tag}.wav'); wr(wav, y); sh(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', wav, '-b:a', '128k', wav[:-4] + '.mp3'])
    log.update({'output_wav': os.path.basename(wav), 'output_sha256': hashlib.sha256(open(wav, 'rb').read()).hexdigest(), 'seconds': round(len(y) / SR, 3),
                'elapsed_s': round(time.time() - t0, 1), 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t0)), 'host': platform.platform()})
    json.dump(log, open(wav[:-4] + '.log.json', 'w'), ensure_ascii=False, indent=1); print('DONE', log['seconds'], log['elapsed_s'])
if __name__ == '__main__': main()
