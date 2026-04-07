---
name: clawreel
description: Orchestrate the end-to-end AI video content production pipeline with Human-In-The-Loop (HITL) checkpoints.
---

# Content Pipeline HITL


## Workflow Overview

The production process is divided into 5 stages. You MUST pause and obtain user approval after Stage 0 and Stage 2 before proceeding to the final composition and publishing.

### Stage 0: Script Generation
1. **Analyze**: Understand the user's topic or requirements.
2. **Execute**: Run `clawreel script --topic "[Topic]"`
3. **Review**: Present the Title, Hooks, and Script to the user.
4. **Checkpoint**: Wait for user approval or feedback. If feedback is provided, re-run with adjusted topic/parameters.

### Phase 1 & 2: Audio & Assets Generation
1. **TTS**: Run `clawreel tts --text "[Script]"`
2. **Assets**: Run `clawreel assets --hook-prompt "[Hook Prompt]" --image-prompt "[Image Prompt]"`
    - Use the first hook from the script for `--hook-prompt`.
    - Use the core script visual description for `--image-prompt`.
3. **Review**: Present the file paths (and descriptions if available) to the user.
4. **Checkpoint**: Ask if the assets (Video, Images, Music) look good.

### Phase 3 & 4: Composition & Post-Processing
1. **Compose**: Run `clawreel compose --tts [TTS Path] --images [Image Path1] [Image Path2]... --music [Music Path] --hook [Video Path]`
2. **Post**: Run `clawreel post --video [Composed Path] --title "[Title]"`
3. **Review**: Show the final output path to the user.

### Phase 5: Publishing
1. **Wait**: Explicitly ask "Should I publish this to Douyin and Xiaohongshu?"
2. **Execute**: Run `clawreel publish --video [Final Path] --title "[Title]"`

## Key Paths & Tools
- Global CLI: `clawreel`
- Output Dir: `assets/` and `output/` (generated relative to your current execution space)

## Guidelines
- **Always be transparent**: Tell the user which stage you are entering.
- **Show, don't just tell**: When a script is generated, display it clearly.
- **Respect Feedback**: If the user wants a change, don't just push forward. Refactor the prompt or parameters and try again.
