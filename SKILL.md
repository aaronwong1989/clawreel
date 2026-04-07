---
name: clawreel
description: Use this skill when you need to produce video content — especially short videos, social media clips, or TTS/voiceover audio. Covers the full pipeline: writing scripts, generating AI voiceovers, creating video clips/images, composing background music, and publishing to 抖音 (Douyin) or 小红书 (Xiaohongshu). Also use for music MV production, live-streaming scripts, narration generation, or any request spanning script → voice → video → publish. Does NOT trigger for video playback issues, codec questions, editing existing footage manually, or non-production questions.
---

# ClawReel - AI Video Content Pipeline

## ⚡ FinOps-Optimized Workflow

**Cost Control First**: Always check for existing resources before generating. AI-generated assets are expensive — never regenerate without user confirmation.

---

## Prerequisites

**一键安装：**
```bash
curl -fsSL https://raw.githubusercontent.com/hrygo/clawreel/main/install.sh | bash
```

**安装后确认：**
| Item | Verify Command |
|------|---------------|
| CLI 可用 | `clawreel --help` |
| API Key | 设置环境变量 `MINIMAX_API_KEY` |
| FFmpeg | `ffmpeg -version` |
| Whisper | `whisper --help`（字幕提取需要） |

---

## When to Use This Skill

**✅ Triggers when:**
- User wants to create short videos for social media
- User mentions script, TTS, AI-generated media, video clips
- User says "生成视频", "做短视频", "内容创作", "配音", "写脚本"

**❌ Does NOT trigger for:**
- Video playback issues, codec questions
- Manual editing with Premiere, Final Cut
- Non-production questions

---

## ⚠️ CRITICAL: Resource Check Before Generation

Always check existing resources FIRST — AI assets are expensive, never regenerate without confirmation.

```bash
clawreel check --topic "Your video topic"
clawreel check --topic "Your video topic" --smart
```

**Required Action:**
1. Display existing resources and missing list
2. Show cost_estimate
3. Ask: "发现已有资源 X 个，缺失 Y 个，预计成本 ¥Z。要开始生成吗？"
4. **Wait for decision** before any generation

---

## ⚡ HITL 增强流程（核心改进）

本流程在关键节点暂停，等待人工确认。**通过 Claude Code 对话直接交互**，无需脚本输入。

### 流程总览

```
Phase 0: 资源检查 → 确认
Phase 1: 脚本生成 → 确认
Phase 2: TTS 生成
Phase 3: 素材生成 → 【HITL 图片审核】→ 确认 I2V 首帧 → 确认合成参数
Phase 4: 合成
Phase 5: 后期处理
Phase 6: 发布 → 确认
```

---

## Phase 0: 资源检查 ⚠️ 必做（零成本）

```bash
clawreel check --topic "Your video topic"
clawreel check --topic "Your video topic" --smart
```

**Required Action:**
1. 显示已有/缺失资源
2. 显示成本估算
3. 询问确认后继续

---

## Phase 1: 脚本生成（可选）

```bash
clawreel script --topic "Your video topic"
```

**Required Action:**
1. 向用户展示 title、hooks、script
2. 询问："脚本满意吗？"
3. **等待用户确认**

---

## Phase 2: TTS 生成（可选）

```bash
clawreel tts --text "配音文本" [--provider minimax|edge]
```

| Provider | Cost | Quality |
|----------|------|---------|
| `edge` | Free | Good |
| `minimax` | Paid | High |

---

## Phase 3: 素材生成 + HITL 审核 ⚠️ 关键节点

**第一步：生成图片（先生成，I2V 需要首帧）**

```bash
clawreel assets \
  --hook-prompt "视频开头画面描述" \
  --image-prompt "正文配图描述" \
  --count 9 \
  --music-prompt "背景音乐风格描述" \
  --topic "Your topic" \
  --skip-existing
```

**第二步：HITL 图片审核（必须等待用户确认）**

> ⚠️ 这是 HITL 核心节点。通过 Claude Code 对话直接展示和交互。

生成完成后，**必须**：

1. **展示图片** — 打印所有图片 OSS URL，让用户能看到
2. **询问满意度** — "图片满意吗？[y] 满意 / [r] 重新生成 / [n] 跳过视频"
3. **等待用户回复**，再决定：
   - `[y]` → 进入 I2V 首帧选择
   - `[r]` → 询问如何调整提示词，重新生成
   - `[n]` → 跳过视频，用纯图片合成

**第三步：I2V 首帧选择（满意后）**

> ⚠️ 必须等用户选择，不能随机取第一张。

向用户展示：
- Agent 推荐哪张图做 I2V 首帧（给出理由）
- 所有图片 URL 列表
- 询问："请选择 I2V 首帧图片 [1-9]（直接回车使用推荐图片 1）"

**第四步：确认合成参数（图片满意后）**

询问用户：
- 转场类型：`[1] fade（淡入淡出）/ [2] slide_left / [3] zoom / [4] 无转场`
- 图片数量：`[3-15]`（建议 TTS时长/5 张）

---

## Phase 4: 合成

**多图转场合成** — 支持 fade/slide/zoom 等 FFmpeg xfade 转场，大幅提升视觉丰富度：

```bash
clawreel compose \
  --tts assets/tts_topic.mp3 \
  --images assets/img_001.png assets/img_002.png ... \
  --music assets/bg_music_topic.mp3 \
  --hook assets/hook_video_topic.mp4
```

**转场参数（通过 CLI 参数扩展）：**
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--transition` | fade | 转场类型：fade / slide_left / slide_right / zoom / none |
| `--img-count` | 9 | 正文使用图片数量 |

**多图 vs 单调对比：**

| 方式 | 图片数 | 视觉体验 |
|------|--------|---------|
| 旧方式 | 3张 | 每张图停留 ~17s，切换生硬 |
| 新方式 | 9-15张 | 每张 ~3-5s，fade 转场，流畅丰富 |

---

## Phase 5: 后期处理

```bash
clawreel post \
  --video output/composed_topic.mp4 \
  --title "Your video title"
```

- **字幕烧录**：Whisper 语音识别（medium 模型）+ FFmpeg subtitles 滤镜烧录硬字幕
- AIGC 水印（如已配置）

### 字幕烧录一键命令

```bash
# Whisper 提取字幕 + 烧录硬字幕（推荐，默认 medium 模型）
clawreel burn-subs -v input.mp4

# 指定模型和语言
clawreel burn-subs -v input.mp4 --model large --language zh

# 已有 SRT，直接烧录（跳过 Whisper 提取）
clawreel burn-subs -v input.mp4 --srt existing.srt
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--model` | medium | Whisper 模型：tiny/base/small/medium/large |
| `--language` | auto | 语言代码：auto/zh/en/ja/ko 等 |
| `--srt` | 自动生成 | 指定已有 SRT，跳过 Whisper 提取 |
| `--word-timestamps` | False | 词级时间戳（更精准但 SRT 较大） |

> **Whisper 模型推荐**：烧录字幕用 `medium`（已安装），正式作品用 `large`。

---

## Phase 6: 发布 ⚠️ 确认节点

```bash
clawreel publish \
  --video output/final_topic.mp4 \
  --title "Your title" \
  --platforms xiaohongshu douyin
```

**Required Action:**
1. 确认视频已就绪
2. 询问："要发布到抖音和小红书吗？"
3. **等待用户明确确认**

---

## FinOps Error Recovery

### 生成中途失败

```bash
clawreel check --topic "topic"
# → 显示缺失资源
clawreel assets --hook-prompt "..." --music-prompt "..." --topic "topic" --skip-existing
```

---

## 完整工作流示例

**用户：** "帮我做一个关于贾丁氏鹦鹉的短视频"

```
你 → Phase 0: clawreel check → 显示资源状态 → 询问确认
用户 → "开始"
你 → Phase 1: clawreel script → 展示脚本 → 询问满意
用户 → "满意"
你 → Phase 2: clawreel tts --provider edge ...
你 → Phase 3:
  1. clawreel assets --count 9 ...
  2. 展示图片 URL → 询问满意？
  用户 → "y"
  3. Agent 推荐 I2V 首帧 → 用户选择 [3]
  4. 询问转场类型和图片数量 → 用户确认
你 → Phase 4: clawreel compose ...
你 → Phase 5: clawreel post ...
你 → 字幕烧录: clawreel burn-subs -v output/composed.mp4
你 → Phase 6: 询问发布 → 用户确认
```

---

## 关键原则

1. **检查优先** — always run `clawreel check` first (zero cost)
2. **增量生成** — 只生成缺失资源
3. **HITL 审核** — Phase 3 图片必须等待用户确认
4. **I2V 首帧必须用户选** — 不能随机取第一张
5. **多图转场** — 正文用 9-15 张图，fade 转场，避免单调
6. **发布确认** — Phase 6 必须等待用户明确确认

---

## 配置参考

```yaml
minimax:
  models:
    t2v: "MiniMax-Hailuo-2.3"
    i2v: "MiniMax-Hailuo-2.3-Fast"
    image: "image-01"
    tts: "speech-2.8-hd"
    music: "music-2.5"

video:
  duration_default: 6

music:
  duration_default: 60
```

**视频模型 Fallback 链：** `MiniMax-Hailuo-2.3 (T2V)` → `MiniMax-Hailuo-2.3-Fast (I2V)` → `MiniMax-Hailuo-02 (T2V)` → `T2V-01 (T2V)`

> I2V 需要首帧图片，MiniMax OSS URL 可直接使用（无需上传）。
