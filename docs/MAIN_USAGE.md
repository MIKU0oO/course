# 主程序使用说明

本文档说明当前项目的推荐运行方式，以及如何使用小语料子集进行测试。

## 一、推荐运行方式

进入项目根目录后，直接执行：

```bash
python main.py --help
python evaluate_main.py --help
python generate_test_set.py --help
python run_web.py --help
python getdata.py
python build_subset_embeddings.py --help
```

## 二、主程序 `main.py`

### 1. 查看帮助

```bash
python main.py --help
```

### 2. 单题问答

```bash
python main.py --query "杭州亚运会男子100米冠军是谁"
```

### 3. 输出证据上下文

```bash
python main.py --query "杭州亚运会男子100米冠军是谁" --show-context
```

### 4. 输出最终召回文档

```bash
python main.py --query "杭州亚运会男子100米冠军是谁" --show-docs
```

### 5. 使用 JSON 输出

```bash
python main.py --query "杭州亚运会男子100米冠军是谁" --json
```

### 6. 批量问题输入

如果 `queries.txt` 中每行一个问题：

```bash
python main.py --query-file queries.txt
```

### 7. 指定检索参数

```bash
python main.py --query "杭州亚运会男子100米冠军是谁" --mode Combine --top-k 50 --top-n 5 --max-query-rounds 3
```

参数说明：

- `--mode`
  检索模式。`Combine` 表示向量检索和 BM25 联合，`True` 表示仅 BM25，`False` 表示仅向量检索。
- `--top-k`
  第一阶段召回数量。
- `--top-n`
  重排后保留数量。
- `--max-query-rounds`
  最大查询轮次，包含首轮查询。

### 8. 使用语料配置接口

当前查询支持通过 `--corpus` 选择语料规模。

默认值：

```text
first100
```

示例：

```bash
python main.py --corpus first100 --query "杭州亚运会男子100米冠军是谁"
python main.py --corpus full --query "杭州亚运会男子100米冠军是谁"
```

当前约定：

- `full`
  使用全量语料：`data/processed/data.jsonl` 和 `data/cache/embeddings.npy`
- `first100`
  使用前 100 篇新闻对应的全部 chunk：`data/processed/data_first100.jsonl` 和 `data/cache/embeddings_first100.npy`
- `firstN`
  如果你后续生成了 `data_firstN.jsonl` 和 `embeddings_firstN.npy`，也可以直接通过 `--corpus firstN` 使用，例如 `first200`

### 9. 显式指定语料文件和 embedding 文件

如果你希望手工指定一对文件，而不通过 `--corpus` 推导：

```bash
python main.py --data-file data/processed/data_first100.jsonl --embedding-file data/cache/embeddings_first100.npy --query "示例问题"
```

说明：

- 查询时，BM25 会基于 `--data-file` 指定的 `jsonl` 现场构建
- 向量检索会使用 `--embedding-file` 指定的 embedding 文件
- 因此这两个文件应当是一对匹配的数据

## 三、小语料 embedding 构建工具 `build_subset_embeddings.py`

该工具用于从 `data.jsonl` 中抽取前 N 篇新闻对应的全部 chunk，并单独构建测试用 embedding，不覆盖现有全量缓存。

### 1. 默认构建前 100 篇新闻

```bash
python build_subset_embeddings.py
```

默认输出：

- 子集语料：`data/processed/data_first100.jsonl`
- 子集 embedding：`data/cache/embeddings_first100.npy`

### 2. 指定文档数量

```bash
python build_subset_embeddings.py --doc-limit 200
```

对应默认输出为：

- `data/processed/data_first200.jsonl`
- `data/cache/embeddings_first200.npy`

### 3. 自定义输出路径

```bash
python build_subset_embeddings.py --doc-limit 100 --subset-jsonl data/processed/test_100.jsonl --output data/cache/test_100.npy
```

### 4. 使用脚本入口

```bash
news-rag-build-subset-embeddings --doc-limit 100
```

## 四、评测脚本 `evaluate_main.py`

### 1. 全量评测

```bash
python evaluate_main.py
```

### 2. 只跑前 10 题

```bash
python evaluate_main.py --test10
```

### 3. 只跑前 N 题

```bash
python evaluate_main.py --limit 20
```

### 4. 指定语料配置

```bash
python evaluate_main.py --corpus first100
python evaluate_main.py --corpus full
```

### 5. 显式指定语料文件和 embedding 文件

```bash
python evaluate_main.py --data-file data/processed/data_first100.jsonl --embedding-file data/cache/embeddings_first100.npy
```

默认输入输出：

- 默认答案文件：`data/eval/answers_100.jsonl`
- 默认评测报告：`outputs/evaluation/evaluation_report.json`
- 默认逐题明细：`outputs/evaluation/evaluation_details.jsonl`

## 五、测试集生成脚本 `generate_test_set.py`

### 1. 使用默认语料生成测试集

```bash
python generate_test_set.py
```

### 2. 指定题目数量

```bash
python generate_test_set.py --count 50
```

### 3. 指定输入语料

```bash
python generate_test_set.py --input data/processed/data.jsonl
```

默认输出位置：

- `data/eval/answers_100.jsonl`
- `data/eval/answers_100.txt`

## 六、数据抓取脚本 `getdata.py`

```bash
python getdata.py
```

该脚本会抓取原始新闻数据，并写入：

```text
data/raw/articles.json
```

## 七、网页前端 `run_web.py`

### 1. 启动网页服务

```bash
python run_web.py
```

默认启动后访问：

```text
http://127.0.0.1:8000
```

### 2. 指定端口

```bash
python run_web.py --port 9000
```

### 3. 指定检索参数

```bash
python run_web.py --mode Combine --top-k 50 --top-n 5 --max-query-rounds 3
```

### 4. 指定语料配置

```bash
python run_web.py --corpus first100
python run_web.py --corpus full
```

### 5. 显式指定语料文件和 embedding 文件

```bash
python run_web.py --data-file data/processed/data_first100.jsonl --embedding-file data/cache/embeddings_first100.npy
```

网页前端会直接调用本地服务提供的：

```text
POST /api/search
```
