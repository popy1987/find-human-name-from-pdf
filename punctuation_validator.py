"""标点符号校验模块，基于 GB/T 15834-2011《标点符号用法》国家标准。

依据标准第 5 章「标点符号的位置和书写形式」及附录 A/B：
- 5.1.1–5.1.2：点号（句号、逗号、顿号、分号、冒号、问号、叹号）占一个字位置，采用全角形式
- 5.1.6：连接号分为短横线 -、一字线 —、浪纹线 ～；破折号用 —
- 5.1.7：间隔号占半个字；4.14.3.5 阿拉伯数字月日间用半角间隔号
- 5.1.9：分隔号占半个字
- 中文语境使用全角标点，外文/数字语境使用半角标点；全角标点两旁不得空半角空格
- 空格：禁止全角空格；中文字符之间禁止半角空格；禁止连续多个半角空格（技术文档/出版物规范）

使用 spaCy 进行分句和上下文分析，结合规则引擎校验标点合规性。
"""

import re
from dataclasses import dataclass
from typing import List, Optional


# 上下文提取的默认前后字符数
CONTEXT_BEFORE = 25
CONTEXT_AFTER = 25


def _get_context(text: str, position: int, length: int) -> str:
    """提取问题标点的上下文。

    Args:
        text: 全文
        position: 问题起始位置
        length: 问题长度

    Returns:
        形如 "…前文【问题】后文…" 的字符串
    """
    start = max(0, position - CONTEXT_BEFORE)
    end = min(len(text), position + length + CONTEXT_AFTER)

    before = "…" if start > 0 else ""
    after = "…" if end < len(text) else ""

    ctx_before = text[start:position]
    problem = text[position : position + length]
    ctx_after = text[position + length : end]

    return f"{before}{ctx_before}【{problem}】{ctx_after}{after}"


def _is_name_before_colon(text: str, colon_pos: int) -> bool:
    """判断冒号前是否为疑似人名（2-4 个汉字，用于对话标注等）。

    如「张三：」「鲁迅：」等为人名后的冒号，属正确用法，不报错。
    """
    if colon_pos <= 0:
        return False
    # 向前找连续的中文字符（可含间隔号 ·）
    i = colon_pos - 1
    count = 0
    while i >= 0:
        c = text[i]
        if '\u4e00' <= c <= '\u9fff':
            count += 1
            i -= 1
        elif c == '·' and count > 0 and i > 0:
            # 间隔号如 马克·吐温
            i -= 1
        else:
            break
    return 2 <= count <= 4


@dataclass
class PunctuationIssue:
    """标点问题记录。"""
    rule_id: str
    position: int
    length: int
    text: str
    message: str
    suggestion: str = ""
    context: str = ""  # 问题标点的上下文


def _check_ellipsis(text: str) -> List[PunctuationIssue]:
    """省略号：GB/T 15834-2011 4.11 统一为六连点 ……，不得使用 ... 或 。。。"""
    issues = []
    # 句号连用（三至五个）视为错误省略号
    for m in re.finditer(r'。{3,5}', text):
        pos, ln = m.start(), len(m.group())
        issues.append(PunctuationIssue(
            rule_id="ELLIPSIS",
            position=pos,
            length=ln,
            text=m.group(),
            message=f"省略号不规范：'{m.group()}'",
            suggestion="应使用六连点 ……",
            context=_get_context(text, pos, ln),
        ))
    # 英文三点省略号在中文语境（前后有中文）时建议改为 ……
    for m in re.finditer(r'\.{3}', text):
        start, end = m.start(), m.end()
        if start > 0 and end < len(text):
            prev_is_cn = '\u4e00' <= text[start - 1] <= '\u9fff'
            next_is_cn = '\u4e00' <= text[end] <= '\u9fff'
            if prev_is_cn or next_is_cn:
                issues.append(PunctuationIssue(
                    rule_id="ELLIPSIS",
                    position=start,
                    length=3,
                    text="...",
                    message="中文语境下省略号应使用 ……",
                    suggestion="应使用六连点 ……",
                    context=_get_context(text, start, 3),
                ))
    return issues


def _check_date_delimiter(text: str) -> List[PunctuationIssue]:
    """日期简写：GB A.4.2 阿拉伯数字年月日间用短横线，不用顿号。"""
    issues = []
    for m in re.finditer(r'\d{4}、\d{1,2}、\d{1,2}', text):
        for i, c in enumerate(m.group()):
            if c == '、':
                pos = m.start() + i
                issues.append(PunctuationIssue(
                    rule_id="DATE_DELIM",
                    position=pos,
                    length=1,
                    text='、',
                    message="日期简写中月日之间应用短横线连接号",
                    suggestion="如 2010-03-02，不用顿号",
                    context=_get_context(text, m.start(), len(m.group())),
                ))
    return issues


def _check_dash(text: str) -> List[PunctuationIssue]:
    """破折号/连接号：GB 4.13 破折号用 —（占两字）；连接号用 -、—、～。

    短横线 - 占半字，用于号码、复合词等；一字线 — 占一字；浪纹线 ～ 用于数值范围。
    两个及以上连字符 -- 视为不规范，应改为破折号 —。
    """
    issues = []
    for m in re.finditer(r'--+', text):
        pos, ln = m.start(), len(m.group())
        issues.append(PunctuationIssue(
            rule_id="DASH",
            position=pos,
            length=ln,
            text=m.group(),
            message=f"破折号形式不规范：'{m.group()}'",
            suggestion="破折号应使用一字线 —（占两个字位置）",
            context=_get_context(text, pos, ln),
        ))
    return issues


def _check_quote_pairs(text: str) -> List[PunctuationIssue]:
    """引号、括号、书名号配对检查（GB 5.1.3）。"""
    issues = []
    # 左右不同的符号对
    pairs = [
        ('「', '」', "方头引号"),
        ('『', '』', "方头书名号式引号"),
        ('（', '）', "圆括号"),
        ('[', ']', "方括号"),
        ('{', '}', "花括号"),
        ('【', '】', "方头括号"),
        ('《', '》', "书名号"),
        ('〈', '〉', "单书名号"),
    ]

    for left, right, name in pairs:
        stack = []
        for i, c in enumerate(text):
            if c == left:
                stack.append((i, c))
            elif c == right:
                if not stack:
                    issues.append(PunctuationIssue(
                        rule_id="PAIR",
                        position=i,
                        length=1,
                        text=c,
                        message=f"{name}多余：多余的 '{right}'",
                        suggestion=f"请检查是否缺少对应的 '{left}'",
                        context=_get_context(text, i, 1),
                    ))
                else:
                    stack.pop()

        for pos, _ in stack:
            issues.append(PunctuationIssue(
                rule_id="PAIR",
                position=pos,
                length=1,
                text=left,
                message=f"{name}未闭合：缺少 '{right}'",
                suggestion=f"请在适当位置添加 '{right}'",
                context=_get_context(text, pos, 1),
            ))

    # 左右相同的符号（"" ''）：计数为奇则未闭合
    for quote, name in [('"', "双引号"), ("'", "单引号")]:
        positions = [i for i, c in enumerate(text) if c == quote]
        if len(positions) % 2 != 0:
            pos = positions[-1]
            issues.append(PunctuationIssue(
                rule_id="PAIR",
                position=pos,
                length=1,
                text=quote,
                message=f"{name}未闭合：数量为奇数",
                suggestion=f"请检查 {name} 是否成对",
                context=_get_context(text, pos, 1),
            ))

    return issues


def _is_chinese(c: str) -> bool:
    """是否为 CJK 统一汉字。"""
    return '\u4e00' <= c <= '\u9fff'


def _check_halfwidth(text: str) -> List[PunctuationIssue]:
    """半角标点误用：GB 5.1.1–5.1.2 中文语境下点号应占一字、使用全角形式。

    例外不报错：数字后的半角标点（如 3.14、1,000、12:30）；人名后的冒号（如「张三：」）。
    """
    issues = []
    halfwidth_map = {
        ',': '，',
        '.': '。',
        ';': '；',
        ':': '：',
        '!': '！',
        '?': '？',
    }
    for char, full in halfwidth_map.items():
        pattern = rf'[\u4e00-\u9fa5]{re.escape(char)}(?=[\s\u4e00-\u9fa5]|$)'
        for m in re.finditer(pattern, text):
            pos = m.start() + len(m.group()) - 1
            if char == ':' and _is_name_before_colon(text, pos):
                continue
            issues.append(PunctuationIssue(
                rule_id="HALFWIDTH",
                position=pos,
                length=1,
                text=char,
                message=f"中文后应使用全角标点：'{char}'（GB 5.1）",
                suggestion=f"应改为 '{full}'",
                context=_get_context(text, pos, 1),
            ))
    return issues


def _check_fullwidth_after_ascii(text: str) -> List[PunctuationIssue]:
    """全角标点误用：英文字母或数字后的全角点号应改为半角（GB 5.1 混排规则）。"""
    issues = []
    full_to_half = {
        '，': ',',
        '。': '.',
        '；': ';',
        '：': ':',
        '！': '!',
        '？': '?',
    }
    for full, half in full_to_half.items():
        # 英文字母或数字后紧跟全角点号
        pattern = rf'[a-zA-Z0-9]{re.escape(full)}'
        for m in re.finditer(pattern, text):
            pos = m.start() + len(m.group()) - 1
            issues.append(PunctuationIssue(
                rule_id="FULLWIDTH_AFTER_ASCII",
                position=pos,
                length=1,
                text=full,
                message=f"英文/数字后应使用半角标点：'{full}'",
                suggestion=f"应改为 '{half}'",
                context=_get_context(text, pos, 1),
            ))
    return issues


def _check_space(text: str) -> List[PunctuationIssue]:
    """空格校验：中文出版物/排版规范。

    依据：技术文档与出版物空格规范、中文技术文档写作风格指南。
    - 禁止使用全角空格（U+3000），应使用半角空格
    - 中文字符（汉字、中文标点）之间禁止插入半角空格
    - 禁止连续两个及以上半角空格（缩进等特殊场景除外）
    """
    issues = []
    i = 0
    while i < len(text):
        c = text[i]
        # 1. 全角空格：禁止使用
        if c == '\u3000':
            issues.append(PunctuationIssue(
                rule_id="FULLWIDTH_SPACE",
                position=i,
                length=1,
                text=c,
                message="禁止使用全角空格",
                suggestion="应改为半角空格",
                context=_get_context(text, i, 1),
            ))
            i += 1
            continue

        # 2. 中文字符之间的半角空格（汉字+空格+汉字；标点旁空格由 _check_space_around_punctuation 处理）
        if c == ' ' and i > 0 and i + 1 < len(text):
            prev, nxt = text[i - 1], text[i + 1]
            if _is_chinese(prev) and _is_chinese(nxt):
                issues.append(PunctuationIssue(
                    rule_id="SPACE_BETWEEN_CJK",
                    position=i,
                    length=1,
                    text=' ',
                    message="中文字符之间不应插入半角空格",
                    suggestion="删除此处空格",
                    context=_get_context(text, i, 1),
                ))

        # 3. 连续两个及以上半角空格
        if c == ' ' and i + 1 < len(text) and text[i + 1] == ' ':
            j = i + 1
            while j < len(text) and text[j] == ' ':
                j += 1
            ln = j - i
            if ln >= 2:
                issues.append(PunctuationIssue(
                    rule_id="MULTI_SPACE",
                    position=i,
                    length=ln,
                    text=' ' * ln,
                    message=f"禁止连续 {ln} 个半角空格",
                    suggestion="保留一个空格或根据排版需求调整",
                    context=_get_context(text, i, ln),
                ))
                i = j
                continue

        i += 1
    return issues


def _check_space_around_punctuation(text: str) -> List[PunctuationIssue]:
    """全角标点两旁不得空半角空格（中文排版规范）。"""
    issues = []
    fullwidth_punct = '，。、；：！？」』）］〕》〉'
    for i, c in enumerate(text):
        if c not in fullwidth_punct:
            continue
        # 全角标点前不应有空格（空格+全角标点）
        if i > 0 and text[i - 1] == ' ':
            issues.append(PunctuationIssue(
                rule_id="SPACE_BEFORE_PUNCT",
                position=i - 1,
                length=1,
                text=' ',
                message="全角标点前不应有半角空格",
                suggestion="删除标点前的空格",
                context=_get_context(text, i - 1, 2),
            ))
        # 全角标点后不应紧跟空格再跟中文（标点+空格+中文）
        if i + 2 < len(text) and text[i + 1] == ' ' and _is_chinese(text[i + 2]):
            issues.append(PunctuationIssue(
                rule_id="SPACE_AFTER_PUNCT",
                position=i + 1,
                length=1,
                text=' ',
                message="全角标点后不应有半角空格再跟中文",
                suggestion="删除标点后的空格",
                context=_get_context(text, i, 3),
            ))
    return issues


def _check_sentence_end_punctuation(
    text: str,
    nlp,
    chunk_size: int = 50000,
) -> List[PunctuationIssue]:
    """句末点号：GB 5.1.1–5.1.2 句末应为 。？！… 之一，或后接引号/括号等。

    基于 spaCy 分句，检查句末不宜使用逗号、顿号、分号、冒号（人名后冒号除外）。
    """
    if nlp is None:
        return []

    issues = []
    valid_endings = ('。', '？', '！', '…', '"', "'", '」', '』', ')', ']', '}', '》', '〉')

    for start in range(0, len(text), chunk_size):
        chunk = text[start:start + chunk_size]
        try:
            doc = nlp(chunk)
            for sent in doc.sents:
                sent_text = sent.text.strip()
                if not sent_text:
                    continue

                # 句末字符
                last_char = sent_text[-1]
                # 若以引号/括号结尾，检查其前一个字符
                check_char = last_char
                for c in reversed(sent_text[:-1]):
                    if c in valid_endings or c in ' \t\n':
                        continue
                    check_char = c
                    break

                # 句子不应以逗号、顿号、分号、冒号结尾（除非是省略等特殊情况）
                # 例外：人名后的冒号是正确的，如「张三：」用于对话标注
                if last_char in ('，', '、', '；', '：'):
                    abs_pos = start + sent.end_char - 1
                    if last_char == '：' and _is_name_before_colon(text, abs_pos):
                        continue  # 人名后的冒号不报错
                    issues.append(PunctuationIssue(
                        rule_id="SENT_END",
                        position=abs_pos,
                        length=1,
                        text=last_char,
                        message=f"句末不宜使用 '{last_char}'",
                        suggestion="句末应使用句号、问号或叹号",
                        context=_get_context(text, abs_pos, 1),
                    ))
        except Exception:
            pass

    return issues


def validate_punctuation(
    text: str,
    nlp=None,
    use_nlp: bool = True,
) -> List[PunctuationIssue]:
    """执行标点符号校验。

    Args:
        text: 待校验文本
        nlp: spaCy 语言模型（用于分句，可选）
        use_nlp: 是否启用基于 NLP 的句末点号检查

    Returns:
        问题列表，按位置排序
    """
    all_issues: List[PunctuationIssue] = []

    # 1. 字符级规则（不依赖 NLP）
    all_issues.extend(_check_ellipsis(text))
    all_issues.extend(_check_date_delimiter(text))
    all_issues.extend(_check_dash(text))
    all_issues.extend(_check_quote_pairs(text))
    all_issues.extend(_check_halfwidth(text))
    all_issues.extend(_check_fullwidth_after_ascii(text))
    all_issues.extend(_check_space(text))
    all_issues.extend(_check_space_around_punctuation(text))

    # 2. 基于 NLP 的句末点号检查
    if use_nlp and nlp and len(text) > 0:
        all_issues.extend(_check_sentence_end_punctuation(text, nlp))

    # 按位置排序
    all_issues.sort(key=lambda x: x.position)

    return all_issues
