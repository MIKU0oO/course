# 前端说明

当前前端采用原生静态页面方案，不依赖 Node.js、Vite 或其他前端构建工具。

## 文件结构

- `frontend/public/index.html`
  页面结构
- `frontend/public/styles.css`
  页面样式
- `frontend/public/app.js`
  前端交互逻辑，负责调用本地搜索接口并渲染结果
- `frontend/public/assets/search-bg.jpg`
  背景图资源
- `frontend/public/assets/search-bg2.jpg`
  备用背景图资源

## 启动方式

在项目根目录执行：

```bash
python run_web.py
```

默认访问地址：

```text
http://127.0.0.1:8000
```

## 接口说明

前端通过本地网页服务提供的接口工作：

```text
POST /api/search
GET /api/health
```

其中 `POST /api/search` 的请求体格式为：

```json
{
  "query": "你的问题"
}
```

## 当前展示信息

页面会显示：

- 最终答案
- 召回证据列表
- 查询轮次
- 第二轮改写候选
- 查询时间
- 当前语料配置

## 与语料配置的关系

网页服务默认使用项目当前默认语料配置，现阶段默认是 `first100`。

也可以在启动时显式指定：

```bash
python run_web.py --corpus full
python run_web.py --corpus first100
python run_web.py --data-file data/processed/data_first100.jsonl --embedding-file data/cache/embeddings_first100.npy
```
