form stretch
  sentence infile
  sentence outfile
  sentence ends
  real factor 1.3
  real span 0.2
endform
s0 = Read from file: infile$
s = Resample: 48000, 50
dur = Get total duration
m = To Manipulation: 0.01, 75, 600
dt = Create DurationTier: "dt", 0, dur
Add point: 0, 1
n = 0
rest$ = ends$
while rest$ <> ""
  sp = index(rest$, " ")
  if sp = 0
    tok$ = rest$
    rest$ = ""
  else
    tok$ = left$(rest$, sp - 1)
    rest$ = mid$(rest$, sp + 1, 10000)
  endif
  te = number(tok$)
  ts = te - span
  if ts < 0.02
    ts = 0.02
  endif
  selectObject: dt
  Add point: ts - 0.015, 1
  Add point: ts, factor
  Add point: te, factor
  Add point: te + 0.015, 1
endwhile
selectObject: m, dt
Replace duration tier
selectObject: m
r = Get resynthesis (overlap-add)
r2 = Resample: 24000, 50
Save as WAV file: outfile$
