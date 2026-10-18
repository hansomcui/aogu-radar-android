#!/usr/bin/env python3
"""E-tone 五档候选音色生成（清云原创脚本）。
用法: python3 make_voice.py STYLE [--max-seconds N] [--out DIR] [--tag TAG]
依赖: sherpa-onnx v1.13.8 (offline-tts CLI)、Kokoro-82M v1.0 (sherpa-onnx 打包, Apache-2.0)、Praat 6.4.27、ffmpeg、numpy。
"""
import argparse, hashlib, json, os, re, subprocess, sys, wave, time, platform
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, 'paths.json')))
SR = 24000

def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {cmd}\n{r.stderr[-2000:]}")
    return r

def read_wav(p):
    w = wave.open(p); sr = w.getframerate(); x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if w.getnchannels() == 2: x = x.reshape(-1, 2).mean(1)
    assert sr == SR, (p, sr)
    return x

def write_wav(p, x):
    y = np.clip(x, -1, 1); y = (y * 32767).astype(np.int16)
    w = wave.open(p, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(y.tobytes()); w.close()

def tts(text, sid, ls, out):
    m = CFG['kokoro_dir']; b = CFG['sherpa_dir']
    env = dict(os.environ, LD_LIBRARY_PATH=os.path.join(b, 'lib'))
    sh([os.path.join(b, 'bin', 'sherpa-onnx-offline-tts'), f'--kokoro-model={m}/model.onnx', f'--kokoro-voices={m}/voices.bin',
        f'--kokoro-tokens={m}/tokens.txt', f'--kokoro-data-dir={m}/espeak-ng-data', f'--kokoro-lexicon={m}/lexicon-us-en.txt,{m}/lexicon-zh.txt',
        '--num-threads=1', f'--sid={sid}', f'--kokoro-length-scale={ls}', f'--output-filename={out}', text], env=env)

def trim(x, thr=0.003):
    idx = np.where(np.abs(x) > thr)[0]
    return x[max(0, idx[0] - 240): idx[-1] + 480] if len(idx) else x

def breath(x, db, seed):
    if db <= -59: return x
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(len(x)).astype(np.float32)
    # 高通（一阶差分两次）模拟气流噪声
    n = np.diff(np.diff(n, prepend=0), prepend=0)
    env = np.convolve(np.abs(x), np.ones(480) / 480, mode='same')
    n = n / (np.sqrt(np.mean(n ** 2)) + 1e-9) * env
    return x + n * (10 ** (db / 20)) * 4

def tilt(x, db):
    if abs(db) < 0.01: return x
    hp = np.diff(x, prepend=0)  # 一阶高频强调
    return x + hp * (10 ** (abs(db) / 20) - 1) * (1 if db > 0 else -1) * 0.5

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('style'); ap.add_argument('--max-seconds', type=float, default=0)
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'out')); ap.add_argument('--tag', default='run1')
    a = ap.parse_args()
    st = json.load(open(os.path.join(HERE, 'styles.json')))[a.style]
    text = open(os.path.join(HERE, 'text_zh.txt'), encoding='utf-8').read().strip()
    sents = [s for s in re.findall(r'[^。？！；]+[。？！；]', text)]
    work = os.path.join(a.out, f'work_{a.style}_{a.tag}'); os.makedirs(work, exist_ok=True)
    t0 = time.time(); pieces = []; log = {'style': a.style, 'params': st, 'sentences': []}
    for i, s in enumerate(sents):
        raw = os.path.join(work, f'{i:02d}_raw.wav'); man = os.path.join(work, f'{i:02d}_man.wav')
        tts(s, st['sid'], st['length_scale'], raw)
        rise = st['final_rise_st'] if s.endswith(('？', '。')) else 0.0
        if s.endswith('？'): rise = max(rise, 1.0) if st['final_rise_st'] > 0 else rise
        sh([CFG['praat'], '--run', os.path.join(HERE, 'manip.praat'), raw, man, str(st['semitones']), str(st['range']), str(rise)])
        x = trim(read_wav(man)); pieces.append(x)
        pause = st['sent_pause_ms'] if s.endswith(('。', '？', '！')) else int(st['sent_pause_ms'] * 0.7)
        pieces.append(np.zeros(int(SR * pause / 1000), np.float32))
        log['sentences'].append({'i': i, 'text': s, 'raw_sha256': hashlib.sha256(open(raw, 'rb').read()).hexdigest(), 'seconds': round(len(x) / SR, 3), 'pause_ms': pause})
        if a.max_seconds and sum(len(p) for p in pieces) / SR >= a.max_seconds: break
    y = np.concatenate([np.zeros(int(SR * 0.25), np.float32)] + pieces)
    y = tilt(y, st['tilt_db']); y = breath(y, st['breath_db'], seed=20261018)
    if a.max_seconds: y = y[:int(SR * a.max_seconds)]
    fade = int(SR * 0.05); y[-fade:] *= np.linspace(1, 0, fade)
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.89  # 峰值 -1 dBFS，无爆音
    os.makedirs(a.out, exist_ok=True)
    suffix = f"_{int(a.max_seconds)}s" if a.max_seconds else ""
    wav = os.path.join(a.out, f'Etone_{a.style}{suffix}_{a.tag}.wav'); write_wav(wav, y)
    mp3 = wav[:-4] + '.mp3'; sh(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', wav, '-b:a', '128k', mp3])
    log.update({'output_wav': os.path.basename(wav), 'output_sha256': hashlib.sha256(open(wav, 'rb').read()).hexdigest(),
                'seconds': round(len(y) / SR, 3), 'peak_dbfs': round(float(20 * np.log10(np.max(np.abs(y)))), 2), 'elapsed_s': round(time.time() - t0, 1),
                'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t0)), 'host': platform.platform()})
    json.dump(log, open(wav[:-4] + '.log.json', 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: log[k] for k in ['style', 'output_wav', 'seconds', 'peak_dbfs', 'elapsed_s', 'output_sha256']}, ensure_ascii=False))

if __name__ == '__main__': main()
