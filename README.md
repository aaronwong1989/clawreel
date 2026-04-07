# AI Content Pipeline (HITL Skill)

这是一个专为 AI 智能体（如 Antigravity）打造的**非交互式短视频内容生成流水线**。该项目采用 **Agent-Driven HITL (Human-In-The-Loop)** 编排模式，并严格遵循 **DRY** 与 **SOLID** 设计原则进行深度解耦。

## 🌟 核心特性

- **分段式 Agent 编排 (HITL)**：摒弃传统阻塞式的控制台 `input()`，流水线被拆分为 5 个独立的阶段命令，由上层 Agent（智能体）主动发起调用并在每个阶段向人类请求审核。
- **DRY & SOLID 架构**：
  - **网络层统一**：所有第三方 API 调用统一收束于底层 `api_client`。
  - **异步任务池**：提取了通用的异步任务轮询封装 `poll_async_task`，大幅消除了视频与音乐轮询的重复代码。
  - **策略模式 (Strategy Pattern)**：分发平台集成完全采用注册字典形式解耦，任意扩充平台（如增加微信视频号）而不改动核心发布逻辑。
- **多提供商灵活性**：深度集成了 MiniMax 视觉系列（Hailuo T2V/I2V）与多路 TTS，且均在 `config.yaml` 中进行参数化管理。

---

## 🛠️ 环境依赖

确保环境为 `Python 3.12+`，并已安装依赖：

```bash
pip install -r requirements.txt
```

---

## ⚙️ 配置文件 (`config.yaml`)

项目摒弃了硬编码，采用统一的 YAML 进行设置管理（包含多 TTS 供应商独立配置）：

```yaml
tts:
  active_provider: "edge"          # 当前激活的 TTS 供应商: "minimax" 或 "edge"
  providers:
    minimax:
      voice_id: "female-shaonv"
      speed: 1.0
      vol: 1.0
      emotion: "happy"
    edge:
      voice_id: "zh-CN-XiaoxiaoNeural"
```
> **注意**：大模型 API Key（MiniMax）需通过环境变量 `MINIMAX_API_KEY` 注入。

---

## 🚀 智能体 CLI 接口 (`aishell_pipeline.py`)

智能体或外部调度器通过本项目的 `scripts/aishell_pipeline.py` 实现全链路自动化，所有输出均被格式化为极其容易解析的 **JSON 标准格式**。

### Stage 0: 脚本生成
自动生成涵盖标题、口播正文、Hooks 的爆款剧本。
```bash
python scripts/aishell_pipeline.py script --topic "未来10年AI对打工人的影响"
```

### Stage 1: 配音生成
采用 `config.yaml` 激活的 TTS 构建底层语音。
```bash
python scripts/aishell_pipeline.py tts --text "我是生成的配音..."
```

### Stage 2: 素材生成 (并行提取)
并行请求 T2V 视频钩子、正文配图及背景音乐。
```bash
python scripts/aishell_pipeline.py assets --hook-prompt "赛博朋克风格的机器人工厂" --image-prompt "未来城市" --count 3
```

### Stage 3: 音视频合成
集成 FFmpeg 对阶段一/二的素材进行对齐、音轨合并与最终转场。
```bash
python scripts/aishell_pipeline.py compose --tts path/to/tts.mp3 --images img1.png img2.png --music music.mp3 --hook hook.mp4
```

### Stage 4: 发布 (Publisher Strategies)
依据 OCP 原则拓展而来的策略分发器，将成品推送至主流社交平台。
```bash
python scripts/aishell_pipeline.py publish --video output/final.mp4 --title "视频标题" --platforms xiaohongshu douyin
```

---

## 📖 技能集成指南 (For Agents)

如果你是一个系统智能体，可以调用项目根目录下的 [`SKILL.md`](./SKILL.md) 了解你在协助流中应尽的**审核中止协议**（Prompt Checkpoints）。在开始阶段任务后，应当展示阶段核心产出（如文本脚本、合成预览）并向用户确认，获得授权后方可执行后续 CLI 操作。
