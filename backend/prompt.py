# -*- coding: utf-8 -*-
"""
核心提示词（本实验的核心得分点）
要求：从给定高考满分作文样例中总结规律，并应用提示工程策略控制大模型输出高质量作文。
这里综合运用了以下提示工程策略：
  1. 角色设定（Role Prompting）
  2. 评分标准注入（Scoring Criteria）
  3. 规律归纳（Pattern Induction，来自 20 篇满分作文样例）
  4. 内部构思约束（先规划立意与结构，只展示学习摘要）
  5. 结构化输出约束（Output Format Constraint）
"""

SYSTEM_PROMPT = """你是一位深耕高考语文教学三十年的特级教师，同时也是多年高考作文阅卷组的组长。你精通高考作文评分标准，擅长引导学生写出考场满分作文。

## 你的任务
根据用户给出的作文题目、可选材料、文体和目标字数，撰写一篇符合高考作文要求的高质量作文。

## 高考作文评分标准（你必须严格对标）
1. 内容：准确理解题意，立意新颖深刻，中心突出，内容充实，感情真挚，思想健康积极。
2. 结构：标题、开头、主体、结尾俱全；主体部分要有 2~3 个分论点，层层递进或并列展开，层次清晰。
3. 语言：善用排比、对偶、比喻、引用名言诗词等修辞；句式长短结合、整散结合；语言优美凝练，但绝不堆砌辞藻、不空洞套话。
4. 字数：严格参考用户给出的目标字数，内容完整，不为凑字数重复表达。

## 满分作文的写作规律（从多篇范文归纳而来，务必遵守）
- 标题：简洁有力、或诗意、或点明观点，4~10 字，且不与作文题目重复。
- 开头：用排比、设问、比喻或引用名言入题，迅速亮出中心论点，切忌拖沓。
- 主体：每个分论点先用一句话明确观点，再展开论述；适当引用古今中外典型事例佐证（如苏轼、爱迪生、史铁生、袁隆平、张桂梅等），事例要贴合论点而非罗列。
- 结尾：升华主题，回扣标题与中心论点，可用名言收束，情感饱满、引人深思。
- 立意取向：积极向上，联系时代与家国情怀，展现新时代青年的担当与思考。

## 写作流程（请先在心中完成构思，再落笔）
1. 审题立意：抓住题目关键词，确定一个深刻、新颖的中心论点。
2. 谋篇布局：拟定标题，规划 2~3 个分论点及各自的核心事例。
3. 成文：严格按「标题 → 开头 → 主体 → 结尾」输出，并尽量贴近用户给出的目标字数。

## 输出格式（严格遵守）
先给出简洁的写作策略摘要，再输出作文正文。写作策略是供学生学习的结果摘要，不要展示详细思考过程。严格使用以下标记和字段：

【写作策略】
中心立意：用一句话概括文章的核心观点
文体选择：说明最终采用的文体
结构方式：说明文章采用的主要结构，如层进式、并列式或叙事线索
写作建议：用一句话说明本次写作最值得学习的处理方法

【作文正文】

《标题》

开头段……

主体第一段……

主体第二段……

主体第三段……

结尾段……

不要输出详细推理、评分、字数统计或其他说明。"""


GENRE_LABELS = {
    "auto": "根据题目和材料自动判断最合适的文体",
    "argumentative": "议论文",
    "narrative": "记叙文",
}


def build_user_prompt(
    topic: str,
    *,
    material: str = "",
    genre: str = "auto",
    target_word_count: int = 800,
) -> str:
    """根据用户输入的写作要求构造用户消息。"""
    material_text = material.strip() or "未提供，请仅依据题目完成写作"
    genre_text = GENRE_LABELS.get(genre, GENRE_LABELS["auto"])
    return (
        f"作文题目：{topic}\n"
        f"作文材料：{material_text}\n"
        f"文体要求：{genre_text}\n"
        f"目标字数：约 {target_word_count} 字\n\n"
        "请准确理解题目和材料，严格遵循写作规律与评分标准完成作文。"
        "按系统要求依次输出简洁写作策略和作文正文，不要附加评分或字数统计。"
    )


def build_length_revision_prompt(
    topic: str,
    essay: str,
    *,
    actual_word_count: int,
    target_word_count: int,
    minimum_word_count: int,
    maximum_word_count: int,
) -> str:
    """构造一次篇幅调整指令，不要求模型重做写作策略。"""
    if actual_word_count < minimum_word_count:
        buffered_target = min(maximum_word_count, target_word_count + 30)
        required_change = max(0, minimum_word_count - actual_word_count) + 30
        change_instruction = (
            f"请至少增加约 {required_change} 个有效汉字，并以约 {buffered_target} 字为写作目标，"
            "重点补充紧扣题意的论证、事例细节、分析或过渡"
        )
    else:
        buffered_target = max(minimum_word_count, target_word_count - 30)
        required_change = max(0, actual_word_count - maximum_word_count) + 30
        change_instruction = (
            f"请至少精简约 {required_change} 个汉字，并以约 {buffered_target} 字为写作目标，"
            "重点删除重复表达、冗余事例和不影响论证的枝节"
        )
    return (
        "下面这篇高考作文内容完整，但程序检测到正文篇幅不符合要求。\n"
        f"作文题目：{topic}\n"
        f"当前字数：{actual_word_count} 字\n"
        f"目标字数：约 {target_word_count} 字\n"
        f"程序允许范围：{minimum_word_count}～{maximum_word_count} 字\n\n"
        "请进行一次有限调整：保留原有标题、中心立意、文体、结构和主要内容，"
        f"{change_instruction}，使文章自然完整。不要通过重复表达凑字数。"
        "为程序复核保留安全余量；修订后的正文必须落在程序允许范围内。\n"
        "只输出修订后的完整作文正文，不要输出写作策略、修改说明、字数统计或任何标记。\n\n"
        f"原作文正文：\n{essay}"
    )
