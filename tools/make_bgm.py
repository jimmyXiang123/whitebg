"""生成 20 秒极简科技风配乐样音（100% 原创，CC0 可商用）。

编曲：120 BPM / 4-4 拍 / 每 4 秒换一次和弦（与切镜对齐）
Am9 -> Fmaj7 -> Cmaj7 -> G6 -> Am9
配器：暖 pad + 正弦 sub + 稀疏马林巴 pluck + 极轻 air
"""
import wave
from pathlib import Path

import numpy as np

SR = 44100
DUR = 20.0
N = int(SR * DUR)
t = np.arange(N) / SR


def midi_f(n):
    return 440.0 * 2 ** ((n - 69) / 12)


# 每个和弦占 4 秒
CHORDS = [
    [57, 60, 64, 67, 71],   # Am9
    [53, 57, 60, 64],       # Fmaj7
    [48, 55, 59, 64],       # Cmaj7
    [43, 50, 55, 59],       # G6
    [45, 57, 60, 64, 67],   # Am9
]
SEG = 4.0


def env_ad(n, attack, release, i0, i1):
    """单段 AD 包络（样本索引）。"""
    idx = np.arange(i0, i1)
    local = (idx - i0) / SR
    total = (i1 - i0) / SR
    a = np.clip(local / max(attack, 1e-6), 0, 1)
    r = np.clip((total - local) / max(release, 1e-6), 0, 1)
    return np.minimum(a, r)


def pad():
    out = np.zeros(N)
    for ci, notes in enumerate(CHORDS):
        s, e = int(ci * SEG * SR), int(min((ci + 1) * SEG, DUR) * SR)
        if e <= s:
            continue
        e2 = min(e + int(0.9 * SR), N)
        env = env_ad(N, 0.8, 1.2, s, e2)
        seg = np.zeros(e2 - s)
        for n in notes:
            f0 = midi_f(n)
            for det in (-0.0015, 0.0, 0.0015):      # 轻微失谐，让 pad 有宽度
                ph = 2 * np.pi * f0 * (1 + det) * np.arange(e2 - s) / SR
                seg += 0.55 * np.sin(ph) + 0.18 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)
        seg /= len(notes) * 3
        out[s:e2] += seg * env * 0.34
    return out


def sub():
    out = np.zeros(N)
    for ci, notes in enumerate(CHORDS):
        s, e = int(ci * SEG * SR), int(min((ci + 1) * SEG, DUR) * SR)
        if e <= s:
            continue
        f0 = midi_f(min(notes) - 12)
        ph = 2 * np.pi * f0 * np.arange(e - s) / SR
        env = env_ad(N, 0.35, 0.9, s, e)
        out[s:e] += np.sin(ph) * env * 0.16
    return out


def pluck():
    out = np.zeros(N)
    step = 1.0                                   # 每拍 0.5s，取 2、4 拍 -> 1.0s 一次
    k = 0.5
    i = 0
    while k < DUR - 0.2:
        notes = CHORDS[min(int(k // SEG), len(CHORDS) - 1)]
        n = notes[i % len(notes)] + 12
        f0 = midi_f(n)
        dur = 0.9
        m = int(dur * SR)
        s = int(k * SR)
        m = min(m, N - s)
        tt = np.arange(m) / SR
        env = np.exp(-tt * 7.0)
        w = np.sin(2 * np.pi * f0 * tt) + 0.25 * np.sin(2 * np.pi * 3 * f0 * tt)
        out[s:s + m] += w * env * 0.075
        k += step
        i += 1
    return out


def air():
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, N)
    # 简单一阶低通，去掉刺耳高频
    b = 0.02
    y = np.zeros(N)
    acc = 0.0
    for i in range(N):                          # 20 秒 * 44.1k 循环，可接受
        acc += b * (noise[i] - acc)
        y[i] = acc
    lfo = 0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t)
    return y * lfo * 0.9


def reverb(x, decay=1.1, mix=0.22):
    rng = np.random.default_rng(3)
    ir_n = int(decay * SR)
    ir = rng.normal(0, 1, ir_n) * np.exp(-np.arange(ir_n) / (0.32 * SR))
    ir[: int(0.02 * SR)] *= np.linspace(0, 1, int(0.02 * SR))   # 淡入，避免爆音
    ir /= np.abs(ir).sum() / 6
    n = 1 << int(np.ceil(np.log2(len(x) + ir_n)))
    wet = np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)[: len(x)]
    return x * (1 - mix) + wet * mix


def main():
    mix = pad() + sub() + pluck() + air() * 0.05
    mix = reverb(mix)
    # 首尾淡入淡出
    fi, fo = int(0.4 * SR), int(1.4 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo)
    mix = np.tanh(mix * 1.2) * 0.86            # 软限幅
    mix /= np.abs(mix).max() + 1e-9
    mix *= 0.72

    # 轻微左右展开：pad 稍宽，低频保持居中
    left = mix * 0.99 + np.roll(mix, 90) * 0.06
    right = mix * 0.99 + np.roll(mix, -90) * 0.06
    stereo = np.stack([left, right], axis=1)
    stereo /= np.abs(stereo).max() + 1e-9
    stereo *= 0.326          # 目标 -18 LUFS（纯配乐无人声）

    pcm = (stereo * 32767).astype("<i2")
    out_dir = Path(__file__).resolve().parents[1] / "docs" / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "bgm.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("写出", wav_path, wav_path.stat().st_size // 1024, "KB")

    # 转成 192k MP3（仓库里只留 mp3，wav 已在 .gitignore）
    try:
        import subprocess

        import imageio_ffmpeg

        ff = imageio_ffmpeg.get_ffmpeg_exe()
        mp3_path = out_dir / "bgm.mp3"
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(wav_path), "-c:a", "libmp3lame",
                        "-b:a", "192k", str(mp3_path)], check=True)
        print("写出", mp3_path, mp3_path.stat().st_size // 1024, "KB")
    except Exception as exc:  # noqa: BLE001
        print("未生成 mp3（缺 imageio-ffmpeg 或 ffmpeg）：", exc)


main()
