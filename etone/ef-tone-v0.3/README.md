# E-tone / F-tone v0.3（清云）

主人 2026-10-18 10:00 反馈：①合成痕迹太强，不像真人；②E-tone 定为台湾普通话，在 v0.2 基础上再慢 10%、再柔 20%、再轻 5%。

## 改了什么
- 换引擎：Kokoro 只用来生成一段 6.8 秒的「提示音」（非真人），正文改由 ZipVoice（零样本、自然语流）按提示音的音色朗读。
- 去掉 v0.1/v0.2 里最像机器的两步：Praat 逐句变调（PSOLA）和后加的气声噪声。现在后期只做响度和柔化均衡（高频衰减 + 轻低通）。
- E：语速比 A 慢约 22–25%（v0.2 为 14%）；响度为 A 的 0.80（v0.2 为 0.84）；高频 −6 dB、低通 9 kHz（v0.2 只做了倾斜）。
- F：语速约为 B 的 0.96–1.00；响度 0.94–0.95；高频 −4 dB、低通 10 kHz。

## 实测（run1 / run2）
| | 时长 | 语速比基础档 | 响度比 | F0 中位 |
|---|---|---|---|---|
| E run1 | 43.1 s | 0.75 | 0.80 | 250 Hz |
| E run2 | 41.3 s | 0.78 | 0.81 | 247 Hz |
| F run1 | 35.1 s | 0.96 | 0.94 | — |
| F run2 | 34.0 s | 1.00 | 0.95 | — |

注意：ZipVoice 每次生成有随机性，两次时长相差 1–2 秒（约 3–5%），比 v0.2 的一致性差。固定母版时以选中的那一次 WAV 为准。

## 来源与许可
- 清云原创：make_voice_zv.py、styles_zv.json。
- ZipVoice distill int8 zh-en（k2-fsa，sherpa-onnx 打包，代码 Apache-2.0；训练数据 Emilia 为 CC BY-NC 4.0，商用许可待核实，个人非商用试听可用）；Kokoro-82M v1.0（Apache-2.0）；sherpa-onnx v1.13.8；ffmpeg。
- 提示音 prompt_*.wav 为 Kokoro 合成，非真人录音；未使用任何私人音频。费用 0。

## 已知局限
- 台湾普通话目前只靠用词和语速；提示音本身不是台湾口音，所以腔调仍偏大陆普通话。要更像台湾腔，需要一段许可明确的台湾普通话提示音。
- 未做 ASR 读音核对。

## 复现
python3 src/make_voice_zv.py E_tw3 --tag run1；python3 src/make_voice_zv.py F_xa3 --tag run1（paths.json 指向 sherpa-onnx、Kokoro、ZipVoice 目录）
