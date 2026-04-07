"""阶段4：后期处理 - 字幕、封面、AIGC标识.

字幕: Whisper 优先提取，SRT 透传次之，FFprobe 兜底。
封面: image-01 生成 3 张，关键内容偏上
AIGC标识: 添加"内容由AI生成"声明
"""
import logging
import shutil
import subprocess
from pathlib import Path

from .config import COVER_FULL, COVER_VISIBLE, FFMPEG_VIDEO_OPTS, OUTPUT_DIR, AIGC_CONFIG
from .utils import ensure_parent_dir, run_ffmpeg as _run_ffmpeg, get_media_duration

logger = logging.getLogger(__name__)


# ── 字幕提取优先级 ─────────────────────────────────────────────────────────────
# 1. Whisper（高质量，模型需已安装）
# 2. FFprobe 硬字幕流（视频内嵌字幕）
# 3. 无字幕（跳过字幕处理）


def _extract_subtitles_whisper(video_path: Path, model: str = "medium", language: str = "auto") -> Path | None:
    """用 Whisper 提取字幕，保存为 SRT.

    Returns:
        SRT 字幕文件路径，失败返回 None
    """
    from .subtitle_extractor import extract_subtitles

    srt_path = video_path.with_suffix(".srt")
    return extract_subtitles(video_path, srt_path, model=model, language=language)


def _extract_subtitles_ffprobe(video_path: Path) -> Path | None:
    """用 FFmpeg 内置字幕提取（如果有硬字幕流）."""
    srt_path = video_path.with_suffix(".srt")
    try:
        _run_ffmpeg([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-map", "0:s:0?",
            str(srt_path),
        ])
        if srt_path.exists() and srt_path.stat().st_size > 0:
            logger.info("✅ FFmpeg 字幕提取成功: %s", srt_path)
            return srt_path
    except subprocess.SubprocessError:
        pass
    return None


def _burn_subtitles(video_path: Path, srt_path: Path, output_path: Path) -> Path:
    """将 SRT 字幕烧录进视频。

    优先使用 ffmpeg-full 的 subtitles 滤镜（libass）烧录硬字幕；
    若滤镜不可用，降级为 mov_text 软字幕封装。
    使用绝对路径避免含冒号的项目路径被 FFmpeg 解析错误。
    字体优先使用系统中文字体。
    """
    ensure_parent_dir(output_path)
    video_abs = str(video_path.resolve())
    srt_abs = str(srt_path.resolve())
    out_abs = str(output_path.resolve())
    input_duration = get_media_duration(video_path)

    # 字体：系统带的中文字体
    font_name = "PingFang SC"

    # 方案 1：subtitles 滤镜（硬字幕）
    subtitles_ok = False
    try:
        _run_ffmpeg([
            "ffmpeg", "-y",
            "-i", video_abs,
            "-vf",
            f"subtitles={srt_abs}:force_style='FontName={font_name},FontSize=22,"
            f"PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=2'",
            *FFMPEG_VIDEO_OPTS,
            "-map", "0:v",          # 明确选择视频流（避免选错 AAC 流）
            "-map", "0:a",          # 明确选择音频流
            "-c:a", "copy",
            "-t", str(input_duration),  # 确保不截断视频
            out_abs,
        ])
        if output_path.exists() and output_path.stat().st_size > 0:
            # 验证输出时长是否正确（容许 1 秒误差）
            output_duration = get_media_duration(output_path)
            if output_duration > 0 and output_duration >= input_duration - 1.0:
                subtitles_ok = True
                logger.debug(
                    "✅ 字幕烧录验证通过: 输入%.1fs → 输出%.1fs",
                    input_duration, output_duration
                )
            else:
                logger.warning(
                    "⚠️ 字幕烧录输出时长异常: 输入%.1fs，输出%s",
                    input_duration,
                    f"{output_duration:.1f}s" if output_duration else "获取失败"
                )
    except subprocess.SubprocessError as e:
        logger.debug("subtitles 滤镜执行失败: %s，尝试 mov_text 封装", e)

    if subtitles_ok:
        logger.info("✅ 字幕烧录完成（硬字幕 subtitles）: %s", output_path)
        return output_path

    # 方案 2：mov_text 软字幕封装（降级方案）
    try:
        _run_ffmpeg([
            "ffmpeg", "-y",
            "-i", video_abs,
            "-i", srt_abs,
            "-map", "0:v",
            "-map", "0:a",
            "-c", "copy",
            "-c:s", "mov_text",
            out_abs,
        ])
    except subprocess.SubprocessError as e:
        raise RuntimeError(f"字幕封装（mov_text）失败: {e}") from e

    if output_path.exists() and output_path.stat().st_size > 0:
        logger.info("✅ 字幕封装完成（软字幕 mov_text）: %s", output_path)
    else:
        raise RuntimeError(f"字幕封装失败，输出文件未生成: {output_path}")
    return output_path


def _add_aigc_watermark(
    video_path: Path, 
    output_path: Path, 
    label: str = "内容由AI生成", 
    position: str = "bottom-right"
) -> Path:
    """添加 AIGC 水印标识.

    支持位置: bottom-right (默认), bottom-left, top-right, top-left
    """
    ensure_parent_dir(output_path)
    
    pos_map = {
        "bottom-right": "x=(w-text_w-10):y=(h-text_h-10)",
        "bottom-left": "x=10:y=(h-text_h-10)",
        "top-right": "x=(w-text_w-10):y=10",
        "top-left": "x=10:y=10",
    }
    drawtext_pos = pos_map.get(position, pos_map["bottom-right"])

    _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf",
        f"drawtext=text='{label}':fontsize=20:fontcolor=white:borderw=1:bordercolor=black:{drawtext_pos}",
        *FFMPEG_VIDEO_OPTS,
        "-c:a", "copy",
        str(output_path),
    ])
    logger.info("✅ AIGC水印添加完成: %s", output_path)
    return output_path


async def post_process(
    video_path: Path,
    title: str | None = None,
    add_subtitles: bool = True,
    add_aigc: bool = True,
    output_path: Path | None = None,
    srt_path: Path | None = None,
    subtitle_model: str = "medium",
    subtitle_language: str = "auto",
) -> Path:
    """后期处理主流程.

    Args:
        video_path: 输入视频路径
        title: 视频标题（未使用，保留向后兼容）
        add_subtitles: 是否添加字幕
        add_aigc: 是否添加 AIGC 标识
        output_path: 输出路径（默认 output/final_原名.mp4）
        srt_path: 已有 SRT 路径（跳过提取）
        subtitle_model: Whisper 模型大小（default/medium/large/small/tiny）
        subtitle_language: 字幕语言代码（auto/zh/en 等）

    Returns:
        处理后的视频路径
    """
    if output_path is None:
        output_path = OUTPUT_DIR / f"final_{video_path.name}"

    logger.info("🎨 开始后期处理: %s", video_path)

    current = video_path

    # 1. 字幕处理
    if add_subtitles:
        # 优先级：显式传入 > 同 stem SRT > Whisper 提取 > FFprobe 兜底
        resolved_srt: Path | None = srt_path

        if resolved_srt is None or not resolved_srt.exists():
            candidate = video_path.with_suffix(".srt")
            if candidate.exists():
                resolved_srt = candidate
            else:
                # Whisper 优先（高质量）
                resolved_srt = _extract_subtitles_whisper(
                    video_path,
                    model=subtitle_model,
                    language=subtitle_language,
                )
                if resolved_srt is None:
                    # FFprobe 兜底（仅提取内嵌字幕）
                    resolved_srt = _extract_subtitles_ffprobe(video_path)

        if resolved_srt and resolved_srt.exists():
            try:
                current = _burn_subtitles(current, resolved_srt, current.with_suffix(".subtitled.mp4"))
            except Exception as e:
                logger.error(f"❌ 字幕烧录失败: {e}")
        else:
            logger.warning("⚠️ 无可用字幕，跳过字幕烧录")

    # 2. AIGC 标识
    # 如果 AIGC_CONFIG 缺省或没有 label，则不添加（按用户要求：如果缺省则不添加）
    if add_aigc and AIGC_CONFIG and AIGC_CONFIG.get("label"):
        label = AIGC_CONFIG.get("label", "内容由AI生成")
        position = AIGC_CONFIG.get("position", "bottom-right")
        # 水印写入独立临时文件，再复制到 output_path（避免 input==output 覆盖）
        aigc_temp = OUTPUT_DIR / f"_aigc_tmp_{video_path.stem}.mp4"
        _add_aigc_watermark(current, aigc_temp, label=label, position=position)
        ensure_parent_dir(output_path)
        shutil.move(str(aigc_temp), str(output_path))
        current = output_path
    else:
        if not (AIGC_CONFIG and AIGC_CONFIG.get("label")):
            logger.info("ℹ️ AIGC 配置缺省，跳过水印添加")
        ensure_parent_dir(output_path)
        shutil.copy2(current, output_path)
        current = output_path

    # 清理字幕中间文件（如果存在）
    subtitled = video_path.with_suffix(".subtitled.mp4")
    if subtitled.exists():
        try:
            subtitled.unlink()
        except OSError:
            pass

    logger.info("✅ 后期处理完成: %s", output_path)
    return output_path
