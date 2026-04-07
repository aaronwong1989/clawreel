---
name: clawreel
description: Use this skill when you need to produce video content — especially short videos, social media clips, or TTS/voiceover audio. Covers the full semantic-alignment pipeline: writing scripts, Edge TTS with word-level timestamps, semantic segmentation, image generation per sentence, FFmpeg composition with precise timing, Whisper subtitle burning, and publishing to 抖音 (Douyin) or 小红书 (Xiaohongshu). Also use for music MV production, live-streaming scripts, narration generation, or any request spanning script → voice → video → publish. Does NOT trigger for video playback issues, codec questions, editing existing footage manually, or non-production questions.
---

# ClawReel - AI 短视频语义对齐流水线

## 核心能力

> **声音、字幕、画面三同步。** 图片切换时机由 TTS 逐词时间戳（~50ms）精确驱动，每张图内容由对应语句语义生成。

---

## 流水线概览

```
主题
  │
  ▼
脚本生成（sentences 用 | 分隔）
  │
  ▼
Edge TTS + 逐词时间戳 ──────────────────────────────────┐
  │                                                      │
  ▼                                                      │
align（词→句对齐）                                       │
  │                                                      │
  ▼                                                      │
segments.json（含每句：text / start_sec / end_sec / image_prompt）
  │                                                      │
  ├──▶ assets（按 segments 批量生成图片，每句一张）        │
  │                                                      │
  └──▶ TTS 音频 ─────────────────────────────────────────┤
                                                        ▼
                                                 compose（精确时长合成）
                                                        │
                                                        ▼
                                                 post（字幕烧录 + AIGC）
                                                        │
                                                        ▼
                                                 publish
```

---

## ⚠️ CRITICAL: 成本控制

AI 素材有成本。在生成任何资源之前，必须先展示 `check` 结果并获得用户确认。

```bash
clawreel check --topic "你的主题"
```

**必须步骤：**
1. 展示已有/缺失资源列表
2. 展示成本估算
3. 询问："发现已有资源 X 个，预计成本 ¥Y。开始生成吗？"
4. **等待用户回复**后再执行任何生成

---

## Phase 0: 资源检查 ⚠️ 必做

```bash
clawreel check --topic "Your video topic"
```

---

## Phase 1: 脚本生成

```bash
clawreel script --topic "AI未来趋势"
```

M2.7 输出示例：
```json
{
  "title": "AI觉醒",
  "script": "你有没有想过，未来AI会超越人类？| 就在昨天，一个AI震惊了科学家。| 看完你就明白了。",
  "sentences": ["你有没有想过，未来AI会超越人类？", "就在昨天，一个AI震惊了科学家。", "看完你就明白了。"],
  "hooks": ["开头钩子1", "开头钩子2"],
  "cta": "关注我，带你看清AI真相"
}
```

**注意**：`script` 字段用 `|` 分隔多句，每句独立对应一张图片。

---

## Phase 2: TTS + 语义对齐（核心）

### 方式一：直接对齐（推荐）

```bash
# 一次性完成：TTS 生成 + 词级时间戳 + 语义分句 → segments.json
clawreel align \
  --text "你有没有想过，未来AI会超越人类？| 就在昨天，一个AI震惊了科学家。| 看完你就明白了。" \
  --output segments.json \
  --split-long
```

`segments.json` 输出结构：
```json
{
  "text": "你有没有想过，未来AI会超越人类？...",
  "segments": [
    {
      "index": 0,
      "text": "你有没有想过，未来AI会超越人类？",
      "start_sec": 0.0,
      "end_sec": 3.24,
      "duration_sec": 3.24,
      "image_prompt": "短视频画面：探讨未来AI会超越人类的视觉场景，电影感，高质量，9:16 竖屏..."
    },
    ...
  ]
}
```

### 方式二：分步执行

```bash
# Step 1: TTS 生成（返回 word_timestamps_count）
clawreel tts --text "你有没有想过..." --provider edge --voice zh-CN-XiaoxiaoNeural

# Step 2: 独立对齐（调试用）
clawreel align --text "你有没有想过..." --output segments.json
```

### TTS 提供商

| Provider | 成本 | 时间戳 | 适用场景 |
|----------|------|--------|----------|
| `edge` | 免费 | ✅ 逐词（~50ms）| **语义对齐流水线必选** |
| `minimax` | 付费 | ❌ 无 | 不支持语义对齐，会抛 `RuntimeError` |

---

## Phase 3: 图片生成（由 segments 驱动）

```bash
clawreel assets --segments segments.json --max-concurrent 3
```

**关键**：图片数量和 prompt 由 `segments.json` 决定。

输出示例：
```json
{
  "images": [
    "assets/images/seg_000.jpg",
    "assets/images/seg_001.jpg",
    "assets/images/seg_002.jpg"
  ],
  "segments_count": 3,
  "generated": 3
}
```

---

## Phase 4: 合成

```bash
clawreel compose \
  --tts assets/tts_output.mp3 \
  --segments segments.json \
  --music assets/bg_music.mp3 \
  --transition fade
```

**参数说明：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `--tts` | ✅ | TTS 音频路径 |
| `--segments` | ✅ | `segments.json` 路径（含精确时长）|
| `--music` | ✅ | 背景音乐路径 |
| `--transition` | 否 | 转场类型：`fade`/`slide_left`/`slide_right`/`zoom`/`none`（默认 `fade`）|
| `--output` | 否 | 输出路径，默认 `output/composed.mp4` |

**合成逻辑**：
- 每张图持续 `segments[i].duration_sec` 秒（精确值，不是均分）
- 图片内容由 `segments[i].image_prompt` 生成（语义相关）
- 背景音乐自动循环扩展以匹配 TTS 时长

---

## Phase 5: 后期处理（FFmpeg SRT + AIGC）

```bash
# FFmpeg SRT 烧录 + AIGC 水印（需传入已有 SRT）
clawreel post --video output/composed.mp4 --title "AI觉醒"
```

### 字幕烧录一键命令

```bash
# Whisper 提取 + FFmpeg 烧录（用于已有视频字幕烧录）
clawreel burn-subs -v input.mp4
clawreel burn-subs -v input.mp4 --model medium --language zh
```

---

## Phase 6: 发布

```bash
clawreel publish \
  --video output/final.mp4 \
  --title "AI觉醒" \
  --platforms xiaohongshu douyin
```

---

## 完整工作流示例

**用户：** "帮我做一个关于 AI 觉醒的短视频"

```
你 → clawreel check --topic "AI觉醒" → 展示资源状态 → 询问确认
用户 → "开始"
你 → clawreel script --topic "AI觉醒" → 展示 title/script/hooks → 询问满意
用户 → "满意"
你 → clawreel align --text "<脚本内容>" --output segments.json --split-long
你 → clawreel assets --segments segments.json
你 → 展示生成的图片 → 询问满意？（可选 HITL 审核）
用户 → "y"
你 → clawreel compose --tts assets/tts_output.mp3 --segments segments.json --music assets/bg_music.mp3
你 → clawreel post --video output/composed.mp4 --title "AI觉醒"
你 → 询问发布平台 → 用户确认
你 → clawreel publish --video output/final.mp4 --title "AI觉醒" --platforms douyin xiaohongshu
```

---

## 关键原则

1. **检查优先** — 始终先运行 `clawreel check`（零成本）
2. **Edge TTS 必选** — 语义对齐流水线强制要求 Edge TTS，不支持 MiniMax TTS
3. **对齐分句** — 脚本用 `|` 分隔句子
4. **精确时长** — `segments.json` 的 `duration_sec` 来自 Edge TTS 逐词时间戳
5. **每句一图** — 图片数量由分句数量决定
6. **发布确认** — Phase 6 必须等待用户明确确认

---

## 常见问题排查

### "MiniMax TTS 不支持词级时间戳"

**原因**：语义对齐流水线强制使用 Edge TTS，MiniMax TTS 会抛 `RuntimeError`。

**解决**：将 `config.yaml` 中的 `TTS_PROVIDER` 设为 `edge`，或命令行传入 `--provider edge`。

### segments.json 句子数超过 30

**原因**：`align` 抛出异常，句子数超过上限。

**解决**：将脚本拆分为多个短视频，每条 60 秒以内。

### 图片数量与分句不一致

**原因**：`align` 未传 `--split-long`，超 5 秒的长句未拆分。

**解决**：重新运行 `clawreel align --text "..." --output segments.json --split-long`。

---

## CLI 命令参考

| 命令 | 用途 |
|------|------|
| `clawreel check --topic "..."` | 资源检查 |
| `clawreel script --topic "..."` | 脚本生成 |
| `clawreel align --text "..."` | TTS + 语义对齐（核心）|
| `clawreel tts --text "..."` | TTS 生成 |
| `clawreel assets --segments PATH` | 图片批量生成 |
| `clawreel compose --tts PATH --segments PATH --music PATH` | 视频合成 |
| `clawreel post --video PATH --title "..."` | 后期处理 |
| `clawreel burn-subs -v PATH` | Whisper 字幕烧录 |
| `clawreel publish --video PATH --title "..." --platforms ...` | 多平台发布 |
