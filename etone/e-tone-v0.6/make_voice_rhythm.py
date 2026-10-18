#!/usr/bin/env python3
"""E-tone v0.6：人声节奏（清云原创）。
在 v0.5 已选中的整句音频上做两件「真人说话」的事：
1) 句读前拖长：每个停顿前、句末的最后约 0.2 s 只拉长时长（×factor），不改音高；
2) 停顿延长与分层：句内停顿按比例延长并带随机抖动；句间停顿按语义分层（转折/新话题前更长）。
另：柔度再加 20%（高频衰减与低通更深）。不重新合成，音色与 v0.5 相同。
"""
import json, os, re, sys, hashlib, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
from make_voice_zv import sh, rd, wr, SR, CFG
def segments(x, thr_rel=30, min_sil=0.05, keep=None):
    n = int(SR * 0.01); m = len(x) // n
    db = 20 * np.log10(np.sqrt(np.mean(x[:m * n].reshape(m, n) ** 2, 1)) + 1e-9)
    sil = db < db.max() - thr_rel
    # 内部静音段 [start,end) in frames
    out = []; i = 0
    while i < m:
        if sil[i]:
            j = i
            while j < m and sil[j]: j += 1
            if i > 0 and j < m and (j - i) * 0.01 >= min_sil: out.append((i, j))
            i = j
        else: i += 1
    if keep is not None:
        out = sorted(sorted(out, key=lambda ab: ab[1] - ab[0], reverse=True)[:keep])
    return out, m
def main():
    st = json.load(open(os.path.join(HERE, 'styles_rhythm.json')))['E_tw6']
    src = json.load(open(os.path.join(HERE, '..', st['source_log'])))
    wdir = os.path.join(HERE, '..', st['source_work']); out = os.path.join(HERE, '..', 'out_rh'); os.makedirs(out, exist_ok=True)
    rng = np.random.default_rng(st['seed']); t0 = time.time()
    pieces = [np.zeros(int(SR * 0.3), np.float32)]; log = {'style': 'E_tw6', 'params': st, 'sentences': []}
    sents = src['sentences']
    for k, s in enumerate(sents):
        f = os.path.join(wdir, f"{s['i']:02d}_c{s['chosen']}.wav.trim.wav")
        x = rd(f); npunct = len(re.findall(r'[，；、]', s['text'])); sil, m = segments(x, keep=npunct)
        ends = [a * 0.01 for a, b in sil] + [len(x) / SR - 0.03]
        tmp = os.path.join(out, f'_s{k}.wav')
        sh([CFG['praat'], '--run', os.path.join(HERE, 'stretch.praat'), f, tmp, ' '.join(f'{e:.3f}' for e in ends), str(st['final_factor']), str(st['final_span'])])
        y = rd(tmp); sil2, m2 = segments(y, keep=npunct)
        # 句内停顿延长
        parts = []; last = 0; n = int(SR * 0.01); ext_log = []
        for a, b in sil2:
            parts.append(y[last * n: b * n])
            ext = (b - a) * 0.01 * (st['inner_pause_factor'] - 1) * (1 + rng.uniform(-0.2, 0.2)) + st['inner_pause_add_s']
            parts.append(np.zeros(int(SR * ext), np.float32)); last = b; ext_log.append(round(ext, 3))
        parts.append(y[last * n:]); y = np.concatenate(parts)
        act = np.abs(y) > 0.01; y = y / (np.sqrt(np.mean(y[act] ** 2)) + 1e-9) * 0.1 * (1 + rng.uniform(-0.06, 0.06))
        pieces.append(y)
        nxt = sents[k + 1]['text'] if k + 1 < len(sents) else ''
        base = st['pause_ms'].get(s['text'][-1], 650)
        if any(nxt.startswith(w) for w in st['topic_shift_starts']): base += st['topic_shift_add_ms']
        if k == len(sents) - 1: base = 400
        pause = int(base * (1 + rng.uniform(-0.15, 0.15)))
        pieces.append(np.zeros(int(SR * pause / 1000), np.float32))
        log['sentences'].append({'text': s['text'], 'source': os.path.basename(f), 'stretch_points_s': [round(e, 2) for e in ends], 'inner_pause_ext_s': ext_log, 'pause_after_ms': pause, 'seconds': round(len(y) / SR, 3)})
        print(k, s['text'], 'ends', len(ends), 'ext', ext_log, 'pause', pause, flush=True)
    y = np.concatenate(pieces); tmp = os.path.join(out, '_mix.wav'); wr(tmp, y / np.max(np.abs(y)) * 0.7)
    eq = os.path.join(out, '_eq.wav')
    af = f"treble=g={st['treble_db']}:f=3500:t=s:w=0.7,lowpass=f={st['lowpass_hz']},aecho=1.0:1.0:{st['room_delays_ms']}:{st['room_decays']}"
    sh(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', tmp, '-af', af, '-ar', str(SR), '-ac', '1', '-c:a', 'pcm_s16le', eq])
    y = rd(eq); act = np.abs(y) > 0.01; y = y / (np.sqrt(np.mean(y[act] ** 2)) + 1e-9) * st['ref_rms'] * st['gain']
    if np.max(np.abs(y)) > 0.89: y = y / np.max(np.abs(y)) * 0.89
    fd = int(SR * 0.08); y[-fd:] *= np.linspace(1, 0, fd)
    wav = os.path.join(out, 'Etone_E_tw6_run1.wav'); wr(wav, y); sh(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', wav, '-b:a', '128k', wav[:-4] + '.mp3'])
    log.update({'output_sha256': hashlib.sha256(open(wav, 'rb').read()).hexdigest(), 'seconds': round(len(y) / SR, 3), 'elapsed_s': round(time.time() - t0, 1)})
    json.dump(log, open(wav[:-4] + '.log.json', 'w'), ensure_ascii=False, indent=1); print('DONE', log['seconds'])
if __name__ == '__main__': main()
