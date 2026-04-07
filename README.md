![ClawReel Hero](assets/hero.png)

# ClawReel: The AI Short-Video Production Factory

> **从创意到发布，只需一次对话。**
> 这是一个专为 **AI 智能体 (Agents)** 打造的**智能体驱动 / 分段编排式**短视频全链路流水线。

---

## 💡 为什么选择 ClawReel？ (Utility & Value)

### 对于人类创作者 (For Humans: Control & Efficiency)
*   **极致高效**：分钟级生成涵盖 脚本、配音、视频、配图与背景音乐 的高质量短视频。
*   **完全掌控 (HITL)**：拒绝“黑盒同步生成”，每个阶段（脚本、素材、合成）均设有审核点，确保内容符合预期。
*   **成本透明 (FinOps)**：内置资源查重与复用逻辑，通过 `check` 命令智能判定，平均节省 50%-80% 的模型调用成本。

### 对于 AI 智能体 (For Agents: Standard & Reliability)
*   **标准化接口**：全量 CLI 命令支持，输出统一为极其易读的 **JSON** 格式。
*   **安全中断协议**：专为 Agent 优化，主动暴露 Checkpoints，方便智能体在关键步骤请求人类授权。
*   **跨环境部署**：一键安装脚本，自动适配 Claude Code, OpenCode, OpenClaw 等多种环境。

---

## 🔄 工作流 (The Workflow)

ClawReel 将复杂的视频制作解构为 5 个原子化的阶段，支持断点续作与资源复用：

```mermaid
graph LR
    A[Stage 0: Script] --> B[Stage 1: TTS]
    B --> C[Stage 2: Assets]
    C --> D[Stage 3: Compose]
    D --> E[Stage 4: Publish]
    
    style A fill:#f9f,stroke:#333,stroke-width:2px
    style E fill:#00ff00,stroke:#333,stroke-width:2px
```

1.  **脚本生成**：基于主题生成爆款剧本、口播词及视觉提示词。
2.  **语音合成**：多供应商支持 (MiniMax / Edge)，灵活切换音质与成本。
3.  **视觉与音频素材**：并行请求 T2V 视频、AI 绘图与 AI 音乐，支持旧资源智能重用。
4.  **合成与后处理**：FFmpeg 驱动的精准对齐、转场与音视频合并。
5.  **多平台分发**：支持一键推送到 抖音、小红书 等主流平台。

---

## 🌟 核心特性

-   **即插即用 CLI**：通过 `pip install -e .` 安装后，可在任何工作空间直接调用 `clawreel` 命令。
-   **FinOps 深度优化**：
    -   `clawreel check`: 零成本扫描物理资源与语义匹配。
    -   `clawreel assets --skip-existing`: 自动跳过已存在的素材，防止高昂的 API 重复调用。
-   **策略模式驱动**：分发平台集成完全采用注册字典形式，易于扩展新渠道（如微信视频号）。
-   **网络层解耦**：所有 API 统一收束，支持异步轮询封装，消除冗余代码。

---

## 🚀 快速开始

### 1. 一键安装
你可以使用我们提供的安装脚本，它会自动配置环境、部署 CLI 并安装智能体技能：

```bash
# 进入项目目录执行
./install.sh
```

### 2. 初始化配置
项目会在执行目录下寻找 `.env` 和 `config.yaml`。
```bash
# 创建并填入你的 API Key
cp .env.example .env
```

### 3. 开始创作
```bash
# 智能体建议首先执行 Check (零成本)
clawreel check --topic "AI未来10年"

# 依次执行管线
clawreel script --topic "AI未来10年"
clawreel tts --text "..."
clawreel assets --hook-prompt "..." --image-prompt "..." --count 3 --music-prompt "..."
clawreel compose --tts ... --images ... --music ... --hook ...
clawreel publish --video ... --title "..." --platforms xiaohongshu douyin
```

---

## 📖 技能集成指南 (For Agents)

如果你是 AI 助理，请务必详细阅读 [**SKILL.md**](./SKILL.md)。

> [!IMPORTANT]
> **财务责任制**：生成视频、图片和音乐是有成本的。在调用 `assets` 之前，必须先通过 `check` 展示现有资源，并向用户确认支出意愿。

---

## 🛠️ 技术栈

*   **Logic**: Python 3.10+, FFmpeg
-   **AI Providers**: MiniMax (Vision/TTS), Microsoft Edge TTS
*   **Design Patterns**: Strategy, Factory, HITL Workflow

---

© 2026 ClawReel Team. Built for the Agentic Era.
