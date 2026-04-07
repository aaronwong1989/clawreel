# ClawReel 语义对齐流水线 — 详细规格说明书

> 目标：声音、字幕、画面三者精确同步，图片内容与语音语义相关。
> 架构：**整洁架构**，全流程基于语义分句，无向后兼容分支。

---

## 1. 核心概念

### 1.1 关键设计原则

1. **TTS 音频来自合成，不是录音**：Edge TTS 的 `WordBoundary` 时间戳是音频合成的副产品，无额外成本，无需 Whisper 重转录
2. **时长由 TTS 实际决定，不是估算**：不依赖字数/语速模型推算，句子的 start/end 直接来自合成时间戳
3. **无向后兼容分支**：`tts_voice` 始终返回词级时间戳，`compose` 始终按语义分段，`cli` 无 dual-path 逻辑
4. **单数据流**：Script → TTS+WordTimestamps → Segments → Images → Compose → Video，每步输出是下一步输入

### 1.2 时间轴

| 名称 | 来源 | 精度 |
|------|------|------|
| **WordTimeline** | Edge TTS `WordBoundary` | ~50ms |
| **SegmentTimeline** | `segment_aligner` 加工 | ~50ms |
| **ClipTimeline** | `composer` 消费 | 秒级 |

---

## 2. 数据结构

### 2.1 WordTimestamp（词级）

```python
class WordTimestamp(TypedDict):
    word: str           # 词文本，如 "你有没有"
    start_sec: float   # 开始时间（秒），如 0.123
    end_sec: float     # 结束时间（秒），如 0.456
    offset_ms: int     # 相对音频开头的毫秒偏移量
```

> 来源：`edge_tts.SubMaker.to_object_list()` 返回值结构

### 2.2 ScriptSegment（脚本段落）

```python
class ScriptSegment(TypedDict):
    index: int          # 段落序号（0-based）
    text: str           # 段落文本（完整句子）
    start_sec: float   # 开始时间（秒），精确值
    end_sec: float     # 结束时间（秒），精确值
    duration_sec: float  # 持续时长（秒）
    image_prompt: str  # 由 text 生成的图片描述
```

> 来源：`segment_aligner.align_segments()` 输出
> **image_prompt 由 text 经过「提纯规则」生成**（见 4.3 节）

### 2.3 ScriptData（增强）

```python
class ScriptData(TypedDict):
    title: str
    script: str         # 完整脚本正文（分句前的原始文本）
    segments: list[ScriptSegment]  # 新增：语义分句 + 时间轴
    hooks: list[str]    # 开头钩子列表
    cta: str            # 结尾号召
```

### 2.4 TTSResult（统一）

```python
class TTSResult(TypedDict):
    audio_path: Path           # 音频文件路径
    srt_path: Path | None     # SRT 字幕文件路径
    word_timestamps: list[WordTimestamp]  # 逐词时间戳（始终返回，无条件）
```

### 2.5 PipelineContext（流水线上下文）

```python
class PipelineContext(TypedDict):
    """贯穿整个流水线的上下文对象，每个阶段消费并丰富它。"""
    title: str
    segments: list[ScriptSegment]          # 始终存在，由 TTS+aligner 填充
    audio_path: Path
    srt_path: Path | None
    image_paths: list[Path]                 # 每段一张图
    music_path: Path | None
    video_path: Path                        # 最终输出
```

---

## 3. 模块规格

### 3.1 `segment_aligner.py`（新文件）

**职责**：将 Edge TTS 逐词时间戳按语义分句，对齐到真实时间轴。

#### 3.1.1 `align_segments(text: str, word_timestamps: list[WordTimestamp]) -> list[ScriptSegment]`

**输入**：
- `text`：TTS 合成的完整文本（与 `word_timestamps` 严格对应）
- `word_timestamps`：Edge TTS SubMaker 返回的词级时间戳列表

**处理流程**：

```
Step 1: 语义分句
  输入: text（完整字符串）
  处理: 按句子边界标记分割
  句子边界: 。 ！？ ！？. ? !
  约束: 合并持续时间 < 1.0 秒的相邻短句（避免图片切换过频）
  输出: list[str] sentences（不含标点）

Step 2: 词级时间戳分配
  输入: sentences, word_timestamps
  处理: 贪心分配
    - 维护游标 cursor，初始 0
    - 累积当前句子词直到词文本结尾标点匹配句子边界标记
    - 记录该句子覆盖的词索引范围 [start_word_idx, end_word_idx]
  输出: list[tuple(sentence_text, start_word_idx, end_word_idx)]

Step 3: 时间轴计算
  输入: 分配结果, word_timestamps
  处理:
    start_sec = word_timestamps[start_word_idx]["start_sec"]
    end_sec   = word_timestamps[end_word_idx]["end_sec"]
    duration  = end_sec - start_sec
  输出: list[ScriptSegment]

Step 4: prompt 提纯
  输入: ScriptSegment["text"]
  处理: 见 4.3 节「图片 prompt 提纯规则」
  输出: ScriptSegment["image_prompt"]
```

**返回**：有序 `ScriptSegment` 列表，每段含精确时间轴。

**前置条件**：`word_timestamps` 必须非空且与 `text` 长度匹配。若不满足，抛出 `ValueError`（不走降级路径）。

#### 3.1.2 `split_long_segments(segments: list[ScriptSegment], max_duration: float = 5.0) -> list[ScriptSegment]`

**职责**：将超长段落（> 5 秒）拆分为多个子段落。

**策略**：
- 按逗号`、`分句（中文场景）
- 每段子段落 ≥ 2.0 秒 才独立
- 保留父段落时间轴，连续子段落之间无缝衔接

#### 3.1.3 `parse_srt_for_align(srt_path: Path) -> tuple[list[SentenceSegment], list[WordTimestamp]]`

**职责**：从 SRT 文件（含 Whisper 输出）反推时间轴，用于 `burn-subs` 场景。

**返回**：
- `list[SentenceSegment]`：SRT 格式的句级段落（不含 word 级）
- `list[WordTimestamp]`：从 SRT 段级时间戳构造的伪词级时间戳（精度降为句级）

> 注：`burn-subs` 场景不追求词级精度，段级已足够。

---

### 3.2 `tts_voice.py`（重构）

#### 3.2.1 `generate_voice()` 签名与返回值

```python
async def generate_voice(
    text: str,
    output_path: Path | None = None,
    voice_id: str | None = None,
    provider: str | None = None,
    srt_path: Path | None = None,
) -> TTSResult
```

**返回值始终为 `TTSResult`**（TypedDict），无条件包含 `word_timestamps`。

#### 3.2.2 MiniMax 分支

MiniMax TTS API 不提供逐词时间戳，因此 `word_timestamps` 返回空列表 `[]`。
调用方检测到空列表时，抛出 `RuntimeError("MiniMax TTS 不支持词级时间戳，请使用 Edge TTS")`。
> **强制要求**：语义对齐流水线必须使用 Edge TTS。

#### 3.2.3 内部实现

```python
async def _generate_edge_voice(
    text: str, output_path: Path, voice_id: str, srt_path: Path,
) -> TTSResult:
    submaker = edge_tts.SubMaker()
    communicate = edge_tts.Communicate(text, voice_id, boundary="WordBoundary")

    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    word_ts = submaker.to_object_list()
    word_timestamps = [
        WordTimestamp(
            word=w["word"],
            start_sec=w["start"],
            end_sec=w["end"],
            offset_ms=w["offset"],
        )
        for w in word_ts
    ]

    return TTSResult(
        audio_path=output_path,
        srt_path=srt_path if srt_path else None,
        word_timestamps=word_timestamps,
    )
```

---

### 3.3 `segment_aligner.py`（新文件）

```python
def align_segments(text: str, word_timestamps: list[WordTimestamp]) -> list[ScriptSegment]:
    """
    将逐词时间戳按语义分句，对齐到真实时间轴。
    前置条件：word_timestamps 必须非空，否则抛出 ValueError。
    """
    ...
```

#### 3.3.1 `split_long_segments()`

```python
def split_long_segments(
    segments: list[ScriptSegment],
    max_duration: float = 5.0,
    min_chunk_duration: float = 2.0,
) -> list[ScriptSegment]:
    """
    将 duration_sec > max_duration 的段落拆分。
    拆分点：逗号、顿号、从句连接词（因为、所以、但是、然而、如果）。
    子段落总时长严格等于父段落时长，无缝衔接。
    """
```

#### 3.3.2 `align_segments()` 算法细节

```
Step 1: 语义分句
  按 SENTENCE_DELIMITERS = {。！？.?!} 分割 text
  合并 duration_sec < 1.0 的相邻短句

Step 2: 词-句分配
  贪心分配词到句子：
    - 遍历 word_timestamps，累积词文本
    - 当累积文本的前缀匹配当前句子文本（允许 2 字符误差）时，确定分配
    - 若某句子未匹配任何词，则均匀分配剩余词

Step 3: 时间轴计算
  start_sec = word_timestamps[start_idx]["start_sec"]
  end_sec   = word_timestamps[end_idx]["end_sec"]

Step 4: prompt 提纯
  详见 4.3 节
```

#### 3.3.3 `parse_srt_segments()`

```python
def parse_srt_segments(srt_path: Path) -> list[ScriptSegment]:
    """
    从 SRT 文件解析句级时间轴（用于 burn-subs 或外部导入场景）。
    word_timestamps 降级为句级精度。
    """
```

---

### 3.4 `script_generator.py`（重构）

#### 3.4.1 M2.7 System Prompt 变更

M2.7 输出 `script` 字段使用 `|` 分隔多句：

```json
{
  "title": "AI觉醒",
  "script": "你有没有想过，未来AI会超越人类？| 就在昨天，一个AI做出了让科学家震惊的事。| 它不仅理解了哲学问题，还主动提出了新的研究方向。",
  "hooks": ["开头钩子1", "开头钩子2"],
  "cta": "关注我，带你看清AI真相"
}
```

#### 3.4.2 `generate_script()` 返回值

```python
class ScriptData(TypedDict):
    title: str
    script: str                       # 用 | 分隔的多句文本
    sentences: list[str]              # 新增：解析后的句子列表（不含 |）
    hooks: list[str]
    cta: str
```

`sentences` 由 `script.split("|")` 解析而来，供流水线后续使用。

---

### 3.5 `composer.py`（重构）

**删除** `compose()`（均分模式），**替换为** `compose_sequential()`。

```python
async def compose_sequential(
    tts_path: Path,
    segments: list[ScriptSegment],
    music_path: Path,
    output_path: Path | None = None,
    transition: Literal["fade", "slide_left", "slide_right", "zoom", "none"] = "fade",
) -> Path:
    """
    按语义分段精确合成。
    每张图持续 segments[i].duration_sec 秒。
    图片内容由 segments[i].image_prompt 生成。
    """
```

**内部流程**：

```
Step 1: 并发生成图片（max_concurrent=3）
  for seg in segments:
    img = generate_image(seg.image_prompt)
  并发控制：asyncio.Semaphore(3)

Step 2: 生成精确时长片段
  for seg, img in zip(segments, image_paths):
    ffmpeg -loop 1 -i img -t {seg.duration_sec} ...

Step 3: FFmpeg concat（变长 clip 拼接）

Step 4: 混音
  TTS 音频 + 背景音乐
  总时长 = segments[-1].end_sec - segments[0].start_sec
```

**必须满足**：`len(segments) >= 2`（至少 2 段才能合成转场），否则抛 `ValueError`。
**必须满足**：`len(segments) >= 2`（至少 2 段才能合成转场），否则抛 `ValueError`。

---

### 3.6 `cli.py`（重构）

#### 3.6.1 简化的命令树

```
clawreel
├── check        # 阶段0：资源扫描
├── script       # 阶段0：脚本生成（输出含 sentences）
├── tts          # 阶段1：配音（始终返回 word_timestamps）
├── assets       # 阶段2：图片生成（由 segments 驱动）
├── compose      # 阶段3：合成（compose_sequential，无 dual-path）
├── post         # 阶段4：后期处理
├── burn-subs    # 字幕烧录（Whisper + FFmpeg）
└── publish      # 阶段5：发布
```

#### 3.6.2 `cmd_tts` 输出变更

```bash
clawreel tts --text "你有没有想过..."
```

```json
{
  "audio_path": "assets/tts_output.mp3",
  "srt": "assets/tts_output.srt",
  "word_timestamps_count": 127
}
```

#### 3.6.3 `cmd_assets` 签名变更

```bash
clawreel assets \
  --segments assets/segments.json \
  --music-prompt "轻快背景音乐" \
  --music-duration 60
```

`--segments` **必填**（无默认值）。无 `--image-prompt`，图片 prompt 从 segments 读取。

#### 3.6.4 `cmd_compose` 签名变更

```bash
clawreel compose \
  --tts assets/tts.mp3 \
  --segments assets/segments.json \
  --images assets/imgs/ \
  --music assets/bg_music.mp3 \
  --transition fade
```

`--segments` **必填**。删除 `--img-count`、`--hook` 等均分时代参数。

#### 3.6.5 新增 `cmd_align`

```bash
clawreel align --text "你有没有想过..." --tts assets/tts.mp3
```

独立命令：给定文本+TTS音频，直接输出对齐后的 segments JSON（不含图片生成）。
用于调试和外部系统集成。

---

## 4. 详细算法

### 4.1 句子边界检测（segment_aligner）

```python
SENTENCE_DELIMITERS = frozenset("。！？.?!")
SHORT_SEGMENT_THRESHOLD = 1.0  # 秒
SHORT_SEGMENT_MERGE_WINDOW = 3.0  # 合并后总时长上限
```

**分句伪代码**：
```
Input: text
Output: list[(sentence_text, delimiter_char)]

1. 遍历 text chars，维护 current_sentence = ""
2. 若 char ∈ SENTENCE_DELIMITERS:
     sentence_list.append((current_sentence, char))
     current_sentence = ""
3. 否则: current_sentence += char
4. 收尾: 若 current_sentence 非空，加入 list
5. 后处理:
     - 过滤空句（len < 2）
     - 去除标点前后空格
     - 合并持续时长 < SHORT_SEGMENT_THRESHOLD 的相邻短句
       （贪婪合并直到 group_duration >= SHORT_SEGMENT_THRESHOLD）
```

### 4.2 词-句时间对齐（segment_aligner）

```python
def align_words_to_sentences(sentences, word_timestamps) -> list[tuple]:
    """
    贪心分配：每个句子收集连续词，直到句子文本的结尾词被匹配。
    关键：句子文本来自原始 text，与 word_timestamps 中的 word 严格对应。
    """
    cursor = 0
    result = []

    for sentence_text, _ in sentences:
        expected_words = sentence_text  # 期望匹配的连续词序列

        # 向前累加词，直到拼接文本前缀匹配 expected_words
        accumulated_words = []
        accumulated_text = ""
        while cursor < len(word_timestamps):
            w = word_timestamps[cursor]["word"]
            accumulated_text += w
            accumulated_words.append(cursor)

            # 模糊匹配：expected 是 accumulated 的前缀（允许 2 字符误差）
            if accumulated_text.startswith(expected_words[:len(accumulated_text)+2]):
                # 找到匹配，记录索引范围
                result.append((sentence_text, accumulated_words[0], accumulated_words[-1]))
                cursor += 1
                break
            cursor += 1
        else:
            # 未匹配到，fallback：均匀分配剩余词
            chunk_size = max(1, len(word_timestamps) // len(sentences))
            result.append((sentence_text, cursor, min(cursor + chunk_size - 1, len(word_timestamps)-1)))

    return result
```

### 4.3 图片 Prompt 提纯规则

```python
def refine_image_prompt(segment_text: str) -> str:
    """
    将句子文本转换为图片生成 prompt。
    规则：
    1. 去除语气词（啊、吧、呢、呀、哦、嗯、嘛、哈、呢、哇）
    2. 去除问句结构（转为描述场景）
       "你有没有想过..." → "一个深邃的哲学思考场景"
    3. 提取关键实体和动作（名词/动词优先）
    4. 限制长度 50-200 字
    5. 补充画面风格和质量标签
    """
    # Step 1: 移除语气词
    filler_words = ["啊", "吧", "呢", "呀", "哦", "嗯", "嘛", "哈", "哇", "嘛", "呃", "噢"]
    cleaned = segment_text
    for fw in filler_words:
        cleaned = cleaned.replace(fw, "")

    # Step 2: 问句转描述
    question_prefixes = ["有没有", "是不是", "能不能", "会不会", "为什么", "怎么", "什么"]
    for qp in question_prefixes:
        if cleaned.startswith(qp):
            cleaned = f"一个关于{segment_text[len(qp):]}的视觉场景"
            break

    # Step 3: 截断超长文本
    if len(cleaned) > 150:
        cleaned = cleaned[:150] + "..."

    # Step 4: 补充画面质量标签
    style_suffix = "，电影感，高质量，9:16 竖屏，视觉冲击力强"
    return f"短视频画面：{cleaned}{style_suffix}"
```

### 4.4 时长超限拆分（segment_aligner）

```python
MAX_SEGMENT_DURATION = 5.0  # 秒
MIN_CHUNK_DURATION = 2.0    # 秒

def split_long_segments(segments: list[ScriptSegment]) -> list[ScriptSegment]:
    """
    将 duration_sec > MAX_SEGMENT_DURATION 的段落拆分。
    拆分点：逗号（,）、顿号（、）、从句连接词（因为、所以、但是、然而、如果）
    """
    CHUNK_DELIMITERS = ["，", "、", "因为", "所以", "但是", "然而", "如果", "不过"]
    result = []
    for seg in segments:
        if seg.duration_sec <= MAX_SEGMENT_DURATION:
            result.append(seg)
            continue

        # 按 CHUNK_DELIMITERS 拆分
        sub_texts = _split_by_delimiters(seg.text, CHUNK_DELIMITERS)
        sub_durations = _distribute_duration(
            seg.duration_sec, len(sub_texts), MIN_CHUNK_DURATION
        )

        for i, (sub_text, sub_dur) in enumerate(zip(sub_texts, sub_durations)):
            sub_start = seg.start_sec + sum(sub_durations[:i])
            result.append(ScriptSegment(
                index=seg.index * 100 + i,  # 子段落用派生索引
                text=sub_text,
                start_sec=sub_start,
                end_sec=sub_start + sub_dur,
                duration_sec=sub_dur,
                image_prompt=refine_image_prompt(sub_text),
            ))

    return result
```

---

## 5. 错误处理

**原则：Fail Fast，不设降级路径。**

| 错误场景 | 处理方式 |
|----------|----------|
| `word_timestamps` 为空（MiniMax TTS） | 抛 `RuntimeError`，提示使用 Edge TTS |
| `word_timestamps` 与 `text` 长度差异 > 10% | 抛 `ValueError`，明确告知数据不一致 |
| `len(segments) < 2` | 抛 `ValueError`，至少需要 2 段才能合成 |
| 图片生成失败 | 抛 `RuntimeError`（不 retry，不 fallback） |
| 句子数 > 30 | 抛 `ValueError`，建议拆分脚本 |
| `segment.duration_sec == 0` | 抛 `ValueError`，该 segment 无有效时长 |

---

## 6. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `clawreel/segment_aligner.py` | **新增** | 词级时间戳 → 语义分段对齐 |
| `clawreel/tts_voice.py` | **重构** | 返回 TTSResult（含 word_timestamps），删除 tuple 返回 |
| `clawreel/script_generator.py` | **重构** | prompt 引导 `|` 分隔，`sentences` 字段 |
| `clawreel/composer.py` | **重构** | 删除 `compose()`，替换为 `compose_sequential()` |
| `clawreel/cli.py` | **重构** | 删除均分时代参数，新增 `--segments`/`--align` 命令 |
| `clawreel/image_generator.py` | **修改** | 新增 `generate_segment_images()`（并发分图）|
| `tests/test_segment_aligner.py` | **新增** | 单元测试 |
| `tests/test_tts_voice.py` | **修改** | 更新返回值断言 |
| `tests/test_segment_aligner.py` | 新增 | 单元测试 |
| `tests/test_tts_voice.py` | 修改 | 新增 word_timestamps 相关用例 |

---

## 8. 依赖变更

**新增依赖**：
- `difflib`（标准库，无需安装）——用于文本相似度匹配

**无需新增第三方包**：
- 词级时间戳：Edge TTS 自带，无需 `whisper-timestamped`
- 分句：纯字符串操作，无需 NLTK

---

## 9. 性能目标

| 指标 | 目标 |
|------|------|
| 词-句对齐延迟 | < 100ms（纯计算，无 IO） |
| 60 秒视频合成总时间 | ≤ 90 秒（并发图片生成 + FFmpeg）|
| 图片并发数 | 3（API 限流保护）|
| 内存峰值 | < 500MB（无大对象缓存）|

---

## 10. 测试策略

### 单元测试

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_segment_aligner.py` | 句子分界、词-句对齐、超长拆分、prompt 提纯 |
| `test_tts_voice.py` | `TTSResult` 返回值结构（audio_path + word_timestamps 非空）|

### 集成测试

| 场景 | 验证点 |
|------|--------|
| `clawreel tts` | 返回 `word_timestamps_count > 0` |
| `clawreel align` | 输出 segments 时间轴单调递增，`duration_sec` 之和 ± 0.1s 内匹配 TTS 时长 |
| `clawreel compose` | 最终视频时长 ± 0.5s 内匹配 `segments[-1].end_sec` |
| 错误：MiniMax TTS | 抛 `RuntimeError`，提示使用 Edge TTS |
| 错误：`segments < 2` | 抛 `ValueError` |

---

## 11. 实施状态

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 1 | segment_aligner.py | ✅ 完成 |
| Phase 1 | test_segment_aligner.py（18 测试） | ✅ 完成 |
| Phase 2 | tts_voice.py（TTSResult，word_timestamps） | ✅ 完成 |
| Phase 2 | test_tts.py 更新 | ✅ 完成 |
| Phase 3 | composer.py（compose_sequential） | ✅ 完成 |
| Phase 4 | image_generator.py（generate_segment_images） | ✅ 完成 |
| Phase 5 | script_generator.py（M2.7 prompt 变更） | ✅ 完成 |
| Phase 6 | cli.py（命令树重构） | ✅ 完成 |
| Phase 7 | 端到端集成测试 | ⏳ 待验证 |
| Phase 7 | README.md / SKILL.md | ⏳ 待更新 |

```
