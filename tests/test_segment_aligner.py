"""单元测试 — segment_aligner."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from clawreel.segment_aligner import (
    align_segments,
    split_long_segments,
    refine_image_prompt,
    parse_srt_segments,
    _split_sentences,
    _assign_words_to_sentences,
    WordTimestamp,
    ScriptSegment,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def simple_word_ts():
    """两句话的词级时间戳。"""
    return [
        WordTimestamp(word="你",     start_sec=0.00, end_sec=0.30, offset_ms=0),
        WordTimestamp(word="有",     start_sec=0.30, end_sec=0.55, offset_ms=300),
        WordTimestamp(word="没",     start_sec=0.55, end_sec=0.80, offset_ms=550),
        WordTimestamp(word="有",     start_sec=0.80, end_sec=1.05, offset_ms=800),
        WordTimestamp(word="想",     start_sec=1.05, end_sec=1.30, offset_ms=1050),
        WordTimestamp(word="过",    start_sec=1.30, end_sec=1.60, offset_ms=1300),
        WordTimestamp(word="，",    start_sec=1.60, end_sec=1.70, offset_ms=1600),
        WordTimestamp(word="未",    start_sec=1.70, end_sec=1.95, offset_ms=1700),
        WordTimestamp(word="来",    start_sec=1.95, end_sec=2.20, offset_ms=1950),
        WordTimestamp(word="会",    start_sec=2.20, end_sec=2.50, offset_ms=2200),
        WordTimestamp(word="超",    start_sec=2.50, end_sec=2.80, offset_ms=2500),
        WordTimestamp(word="越",    start_sec=2.80, end_sec=3.10, offset_ms=2800),
        WordTimestamp(word="人",    start_sec=3.10, end_sec=3.40, offset_ms=3100),
        WordTimestamp(word="类",    start_sec=3.40, end_sec=3.70, offset_ms=3400),
        WordTimestamp(word="？",    start_sec=3.70, end_sec=3.90, offset_ms=3700),
        WordTimestamp(word="就",    start_sec=3.90, end_sec=4.10, offset_ms=3900),
        WordTimestamp(word="在",    start_sec=4.10, end_sec=4.30, offset_ms=4100),
        WordTimestamp(word="昨",    start_sec=4.30, end_sec=4.55, offset_ms=4300),
        WordTimestamp(word="天",    start_sec=4.55, end_sec=4.85, offset_ms=4550),
        WordTimestamp(word="。",    start_sec=4.85, end_sec=4.95, offset_ms=4850),
    ]


@pytest.fixture
def simple_text():
    return "你有没有想过，未来会超越人类。就在昨天。"


# ── 句子分句 ────────────────────────────────────────────────────────────────

class TestSentenceSplitting:
    def test_split_by_delimiters(self):
        text = "你有没有想过？未来会超越人类！就在昨天。"
        result = _split_sentences(text)
        assert len(result) == 3
        assert result[0] == "你有没有想过"
        assert result[1] == "未来会超越人类"
        assert result[2] == "就在昨天"

    def test_punctuation_only_no_empty(self):
        text = "你好！！！世界？"
        result = _split_sentences(text)
        assert all(len(s) >= 2 for s in result)

    def test_trailing_punctuation_stripped(self):
        text = "你好。" * 10
        result = _split_sentences(text)
        assert all(not s.endswith("。") for s in result)

    def test_empty_text_returns_empty_list(self):
        result = _split_sentences("")
        assert result == []


# ── 词-句对齐 ────────────────────────────────────────────────────────────────

class TestWordSentenceAlignment:
    def test_align_two_sentences(self, simple_word_ts, simple_text):
        """两句话各占对应词区间。"""
        # 先手动分句
        sentences = _split_sentences(simple_text)
        assignments = _assign_words_to_sentences(sentences, simple_word_ts)

        assert len(assignments) == 2
        sent1_text, sent1_start, sent1_end = assignments[0]
        sent2_text, sent2_start, sent2_end = assignments[1]

        # 第一句
        assert "你有没有想过" in sent1_text or sent1_text.startswith("你有")
        assert sent1_start == 0
        assert sent1_end >= sent1_start

        # 第二句
        assert sent2_start > sent1_end or sent2_start == sent1_end
        assert sent2_end < len(simple_word_ts)

    def test_align_segments_returns_typed_segments(self, simple_word_ts, simple_text):
        segments = align_segments(simple_text, simple_word_ts)
        assert isinstance(segments, list)
        assert all(isinstance(s, dict) for s in segments)
        assert all("index" in s for s in segments)
        assert all("text" in s for s in segments)
        assert all("start_sec" in s for s in segments)
        assert all("end_sec" in s for s in segments)
        assert all("duration_sec" in s for s in segments)
        assert all("image_prompt" in s for s in segments)

    def test_segments_time_monotonically_increasing(self, simple_word_ts, simple_text):
        segments = align_segments(simple_text, simple_word_ts)
        for i in range(1, len(segments)):
            assert segments[i]["start_sec"] >= segments[i - 1]["end_sec"], \
                f"段 {i} start_sec < 段 {i-1} end_sec：{segments[i]['start_sec']} < {segments[i-1]['end_sec']}"

    def test_segments_duration_positive(self, simple_word_ts, simple_text):
        segments = align_segments(simple_text, simple_word_ts)
        for s in segments:
            assert s["duration_sec"] > 0, f"段 {s['index']} duration_sec ≤ 0: {s['duration_sec']}"

    def test_empty_word_timestamps_raises(self, simple_text):
        with pytest.raises(ValueError, match="word_timestamps 为空"):
            align_segments(simple_text, [])


# ── prompt 提纯 ──────────────────────────────────────────────────────────────

class TestPromptRefinement:
    def test_removes_filler_words(self):
        text = "你有没有想过啊吧呢"
        prompt = refine_image_prompt(text)
        assert "啊" not in prompt
        assert "吧" not in prompt
        assert "呢" not in prompt

    def test_question_prefix_converted(self):
        text = "有没有想过未来会怎样？"  # 以"有没有"开头，触发转换
        prompt = refine_image_prompt(text)
        assert "探讨" in prompt, f"问句前缀未被转换: {prompt}"

    def test_prompt_has_style_suffix(self):
        text = "未来已来"
        prompt = refine_image_prompt(text)
        assert "9:16" in prompt
        assert "短视频画面" in prompt

    def test_truncates_long_text(self):
        text = "测试" * 100
        prompt = refine_image_prompt(text)
        assert len(prompt) <= 200


# ── 长段拆分 ─────────────────────────────────────────────────────────────────

class TestLongSegmentSplitting:
    def test_short_segment_unchanged(self):
        segments = [
            ScriptSegment(index=0, text="短句", start_sec=0.0, end_sec=2.0,
                          duration_sec=2.0, image_prompt=""),
        ]
        result = split_long_segments(segments)
        assert len(result) == 1

    def test_long_segment_split_by_comma(self):
        """时长超过 5 秒的段落按逗号拆分。"""
        segments = [
            ScriptSegment(
                index=0,
                text="第一部分，第二部分，第三部分",
                start_sec=0.0,
                end_sec=7.0,
                duration_sec=7.0,
                image_prompt="",
            )
        ]
        result = split_long_segments(segments)
        # 应拆分为 3 段
        assert len(result) >= 2
        # 总时长应等于原始时长
        total = sum(s["duration_sec"] for s in result)
        assert abs(total - 7.0) < 0.01

    def test_sub_segments_have_sequential_timing(self):
        segments = [
            ScriptSegment(
                index=0,
                text="第一，第二，第三，第四",
                start_sec=1.0,
                end_sec=10.0,
                duration_sec=9.0,
                image_prompt="",
            )
        ]
        result = split_long_segments(segments)
        for i in range(1, len(result)):
            prev = result[i - 1]
            curr = result[i]
            assert abs(curr["start_sec"] - prev["end_sec"]) < 0.01, \
                f"段 {i} start_sec {curr['start_sec']} != 前段 end_sec {prev['end_sec']}"


# ── SRT 解析 ────────────────────────────────────────────────────────────────

class TestSRTParsing:
    def test_parse_valid_srt(self, tmp_path):
        srt_content = """1
00:00:00,000 --> 00:00:03,500
你有没有想过，未来会超越人类？

2
00:00:03,500 --> 00:00:07,200
就在昨天，一个AI震惊了世界。

"""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text(srt_content, encoding="utf-8")

        segments = parse_srt_segments(str(srt_file))
        assert len(segments) == 2
        assert segments[0]["text"] == "你有没有想过，未来会超越人类？"
        assert 0.0 <= segments[0]["start_sec"] < 1.0
        assert segments[1]["start_sec"] >= segments[0]["end_sec"]

    def test_nonexistent_srt_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_srt_segments("/nonexistent/path.srt")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
