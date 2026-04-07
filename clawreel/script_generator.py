"""阶段0：脚本生成 — 使用 MiniMax M2.7 生成口播脚本。

M2.7 通过 Anthropic 兼容接口调用，端点：/anthropic/v1/messages
script 字段使用 | 分隔多句，供语义对齐流水线使用。
image_prompts 与 sentences 一一对应，由 LLM 根据每句内容生成专业配图提示词。
"""
import json
import logging
from typing import TypedDict

from .api_client import call_anthropic_api

logger = logging.getLogger(__name__)


class ScriptData(TypedDict):
    """生成的脚本数据结构（含语义分句及配图提示词）。"""
    title: str
    script: str             # 用 | 分隔的多句文本
    sentences: list[str]     # 解析后的句子列表（不含 |）
    hooks: list[str]        # 钩子列表
    cta: str                # 结尾号召
    image_prompts: list[str]  # 与 sentences 一一对应的配图提示词


SYSTEM_PROMPT = """你是一位抖音内容创作专家。请根据用户给定的主题，生成适合抖音口播的短视频脚本。

输出格式（JSON，必须严格遵循）：
{
  "title": "视频标题（吸引眼球，20字以内）",
  "script": "口播脚本正文，用 | 分隔多句，每句独立表达一个完整意思，如：你有没有想过未来会改变？| 就在昨天，一件事震惊了所有人。| 看完你就会有答案。",
  "hooks": ["开头钩子1：3秒抓人", "开头钩子2：悬念或痛点"],
  "cta": "结尾号召行动（如：关注我，带你xxx）",
  "image_prompts": ["第1句对应的配图提示词，描述画面场景，要求生动具体，与句子内容高度相关，包含艺术风格和质量标签，如：一只金黄色羽毛的鹦鹉站在热带树枝上，阳光穿透羽毛，摄影作品质感，电影感，9:16竖屏", "第2句对应的配图提示词", "第3句对应的配图提示词", "..."]
}

要求：
- script 字段必须使用 | 作为句子分隔符，每句表达一个完整语义
- 每句长度建议 5-20 字，不要过长
- hooks 是开头用的高能片段，要有冲击力
- script 要口语化，像真实说话
- image_prompts 数量必须与 script 被 | 分割后的句子数量完全一致
- 每条 image_prompt 要描述具体画面场景，融入句子关键词，艺术风格明确（如：摄影作品质感、电影感人、动漫风格等），包含 9:16 竖屏构图要求
- 不要使用 emoji"""


async def _generate_script_content(topic: str) -> str:
    """调用 MiniMax M2.7 API 生成脚本内容。"""
    return await call_anthropic_api(
        prompt=topic,
        model="MiniMax-M2.7",
        system=SYSTEM_PROMPT,
        max_tokens=8192,
        temperature=0.7,
    )


async def _parse_script(topic: str) -> ScriptData:
    """调用 API 并解析 JSON 脚本。"""
    raw = await _generate_script_content(topic)
    text = raw.strip()
    start_idx = text.find('{')
    end_idx = text.rfind('}')

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]

    data = json.loads(text)
    for field in ("title", "script", "hooks", "cta", "image_prompts"):
        if field not in data:
            raise ValueError(f"脚本缺少字段: {field}")

    script_str = str(data["script"])
    sentences = [s.strip() for s in script_str.split("|") if s.strip()]
    image_prompts = list(data["image_prompts"])

    if len(image_prompts) != len(sentences):
        logger.warning(
            "⚠️ image_prompts 数量（%d）与 sentences 数量（%d）不一致，截断对齐",
            len(image_prompts), len(sentences),
        )
        image_prompts = image_prompts[:len(sentences)]

    return ScriptData(
        title=str(data["title"]),
        script=script_str,
        sentences=sentences,
        hooks=list(data["hooks"]),
        cta=str(data["cta"]),
        image_prompts=image_prompts,
    )


async def generate_script(topic: str) -> ScriptData:
    """生成口播脚本（含配图提示词）。

    Args:
        topic: 视频主题

    Returns:
        ScriptData，包含 title、script、sentences、hooks、cta、image_prompts
    """
    logger.info("📝 正在生成脚本，主题: %s", topic)
    result = await _parse_script(topic)
    logger.info(
        "✅ 脚本生成完成: %s（%d 句，配图提示词 %d 条）",
        result["title"], len(result["sentences"]), len(result["image_prompts"])
    )
    return result
