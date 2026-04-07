#!/usr/bin/env python3
"""Antigravity 专用：智能体驱动 / 分段编排式内容创作流水线封装。
为 AI 智能体编排 HITL 流程提供 CLI 接口。
FinOps 优化：支持增量生成和资源复用。
"""
import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import (
    ASSETS_DIR,
    OUTPUT_DIR,
    VIDEO_DURATION_DEFAULT,
    VIDEO_DURATION_MIN,
    VIDEO_DURATION_MAX,
    MUSIC_DURATION_DEFAULT,
    MUSIC_DURATION_MIN,
    MUSIC_DURATION_MAX,
)
from .utils import CLEAN_CHAR_CLASS_RE as _CLEAN_RE
from .script_generator import generate_script
from .tts_voice import generate_voice
from .video_generator import generate_video
from .image_generator import generate_image, generate_image_with_urls
from .music_generator import generate_music
from .composer import compose
from .post_processor import post_process
from .publisher import publish
from .subtitle_extractor import extract_subtitles

# 禁用基础日志输出到 stdout，以免干扰 JSON 解析
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("clawreel")


def print_json(data: Any):
    """将结果以 JSON 格式输出到 stdout。"""
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# FinOps: 资源检查与扫描
# ─────────────────────────────────────────────────────────────────────────────

class ResourceType:
    """资源类型常量（消除散落的硬编码字符串）。"""
    SCRIPT = "script"
    TTS = "tts"
    VIDEO = "video"
    IMAGES = "images"
    MUSIC = "music"

# 资源类型 → glob 模式映射（整洁架构：单点定义）
_RESOURCE_PATTERNS: dict[str, list[str]] = {
    ResourceType.SCRIPT: ["script_*.json"],
    ResourceType.TTS: ["tts_*.mp3"],
    ResourceType.VIDEO: ["hook_video_*.mp4"],
    ResourceType.IMAGES: ["img_*.png", "img_*.jpg"],
    ResourceType.MUSIC: ["bg_music_*.mp3"],
}

# 资源类型 → 正则前缀映射（与 glob 同步维护）
_RESOURCE_PREFIXES: dict[str, str] = {
    ResourceType.SCRIPT: "script_",
    ResourceType.TTS: "tts_",
    ResourceType.VIDEO: "hook_video_",
    ResourceType.IMAGES: "img_",
    ResourceType.MUSIC: "bg_music_",
}


def _normalize_topic(topic: str) -> str:
    """标准化主题名称用于文件名匹配。"""
    return _CLEAN_RE.sub("_", topic.lower()).strip("_")


def _find_files_by_pattern(directory: Path, pattern: str) -> list[Path]:
    """查找匹配模式的文件。"""
    if not directory.exists():
        return []
    return sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)


def _extract_topic_from_filename(filename: str) -> Optional[str]:
    """从文件名提取主题名称（格式：前缀_主题[_日期]）。"""
    name = Path(filename).stem
    prefixes = "|".join(re.escape(p) for p in _RESOURCE_PREFIXES.values())
    for pattern in [
        rf"^(?:{prefixes})(.+?)_\d{8}",
        rf"^(?:{prefixes})(.+?)$",
    ]:
        match = re.match(pattern, name)
        if match:
            return match.group(1)
    return None


def _topic_matches(filename: str, normalized_topic: str) -> bool:
    """检查文件名是否匹配给定主题。"""
    # 直接在文件名中搜索标准化后的主题
    if normalized_topic in filename:
        return True

    # 尝试从文件名提取主题
    extracted = _extract_topic_from_filename(filename)
    if extracted:
        # 标准化提取的主题进行比较
        extracted_normalized = _normalize_topic(extracted)
        return extracted_normalized == normalized_topic or normalized_topic in extracted_normalized

    return False


def scan_existing_resources(topic: str) -> dict:
    """扫描现有资源，支持 FinOps 成本优化。

    Args:
        topic: 视频主题

    Returns:
        包含现有资源信息的字典
    """
    normalized = _normalize_topic(topic)
    assets = ASSETS_DIR

    result = {
        "topic": topic,
        "normalized_topic": normalized,
        "existing": {
            "script": None,
            "tts": None,
            "video": None,
            "images": [],
            "music": None,
        },
        "missing": [],
        "recommendation": "generate_all",
        "cost_estimate": {
            "full": "~¥1.5 (T2V + 3图片 + 音乐 + TTS)",
            "incremental": "~¥0.3-0.5 (仅缺失资源)"
        },
        "reuse_possible": False,
    }

    # 统一扫描：基于集中定义的资源类型
    existing = result["existing"]
    for rtype, patterns in _RESOURCE_PATTERNS.items():
        files: list[Path] = []
        for pat in patterns:
            files.extend(_find_files_by_pattern(assets, pat))
        matched = [str(f) for f in files if _topic_matches(f.name, normalized)]
        if rtype == ResourceType.IMAGES:
            existing[rtype] = matched
        elif matched:
            existing[rtype] = matched[0]

    # 确定缺失资源（基于集中定义，避免与扫描逻辑脱节）
    for rtype, patterns in _RESOURCE_PATTERNS.items():
        if rtype == ResourceType.IMAGES:
            if len(existing[rtype]) < 3:
                result["missing"].append(rtype)
        elif not existing[rtype]:
            result["missing"].append(rtype)

    # 生成建议
    if not any(result["existing"].values()):
        result["recommendation"] = "generate_all"
    elif not result["missing"]:
        result["recommendation"] = "use_existing"
        result["reuse_possible"] = True
    else:
        result["recommendation"] = "generate_missing"
        result["reuse_possible"] = True

    return result


async def cmd_check(args):
    """阶段 0（FinOps）：检查现有资源。

    支持两种模式：
    1. 快速模式（默认）：使用关键词匹配，无需 API
    2. 智能模式（--smart）：使用 LLM 语义判断，更准确
    """
    result = scan_existing_resources(args.topic)

    # 生成可读的建议消息
    if result["recommendation"] == "use_existing":
        # 显式统计每个资源类型（images 是列表，其余是单值路径）
        ex = result["existing"]
        existing_count = (
            (1 if ex["script"] else 0) +
            (1 if ex["tts"] else 0) +
            (1 if ex["video"] else 0) +
            (1 if len(ex["images"]) else 0) +
            (1 if ex["music"] else 0)
        )
        result["message"] = f"✅ 发现 {existing_count} 个现有资源，可直接复用"
    elif result["recommendation"] == "generate_missing":
        existing_images_count = len(result["existing"]["images"])
        result["message"] = f"📦 发现 {existing_images_count} 张图片，需生成: {', '.join(result['missing'])}"
    else:
        result["message"] = "🆕 无现有资源，需全部生成"

    # LLM 智能建议（可选）
    if getattr(args, 'smart', False):
        logger.info("🤖 启用 LLM 智能分析...")
        try:
            from .resource_index import llm_check_and_suggest

            # 收集现有资源
            existing = {
                "script": [result["existing"]["script"]] if result["existing"]["script"] else [],
                "tts": [result["existing"]["tts"]] if result["existing"]["tts"] else [],
                "video": [result["existing"]["video"]] if result["existing"]["video"] else [],
                "images": result["existing"]["images"],
                "music": [result["existing"]["music"]] if result["existing"]["music"] else [],
            }

            llm_result = await llm_check_and_suggest(args.topic, existing)

            if "error" in llm_result:
                result["llm_suggestion"] = llm_result
                result["llm_error"] = llm_result.get("error")
                logger.warning(f"LLM 分析失败: {llm_result.get('error')}")
            else:
                result["llm_suggestion"] = llm_result
                result["recommendation"] = "llm_guided"
                logger.info(f"✅ LLM 分析完成: {llm_result.get('recommended_plan', '无')}")
        except Exception as e:
            logger.error(f"LLM 分析出错: {e}")
            result["llm_error"] = str(e)

    print_json(result)


async def cmd_script(args):
    """阶段 0：脚本生成。"""
    result = await generate_script(args.topic)
    print_json(result)


async def cmd_tts(args):
    """阶段 1：配音生成。"""
    path, srt_path = await generate_voice(
        args.text,
        voice_id=args.voice,
        provider=args.provider
    )
    print_json({"path": str(path), "srt": str(srt_path) if srt_path else None})


async def _generate_with_finops(
    name: str,
    output_key: str,
    coro_factory,
    glob_pattern: str,
    force_regenerate: bool,
    skip_existing: bool,
    normalized: str | None,
    output: dict,
    safe_task,
    logger,
) -> None:
    """生成单个资源，消除视频/音乐块的 DRY 违规。

    Args:
        name: 资源名称（如 "视频"）
        output_key: output dict 的 key（如 "video"）
        coro_factory: 无参协程工厂（如 lambda: generate_video(...)）
        glob_pattern: skip-existing 扫描的 glob 模式
        force_regenerate: 强制重新生成
        skip_existing: 启用 FinOps 跳过
        normalized: 标准化后的主题名
        output: 收集结果的 dict
        safe_task: cmd_assets 内的 safe_task 闭包
        logger: logger 实例
    """
    if force_regenerate:
        logger.info(f"🔄 强制重新生成 {name}...")
        res = await safe_task(name, coro_factory())
        output[output_key] = str(res) if res else None
        if res:
            output["generated"].append(name)
        return

    if skip_existing and normalized:
        existing = _find_files_by_pattern(ASSETS_DIR, glob_pattern)
        matched = [f for f in existing if _topic_matches(f.name, normalized)]
        if matched:
            output[output_key] = str(matched[0])
            output["skipped"].append(f"{name} (already exists)")
            output["cost_saved"] += 1
            logger.info(f"✅ 跳过 {name} 生成，复用: {matched[0]}")
            return

    res = await safe_task(name, coro_factory())
    output[output_key] = str(res) if res else None
    if res:
        output["generated"].append(name)


async def cmd_assets(args):
    """阶段 2：素材生成（FinOps 优化：支持增量生成）。

    输出 JSON 包含：
      - images: 本地路径列表（供 compose 使用）
      - image_urls: OSS URL 列表（供 HITL 展示）
    """
    async def safe_task(name, coro):
        try:
            return await coro
        except Exception as e:
            logger.error(f"❌ {name} 生成失败: {e}")
            return None

    output = {
        "video": None,
        "images": [],
        "image_urls": [],
        "music": None,
        "skipped": [],
        "generated": [],
        "cost_saved": 0,
    }

    skip_existing = getattr(args, 'skip_existing', False)
    force_regenerate = getattr(args, 'force', False)
    topic = getattr(args, 'topic', None)
    normalized = _normalize_topic(topic) if topic else None
    target_count = args.count

    # ─── 图片生成 ────────────────────────────────────────────────────────────
    if force_regenerate:
        logger.info(f"🔄 强制重新生成 {target_count} 张图片...")
        result = await safe_task("图片", generate_image_with_urls(
            args.image_prompt, count=target_count,
            output_filename=f"img_{normalized}" if normalized else None
        ))
        if result:
            output["images"] = [str(p) for p in result[0]]
            output["image_urls"] = result[1]
            output["generated"].append(f"{len(output['images'])} images")
    elif skip_existing and normalized:
        all_images = _find_files_by_pattern(ASSETS_DIR, "img_*.png") + _find_files_by_pattern(ASSETS_DIR, "img_*.jpg")
        existing_images = sorted([f for f in all_images if _topic_matches(f.name, normalized)])

        if len(existing_images) >= target_count:
            output["images"] = [str(p) for p in existing_images[:target_count]]
            output["skipped"].append(f"{target_count} images (already exist)")
            output["cost_saved"] += target_count
            logger.info(f"✅ 跳过图片生成，复用 {len(existing_images)} 张已有图片")
        else:
            need_count = target_count - len(existing_images)
            if existing_images:
                output["images"] = [str(p) for p in existing_images]
                output["skipped"].append(f"{len(existing_images)} images (reused)")
                output["cost_saved"] += len(existing_images)

            if need_count > 0:
                logger.info(f"📸 生成 {need_count} 张新图片...")
                result = await safe_task("图片", generate_image_with_urls(
                    args.image_prompt, count=need_count,
                    output_filename=f"img_{normalized}" if normalized else None
                ))
                if result:
                    new_paths, new_urls = result
                    output["images"].extend([str(p) for p in new_paths])
                    output["image_urls"] = new_urls
                    output["generated"].append(f"{len(new_paths)} new images")
    else:
        result = await safe_task("图片", generate_image_with_urls(
            args.image_prompt, count=target_count
        ))
        if result:
            output["images"] = [str(p) for p in result[0]]
            output["image_urls"] = result[1]
            if output["images"]:
                output["generated"].append(f"{len(output['images'])} images")

    # ─── Hook 视频（I2V，需首帧图片 URL） ────────────────────────────────────
    # I2V 需要 OSS URL 作为首帧；image_urls 为空时跳过
    hook_input_image = output["image_urls"][0] if output["image_urls"] else None

    await _generate_with_finops(
        name="视频", output_key="video",
        coro_factory=lambda: generate_video(
            args.hook_prompt, type="i2v",
            duration=args.video_duration,
            input_image=hook_input_image,
            output_filename=f"hook_video_{normalized}.mp4" if normalized else None
        ),
        glob_pattern="hook_video_*.mp4",
        force_regenerate=force_regenerate, skip_existing=skip_existing,
        normalized=normalized, output=output, safe_task=safe_task, logger=logger,
    )

    await _generate_with_finops(
        name="音乐", output_key="music",
        coro_factory=lambda: generate_music(
            prompt=args.music_prompt, duration=args.music_duration,
            output_filename=f"bg_music_{normalized}.mp3" if normalized else None
        ),
        glob_pattern="bg_music_*.mp3",
        force_regenerate=force_regenerate, skip_existing=skip_existing,
        normalized=normalized, output=output, safe_task=safe_task, logger=logger,
    )

    # 摘要
    # HITL：打印纯文本 URL（避免 JSON 转义 %2F）
    if output.get("image_urls"):
        print("\n" + "=" * 60)
        print("📸 图片 OSS URL（HITL 展示，可直接访问）：")
        print("=" * 60)
        for i, url in enumerate(output["image_urls"], 1):
            print(f"  [{i}] {url}")
        print("=" * 60)

    if output["skipped"]:
        output["summary"] = f"生成 {len(output['generated'])} 项，跳过 {len(output['skipped'])} 项（节省 API 调用）"

    # 打印 JSON（含 image_urls 明文）
    print_json(output)


async def cmd_compose(args):
    """阶段 3：多图转场音视频合成。"""
    image_urls = args.images[:args.img_count] if args.img_count else args.images

    tts_path = Path(args.tts)
    # 自动推导 SRT：与 TTS 同 stem（Edge TTS 生成规则）
    srt_path = tts_path.with_suffix(".srt")
    srt_exists = srt_path.exists()

    composed_path, _ = compose(
        tts_path=tts_path,
        image_urls=image_urls,
        music_path=Path(args.music),
        hook_video_path=Path(args.hook) if args.hook else None,
        transition=args.transition,
        srt_path=srt_path if srt_exists else None,
    )

    print_json({
        "path": str(composed_path),
        "srt": str(srt_path) if srt_exists else None,
    })


async def cmd_post(args):
    """阶段 4：后期处理。"""
    srt_path = Path(args.srt) if getattr(args, "srt", None) else None
    path = await post_process(
        Path(args.video),
        args.title,
        add_subtitles=not args.no_subtitles,
        srt_path=srt_path,
        subtitle_model=getattr(args, "subtitle_model", "medium"),
        subtitle_language=getattr(args, "subtitle_language", "auto"),
    )
    print_json({"path": str(path)})


async def cmd_publish(args):
    """阶段 5：发布。"""
    results = await publish(
        Path(args.video),
        title=args.title,
        platforms=args.platforms
    )
    print_json({"results": results})


async def cmd_burn_subs(args):
    """Whisper 字幕提取 + 烧录一键命令。

    等效于: whisper → 烧录硬字幕（subtitles 滤镜）
    """
    video_path = Path(args.video)
    output_path = Path(args.output) if args.output else None

    # 1. Whisper 提取字幕
    srt_path = extract_subtitles(
        video_path,
        output_srt=Path(args.srt) if args.srt else None,
        model=args.model,
        language=args.language,
        word_timestamps=args.word_timestamps,
    )
    if not srt_path:
        logger.error("❌ 字幕提取失败")
        print_json({"success": False, "error": "Whisper 字幕提取失败"})
        return

    # 2. 烧录硬字幕
    await post_process(
        video_path,
        title=video_path.stem,
        add_subtitles=True,
        add_aigc=False,
        output_path=output_path,
        srt_path=srt_path,
        subtitle_model=args.model,
        subtitle_language=args.language,
    )
    print_json({"success": True, "srt": str(srt_path)})


def main():
    parser = argparse.ArgumentParser(
        description="""
ClawReel - AI 短视频内容自动化流水线 (FinOps 成本优化版)
助力 AI 智能体 (Agent) 编排高效、低成本的短视频制作流程。

主要阶段:
  0. 资源检查 (check) & 脚本生成 (script)
  1. 配音生成 (tts)
  2. 素材生成 (assets: 视频、图片、音乐)
  3. 音视频合成 (compose)
  4. 后期处理 (post: 字幕、AIGC 标识)
  5. 多平台发布 (publish)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 1. 成本优化流 (FinOps): 先检查，只生成缺失资源
  clawreel check --topic "AI未来趋势"
  clawreel assets --topic "AI未来趋势" --hook-prompt "..." --image-prompt "..." --skip-existing

  # 2. 全自动执行流: 强制重新生成
  clawreel assets --hook-prompt "..." --image-prompt "..." --force
  
  # 3. 字幕与后期处理:
  clawreel post --video output/draft.mp4 --title "我的AI视频"

  # 4. 配音测试:
  clawreel tts --text "你好，我是 ClawReel" --provider edge --voice zh-CN-XiaoxiaoNeural
        """
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ─── Phase 0: 资源检查 ───
    p_check = subparsers.add_parser("check", help="[阶段 0] 扫描现有资源，避免重复生成（FinOps 核心）")
    p_check.add_argument("--topic", "-t", required=True, metavar="TOPIC", help="视频主题名称")
    p_check.add_argument("--json", action="store_true", help="强制输出纯 JSON 格式数据")
    p_check.add_argument("--smart", action="store_true",
                        help="[LLM] 启用智能语义分析，判断资源是否可复用（需要 API Key）")

    # ─── Phase 0: 脚本生成 ───
    p_script = subparsers.add_parser("script", help="[阶段 0] 生成视频脚本 (建议由 Agent 进一步优化)")
    p_script.add_argument("--topic", "-t", required=True, metavar="TOPIC", help="视频创作的主题")

    # ─── Phase 1: 配音生成 ───
    p_tts = subparsers.add_parser("tts", help="[阶段 1] 将文本转换为语音 (TTS)")
    p_tts.add_argument("--text", required=True, metavar="TEXT", help="待转换的文本内容")
    p_tts.add_argument("--voice", default=None, metavar="VOICE_ID", help="声音 ID (如: female-shaonv 或 zh-CN-XiaoxiaoNeural)")
    p_tts.add_argument("--provider", default=None, choices=["minimax", "edge"], help="TTS 供应商 (默认从 config.yaml 读取)")

    # ─── Phase 2: 素材生成 ───
    p_assets = subparsers.add_parser("assets", help="[阶段 2] 并行生成视频回扣 (T2V)、配图和背景音乐")
    p_assets.add_argument("--hook-prompt", required=True, metavar="PROMPT", help="视频开头 6 秒的视觉提示词")
    p_assets.add_argument("--image-prompt", required=True, metavar="PROMPT", help="中间卡片图片的视觉提示词")
    p_assets.add_argument("--count", type=int, default=9, metavar="N", help="生成的图片张数 (默认: 9，建议 9-15)")
    p_assets.add_argument("--music-prompt", default="轻快、节奏感强、适合短视频的背景音乐",
                         metavar="PROMPT", help="背景音乐风格描述")
    p_assets.add_argument("--topic", "-t", default=None, metavar="TOPIC",
                         help="主题名称 (用于 FinOps 匹配现有资源)")
    p_assets.add_argument("--skip-existing", action="store_true",
                         help="[FinOps] 若发现同主题资源则跳过生成（推荐开启）")
    p_assets.add_argument("--force", action="store_true",
                         help="强制重新生成所有资源，忽略本地缓存")
    p_assets.add_argument("--video-duration", type=int, default=VIDEO_DURATION_DEFAULT, metavar="SEC",
                         help=f"视频时长，单位秒 (默认: {VIDEO_DURATION_DEFAULT}，范围: {VIDEO_DURATION_MIN}-{VIDEO_DURATION_MAX})")
    p_assets.add_argument("--music-duration", type=int, default=MUSIC_DURATION_DEFAULT, metavar="SEC",
                         help=f"音乐时长，单位秒 (默认: {MUSIC_DURATION_DEFAULT}，范围: {MUSIC_DURATION_MIN}-{MUSIC_DURATION_MAX})")

    # ─── Phase 3: 合成 ───
    p_compose = subparsers.add_parser("compose", help="[阶段 3] 将素材组装为初始视频草稿")
    p_compose.add_argument("--tts", required=True, metavar="PATH", help="配音音频路径")
    p_compose.add_argument("--images", nargs="+", required=True, metavar="URL_or_PATH", help="图片 URL 或本地路径列表")
    p_compose.add_argument("--music", required=True, metavar="PATH", help="背景音乐路径")
    p_compose.add_argument("--hook", default=None, metavar="PATH", help="视频开头回扣 (mp4) 路径")
    p_compose.add_argument("--transition", default="fade", metavar="TYPE",
                           choices=["fade", "slide_left", "slide_right", "zoom", "none"],
                           help="转场类型 (默认: fade，推荐 fade/zoom)")
    p_compose.add_argument("--img-count", type=int, default=9, metavar="N",
                           help="正文使用图片数量，默认 9")

    # ─── Phase 4: 后期 ───
    p_post = subparsers.add_parser("post", help="[阶段 4] 添加字幕、AIGC 标识等视觉修饰")
    p_post.add_argument("--video", required=True, metavar="PATH", help="待处理的视频草稿路径")
    p_post.add_argument("--title", required=True, metavar="STR", help="视频标题 (将用于文件名和发布元数据)")
    p_post.add_argument("--srt", default=None, metavar="PATH",
                        help="SRT 字幕路径（若已由 TTS 阶段生成，直接传入以跳过提取）")
    p_post.add_argument("--no-subtitles", action="store_true",
                        help="跳过字幕烧录")
    p_post.add_argument("--subtitle-model", default="medium",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper 模型大小 (默认: medium)")
    p_post.add_argument("--subtitle-language", default="auto",
                        help="字幕语言代码 (默认: auto 自动检测)")

    # ─── 字幕烧录一键命令 ───
    p_burn = subparsers.add_parser(
        "burn-subs",
        help="Whisper 提取字幕 + FFmpeg 烧录硬字幕（medium 模型，推荐）",
        description="等价于: Whisper 提取 SRT → FFmpeg subtitles 滤镜烧录",
    )
    p_burn.add_argument("--video", "-v", required=True, metavar="PATH",
                        help="视频文件路径")
    p_burn.add_argument("--output", "-o", default=None, metavar="PATH",
                        help="输出路径（默认: output/原名_subtitled.mp4）")
    p_burn.add_argument("--srt", default=None, metavar="PATH",
                        help="指定 SRT 路径（跳过 Whisper 提取）")
    p_burn.add_argument("--model", default="medium",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper 模型 (默认: medium)")
    p_burn.add_argument("--language", default="auto",
                        help="语言代码 (默认: auto)")
    p_burn.add_argument("--word-timestamps", action="store_true",
                        help="启用词级时间戳（精度更高）")

    # ─── Phase 5: 发布 ───
    p_publish = subparsers.add_parser("publish", help="[阶段 5] 自动化分发到主流视频平台 (需配置 Cookies)")
    p_publish.add_argument("--video", required=True, metavar="PATH", help="最终视频路径")
    p_publish.add_argument("--title", required=True, metavar="STR", help="发布时使用的标题")
    p_publish.add_argument("--platforms", nargs="+", default=["xiaohongshu", "douyin"], 
                         choices=["xiaohongshu", "douyin", "bilibili"],
                         help="目标发布平台 (默认: 小红书/抖音)")

    args = parser.parse_args()

    async def run():
        try:
            if args.command == "check":
                await cmd_check(args)
            elif args.command == "script":
                await cmd_script(args)
            elif args.command == "tts":
                await cmd_tts(args)
            elif args.command == "assets":
                await cmd_assets(args)
            elif args.command == "compose":
                await cmd_compose(args)
            elif args.command == "post":
                await cmd_post(args)
            elif args.command == "publish":
                await cmd_publish(args)
            elif args.command == "burn-subs":
                await cmd_burn_subs(args)
        except Exception as e:
            logger.exception("命令执行失败: %s", args.command)
            print_json({"success": False, "error": str(e)})
            sys.exit(1)
        finally:
            # 确保关闭 aiohttp session
            try:
                from .api_client import close_session
                await close_session()
            except ImportError:
                pass


    asyncio.run(run())


if __name__ == "__main__":
    main()
