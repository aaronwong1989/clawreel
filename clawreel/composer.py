"""阶段3：音视频合成 — FFmpeg 多图转场合成。

流程: HOOK(6s I2V) + BODY(多图+xfade转场) + 混音
转场: fade / slide_left / slide_right / zoom / none
"""
import asyncio
import logging
import math
from pathlib import Path
from typing import Literal

from .config import (
    ASSETS_DIR,
    AUDIO_BIT_RATE,
    AUDIO_SAMPLE_RATE,
    BG_MUSIC_VOLUME,
    FFMPEG_VIDEO_OPTS,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from .api_client import download_file
from .utils import run_ffmpeg, get_media_duration

logger = logging.getLogger(__name__)

TRANSITION_DURATION = 0.8  # 转场持续时间（秒）


async def compose(
    tts_path: Path,
    image_urls: list[str],
    music_path: Path,
    hook_video_path: Path | None = None,
    transition: Literal["fade", "slide_left", "slide_right", "zoom", "none"] = "fade",
    output_path: Path | None = None,
    srt_path: Path | None = None,
) -> tuple[Path, Path | None]:
    """多图转场音视频合成。

    Args:
        tts_path:        TTS 音频文件路径
        image_urls:      图片 OSS URL 或本地路径列表（多图转场）
        music_path:      背景音乐路径
        hook_video_path: 开场 I2V 视频路径（可选，跳过则纯图片合成）
        transition:      转场类型：fade / slide_left / slide_right / zoom / none
        output_path:     输出路径，默认 output/composed.mp4
        srt_path:        SRT 字幕路径（仅透传到返回值，不参与合成）

    Returns:
        (合成视频路径, SRT字幕路径或None) 元组
    """
    if output_path is None:
        output_path = Path("output/composed.mp4")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    tts_duration = get_media_duration(tts_path)
    music_duration = get_media_duration(music_path)
    num_images = len(image_urls)

    logger.info(
        "🎞️ 开始合成视频，TTS=%.1fs，图片=%d张，转场=%s，音乐=%.1fs",
        tts_duration, num_images, transition, music_duration
    )

    # ── Step 1: 收集本地图片路径（本地路径直接用，URL 批量异步下载）───────────
    img_dir = ASSETS_DIR / "body_images"
    img_dir.mkdir(parents=True, exist_ok=True)
    local_paths: list[Path] = []
    urls_to_dl: list[tuple[int, str, Path]] = []

    for i, url_or_path in enumerate(image_urls):
        p = Path(url_or_path)
        if p.exists() and p.is_file():
            local_paths.append(p)
            logger.debug("✅ 使用本地图片 %d/%d: %s", i + 1, num_images, p.name)
        else:
            ext = "jpg"
            img_path = img_dir / f"body_{i:03d}.{ext}"
            if not img_path.exists():
                urls_to_dl.append((i, url_or_path, img_path))

    # 批量异步下载
    if urls_to_dl:
        tasks = [download_file(url, path) for _, url, path in urls_to_dl]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for (i, url, path), res in zip(urls_to_dl, results):
            if isinstance(res, Exception):
                logger.warning("⚠️ 下载失败 %s: %s，跳过该张", url, res)
            else:
                local_paths.append(path)
                logger.debug("✅ 下载图片 %d/%d: %s", i + 1, num_images, path.name)

    if len(local_paths) < 2:
        raise RuntimeError(f"有效图片不足 2 张（当前 {len(local_paths)} 张），无法合成转场视频")

    # ── Step 2: 扩展音乐 ─────────────────────────────────────────────────────
    if music_duration < tts_duration:
        loop_count = math.ceil(tts_duration / music_duration)
        ext_music = ASSETS_DIR / "music_extended.mp3"
        run_ffmpeg([
            "ffmpeg", "-y",
            "-stream_loop", str(loop_count - 1),
            "-i", str(music_path),
            "-t", str(tts_duration),
            "-c", "copy",
            str(ext_music),
        ])
        music_path = ext_music

    # ── Step 3: 生成单张图片视频片段 ─────────────────────────────────────────
    body_dir = ASSETS_DIR / "body_clips"
    body_dir.mkdir(parents=True, exist_ok=True)

    # 每张图分配时长：TTS总时长 / 图片数
    per_image_duration = tts_duration / len(local_paths)

    for i, img_path in enumerate(local_paths):
        clip_path = body_dir / f"clip_{i:03d}.mp4"
        if clip_path.exists():
            continue
        run_ffmpeg([
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(img_path),
            "-t", str(per_image_duration),
            "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
                   f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
            "-r", str(VIDEO_FPS),
            *FFMPEG_VIDEO_OPTS,
            "-an",
            str(clip_path),
        ])
        logger.debug("✅ 生成片段 %d/%d: %s", i + 1, len(local_paths), clip_path.name)

    clip_paths = sorted(body_dir.glob("clip_*.mp4"))
    if len(clip_paths) < 2:
        raise RuntimeError(f"有效片段不足 2 个，无法合成转场")

    # ── Step 4: FFmpeg xfade 转场合成 BODY ────────────────────────────────────
    body_video = ASSETS_DIR / "body_xfade.mp4"

    if transition == "none":
        # 直接 concat（无转场）
        _concat_clips(clip_paths, body_video)
    else:
        _xfade_clips(clip_paths, body_video, transition, per_image_duration)

    # ── Step 5: 合并 HOOK + BODY ─────────────────────────────────────────────
    # 注意：hook 视频可能与 body 分辨率不同（如 MiniMax I2V 输出横屏）。
    # 必须先 scale 到目标分辨率再拼接，否则 concat 失败。
    segments: list[Path] = []
    if hook_video_path and hook_video_path.exists():
        # 缩放 hook 到目标竖屏分辨率（中心裁切）
        scaled_hook = ASSETS_DIR / "_hook_scaled.mp4"
        run_ffmpeg([
            "ffmpeg", "-y",
            "-i", str(hook_video_path),
            "-vf", (
                f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
                f":force_original_aspect_ratio=increase"
                f":force_divisible_by=2"
                f",crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}"
            ),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-an", str(scaled_hook),
        ])
        segments.append(scaled_hook)
    segments.append(body_video)

    if len(segments) > 1:
        video_only = ASSETS_DIR / "video_no_audio.mp4"
        _concat_clips(segments, video_only)
    else:
        video_only = segments[0]

    # ── Step 6: 混音（TTS + 背景音乐）─ 输出最终视频 ─────────────────────────
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(video_only),
        "-i", str(tts_path),
        "-i", str(music_path),
        "-filter_complex",
        f"[2:a]volume={BG_MUSIC_VOLUME}[bg];[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2,"
        f"aresample={AUDIO_SAMPLE_RATE},aformat=sample_fmts=fltp:sample_rates={AUDIO_SAMPLE_RATE}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-b:v", "6M",
        "-c:a", "aac",
        "-b:a", str(AUDIO_BIT_RATE),
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-pix_fmt", "yuv420p",
        "-t", str(tts_duration),
        str(output_path),
    ])

    logger.info("✅ 视频合成完成: %s", output_path)

    # ── Step 7: 清理中间文件 ─────────────────────────────────────────────────
    for d in [body_dir, img_dir]:
        for f in d.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            d.rmdir()
        except OSError:
            pass

    for pattern in [
        "body_xfade.mp4", "video_no_audio.mp4",
        "music_extended.mp3", "_hook_scaled.mp4",
    ]:
        for f in ASSETS_DIR.glob(pattern):
            try:
                f.unlink()
            except OSError:
                pass

    return output_path, srt_path


def _xfade_clips(
    clip_paths: list[Path],
    output: Path,
    transition: Literal["fade", "slide_left", "slide_right", "zoom", "none"],
    per_image_duration: float,
) -> None:
    """多 clip 转场合成。

    实现策略：
    - fade:   每个 clip 首尾加 fade，用 concat 拼接（最轻量）
    - slide/zoom: overlay 链式叠加，支持 t 变量实现滑动/缩放动画
    """
    n = len(clip_paths)
    xfade_dur = min(TRANSITION_DURATION, per_image_duration * 0.3)

    if transition == "fade":
        _xfade_fade(clip_paths, output, xfade_dur, per_image_duration)
        return

    # slide_left / slide_right / zoom: overlay 链
    _xfade_overlay(clip_paths, output, transition, xfade_dur, per_image_duration)


def _xfade_fade(
    clip_paths: list[Path],
    output: Path,
    xfade_dur: float,
    per_image_duration: float,
) -> None:
    """fade 转场：每个 clip 首尾加 fade，用 concat 拼接。"""
    n = len(clip_paths)
    total_dur = n * per_image_duration - (n - 1) * xfade_dur

    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]

    filter_parts = []
    for i in range(n):
        if i == 0:
            filter_parts.append(
                f"[{i}:v]fade=t=out:st={per_image_duration - xfade_dur}"
                f":d={xfade_dur}[v{i}]"
            )
        elif i == n - 1:
            filter_parts.append(f"[{i}:v]fade=t=in:st=0:d={xfade_dur}[v{i}]")
        else:
            filter_parts.append(
                f"[{i}:v]"
                f"fade=t=in:st=0:d={xfade_dur},"
                f"fade=t=out:st={per_image_duration - xfade_dur}:d={xfade_dur}[v{i}]"
            )

    concat_labels = "+".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_labels}concat=n={n}:v=1:a=0[outv]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]",
        *FFMPEG_VIDEO_OPTS,
        "-t", str(total_dur),
        str(output),
    ]
    run_ffmpeg(cmd)


def _xfade_overlay(
    clip_paths: list[Path],
    output: Path,
    transition: Literal["slide_left", "slide_right", "zoom"],
    xfade_dur: float,
    per_image_duration: float,
) -> None:
    """slide_left / slide_right / zoom 转场：overlay 链式叠加。

    overlay 的 x/y 参数支持算术表达式和 t 变量，可实现动画效果。
    参考文献: https://ffmpeg.org/ffmpeg-filters.html#overlay
    """
    n = len(clip_paths)

    # 每个 clip[i] (i>0) 开始叠加到前一个 clip 上的时刻
    xfade_offset = [0.0] * n
    for i in range(1, n):
        xfade_offset[i] = (i - 1) * (per_image_duration - xfade_dur) + xfade_dur

    total_dur = xfade_offset[-1] + per_image_duration

    cmd = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", str(p)]

    filter_parts: list[str] = []

    if transition == "slide_left":
        # 新 clip 从右侧滑入：x = W*(1 - t_norm)
        # t=offset:  x=W (右侧外); t=offset+xfade_dur: x=0 (完全覆盖)
        for i in range(1, n):
            offset = xfade_offset[i]
            end_t = offset + xfade_dur
            x_expr = f"W*(1-(t-{offset})/{xfade_dur})"
            filter_parts.append(
                f"[{i-1}:v][{i}:v]overlay=x={x_expr}:y=0:"
                f"enable='between(t\\,{offset}\\,{end_t})'[vo{i}]"
            )
        last = f"[vo{n-1}]"

    elif transition == "slide_right":
        # 新 clip 从左侧滑入：x = -W * (t - offset) / xfade_dur
        for i in range(1, n):
            offset = xfade_offset[i]
            end_t = offset + xfade_dur
            x_expr = f"-W*(t-{offset})/{xfade_dur}"
            filter_parts.append(
                f"[{i-1}:v][{i}:v]overlay=x={x_expr}:y=0:"
                f"enable='between(t\\,{offset}\\,{end_t})'[vo{i}]"
            )
        last = f"[vo{n-1}]"

    elif transition == "zoom":
        # clip[i-1]: zoompan (scale 1→1.5) + fade-out
        # clip[i]:    fade-in
        # 两者叠加：前一张缩小消失 + 后一张淡入
        for i in range(1, n):
            offset = xfade_offset[i]
            end_t = offset + xfade_dur
            zoom_filter = (
                f"zoompan=z='min(zoom+0.003,1.5)':x=iw/2-(iw/zoom/2):"
                f"y=ih/2-(ih/zoom/2):d=1:s={VIDEO_WIDTH}x{VIDEO_HEIGHT},"
                f"fade=t=out:st=0:d={xfade_dur}"
            )
            filter_parts.append(f"[{i-1}:v]{zoom_filter}[v{i-1}z]")
            filter_parts.append(f"[{i}:v]fade=t=in:st=0:d={xfade_dur}[v{i}f]")
            filter_parts.append(
                f"[v{i-1}z][v{i}f]overlay=0:0:"
                f"enable='between(t\\,{offset}\\,{end_t})'[vo{i}]"
            )
        last = f"[vo{n-1}]"

    else:
        _concat_clips(clip_paths, output)
        return

    filter_parts.append(f"{last}copy[outv]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[outv]",
        *FFMPEG_VIDEO_OPTS,
        "-t", str(total_dur),
        str(output),
    ]
    run_ffmpeg(cmd)


def _concat_clips(clip_paths: list[Path], output: Path) -> None:
    """无转场，直接 concat 拼接。"""
    lst = ASSETS_DIR / "concat_list.txt"
    with open(lst, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.absolute()}'\n")
    run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(lst),
        *FFMPEG_VIDEO_OPTS,
        str(output),
    ])
    lst.unlink()
