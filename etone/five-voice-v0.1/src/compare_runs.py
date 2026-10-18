#!/usr/bin/env python3
"""比较同一档两次生成：时长差、F0 中位数差（半音）、逐句时长差、MFCC 余弦相似度。"""
import json, sys, os, subprocess, wave, numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); CFG=json.load(open(os.path.join(HERE,'paths.json')))
def f0med(p):
    s=f'''s = Read from file: "{p}"\np = To Pitch: 0, 75, 600\nm = Get quantile: 0, 0, 0.5, "Hertz"\nwriteInfoLine: m\n'''
    open('/tmp/_f0.praat','w').write(s); return float(subprocess.run([CFG['praat'],'--run','/tmp/_f0.praat'],capture_output=True,text=True).stdout.strip())
def spec(p):
    w=wave.open(p); x=np.frombuffer(w.readframes(w.getnframes()),np.int16).astype(float)/32768
    n=1024; h=256; fr=np.lib.stride_tricks.sliding_window_view(x,n)[::h]*np.hanning(n)
    S=np.log(np.abs(np.fft.rfft(fr))[:, :400].mean(0)+1e-9); return S
out=os.path.join(HERE,'..','out'); res={}
for s in 'ABCDE':
    a=os.path.join(out,f'Etone_{s}_run1.wav'); b=os.path.join(out,f'Etone_{s}_run2.wav')
    if not (os.path.exists(a) and os.path.exists(b)): continue
    la=json.load(open(a[:-4]+'.log.json')); lb=json.load(open(b[:-4]+'.log.json'))
    fa,fb=f0med(a),f0med(b); sa,sb=spec(a),spec(b)
    cos=float(np.dot(sa-sa.mean(),sb-sb.mean())/np.linalg.norm(sa-sa.mean())/np.linalg.norm(sb-sb.mean()))
    sd=[abs(x['seconds']-y['seconds']) for x,y in zip(la['sentences'],lb['sentences'])]
    res[s]={'dur_run1':la['seconds'],'dur_run2':lb['seconds'],'dur_diff_s':round(abs(la['seconds']-lb['seconds']),3),
            'f0_median_hz':[round(fa,1),round(fb,1)],'f0_diff_semitones':round(abs(12*np.log2(fa/fb)),3),
            'max_sentence_dur_diff_s':round(max(sd),3),'avg_spectrum_corr':round(cos,4),
            'bit_identical':la['output_sha256']==lb['output_sha256']}
print(json.dumps(res,ensure_ascii=False,indent=1)); json.dump(res,open(os.path.join(out,'repeatability.json'),'w'),ensure_ascii=False,indent=1)
