# -*- coding: utf-8 -*-
"""基于 Wikipedia-API 为人名生成维基百科简介。"""
import logging
import re
import time
from typing import Optional, Tuple

# 简介最大字符数
INTRO_MAX_CHARS = 200

# 嗅探超时秒数
PROBE_TIMEOUT = 5

# 连续超时次数上限，超过则停止后续请求
CONSECUTIVE_TIMEOUT_LIMIT = 3


def probe_wikipedia_api(
    timeout: float = PROBE_TIMEOUT,
    logger: Optional[logging.Logger] = None,
) -> bool:
    """嗅探维基百科 API 是否可访问。

    在 prepare 阶段调用，若超时则本次运行不进行维基简介获取。

    Args:
        timeout: 超时秒数
        logger: 日志记录器

    Returns:
        True 表示可访问，False 表示超时或不可用
    """
    import urllib.request
    import urllib.error

    url = "https://zh.wikipedia.org/w/api.php?action=query&titles=Wikipedia&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "find-human-name-from-pdf/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception as e:
        if logger:
            logger.info(
                f"维基百科 API 嗅探超时或不可达: {e}，本次不获取人名简介"
            )
        return False


def _is_chinese_name(name: str) -> bool:
    """判断是否主要为中文人名。"""
    return bool(re.search(r"[\u4e00-\u9fa5]", name))


def _is_english_name(name: str) -> bool:
    """判断是否主要为英文人名。"""
    return bool(re.match(r"^[a-zA-Z\s\.\-'・]+$", name))


def _is_timeout_error(e: Exception) -> bool:
    """判断异常是否为超时类错误。"""
    err_str = str(e).lower()
    if "timeout" in err_str or "timed out" in err_str:
        return True
    try:
        import requests
        if isinstance(e, requests.exceptions.Timeout):
            return True
        if isinstance(e, requests.exceptions.ConnectionError):
            return True
    except ImportError:
        pass
    return False


def fetch_wikipedia_intro(
    name: str,
    name_type: str,
    logger: Optional[logging.Logger] = None,
) -> Tuple[Optional[str], bool]:
    """从维基百科获取人名的简介（摘要）。

    优先使用中文维基，英文人名使用英文维基。简介截断至 INTRO_MAX_CHARS 字。

    Args:
        name: 人名
        name_type: 人名类型（中文/英文/混合）
        logger: 日志记录器，可选

    Returns:
        (简介文本, 是否因超时失败)。未找到词条返回 (None, False)；超时/网络错误返回 (None, True)
    """
    try:
        import wikipediaapi
    except ImportError:
        if logger:
            logger.warning("未安装 Wikipedia-API，无法获取简介。pip install Wikipedia-API")
        return None, False

    user_agent = "find-human-name-from-pdf/1.0 (https://github.com/; python)"
    lang = "zh" if _is_chinese_name(name) or name_type == "中文" else "en"

    try:
        wiki = wikipediaapi.Wikipedia(user_agent=user_agent, language=lang)
        page = wiki.page(name)

        if not page.exists():
            # 英文人名可尝试英文维基
            if lang == "zh" and _is_english_name(name):
                time.sleep(0.2)  # 礼貌延迟
                wiki_en = wikipediaapi.Wikipedia(user_agent=user_agent, language="en")
                page = wiki_en.page(name)
            if not page.exists():
                return None, False

        summary = getattr(page, "summary", None) or getattr(page, "text", "")
        if not summary or not summary.strip():
            return None, False

        intro = summary.strip()
        if len(intro) > INTRO_MAX_CHARS:
            # 在句号、换行处截断，避免截断到句子中间
            cut = intro[: INTRO_MAX_CHARS + 1]
            for sep in ("。", "．", ".\n", "\n", " "):
                idx = cut.rfind(sep)
                if idx > INTRO_MAX_CHARS // 2:
                    intro = intro[: idx + len(sep)].rstrip()
                    break
            else:
                intro = intro[:INTRO_MAX_CHARS] + "…"
        return intro, False

    except Exception as e:
        is_timeout = _is_timeout_error(e)
        if logger:
            logger.debug(f"获取 {name} 维基简介失败: {e}")
        return None, is_timeout


def fetch_intros_for_names(
    names: list,
    logger: Optional[logging.Logger] = None,
    delay: float = 0.2,
    max_names: Optional[int] = 20,
    consecutive_timeout_limit: int = CONSECUTIVE_TIMEOUT_LIMIT,
) -> dict:
    """批量为多个人名获取维基简介。

    当连续超时达到 consecutive_timeout_limit 次时，停止后续请求。

    Args:
        names: 人名列表，每项为 {"name": str, "type": str, ...}
        logger: 日志记录器
        delay: 每次请求间隔（秒），避免触发维基 API 限制
        max_names: 最多查询的人数，None 表示不限制
        consecutive_timeout_limit: 连续超时次数上限，超过则停止

    Returns:
        {name: intro} 字典，未找到的 name 不会出现在字典中
    """
    result = {}
    to_fetch = names[:max_names] if max_names else names
    consecutive_timeouts = 0

    if logger:
        logger.info(f"正在为 {len(to_fetch)} 个人名获取维基百科简介…")

    for i, item in enumerate(to_fetch):
        if consecutive_timeouts >= consecutive_timeout_limit:
            if logger:
                logger.warning(
                    f"已连续 {consecutive_timeout_limit} 次超时，停止后续维基简介获取"
                )
            break

        name = item.get("name", "")
        name_type = item.get("type", "中文")
        if not name:
            continue

        intro, is_timeout = fetch_wikipedia_intro(name, name_type, logger)
        if is_timeout:
            consecutive_timeouts += 1
        else:
            consecutive_timeouts = 0
            if intro:
                result[name] = intro

        if i < len(to_fetch) - 1:
            time.sleep(delay)

    if logger:
        logger.info(f"成功获取 {len(result)} 个人名的维基简介")
    return result
