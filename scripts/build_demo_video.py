#!/usr/bin/env python3
"""Build a 60-second captioned screenshot tour, not a real-time recording.

Run with a Python containing Pillow and ffmpeg/ffprobe on PATH:
    python3 scripts/build_demo_video.py

No application server, credentials, live API or external media is used.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media" / "v1.1.0"
OUTPUT_NAME = "AKDesk-60秒导览.mp4"
WIDTH, HEIGHT = 1280, 900
BACKGROUND = "#091321"
MINT = "#8ae7d1"
WHITE = "#edf5fa"


@dataclass(frozen=True)
class Scene:
    duration: int
    image: str
    title: str
    caption: str
    crop: tuple[int, int, int, int] | None = None
    cover: bool = False


SCENES = (
    Scene(7, "01-overview.png", "AKDesk Fixed · 60 秒界面导览", "固定合成示例，无需安装、登录、后台服务或 API Key。", cover=True),
    Scene(11, "02-market-changes.png", "01 观察变化", "把资金、曲线和国债期货放在一起，先发现需要核验的差异。"),
    Scene(10, "03-evidence.png", "展开数据依据", "检查数值、前值与 BP 换算；演示不会生成可信交易信号。"),
    Scene(12, "04-curves.png", "02 核验曲线", "对照期限结构与前值：10Y 下行 2 BP，10Y–1Y 利差为 40 BP。"),
    Scene(8, "05-brief.png", "03 形成一页简报", "资金、曲线与期货汇成研究底稿，保留示例标识和观测区间。", crop=(90, 380, 1350, 1280)),
    Scene(7, "05-brief.png", "带走可以继续编辑的材料", "来源与时点保留在导出中；可补临时备注、下载 Markdown 或打印。", crop=(90, 900, 1350, 1605)),
    Scene(5, "01-overview.png", "从在线体验开始", "喜欢这个流程？下载 macOS 本地版连接真实数据，或到 GitHub 反馈。", cover=True),
)


def font_path() -> Path:
    candidates = [
        os.getenv("AKDESK_VIDEO_FONT", ""),
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise RuntimeError("没有找到中文字体；请设置 AKDESK_VIDEO_FONT 为可用字体路径")


def load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def centered(draw: ImageDraw.ImageDraw, y: int, text: str, font: ImageFont.FreeTypeFont, fill: str) -> None:
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((WIDTH - (right - left)) / 2, y), text, font=font, fill=fill)


def render_scene(scene: Scene, output: Path, font: Path, index: int) -> None:
    image = Image.open(MEDIA / scene.image).convert("RGB")
    if scene.crop:
        image = image.crop(scene.crop)
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    image.thumbnail((1200, 740), Image.Resampling.LANCZOS)
    x, y = (WIDTH - image.width) // 2, 48 + (740 - image.height) // 2
    canvas.paste(image, (x, y))
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 13), "真实界面截图导览 · 固定合成示例 · 非实时录屏", font=load_font(font, 17), fill="#a4bac8")
    draw.text((1130, 13), f"{index + 1:02d} / {len(SCENES):02d}", font=load_font(font, 17), fill="#8ba5b7")
    draw.line((40, 792, WIDTH - 40, 792), fill="#315062", width=1)
    draw.text((40, 811), scene.title, font=load_font(font, 25), fill=MINT)
    draw.text((40, 853), scene.caption, font=load_font(font, 22), fill=WHITE)
    if scene.cover:
        # A visibly editorial title overlay keeps this distinct from a recording.
        shade = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        overlay = ImageDraw.Draw(shade)
        overlay.rounded_rectangle((125, 225, 1155, 570), radius=22, fill=(7, 18, 30, 238), outline=(67, 121, 125, 255), width=2)
        canvas = Image.alpha_composite(canvas.convert("RGBA"), shade).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        centered(draw, 270, "AKDesk Fixed", load_font(font, 58), WHITE)
        centered(draw, 362, "从市场变化到一页研究底稿" if index == 0 else "在线体验 → 下载本地版 → 分享反馈", load_font(font, 34), MINT)
        centered(draw, 442, "固定合成示例 · 无后台 · 无需 API Key", load_font(font, 24), "#d2c49b")
        centered(draw, 492, "本视频由真实产品截图编排，不是实时行情或实时录屏", load_font(font, 19), "#95acbd")
    canvas.save(output, optimize=True)


def timecode(seconds: int) -> str:
    return f"00:{seconds // 60:02d}:{seconds % 60:02d}.000"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=MEDIA / OUTPUT_NAME)
    args = parser.parse_args()
    if sum(scene.duration for scene in SCENES) != 60:
        raise RuntimeError("导览必须正好 60 秒")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("需要安装 ffmpeg 和 ffprobe")
    font = font_path()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    captions = ["WEBVTT", ""]
    elapsed = 0
    with tempfile.TemporaryDirectory(prefix="akdesk-demo-video-") as temp:
        directory = Path(temp)
        manifest: list[str] = []
        for index, scene in enumerate(SCENES):
            frame = directory / f"scene-{index:02d}.png"
            render_scene(scene, frame, font, index)
            if index == 0:
                shutil.copyfile(frame, MEDIA / "video-poster.png")
            manifest.extend([f"file '{frame.as_posix()}'", f"duration {scene.duration}"])
            captions.extend([str(index + 1), f"{timecode(elapsed)} --> {timecode(elapsed + scene.duration)}", scene.title, scene.caption, ""])
            elapsed += scene.duration
        manifest.append(f"file '{frame.as_posix()}'")
        input_file = directory / "frames.ffconcat"
        input_file.write_text("\n".join(manifest) + "\n", encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(input_file),
            "-vf", "fps=12,format=yuv420p", "-t", "60", "-an",
            "-c:v", "libx264", "-preset", "slow", "-crf", "25",
            "-movflags", "+faststart", str(args.output),
        ], check=True)
    (MEDIA / "demo-tour.zh-CN.vtt").write_text("\n".join(captions), encoding="utf-8")
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height,pix_fmt",
        "-of", "json", str(args.output),
    ], check=True, capture_output=True, text=True)
    report = json.loads(result.stdout)
    if abs(float(report["format"]["duration"]) - 60) > 0.1:
        raise RuntimeError("视频时长验证失败")
    if args.output.stat().st_size > 5 * 1024 * 1024:
        raise RuntimeError("视频超过 5 MiB；请检查画面和编码参数")
    report.update({"output": str(args.output), "source": "real UI screenshots", "sample": "fixed synthetic data", "font": str(font)})
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
