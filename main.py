import argparse
import logging
import os
import sys
from datetime import datetime

# 修复 Windows 控制台 UTF-8 编码
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from prepare import Prepare
from run import Run
from teardown import Teardown


class Main:
    """Main class for the application entry point.

    功能职责：
    1. 接收命令行参数（文件绝对路径）
    2. 配置全局日志（控制台输出 + 文件输出到 logs/ 目录）
    3. 协调 prepare -> run -> teardown 的执行流程
    """

    def __init__(self, file_path: str):
        """Initialize the Main class.

        Args:
            file_path: 输入文件的绝对路径
        """
        self.file_path = file_path
        self.logger = None
        self.prepare = None
        self.run = None
        self.teardown = None

    def setup_logging(self) -> logging.Logger:
        """配置全局日志，输出到控制台和文件。

        Returns:
            配置好的 logger 实例
        """
        logger = logging.getLogger("find_human_name")
        logger.setLevel(logging.DEBUG)

        # 清除已有处理器
        logger.handlers = []

        # 创建格式器
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # 1. 控制台输出
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 2. 文件输出到 logs/ 目录
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"app_{timestamp}.log")

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger

    def execute(self):
        """执行主流程：prepare -> run -> teardown."""
        try:
            # 设置日志
            self.logger = self.setup_logging()
            self.logger.info(f"开始处理文件: {self.file_path}")

            # 1. 准备阶段
            self.logger.info("=== 准备阶段 ===")
            self.prepare = Prepare(self.file_path, self.logger)
            content = self.prepare.process()

            # 2. 运行阶段
            self.logger.info("=== 运行阶段 ===")
            self.run = Run(content, self.logger, custom_names=self.prepare.custom_names)
            results = self.run.process()

            # 3. 清理阶段
            self.logger.info("=== 清理阶段 ===")
            self.teardown = Teardown(results, self.logger)
            self.teardown.process()

            self.logger.info("处理完成")

        except Exception as e:
            if self.logger:
                self.logger.error(f"执行出错: {e}", exc_info=True)
            raise


def main():
    """入口函数，解析命令行参数并启动主流程。"""
    parser = argparse.ArgumentParser(
        description="从 PDF 文件中提取人名",
        prog="find-human-name-from-pdf"
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="输入文件的绝对路径（支持 PDF、DOC、DOCX）"
    )

    args = parser.parse_args()

    # 验证文件路径
    if not os.path.isabs(args.file_path):
        print(f"错误: 请提供绝对路径。当前路径: {args.file_path}")
        sys.exit(1)

    if not os.path.exists(args.file_path):
        print(f"错误: 文件不存在: {args.file_path}")
        sys.exit(1)

    # 启动主流程
    app = Main(args.file_path)
    app.execute()


def test():
    """测试函数，使用工程目录下的 sample.pdf 运行主流程。"""
    # 构建 sample.pdf 的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sample_pdf_path = os.path.join(current_dir, "sample.pdf")

    # 检查文件是否存在
    if not os.path.exists(sample_pdf_path):
        print(f"错误: 测试文件不存在: {sample_pdf_path}")
        print("请确保工程目录下存在 sample.pdf 文件")
        sys.exit(1)

    print(f"测试模式: 使用文件 {sample_pdf_path}")

    # 启动主流程
    app = Main(sample_pdf_path)
    app.execute()


if __name__ == "__main__":
    # 检测是否以测试模式运行
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test()
    else:
        main()
