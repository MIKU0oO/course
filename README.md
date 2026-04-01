# 中文新闻 RAG 项目说明

本项目是一个面向中文新闻语料的 RAG 问答系统，当前包含：

- 两阶段检索：`BM25 + embedding + reranker`
- 多轮查询流程：首轮原问题、次轮多角度改写、后续 step-back
- 命令行问答入口
- 网页检索入口
- 自动评测脚本
- 测试集生成脚本
- 新闻抓取脚本
- 小语料子集 embedding 构建工具

当前默认运行方式仍然是直接在项目根目录执行 Python 脚本，不要求先安装成包。

## 推荐入口

在项目根目录执行：

```bash
python main.py --help
python run_web.py --help
python evaluate_main.py --help
python generate_test_set.py --help
python getdata.py
python build_subset_embeddings.py --help
```

如果你已经安装了项目，也可以使用 `pyproject.toml` 中声明的脚本入口：

```bash
news-rag
news-rag-evaluate
news-rag-generate-test-set
news-rag-getdata
news-rag-build-subset-embeddings
```

## 当前语料模式

项目现在支持通过语料配置切换不同规模的检索数据。

默认值：

```text
first100
```

含义：

- `full`
  使用全量语料：`data/processed/data.jsonl` 和 `data/cache/embeddings.npy`
- `first100`
  使用前 100 篇新闻对应的全部 chunk：`data/processed/data_first100.jsonl` 和 `data/cache/embeddings_first100.npy`
- `firstN`
  如果你后续生成了 `data_firstN.jsonl` 和 `embeddings_firstN.npy`，可以直接通过 `--corpus firstN` 使用，例如 `first200`

示例：

```bash
python main.py --corpus first100 --query "杭州亚运会男子100米冠军是谁"
python run_web.py --corpus full
python evaluate_main.py --corpus first100
```

也支持显式指定一对文件：

```bash
python main.py --data-file data/processed/data_first100.jsonl --embedding-file data/cache/embeddings_first100.npy
```

## 小语料功能

为了缩短测试阶段的 embedding 构建时间，项目新增了小语料子集构建工具。

默认构建前 100 篇新闻对应的全部 chunk：

```bash
python build_subset_embeddings.py
```

默认输出：

- `data/processed/data_first100.jsonl`
- `data/cache/embeddings_first100.npy`

也可以指定其他规模：

```bash
python build_subset_embeddings.py --doc-limit 200
```

## 目录概览

- `main.py`
  主程序入口，调用 `src/news_rag/cli.py`
- `run_web.py`
  网页服务入口，调用 `src/news_rag/tools/web_server.py`
- `evaluate_main.py`
  评测入口
- `generate_test_set.py`
  测试集生成入口
- `getdata.py`
  新闻抓取入口
- `build_subset_embeddings.py`
  小语料 embedding 构建入口
- `src/news_rag/`
  核心后端代码
- `src/news_rag/tools/`
  工具脚本实现
- `data/`
  语料、缓存、评测数据
- `outputs/`
  评测输出
- `docs/`
  使用文档和结构文档
- `frontend/`
  网页前端静态资源

## 关键文档

- [MAIN_USAGE.md](E:\demo\python\自然语言处理\rag\docs\MAIN_USAGE.md)
  主程序、评测、网页、小语料构建的详细用法
- [PROJECT_LAYOUT.md](E:\demo\python\自然语言处理\rag\docs\PROJECT_LAYOUT.md)
  目录结构与文件职责说明
- [frontend/README.md](E:\demo\python\自然语言处理\rag\frontend\README.md)
  网页前端说明

## 开发说明

- 新的核心逻辑优先放到 `src/news_rag/`
- 新的工具脚本优先放到 `src/news_rag/tools/`
- 新的处理后语料放到 `data/processed/`
- 新的 embedding 缓存放到 `data/cache/`
- 新的评测结果放到 `outputs/`

如果要看详细命令示例，直接看 [MAIN_USAGE.md](E:\demo\python\自然语言处理\rag\docs\MAIN_USAGE.md)。
