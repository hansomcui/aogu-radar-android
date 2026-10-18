form manip
  sentence infile
  sentence outfile
  real semitones 0
  real range 1
  real rise 0
endform
s0 = Read from file: infile$
s = Resample: 48000, 50
dur = Get total duration
m = To Manipulation: 0.01, 75, 600
pt = Extract pitch tier
med = Get mean (curve): 0, 0
if med = undefined
  med = 250
endif
Formula: "med * (self/med)^range * 2^(semitones/12)"
if rise <> 0
  t0 = dur * 0.75
  Formula: "if x > t0 then self * 2^(rise/12 * (x - t0)/(dur - t0)) else self fi"
endif
selectObject: m, pt
Replace pitch tier
selectObject: m
r = Get resynthesis (overlap-add)
r2 = Resample: 24000, 50
Save as WAV file: outfile$
