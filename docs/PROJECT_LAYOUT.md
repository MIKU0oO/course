# 项目结构说明

本文档说明当前仓库的目录组织方式，以及每类文件应当放在哪里。

## 一、整体结构

项目采用标准 `src` 布局，根目录保留轻量入口脚本，核心逻辑放在 `src/news_rag/`，数据、输出和前端资源分别独立存放。

当前根目录结构：

```text
rag/
├─ data/
├─ docs/
├─ frontend/
├─ outputs/
├─ src/
├─ build_subset_embeddings.py
├─ evaluate_main.py
├─ generate_test_set.py
├─ getdata.py
├─ main.py
├─ run_web.py
├─ pyproject.toml
└─ README.md
```

## 二、根目录入口

- `main.py`
  主问答入口，负责把 `src` 加入运行路径，再调用 `news_rag.cli`
- `run_web.py`
  网页服务入口，调用 `news_rag.tools.web_server`
- `evaluate_main.py`
  自动评测入口
- `generate_test_set.py`
  测试集生成入口
- `getdata.py`
  新闻抓取入口
- `build_subset_embeddings.py`
  小语料 embedding 构建入口
- `pyproject.toml`
  打包配置和脚本入口配置
- `README.md`
  项目总说明

## 三、核心代码目录 `src/news_rag/`

这里放后端核心逻辑。

- `__init__.py`
  包初始化
- `__main__.py`
  支持 `python -m news_rag`
- `config.py`
  统一管理目录路径、默认语料配置和运行时目录
- `cli.py`
  命令行参数解析、结果输出和主流程调度
- `agent.py`
  RAG Agent 主流程，负责多轮查询、证据检查、上下文构造和答案生成
- `retrieval.py`
  检索层实现，包含语料加载、BM25、embedding 检索、rerank 和两阶段检索封装
- `transport.py`
  原始文章到检索 `jsonl` 的转换逻辑
- `retry.py`
  通用重试工具

## 四、工具目录 `src/news_rag/tools/`

这里放可执行工具逻辑。

- `evaluate.py`
  自动评测实现
- `generate_test_set.py`
  测试集生成实现
- `getdata.py`
  新闻抓取实现
- `web_server.py`
  网页服务实现
- `build_subset_embeddings.py`
  小语料子集构建与 embedding 生成实现

## 五、数据目录 `data/`

这里放项目运行需要的数据、缓存和评测集。

### 1. `data/raw/`

- `articles.json`
  原始抓取文章数据

### 2. `data/processed/`

- `data.jsonl`
  全量检索语料
- `training_data.jsonl`
  历史或备用处理语料
- `data_first100.jsonl`
  前 100 篇新闻对应的全部 chunk
- `data_firstN.jsonl`
  其他小语料规模的约定命名

### 3. `data/cache/`

- `embeddings.npy`
  全量 embedding 缓存
- `embeddings_first100.npy`
  前 100 篇新闻对应的 embedding 缓存
- `embeddings_firstN.npy`
  其他小语料规模的约定命名

### 4. `data/eval/`

- `answers_100.jsonl`
  默认评测答案集

## 六、文档目录 `docs/`

- `MAIN_USAGE.md`
  命令行、网页、评测和小语料功能的详细使用方式
- `PROJECT_LAYOUT.md`
  当前文档，说明目录结构

## 七、输出目录 `outputs/`

主要放自动评测和实验结果。

- `outputs/evaluation/evaluation_report.json`
  汇总评测报告
- `outputs/evaluation/evaluation_details.jsonl`
  逐题评测结果

## 八、前端目录 `frontend/`

这里放网页前端资源。

- `frontend/public/index.html`
  页面结构
- `frontend/public/styles.css`
  页面样式
- `frontend/public/app.js`
  前端交互逻辑，调用 `/api/search`
- `frontend/public/assets/`
  背景图等静态资源
- `frontend/README.md`
  前端说明

## 九、当前语料切换机制

当前默认语料是 `first100`，定义在 [config.py](E:\demo\python\自然语言处理\rag\src\news_rag\config.py)。

语料切换通过 `resolve_corpus_paths()` 完成：

- `full`
  对应 `data/processed/data.jsonl` + `data/cache/embeddings.npy`
- `first100`
  对应 `data/processed/data_first100.jsonl` + `data/cache/embeddings_first100.npy`
- `firstN`
  对应 `data/processed/data_firstN.jsonl` + `data/cache/embeddings_firstN.npy`

因此：

- BM25 由当前 `jsonl` 文件现场构建
- embedding 由当前 `embedding` 文件加载

这两者始终基于同一套语料规模运行。

## 十、文件放置建议

- 新增核心检索或问答逻辑：放到 `src/news_rag/`
- 新增独立工具脚本：放到 `src/news_rag/tools/`
- 新增原始数据：放到 `data/raw/`
- 新增处理后语料：放到 `data/processed/`
- 新增缓存：放到 `data/cache/`
- 新增评测集：放到 `data/eval/`
- 新增实验输出：放到 `outputs/`
- 新增网页资源：放到 `frontend/`
