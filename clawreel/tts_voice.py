"""阶段1：TTS配音 — 使用统一 api_client。

采样率使用 config.AUDIO_SAMPLE_RATE（44100 Hz）。
字幕: Edge TTS WordBoundary 逐字时间戳生成 SRT，无需 Whisper。
"""
import logging
from pathlib import Path

import edge_tts

from .api_client import api_post
from .config import ASSETS_DIR, AUDIO_SAMPLE_RATE, TTS_PROVIDER, TTS_CONFIG
from .utils import get_media_duration, save_hex_audio, check_base_resp

logger = logging.getLogger(__name__)


async def generate_voice(
    text: str,
    output_path: Path | None = None,
    voice_id: str | None = None,
    provider: str | None = None,
    srt_path: Path | None = None,
) -> tuple[Path, Path | None]:
    """生成 TTS 音频（支持 MiniMax 和 Edge），并生成 SRT 字幕（Edge 专有）。

    Args:
        text:        TTS 文本
        output_path: 音频输出路径，默认 assets/tts_output.mp3
        voice_id:    音色 ID，默认从 TTS_CONFIG 读取
        provider:    TTS 提供商，默认从 TTS_CONFIG 读取
        srt_path:    SRT 字幕输出路径，默认 assets/tts_output.srt（仅 Edge TTS 生效）

    Returns:
        (音频路径, SRT路径或None) 元组
    """
    if output_path is None:
        output_path = ASSETS_DIR / "tts_output.mp3"
    if srt_path is None:
        srt_path = output_path.with_suffix(".srt")

    if provider is None:
        provider = TTS_PROVIDER

    provider_config = TTS_CONFIG.get("providers", {}).get(provider, {})
    default_voice = provider_config.get("voice_id")

    if provider == "edge":
        path = await _generate_edge_voice(text, output_path, voice_id or default_voice, srt_path)
        srt_out = srt_path  # _generate_edge_voice 成功返回时 SRT 文件已写入
    else:
        path = await _generate_minimax_voice(text, output_path, voice_id or default_voice)
        srt_out = None

    duration = get_media_duration(path)
    logger.info("✅ TTS 生成完成: %s (%.1f 秒)", path, duration)
    return path, srt_out


async def _generate_edge_voice(
    text: str,
    output_path: Path,
    voice_id: str,
    srt_path: Path,
) -> Path:
    """使用 Edge TTS 生成音频，并从 WordBoundary 生成 SRT 字幕。

    Edge TTS 在流式返回音频时附带每个词的精确时间戳，
    无需 Whisper 或任何网络请求即可生成逐字 SRT。
    """
    logger.info("🎙️ 正在生成 Edge TTS，音色: %s, 文本长度: %d", voice_id, len(text))

    submaker = edge_tts.SubMaker()
    communicate = edge_tts.Communicate(text, voice_id, boundary="WordBoundary")

    # 单次 stream() 循环同时收集音频 bytes 和 word boundary 元数据
    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    srt_content = submaker.get_srt()
    if srt_content.strip():
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        logger.info("✅ Edge TTS SRT 生成完成: %s", srt_path)
    else:
        logger.warning("⚠️ Edge TTS 未生成任何字幕条目")

    return output_path


async def _generate_minimax_voice(
    text: str,
    output_path: Path,
    voice_id: str,
) -> Path:
    """使用 MiniMax 生成 TTS 音频。"""
    logger.info("🎙️ 正在生成 MiniMax TTS，音色: %s, 文本长度: %d", voice_id, len(text))
    
    provider_config = TTS_CONFIG.get("providers", {}).get("minimax", {})

    result = await api_post(
        endpoint="/t2a_v2",
        payload={
            "model": "speech-2.8-hd",
            "text": text,
            "stream": False,
            "output_format": "hex",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": provider_config.get("speed", 1.0),
                "vol": provider_config.get("vol", 1.0),
                "pitch": provider_config.get("pitch", 0),
                "emotion": provider_config.get("emotion", "happy"),
            },
            "audio_setting": {
                "sample_rate": AUDIO_SAMPLE_RATE,
                "format": "mp3",
                "channel": 1,
            },
        },
    )

    check_base_resp(result, context="MiniMax TTS API")

    audio_hex = result.get("data", {}).get("audio")
    if not audio_hex:
        raise RuntimeError(f"MiniMax TTS API 返回无 audio_hex: {result}")

    return save_hex_audio(audio_hex, output_path)
