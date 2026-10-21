"""Build a synthetic long Chinese text (no personal data) and split it exactly like
VoiceForge v0.3.5.8 splitText(text, maxChars) so chunk sizes match the phone run."""
import random, re, sys, json

random.seed(20261021)
subj = ["小镇的清晨", "河边的老人", "图书馆里的学生", "厨房里的妈妈", "放学的孩子", "远处的山", "城市的夜晚", "海边的渔船", "窗外的雨", "公园的长椅"]
verb = ["慢慢醒来", "安静地等待", "认真地读书", "忙着准备早饭", "一路说说笑笑", "披上了一层薄雾", "亮起了无数盏灯", "缓缓驶回港口", "轻轻敲打着玻璃", "留下了落叶的影子"]
tail = ["，空气里有淡淡的花香", "，时间好像也变慢了", "，让人想起很久以前的事情", "，每个人都有自己的故事", "，远处传来几声鸟叫", "，阳光从云缝里照下来", "，街上的行人渐渐多了", "，风里带着一点海水的味道"]
end = ["。", "。", "。", "！", "？", "；"]

def sentence():
    s = random.choice(subj) + random.choice(verb) + random.choice(tail)
    if random.random() < 0.5:
        s += "，" + random.choice(subj) + random.choice(verb)
    return s + random.choice(end)

paras = []
total = 0
while total < 3150:
    p = "".join(sentence() for _ in range(random.randint(3, 7)))
    paras.append(p); total += len(p)
text = "\n\n".join(paras)

# ---- port of MainActivity.splitText / splitIntoLogicalSentences / splitLongSentence ----
ENDS = set("。！？!?；;"); CLOSE = set("”’\"'》）)】]")
def logical(par):
    out, buf, i = [], "", 0
    while i < len(par):
        c = par[i]; buf += c
        if c in ENDS:
            j = i + 1
            while j < len(par) and par[j] in CLOSE: buf += par[j]; j += 1
            if buf.strip(): out.append(buf.strip())
            buf = ""; i = j; continue
        i += 1
    if buf.strip(): out.append(buf.strip())
    return out
def split_long(s, tmin, tmax):
    out, rem = [], s.strip()
    while len(rem) > tmax:
        b, e, cut = min(tmin, len(rem) - 1), min(tmax, len(rem) - 1), -1
        for i in range(e, b - 1, -1):
            if rem[i] in "：:—": cut = i + 1; break
        if cut <= 0:
            for i in range(e, b - 1, -1):
                if rem[i] in "，,、": cut = i + 1; break
        if cut <= 0: cut = tmax
        out.append(rem[:cut].strip()); rem = rem[cut:].strip()
    if rem: out.append(rem)
    return out
def split_text(text, max_chars):
    norm = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
    tmin, tmax = 180, min(max(240, max_chars), 340)
    pars = [p.strip() for p in re.split(r"\n\s*\n+", norm) if p.strip()]
    out, pack = [], [""]
    def flush():
        s = pack[0].strip()
        if s: out.append(s)
        pack[0] = ""
    def app(s):
        s = s.strip()
        if not s: return
        if len(s) > tmax:
            if pack[0]: flush()
            out.extend(x.strip() for x in split_long(s, tmin, tmax) if x.strip()); return
        if not pack[0]: pack[0] = s
        elif len(pack[0]) + len(s) <= tmax: pack[0] += s
        else: flush(); pack[0] = s
    for k, p in enumerate(pars):
        for s in logical(p): app(s)
        if len(pack[0]) >= tmin or k == len(pars) - 1: flush()
        elif pack[0]: pack[0] += "\n"
    flush()
    return out

if __name__ == "__main__":
    max_chars = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    open("long_text.txt", "w").write(text)
    chunks = split_text(text, max_chars)
    with open(f"chunks_{max_chars}.txt", "w") as f:
        for c in chunks: f.write(c.replace("\n", " ") + "\n")
    print(len(text), "chars;", len(chunks), "chunks;", [len(c) for c in chunks])
