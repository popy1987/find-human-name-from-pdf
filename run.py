import logging
import os
import re
from typing import Dict, List, Optional, Set

from punctuation_validator import validate_punctuation
from wiki_intro import fetch_intros_for_names


def _add_custom_names_to_nlp(nlp, custom_names: List[str], logger: logging.Logger) -> None:
    """将自定义人名通过 EntityRuler 注入 spaCy 管道，设为最高优先级。

    使用 after=\"ner\" 让 EntityRuler 在 NER 之后执行，
    overwrite_ents=True 使得自定义人名可覆盖 NER 的识别结果。
    """
    if not custom_names:
        return
    try:
        if "entity_ruler" in nlp.pipe_names:
            ruler = nlp.get_pipe("entity_ruler")
        else:
            ruler = nlp.add_pipe(
                "entity_ruler",
                after="ner",
                config={"overwrite_ents": True},
            )
        patterns = [{"label": "PERSON", "pattern": name} for name in custom_names]
        ruler.add_patterns(patterns)
        logger.info(f"已将 {len(custom_names)} 个自定义人名注入 spaCy（最高优先级）")
    except Exception as e:
        logger.warning(f"注入自定义人名失败: {e}")


class Run:
    """Run class for executing the main workflow.

    功能职责：
    1. 接收来自 Prepare 的文本内容
    2. 使用 spaCy NER 进行中英文人名识别（唯一方式）
    3. 标点符号校验（基于 GB/T 15834-2011，spaCy 分句 + 规则引擎）
    4. 去重并统计人名出现频率
    5. 返回结构化的人名列表和标点问题列表

    注意：所有人名必须通过 spaCy NER 提取，不使用任何正则匹配或词典匹配。
    """

    def __init__(
        self,
        content: str,
        logger: logging.Logger,
        custom_names: Optional[List[str]] = None,
        wiki_available: bool = True,
    ):
        """Initialize the Run class.

        Args:
            content: 从文件提取的文本内容
            logger: 日志记录器实例
            custom_names: 来自 name_dic_for_user.txt 的自定义人名列表
            wiki_available: prepare 阶段嗅探结果，为 False 时不获取维基简介
        """
        self.content = content
        self.logger = logger
        self.custom_names = custom_names or []
        self.wiki_available = wiki_available
        self.names: Set[str] = set()
        self.name_counts: Dict[str, int] = {}

        # 本地模型目录
        self.dic_dir = os.path.join(os.path.dirname(__file__), "dic")

        # 加载 spaCy 模型
        self.nlp_en = None
        self.nlp_zh = None
        self._load_spacy_models()

    def _get_local_model_path(self, model_name: str) -> Optional[str]:
        """获取本地模型路径，兼容多种目录结构。

        支持的目录结构：
        1. dic/{model}/config.cfg  - 直接放置的模型
        2. dic/{model}/{model}-3.x.x/config.cfg  - pip 安装后的包结构（子目录）
        """
        base_path = os.path.join(self.dic_dir, model_name)
        if not os.path.exists(base_path) or not os.path.isdir(base_path):
            return None

        # 结构1: config.cfg 直接在模型目录下
        config_direct = os.path.join(base_path, "config.cfg")
        if os.path.exists(config_direct):
            return base_path

        # 结构2: 模型在子目录 {model_name}-版本号/ 下（pip 安装的包结构）
        try:
            for item in os.listdir(base_path):
                sub_path = os.path.join(base_path, item)
                if os.path.isdir(sub_path) and item.startswith(model_name + "-"):
                    config_in_sub = os.path.join(sub_path, "config.cfg")
                    if os.path.exists(config_in_sub):
                        return sub_path
        except OSError:
            pass

        return None

    def _load_spacy_models(self):
        """加载 spaCy 中英文模型。

        优先从本地 dic 目录加载，如不存在则尝试系统安装路径。
        """
        try:
            import spacy

            # 英文模型
            loaded = False
            local_en = self._get_local_model_path("en_core_web_sm")
            if local_en:
                try:
                    self.nlp_en = spacy.load(local_en)
                    self.logger.info(f"成功从本地加载 spaCy 英文模型: {local_en}")
                    _add_custom_names_to_nlp(self.nlp_en, self.custom_names, self.logger)
                    loaded = True
                except Exception as e:
                    self.logger.warning(f"本地英文模型加载失败: {e}")

            if not loaded:
                try:
                    self.nlp_en = spacy.load("en_core_web_sm")
                    self.logger.info("成功从系统路径加载 spaCy 英文模型")
                    _add_custom_names_to_nlp(self.nlp_en, self.custom_names, self.logger)
                except OSError:
                    self.logger.warning("未找到 spaCy 英文模型")

            # 中文模型
            loaded = False
            local_zh = self._get_local_model_path("zh_core_web_sm")
            if local_zh:
                try:
                    self.nlp_zh = spacy.load(local_zh)
                    self.logger.info(f"成功从本地加载 spaCy 中文模型: {local_zh}")
                    _add_custom_names_to_nlp(self.nlp_zh, self.custom_names, self.logger)
                    loaded = True
                except Exception as e:
                    self.logger.warning(f"本地中文模型加载失败: {e}")

            if not loaded:
                try:
                    self.nlp_zh = spacy.load("zh_core_web_sm")
                    self.logger.info("成功从系统路径加载 spaCy 中文模型")
                    _add_custom_names_to_nlp(self.nlp_zh, self.custom_names, self.logger)
                except OSError:
                    self.logger.warning("未找到 spaCy 中文模型")

        except ImportError:
            self.logger.error("未安装 spaCy，无法提取人名")
            raise

    def extract_names_with_spacy(self) -> Set[str]:
        """使用 spaCy NER 提取所有人名（中英文）。

        这是提取人名的唯一方式，必须通过 spaCy 的 NER 识别 PERSON 类型实体。

        Returns:
            提取到的人名集合
        """
        self.logger.info("开始提取人名（使用 spaCy NER）")

        all_names = set()

        # 1. 使用英文模型提取英文人名
        if self.nlp_en:
            self.logger.info("使用 spaCy 英文 NER 提取人名")
            chunk_size = 100000
            total_chunks = (len(self.content) + chunk_size - 1) // chunk_size

            for i in range(0, len(self.content), chunk_size):
                chunk = self.content[i:i + chunk_size]
                doc = self.nlp_en(chunk)

                for ent in doc.ents:
                    if ent.label_ == "PERSON":
                        name = ent.text.strip()
                        if 2 <= len(name) <= 50:
                            all_names.add(name)

                if (i // chunk_size + 1) % 10 == 0:
                    self.logger.info(f"英文 NER 进度: {i // chunk_size + 1}/{total_chunks} 段")

            self.logger.info(f"英文 NER 完成")

        # 2. 使用中文模型提取中文人名
        if self.nlp_zh:
            self.logger.info("使用 spaCy 中文 NER 提取人名")
            chunk_size = 50000
            total_chunks = (len(self.content) + chunk_size - 1) // chunk_size

            for i in range(0, len(self.content), chunk_size):
                chunk = self.content[i:i + chunk_size]
                doc = self.nlp_zh(chunk)

                for ent in doc.ents:
                    if ent.label_ == "PERSON":
                        name = ent.text.strip()
                        # 中文人名通常 2-6 个字（包括复姓和外国人名译名）
                        if 2 <= len(name) <= 15:
                            all_names.add(name)

                if (i // chunk_size + 1) % 10 == 0:
                    self.logger.info(f"中文 NER 进度: {i // chunk_size + 1}/{total_chunks} 段")

            self.logger.info(f"中文 NER 完成")

        # 检查是否有可用的模型
        if self.nlp_en is None and self.nlp_zh is None:
            raise RuntimeError(
                "没有可用的 spaCy 模型，无法提取人名。"
                "请确保 dic/ 目录下有 zh_core_web_sm 和/或 en_core_web_sm，"
                "或运行: python -m spacy download zh_core_web_sm en_core_web_sm"
            )

        self.names = all_names

        # 统计频率
        for name in all_names:
            count = self.content.count(name)
            self.name_counts[name] = count

        self.logger.info(f"共提取到 {len(self.names)} 个唯一人名")
        return self.names

    def _validate_punctuation(self) -> List:
        """标点符号校验（基于 GB/T 15834-2011）。

        使用 spaCy 分句进行上下文分析，结合规则引擎校验。
        """
        self.logger.info("开始标点符号校验（GB/T 15834-2011）")

        nlp = self.nlp_zh or self.nlp_en
        issues = validate_punctuation(self.content, nlp=nlp, use_nlp=(nlp is not None))

        self.logger.info(f"标点校验完成，发现 {len(issues)} 处问题")

        if issues:
            for i, issue in enumerate(issues[:5], 1):
                ctx = getattr(issue, "context", "") or ""
                self.logger.info(
                    f"  {i}. [{issue.rule_id}] {issue.message} (位置 {issue.position})"
                )
                if ctx:
                    self.logger.info(f"      → {ctx}")
            if len(issues) > 5:
                self.logger.info(f"  ... 还有 {len(issues) - 5} 处问题")

        return issues

    def filter_and_rank(self, min_count: int = 2) -> List[Dict]:
        """过滤并排序人名。

        Args:
            min_count: 最小出现次数阈值

        Returns:
            排序后的人名列表
        """
        self.logger.info(f"过滤出现次数 >= {min_count} 的人名")

        def get_name_type(name: str) -> str:
            """判断人名类型。"""
            # 如果包含中文字符
            if re.search(r'[\u4e00-\u9fa5]', name):
                return "中文"
            # 如果只包含英文字符和常见分隔符
            elif re.match(r'^[a-zA-Z\s\.\-\'・]+$', name):
                return "英文"
            else:
                return "混合"

        filtered = [
            {
                "name": name,
                "count": count,
                "type": get_name_type(name)
            }
            for name, count in self.name_counts.items()
            if count >= min_count
        ]

        # 按出现次数降序排序
        sorted_names = sorted(filtered, key=lambda x: x["count"], reverse=True)

        self.logger.info(f"过滤后剩余 {len(sorted_names)} 个人名")
        return sorted_names

    def _fetch_wiki_intros(self, ranked_names: List[Dict], max_names: int = 20) -> dict:
        """为排名靠前的人名获取维基百科简介。

        Args:
            ranked_names: 过滤排序后的人名列表
            max_names: 最多获取简介的人数（避免请求过多）

        Returns:
            {name: intro} 字典
        """
        try:
            return fetch_intros_for_names(
                ranked_names,
                logger=self.logger,
                delay=0.2,
                max_names=max_names,
            )
        except Exception as e:
            self.logger.warning(f"获取维基简介时出错: {e}")
            return {}

    def process(self) -> Dict:
        """执行完整的人名提取流程。

        Returns:
            提取结果字典
        """
        self.logger.info("=== 开始人名提取流程 ===")

        # 使用 spaCy NER 提取人名（唯一方式）
        self.extract_names_with_spacy()

        # 标点符号校验（基于 GB/T 15834-2011，使用 spaCy 分句）
        punctuation_issues = self._validate_punctuation()

        # 过滤和排序
        ranked_names = self.filter_and_rank(min_count=2)

        # 为排名靠前的人名获取维基百科简介（仅当 prepare 嗅探通过时）
        if self.wiki_available and ranked_names:
            intros = self._fetch_wiki_intros(ranked_names, max_names=20)
            for item in ranked_names:
                item["intro"] = intros.get(item["name"])
        else:
            for item in ranked_names:
                item["intro"] = None

        # 统计
        english_count = sum(1 for n in ranked_names if n["type"] == "英文")
        chinese_count = sum(1 for n in ranked_names if n["type"] == "中文")
        mixed_count = sum(1 for n in ranked_names if n["type"] == "混合")

        results = {
            "total_names": len(self.names),
            "filtered_names": len(ranked_names),
            "english_count": english_count,
            "chinese_count": chinese_count,
            "mixed_count": mixed_count,
            "names": ranked_names,
            "content_length": len(self.content),
            "punctuation_issues": [
                {
                    "rule_id": i.rule_id,
                    "position": i.position,
                    "length": i.length,
                    "text": i.text,
                    "message": i.message,
                    "suggestion": i.suggestion,
                    "context": getattr(i, "context", ""),
                }
                for i in punctuation_issues
            ],
        }

        self.logger.info(f"处理完成: {results['filtered_names']} 个人名")
        self.logger.info(f"  - 英文人名: {english_count} 个")
        self.logger.info(f"  - 中文人名: {chinese_count} 个")
        self.logger.info(f"  - 混合人名: {mixed_count} 个")

        # 打印 Top 10
        if ranked_names:
            self.logger.info("Top 10 人名:")
            for i, item in enumerate(ranked_names[:10], 1):
                self.logger.info(
                    f"  {i}. [{item['type']}] {item['name']}: {item['count']} 次"
                )

        return results
