---
name: clawreel
description: Use this skill when you need to produce video content — especially short videos, social media clips, or TTS/voiceover audio. Covers the full pipeline: writing scripts, generating AI voiceovers, creating video clips/images, composing background music, and publishing to 抖音 (Douyin) or 小红书 (Xiaohongshu). Also use for music MV production, live-streaming scripts, narration generation, or any request spanning script → voice → video → publish. Does NOT trigger for video playback issues, codec questions, editing existing footage manually, or non-production questions.
---

# ClawReel - AI Video Content Pipeline

## ⚡ FinOps-Optimized Workflow

**Cost Control First**: Always check for existing resources before generating. AI-generated assets are expensive — never regenerate without user confirmation.

---

## Prerequisites

**This skill requires the `clawreel` CLI tool.**

### If `clawreel` command is not found:

```bash
./install.sh
```

### Required Configuration

| Item | Requirement |
|------|-------------|
| **MINIMAX_API_KEY** | Required for video, images, music generation |
| **Python** | 3.10+ |
| **FFmpeg** | Required for video composition |

---

## When to Use This Skill

**✅ Triggers when:**
- User wants to create short videos for social media (抖音, 小红书, TikTok)
- User mentions script generation, TTS, AI-generated media
- User says "生成视频", "做短视频", "内容创作", "配音", "写脚本"
- User wants multi-platform publishing

**❌ Does NOT trigger for:**
- Video playback or viewing issues
- Manual video editing with tools like Premiere, Final Cut
- Codec or format conversion questions
- Non-production video questions

---

## ⚠️ CRITICAL: Resource Check Before Generation

**This is a FinOps requirement. Always check existing resources FIRST before any generation.**

### Step 0: Inventory Check

**Quick Mode (Free):**
```bash
clawreel check --topic "AI未来趋势"
```

**Smart Mode (LLM-powered, more accurate):**
```bash
clawreel check --topic "AI未来趋势" --smart
```

The LLM mode understands semantic similarity — it knows that "AI发展趋势" and "人工智能未来趋势" are related even if filenames don't match exactly.

### Resource Decision Matrix

| Scenario | Action | API Calls |
|----------|--------|-----------|
| All resources exist, topic matches | Use existing | 0 |
| Partial resources exist | Generate missing only | ~50% |
| New topic or user wants fresh | Generate all | 100% |
| Generation failed mid-way | Resume from failure | ~30% |

### LLM Smart Recommendations

When using `--smart`, the LLM will analyze:
- Is the new topic semantically similar to existing resources?
- Can images/music be reused even with different wording?
- What is the optimal regeneration strategy?

Example output with `--smart`:
```json
{
  "llm_suggestion": {
    "can_reuse": [
      {"type": "image", "path": "...", "reason": "科技风格图片可复用"},
      {"type": "music", "path": "...", "reason": "轻快背景音乐适合"}
    ],
    "must_regenerate": [
      {"type": "script", "reason": "主题不同需要新内容"}
    ],
    "recommended_plan": "复用图片和音乐，只重新生成脚本和配音",
    "estimated_savings": "约 60%"
  }
}
```

---

## FinOps Workflow (Revised)

### Phase 0: Inventory Check ⚠️ MANDATORY (Zero Cost)

```bash
clawreel check --topic "Your video topic"
```

**Output:**
```json
{
  "topic": "Your video topic",
  "existing": {
    "script": "assets/script_20260407_120000.json",
    "tts": "assets/tts_20260407_120000.mp3",
    "video": null,
    "images": ["assets/img_001.png"],
    "music": null
  },
  "missing": ["video", "music"],
  "recommendation": "generate_missing",
  "reuse_prompt": "Found 1 image for topic 'Your video topic'. Generate only missing video and music."
}
```

**Required Action:**
1. Display existing resources to user
2. Ask: "发现已有资源（1张图片）。要复用现有资源，只生成缺失的视频和音乐吗？"
3. **Wait for decision** before any generation

---

### Phase 1: Script Generation (If Needed)

**Only run if no script exists or user wants refresh:**

```bash
clawreel script --topic "Your video topic"
```

**Output:**
```json
{
  "title": "视频标题",
  "hooks": ["钩子1", "钩子2"],
  "script": "完整配音文本...",
  "hook_prompts": ["视频钩子提示词"],
  "image_prompts": ["图片提示词"]
}
```

**Required Action:**
1. Display title, hooks, and script to user
2. Ask: "脚本已生成，满意吗？"
3. **Wait for approval**

---

### Phase 2: TTS Generation (If Needed)

**Only run if no TTS exists for this topic:**

```bash
clawreel tts --text "配音文本" [--provider minimax|edge]
```

**Providers:**
| Provider | Cost | Quality | API Key |
|----------|------|---------|---------|
| `edge` | Free | Good | No |
| `minimax` | Paid | High | Yes |

**Recommendation:** Use `edge` for drafts, `minimax` for final production.

---

### Phase 3: Asset Generation ⚠️ CHECKPOINT

**Generate only missing assets:**

```bash
clawreel assets \
  --hook-prompt "视频开头画面描述" \
  --image-prompt "正文配图描述" \
  --count 3 \
  --music-prompt "背景音乐风格描述" \
  --skip-existing  # IMPORTANT: Skip if files exist
```

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|--------|-------------|
| `--skip-existing` | No | false | Skip generation if files already exist |
| `--force` | No | false | Force regeneration (costs money!) |

**Output:**
```json
{
  "video": "assets/hook_video_20260407.mp4",
  "images": ["assets/img_001.png", "assets/img_002.png"],
  "music": "assets/bg_music_20260407.mp3",
  "skipped": ["img_003.png (already exists)"],
  "cost_saved": 1
}
```

**FinOps Action:**
1. Show which assets were generated vs skipped
2. Report: "生成 2 个新资源，跳过 1 个已有资源"
3. Ask: "素材已生成，要继续合成吗？"

---

### Phase 4: Composition

```bash
clawreel compose \
  --tts assets/tts_xxx.mp3 \
  --images assets/img_001.png assets/img_002.png \
  --music assets/bg_music_xxx.mp3 \
  --hook assets/hook_video_xxx.mp4
```

**Output:**
```json
{
  "path": "output/composed_20260407_123456.mp4",
  "duration": "60s",
  "cost": 0
}
```

---

### Phase 5: Post-Processing

```bash
clawreel post \
  --video output/composed_xxx.mp4 \
  --title "Your video title"
```

---

### Phase 6: Publishing ⚠️ CHECKPOINT

```bash
clawreel publish \
  --video output/final_xxx.mp4 \
  --title "Your title" \
  --platforms xiaohongshu douyin
```

**Required Action:**
1. Ask: "视频已准备就绪，要发布到抖音和小红书吗？"
2. **Wait for explicit confirmation**

---

## FinOps Error Recovery

### When Generation Fails Mid-Way

**❌ DO:** Check what's missing, generate only that
**✅ DO:** Use `clawreel check` to identify missing resources

```bash
# After a partial failure, check what's missing
clawreel check --topic "AI未来趋势"

# Output shows exactly what's missing
{
  "existing": {
    "tts": "assets/tts_xxx.mp3",
    "images": ["assets/img_001.png"],
    "music": null,
    "video": null
  },
  "missing": ["video", "music"],
  "recommendation": "generate_missing"
}

# Only generate the missing ones
clawreel assets --hook-prompt "..." --music-prompt "..."
```

### Cost-Saving Tips

1. **Reuse Images**: If you only changed the script, don't regenerate images
2. **Use Edge TTS First**: Test with free Edge TTS, upgrade to MiniMax for final
3. **Batch Similar Topics**: Group similar video topics to reuse background music
4. **Partial Regeneration**: If script changes, only regenerate TTS (not images/video)

---

## Cost Estimation Reference

| Resource | Approximate Cost (CNY) |
|----------|------------------------|
| T2V Video (6s) | ¥0.5 - ¥1.0 |
| Image | ¥0.1 - ¥0.2 |
| Music | ¥0.3 - ¥0.5 |
| TTS (MiniMax) | ¥0.1 / 100 chars |
| TTS (Edge) | Free |

**Tip:** A full video (1 T2V + 3 images + 1 music + TTS) costs approximately ¥1-2.

---

## Complete FinOps Workflow Example

**User says:** "帮我做一个关于AI未来趋势的短视频"

**Agent execution:**

```bash
# Step 0: ALWAYS check first (zero cost)
clawreel check --topic "AI未来趋势"

# Output:
# {
#   "existing": {},
#   "recommendation": "generate_all",
#   "cost_estimate": "¥1.5"
# }

# Ask user
# "当前项目没有资源，预计成本 ¥1.5。要开始生成吗？"
# [User confirms]

# Phase 1: Generate script (only if needed)
clawreel script --topic "AI未来10年趋势"

# [User approves]

# Phase 2: Generate TTS (only if needed)
clawreel tts --text "大家好，今天聊聊AI..."

# Phase 3: Generate assets (only if needed)
clawreel assets \
  --hook-prompt "未来科技城市" \
  --image-prompt "AI科技概念图" \
  --count 3

# [User approves]

# Phase 4-6: Compose, Post, Publish
# ...
```

### When User Returns for Same Topic

```bash
# Step 0: Check what exists
clawreel check --topic "AI未来趋势"

# Output:
# {
#   "existing": {
#     "script": "assets/script_xxx.json",
#     "tts": "assets/tts_xxx.mp3",
#     "images": ["assets/img_001.png", "assets/img_002.png", "assets/img_003.png"],
#     "music": "assets/music_xxx.mp3"
#   },
#   "recommendation": "use_existing"
# }

# Ask user
# "发现已有资源：1个脚本、1个配音、3张图片、1段音乐"
# "要复用现有资源直接合成吗？（预计成本 ¥0）"
# [User confirms]

# Skip to composition
clawreel compose --tts assets/tts_xxx.mp3 ...
```

---

## Error Handling

### Command Not Found

```bash
./install.sh
```

### API Key Missing

```json
{"success": false, "error": "API key not found"}
```

**Solution:**
```bash
# Add to .env file
echo "MINIMAX_API_KEY=your_key" >> .env
```

### Generation Failed

```json
{"success": false, "error": "rate limit exceeded"}
```

**Solution:**
1. Check what's missing: `clawreel check --topic "topic"`
2. Generate only the failed resource
3. Do NOT regenerate everything

### Partial Success

If only some assets were generated:

```bash
# Check what we have
clawreel check --topic "topic"

# Generate only missing
clawreel assets --hook-prompt "..." --music-prompt "..."
```

---

## Configuration File (config.yaml)

```yaml
minimax:
  api_key: "${MINIMAX_API_KEY}"
  models:
    t2v: "MiniMax-Hailuo-02"
    i2v: "MiniMax-Hailuo-2.3-Fast"
    image: "image-01"
    tts: "speech-2.8-hd"
    music: "music-2.5+"

tts:
  active_provider: "edge"  # Use edge for cost saving
  providers:
    minimax:
      voice_id: "female-shaonv"
      speed: 1.0
    edge:
      voice_id: "zh-CN-XiaoxiaoNeural"
```

---

## Key Principles

1. **Check Before Generate** - Always run `clawreel check` first (zero cost)
2. **Increment Over Replace** - Generate missing resources, not everything
3. **Show Cost Awareness** - Report what's being generated and what's reused
4. **Respect User Budget** - Ask before expensive operations
5. **Recover Smart** - On failure, only generate what failed
