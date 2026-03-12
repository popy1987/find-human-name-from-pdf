# Find Human Name from PDF

从 PDF、DOC、DOCX、TXT 文件中提取人名的 Python 工具，使用 spaCy NER（命名实体识别）进行中英文人名识别。

## 核心特点

- **纯 NER 提取**：所有人名均通过 spaCy 的 NER 模型识别，不使用正则或词典匹配
- **本地模型优先**：优先从 `dic/` 目录加载 spaCy 模型，便于离线部署
- **自动模型管理**：缺失的模型会自动下载到本地
- **双日志输出**：同时输出到控制台和 `logs/` 目录的日志文件
- **多格式支持**：PDF、DOC、DOCX、TXT
- **大文件支持**：流式读取，支持几十万字的大文档
- **标点校验**：基于 GB/T 15834-2011，使用 spaCy 分句进行标点合规性检查

## 项目结构

```
.
├── main.py           # 入口文件，协调整个流程
├── prepare.py        # 准备阶段：检查/安装模型 + PDF 解析
├── run.py            # 运行阶段：人名提取 + 标点校验
├── punctuation_validator.py  # 标点符号校验（GB/T 15834-2011）
├── teardown.py       # 清理阶段：保存结果和生成报告
├── dic/                  # 本地 spaCy 模型目录
│   ├── zh_core_web_sm/   # 中文 NER 模型
│   ├── en_core_web_sm/   # 英文 NER 模型
│   ├── name_dic_for_user.txt  # 用户自定义人名（每行一个，可选）
│   └── README.md         # 模型目录说明
├── logs/             # 日志文件目录（自动创建，不加入 Git）
├── output/           # 结果输出目录（自动创建，不加入 Git）
├── sample.pdf        # 测试用的示例 PDF
├── requirements.txt  # Python 依赖
└── README.md         # 本文档
```

## 安装依赖

```bash
pip install -r requirements.txt
```

依赖包括：
- `PyMuPDF` - PDF 解析
- `python-docx` - DOCX 解析
- `textract` - DOC 解析（需系统安装 antiword 等依赖）
- `spacy` - NER 模型运行框架

## 自定义人名（可选）

在 `dic/name_dic_for_user.txt` 中添加需要特别识别的名字，每行一个。这些名字会通过 spaCy 的 **EntityRuler** 注入 NER 管道，作为 PERSON 实体规则。

```
# 每行一个名字，# 开头的行会被忽略
鲁迅
村上春树
```

若文件不存在，首次运行时会自动创建空模板。

## 准备 spaCy 模型

### 方式一：自动下载（推荐）

首次运行时会自动检查并下载缺失的模型到 `dic/` 目录：

```bash
python main.py --test
```

### 方式二：手动下载

```bash
# 下载中文模型
python -m spacy download zh_core_web_sm

# 下载英文模型  
python -m spacy download en_core_web_sm

# 或者下载到指定目录
python -m spacy download zh_core_web_sm --target ./dic
```

### 方式三：复制已有模型

如果其他机器已有模型，可直接复制模型文件夹到 `dic/`：

```bash
cp -r /path/to/zh_core_web_sm ./dic/
cp -r /path/to/en_core_web_sm ./dic/
```

模型文件夹特征：
- 包含 `meta.json` 文件
- 包含 `tokenizer/`、`vocab/` 等子目录

## 使用方法

### 正常模式

```bash
python main.py <文件绝对路径>
```

示例：
```bash
python main.py "C:\Users\Documents\book.pdf"
```

### 测试模式

使用项目自带的 `sample.pdf` 进行测试：

```bash
python main.py --test
```

## 输出结果

运行后会在 `output/` 目录生成 JSON 文件，包含：

```json
{
  "metadata": {
    "timestamp": "20260311_162942",
    "version": "1.0.0"
  },
  "results": {
    "total_names": 46,
    "filtered_names": 38,
    "english_count": 0,
    "chinese_count": 38,
    "mixed_count": 8,
    "names": [
      {
        "name": "张三",
        "count": 43,
        "type": "中文"
      },
      {
        "name": "村上春树",
        "count": 18,
        "type": "中文"
      }
    ],
    "content_length": 14590
  }
}
```

同时在控制台输出人名提取报告。

## 模块说明

### main.py

- 解析命令行参数
- 配置全局日志（控制台 + 文件双输出）
- 协调 `prepare -> run -> teardown` 三阶段流程

### prepare.py

**第一阶段：确保 spaCy 模型**

1. 优先检查本地 `dic/` 目录
2. 其次检查系统已安装路径
3. 如不存在，自动下载到 `dic/` 目录

**第二阶段：校验 PDF 文件**

- 检查文件存在性、可读性、格式支持

**第三阶段：文件解析**

- PDF：使用 PyMuPDF 逐页读取
- DOCX：使用 python-docx 提取段落和表格
- DOC：使用 textract 提取（需系统依赖）
- TXT：直接读取，支持 UTF-8/GBK 等编码

### run.py

**人名提取** + **标点符号校验**

- 英文模型 (`en_core_web_sm`)：识别英文人名
- 中文模型 (`zh_core_web_sm`)：识别中文人名

**重要约束**：所有人名必须通过 spaCy NER 提取，模型不可用时程序会报错退出。

**标点校验**：基于 GB/T 15834-2011 国家标准，使用 spaCy 分句 + 规则引擎校验。详见下方「标点符号校验规则」。

### punctuation_validator.py

标点符号校验模块，依据 GB/T 15834-2011《标点符号用法》第 5 章及附录 A/B 实现。

### teardown.py

- 保存 JSON 结果到 `output/` 目录
- 生成并打印人名提取报告
- 清理内存资源

## 标点符号校验规则

依据 **GB/T 15834-2011《标点符号用法》** 国家标准，本工具对提取的文本进行标点合规性检查。规则与条款对应如下。

### 规则对照表

| 规则 ID | 说明 | GB 依据 |
|---------|------|---------|
| `ELLIPSIS` | 省略号应使用六连点 ……，不得使用 ... 或 。。。 | 4.11 |
| `DATE_DELIM` | 阿拉伯数字年月日简写用短横线（如 2010-03-02），不用顿号 | 附录 A.4.2 |
| `DASH` | 破折号应使用一字线 —，不得使用 -- 等形式 | 4.13 |
| `PAIR` | 引号、括号、书名号须成对出现，不得未闭合或多余 | 5.1.3 |
| `HALFWIDTH` | 中文后应使用全角标点，不得使用半角 , . ; : ! ? | 5.1.1–5.1.2 |
| `FULLWIDTH_AFTER_ASCII` | 英文或数字后应使用半角标点，不得使用全角 ，。；：！？ | 5.1 混排规则 |
| `SPACE_BEFORE_PUNCT` | 全角标点前不应有半角空格 | 中文排版规范 |
| `SPACE_AFTER_PUNCT` | 全角标点后不应有半角空格再跟中文 | 中文排版规范 |
| `FULLWIDTH_SPACE` | 禁止使用全角空格（U+3000），应使用半角空格 | 技术文档/出版物规范 |
| `SPACE_BETWEEN_CJK` | 汉字与汉字之间不应插入半角空格 | 技术文档/出版物规范 |
| `MULTI_SPACE` | 禁止连续两个及以上半角空格 | 技术文档/出版物规范 |
| `SENT_END` | 句末应使用句号、问号或叹号，不宜以逗号、顿号、分号、冒号结尾 | 5.1.1–5.1.2 |

### 空格使用规范

依据中文技术文档与出版物排版规范：

- **禁止全角空格**：一律使用半角空格（U+0020）
- **中文字符之间禁止空格**：汉字与汉字之间、全角标点与文字之间不得插入半角空格
- **禁止连续多个空格**：除缩进、列表等特殊场景外，不得连续出现两个及以上半角空格

### 半角与全角使用场景

- **中文语境**：点号（句号、逗号、顿号、分号、冒号、问号、叹号）占一个字位置，使用全角形式
- **外文/数字语境**：英文字母或阿拉伯数字后的点号应使用半角形式
- **例外**：人名后的冒号（如「张三：」「鲁迅：」）视为正确用法，不报错
- **连接号**：短横线 `-`、一字线 `—`、浪纹线 `～` 按 GB 4.13 使用；间隔号、分隔号占半个字

### 示例

| 错误示例 | 正确示例 |
|----------|----------|
| 你好,世界 | 你好，世界 |
| OK，这是测试 | OK, 这是测试 |
| 2010、03、02 | 2010-03-02 |
| 他说了。。。 | 他说了…… |
| 文字 ， 文字 | 文字，文字 |
| 你好 世界 | 你好世界 |
| 文中含全角空格（　） | 应使用半角空格 |

## 日志

日志文件保存在 `logs/` 目录，命名格式：`app_YYYYMMDD_HHMMSS.log`

日志级别：
- 控制台：INFO 及以上
- 文件：DEBUG 及以上

## 常见问题

### Q: 控制台显示乱码？

A: 已自动处理 Windows 控制台 UTF-8 编码。如仍有问题，请确保使用支持 UTF-8 的终端。

### Q: zh_core_web_sm 下载不下来或很慢？

A: 国内访问 GitHub 可能较慢，可尝试：

1. **先安装到系统，再复制到 dic：**
   ```bash
   python -m spacy download zh_core_web_sm
   # 复制 Python\Lib\site-packages\zh_core_web_sm 文件夹到项目 dic/ 目录
   ```

2. **使用镜像或代理** 加速 GitHub 下载

3. **手动下载 whl 文件** 从 [spacy-models releases](https://github.com/explosion/spacy-models/releases) 下载对应版本，然后：
   ```bash
   pip install zh_core_web_sm-3.8.0-py3-none-any.whl --target ./dic
   ```

### Q: .doc 文件解析失败？

A: textract 解析 .doc 需要系统依赖。Linux 可安装 `antiword`。建议将 .doc 转为 .docx 后使用。

### Q: 提取的人名不完整？

A: 本工具完全依赖 spaCy NER 模型，不添加任何自定义规则。如需改进识别效果：
1. 使用更大的 spaCy 模型（如 `zh_core_web_md` 或 `zh_core_web_lg`）
2. 或训练自定义 NER 模型

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件
