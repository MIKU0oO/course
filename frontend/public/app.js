const searchForm = document.getElementById("searchForm");
const searchInput = document.getElementById("searchInput");
const searchButton = document.getElementById("searchButton");
const heroSection = document.getElementById("heroSection");
const loadingState = document.getElementById("loadingState");
const loadingCopy = document.getElementById("loadingCopy");
const errorBanner = document.getElementById("errorBanner");
const resultsArea = document.getElementById("resultsArea");
const resultCountline = document.getElementById("resultCountline");
const resultQuery = document.getElementById("resultQuery");
const resultStats = document.getElementById("resultStats");
const answerText = document.getElementById("answerText");
const answerBadge = document.getElementById("answerBadge");
const answerReason = document.getElementById("answerReason");
const contextText = document.getElementById("contextText");
const evidenceList = document.getElementById("evidenceList");
const rewrittenQueries = document.getElementById("rewrittenQueries");
const finalQueries = document.getElementById("finalQueries");
const roundList = document.getElementById("roundList");
const topbarStatus = document.getElementById("topbarStatus");
const evidenceTemplate = document.getElementById("evidenceTemplate");
const roundTemplate = document.getElementById("roundTemplate");

const loadingMessages = [
  "正在分析问题并准备检索",
  "正在召回相关文章并执行重排",
  "正在审查证据是否足够回答问题",
  "正在生成答案与来源摘要"
];

let loadingTimer = null;

function setLoading(isLoading) {
  searchButton.disabled = isLoading;
  searchButton.textContent = isLoading ? "搜索中..." : "搜索";
  loadingState.classList.toggle("hidden", !isLoading);

  if (isLoading) {
    let index = 0;
    loadingCopy.textContent = loadingMessages[index];
    loadingTimer = window.setInterval(() => {
      index = (index + 1) % loadingMessages.length;
      loadingCopy.textContent = loadingMessages[index];
    }, 1800);
  } else if (loadingTimer) {
    clearInterval(loadingTimer);
    loadingTimer = null;
  }
}

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.classList.remove("hidden");
}

function clearError() {
  errorBanner.textContent = "";
  errorBanner.classList.add("hidden");
}

function createPill(text, className = "stat-pill") {
  const span = document.createElement("span");
  span.className = className;
  span.textContent = text;
  return span;
}

function safeUrlLabel(url) {
  if (!url) {
    return "本地语料";
  }
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname === "/" ? "" : parsed.pathname}`;
  } catch {
    return url;
  }
}

function safeDomain(url) {
  if (!url) {
    return "本地语料";
  }
  try {
    return new URL(url).hostname;
  } catch {
    return "外部链接";
  }
}

function renderDocCard(doc) {
  const fragment = evidenceTemplate.content.cloneNode(true);
  const sourceLink = fragment.querySelector(".result-source-link");
  const sourceDate = fragment.querySelector(".result-source-date");
  const titleLink = fragment.querySelector(".result-title-link");
  const snippet = fragment.querySelector(".result-snippet");
  const docTag = fragment.querySelector(".result-doc");
  const chunkTag = fragment.querySelector(".result-chunk");

  titleLink.textContent = doc.title || `相关结果 ${doc.rank}`;
  snippet.textContent = doc.snippet || "暂无摘要";
  docTag.textContent = `doc_id ${doc.doc_id ?? "-"}`;
  chunkTag.textContent = `chunk ${doc.chunk_id ?? "-"}/${doc.chunk_total ?? "-"}`;

  if (doc.url) {
    titleLink.href = doc.url;
    sourceLink.href = doc.url;
    sourceLink.textContent = safeUrlLabel(doc.url);
  } else {
    titleLink.href = "#";
    titleLink.removeAttribute("target");
    titleLink.removeAttribute("rel");
    sourceLink.href = "#";
    sourceLink.removeAttribute("target");
    sourceLink.removeAttribute("rel");
    sourceLink.textContent = safeDomain(doc.url);
  }

  sourceDate.textContent = doc.publish_time || "发布时间未知";
  return fragment;
}

function renderRound(round) {
  const fragment = roundTemplate.content.cloneNode(true);
  const index = fragment.querySelector(".round-index");
  const queries = fragment.querySelector(".round-queries");
  const assessment = fragment.querySelector(".round-assessment");

  index.textContent = `R${round.round}`;
  round.queries.forEach((query) => {
    queries.appendChild(createPill(query, "chip"));
  });

  const pieces = [];
  pieces.push(round.assessment.sufficient ? "证据充足" : "证据不足");
  if (round.assessment.reason) {
    pieces.push(`原因: ${round.assessment.reason}`);
  }
  if (typeof round.doc_count === "number") {
    pieces.push(`文档数: ${round.doc_count}`);
  }
  assessment.textContent = pieces.join(" | ");

  return fragment;
}

function updateUrl(query) {
  const url = new URL(window.location.href);
  url.searchParams.set("q", query);
  window.history.replaceState({}, "", url);
}

function renderResults(data) {
  heroSection.classList.add("hidden");
  resultsArea.classList.remove("hidden");

  resultCountline.textContent = `找到 ${data.stats.doc_count} 条相关结果，查询时间 ${(data.stats.elapsed_ms / 1000).toFixed(2)} 秒`;
  resultQuery.textContent = data.query;
  answerText.textContent = data.answer || "暂无答案";
  answerReason.textContent = data.assessment.reason || "未返回补充说明";
  answerBadge.textContent = data.assessment.sufficient ? "答案可信" : "证据有限";
  answerBadge.classList.toggle("warning", !data.assessment.sufficient);
  contextText.textContent = data.context || "暂无证据上下文";
  topbarStatus.textContent = data.assessment.sufficient ? "已返回答案和相关结果" : "已返回结果，建议继续核对来源";

  resultStats.innerHTML = "";
  resultStats.appendChild(createPill(`查询时间 ${(data.stats.elapsed_ms / 1000).toFixed(2)} 秒`));
  resultStats.appendChild(createPill(`语料 ${data.stats.corpus}`));
  resultStats.appendChild(createPill(`模式 ${data.stats.mode}`));
  resultStats.appendChild(createPill(`top_k ${data.stats.top_k}`));
  resultStats.appendChild(createPill(`top_n ${data.stats.top_n}`));
  resultStats.appendChild(createPill(`轮次 ${data.query_rounds.length}`));

  evidenceList.innerHTML = "";
  if (data.docs.length === 0) {
    const empty = document.createElement("article");
    empty.className = "search-result-card";
    empty.innerHTML = '<p class="result-snippet">没有返回可展示的证据结果，建议把问题问得更具体一些后重试。</p>';
    evidenceList.appendChild(empty);
  } else {
    data.docs.forEach((doc) => evidenceList.appendChild(renderDocCard(doc)));
  }

  rewrittenQueries.innerHTML = "";
  data.rewritten_queries.forEach((query) => {
    rewrittenQueries.appendChild(createPill(`第二轮: ${query}`, "chip"));
  });

  finalQueries.innerHTML = "";
  data.final_queries.forEach((query) => {
    finalQueries.appendChild(createPill(`最终: ${query}`, "chip"));
  });

  roundList.innerHTML = "";
  data.query_rounds.forEach((round) => roundList.appendChild(renderRound(round)));
}

async function search(query) {
  const normalized = query.trim();
  if (!normalized) {
    showError("请输入问题后再开始搜索。");
    searchInput.focus();
    return;
  }

  clearError();
  setLoading(true);
  updateUrl(normalized);

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ query: normalized })
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || data.error || "搜索失败");
    }

    renderResults(data);
  } catch (error) {
    showError(error.message || "搜索失败，请稍后重试。");
  } finally {
    setLoading(false);
  }
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  search(searchInput.value);
});

document.querySelectorAll(".suggestion-chip").forEach((button) => {
  button.addEventListener("click", () => {
    const query = button.textContent.trim();
    searchInput.value = query;
    search(query);
  });
});

window.addEventListener("DOMContentLoaded", () => {
  const url = new URL(window.location.href);
  const query = url.searchParams.get("q");
  if (query) {
    searchInput.value = query;
    search(query);
  }
});
