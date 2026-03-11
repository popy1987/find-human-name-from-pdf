import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict


class Teardown:
    """Teardown class for cleanup and resource release.

    功能职责：
    1. 接收来自 Run 的处理结果
    2. 将结果保存到输出文件
    3. 清理临时资源
    4. 生成处理报告
    """

    def __init__(self, results: Dict[str, Any], logger: logging.Logger):
        """Initialize the Teardown class.

        Args:
            results: Run 阶段产生的处理结果
            logger: 日志记录器实例
        """
        self.results = results
        self.logger = logger
        self.output_dir = os.path.join(os.path.dirname(__file__), "output")

    def save_results(self) -> str:
        """将处理结果保存到 JSON 文件。

        Returns:
            输出文件的绝对路径
        """
        os.makedirs(self.output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(
            self.output_dir,
            f"names_result_{timestamp}.json"
        )

        # 添加元数据
        output_data = {
            "metadata": {
                "timestamp": timestamp,
                "version": "1.0.0",
            },
            "results": self.results,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        self.logger.info(f"结果已保存到: {output_file}")
        return output_file

    def generate_report(self) -> str:
        """生成人名提取的文本报告。

        Returns:
            报告内容的字符串
        """
        lines = [
            "=" * 50,
            "人名提取报告",
            "=" * 50,
            f"文本总长度: {self.results.get('content_length', 0)} 字符",
            f"提取人名总数: {self.results.get('total_names', 0)} 个",
            f"过滤后人名数: {self.results.get('filtered_names', 0)} 个",
            "-" * 50,
            "人名列表（按出现频率排序）:",
            "-" * 50,
        ]

        names = self.results.get("names", [])
        if names:
            for i, item in enumerate(names, 1):
                lines.append(f"{i}. {item['name']}: {item['count']} 次")
        else:
            lines.append("未提取到符合条件的人名")

        lines.append("=" * 50)

        report = "\n".join(lines)
        return report

    def cleanup(self):
        """清理临时资源。

        目前主要清理内存中的大对象，未来可扩展清理临时文件。
        """
        self.logger.info("开始清理资源")

        # 释放大对象引用
        if hasattr(self, 'results'):
            self.results = None

        self.logger.info("资源清理完成")

    def process(self) -> Dict[str, Any]:
        """执行完整的清理流程。

        Returns:
            包含输出文件路径和报告的字典
        """
        self.logger.info("=== 开始清理阶段 ===")

        # 1. 保存结果到文件
        output_file = self.save_results()

        # 2. 生成并打印报告
        report = self.generate_report()
        # 处理 Windows 控制台编码问题
        try:
            print("\n" + report)
        except UnicodeEncodeError:
            # 如果控制台不支持某些字符，使用替代字符
            safe_report = report.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
            print("\n" + safe_report)

        # 3. 清理资源
        self.cleanup()

        self.logger.info("清理阶段完成")

        return {
            "output_file": output_file,
            "report": report,
        }
