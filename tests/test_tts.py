"""集成测试 — tts_voice 模块（语义对齐流水线版）。"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clawreel.tts_voice import generate_voice, TTSResult

logging.basicConfig(level=logging.INFO)


async def main():
    text = "你有没有想过，未来AI会超越人类？就在昨天，一个AI震惊了科学家。"

    # Edge TTS 必须返回 word_timestamps
    print("Testing Edge TTS with word_timestamps...")
    edge_path = Path("assets/test_edge.mp3")
    srt_path = Path("assets/test_edge.srt")
    try:
        result: TTSResult = await generate_voice(
            text,
            output_path=edge_path,
            provider="edge",
            voice_id="zh-CN-XiaoxiaoNeural",
            srt_path=srt_path,
        )
        print(f"✅ Edge TTS: {result['audio_path']}")
        print(f"   SRT: {result['srt_path']}")
        print(f"   word_timestamps: {len(result['word_timestamps'])} 个词")
        assert result["word_timestamps"], "word_timestamps 不应为空"
        assert all("word" in w and "start_sec" in w and "end_sec" in w for w in result["word_timestamps"]), \
            "word_timestamps 字段不完整"
        print(f"   首词: {result['word_timestamps'][0]}")
    except Exception as e:
        print(f"❌ Edge TTS failed: {e}")
        raise

    # MiniMax TTS 必须抛出 RuntimeError
    print("\nTesting MiniMax TTS raises RuntimeError...")
    try:
        await generate_voice(text, provider="minimax")
        print("❌ MiniMax TTS should have raised RuntimeError")
    except RuntimeError as e:
        print(f"✅ MiniMax TTS correctly raised: {e}")
    except Exception as e:
        print(f"❌ MiniMax TTS raised unexpected error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
