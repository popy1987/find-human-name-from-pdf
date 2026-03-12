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
        self.log_file_path = None
        self.output_file_path = None
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

        # 清除已有处理器（先关闭文件类 handler 再清除，避免占用）
        for h in logger.handlers[:]:
            if isinstance(h, logging.FileHandler):
                try:
                    h.close()
                except Exception:
                    pass
            logger.removeHandler(h)

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
        self.log_file_path = os.path.join(log_dir, f"app_{timestamp}.log")

        file_handler = logging.FileHandler(self.log_file_path, encoding="utf-8")
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
            self.run = Run(
                content,
                self.logger,
                custom_names=self.prepare.custom_names,
                wiki_available=self.prepare.wiki_available,
                name_blacklist=self.prepare.name_blacklist,
            )
            results = self.run.process()

            # 3. 清理阶段
            self.logger.info("=== 清理阶段 ===")
            self.teardown = Teardown(results, self.logger)
            process_result = self.teardown.process()
            self.output_file_path = process_result.get("output_file")

            self.logger.info("处理完成")

        except Exception as e:
            if self.logger:
                self.logger.error(f"执行出错: {e}", exc_info=True)
            raise

    def close_logging(self):
        """关闭日志文件句柄，释放文件占用，便于后续删除。

        测试模式下在删除 log 文件前必须调用，否则可能因进程占用导致删除失败。
        """
        if not self.logger:
            return
        for h in self.logger.handlers[:]:
            if isinstance(h, logging.FileHandler):
                try:
                    h.close()
                except Exception:
                    pass
                self.logger.removeHandler(h)


def main():
    """入口函数，解析命令行参数并启动主流程。"""
    parser = argparse.ArgumentParser(
        description="从 PDF 文件中提取人名",
        prog="find-human-name-from-pdf"
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="输入文件的绝对路径（支持 PDF、DOC、DOCX、TXT）"
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
    """测试函数，依次使用工程目录下的 sample.pdf、sample.docx、sample.md 运行主流程。

    测试结束后删除本次生成的 log 和 JSON 文件，避免测试产物堆积。
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sample_files = ["sample.pdf", "sample.docx", "sample.md"]
    files_to_delete = []

    for i, filename in enumerate(sample_files):
        file_path = os.path.join(current_dir, filename)

        if not os.path.exists(file_path):
            print(f"警告: 测试文件不存在: {file_path}，跳过")
            continue

        print(f"\n{'='*60}")
        print(f"测试模式 ({i+1}/{len(sample_files)}): 使用文件 {file_path}")
        print(f"{'='*60}\n")

        app = Main(file_path)
        try:
            app.execute()
        finally:
            # 关闭日志文件句柄，避免进程占用导致无法删除
            app.close_logging()
            if app.log_file_path:
                files_to_delete.append(app.log_file_path)
            if app.output_file_path:
                files_to_delete.append(app.output_file_path)

    # 收尾：删除本次测试生成的 log 和 JSON
    if files_to_delete:
        print(f"\n{'='*60}")
        print("测试收尾：清理本次生成的 log 和 JSON 文件")
        print(f"{'='*60}")
    deleted = 0
    for path in files_to_delete:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                print(f"  已删除: {os.path.basename(path)}")
                deleted += 1
        except OSError as e:
            print(f"  无法删除 {path}: {e}")
    if deleted:
        print(f"共清理 {deleted} 个文件")


if __name__ == "__main__":
    # 检测是否以测试模式运行
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test()
    else:
        main()
