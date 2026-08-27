import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom";
import {
  fallbackDisplayTag,
  papersForView,
  researchDetailEntries,
  showAbEvidence,
  trackScore,
  trackTopics
} from "./paper-utils.mjs";
import "./styles.css";

const MARKS_KEY = "daily-paper-marks-v1";
const AB_LABELS = {
  yes: "有线上 A/B",
  no: "无线上 A/B",
  unknown: "未说明"
};
const AB_FILTER_LABELS = {
  All: "全部 A/B 状态",
  ...AB_LABELS
};
const TOPIC_LABELS = {
  post_training: "Post-training",
  llm_rl: "LLM RL",
  llm_agent: "LLM Agent"
};
const CLOUD_TOPIC_GROUPS = [
  {
    label: "LLM4Rec",
    aliases: [
      "LLM4Rec",
      "LLM recommendation",
      "LLM recommender",
      "LLM-based recommendation",
      "large language model recommendation",
      "large language models for recommendation",
      "large language model recommender",
      "foundation model recommendation",
      "foundation model recommender",
      "大语言模型推荐",
      "大模型推荐"
    ]
  },
  {
    label: "Generative Recommendation",
    aliases: [
      "generative recommendation",
      "generative recommender",
      "generative recommender system",
      "generative sequential recommendation",
      "generative collaborative filtering",
      "生成式推荐",
      "生成推荐"
    ]
  },
  {
    label: "Generative Retrieval",
    aliases: ["generative retrieval", "generative item retrieval", "生成式检索", "生成检索"]
  },
  {
    label: "Generative Ranking",
    aliases: ["generative ranking", "生成式排序", "生成排序"]
  },
  {
    label: "Semantic ID",
    aliases: [
      "semantic id",
      "semantic ids",
      "semantic identifier",
      "semantic identifiers",
      "item identifier",
      "item identifiers",
      "hierarchical identifier",
      "hierarchical identifier recommendation",
      "语义id",
      "语义 id",
      "语义标识",
      "语义标识符"
    ]
  },
  {
    label: "Semantic Tokenization",
    aliases: ["semantic token", "semantic tokens", "semantic tokenization", "语义token", "语义 token"]
  },
  {
    label: "Item Tokenization",
    aliases: ["item tokenization", "item token", "item tokens", "discrete item token", "discrete token recommendation"]
  },
  {
    label: "Codebook",
    aliases: ["codebook", "codebook recommendation", "码本"]
  },
  {
    label: "RQ-VAE",
    aliases: ["RQ-VAE", "RQVAE", "RQ-VAE recommendation", "residual quantization VAE"]
  },
  {
    label: "VQ-VAE",
    aliases: ["VQ-VAE", "VQVAE", "VQ-VAE recommendation", "vector quantization VAE"]
  },
  {
    label: "Vector Quantization",
    aliases: ["vector quantization", "vector quantization recommendation", "residual quantization", "residual quantization recommendation", "向量量化", "残差量化"]
  },
  {
    label: "Autoregressive Rec",
    aliases: ["autoregressive recommendation", "autoregressive recommender", "自回归推荐"]
  },
  {
    label: "Sequential Recommendation",
    aliases: ["sequential recommendation", "next item recommendation", "序列推荐"]
  },
  {
    label: "Session-based Recommendation",
    aliases: ["session-based recommendation", "session based recommendation", "会话推荐"]
  },
  {
    label: "Conversational Recommendation",
    aliases: ["conversational recommendation", "dialogue recommendation", "对话推荐"]
  },
  {
    label: "Interactive Recommendation",
    aliases: ["interactive recommendation", "交互式推荐"]
  },
  {
    label: "Explainable Recommendation",
    aliases: ["explainable recommendation", "可解释推荐"]
  },
  {
    label: "Personalized Recommendation",
    aliases: ["personalized recommendation", "personalised recommendation", "个性化推荐"]
  },
  {
    label: "RAG Recommendation",
    aliases: [
      "RAG recommendation",
      "RAG recommender",
      "RAG-based recommendation",
      "retrieval augmented recommendation",
      "retrieval augmented generation recommendation",
      "检索增强推荐"
    ]
  },
  {
    label: "Instruction Tuning",
    aliases: ["instruction tuning recommendation", "instruction tuning", "指令微调"]
  },
  {
    label: "Prompt-based Recommendation",
    aliases: ["prompt-based recommendation", "prompt based recommendation", "prompt-based recommender"]
  },
  {
    label: "In-context Learning",
    aliases: ["in-context learning recommendation", "in context learning recommendation", "zero-shot recommendation", "few-shot recommendation"]
  },
  {
    label: "User Modeling",
    aliases: ["LLM user modeling", "user preference modeling LLM", "user preference modeling", "用户建模", "偏好建模"]
  },
  {
    label: "Agent4Rec",
    aliases: [
      "Agent4Rec",
      "agent recommendation",
      "agent recommender",
      "agentic recommendation",
      "LLM agent recommendation",
      "LLM agent recommender",
      "recommendation agent",
      "recommender agent",
      "智能体推荐",
      "推荐智能体"
    ]
  },
  {
    label: "Multi-agent Recommendation",
    aliases: ["multi-agent recommendation", "multi-agent recommender", "多智能体推荐"]
  },
  {
    label: "User Simulator",
    aliases: ["user simulator recommendation", "LLM user simulator", "用户模拟器", "用户模拟"]
  },
  {
    label: "Tool-augmented Recommendation",
    aliases: ["tool-augmented recommendation", "工具增强推荐"]
  },
  {
    label: "Planning Agent",
    aliases: ["planning recommendation agent", "规划推荐智能体"]
  },
  {
    label: "Reasoning Agent",
    aliases: ["reasoning recommendation agent", "推理推荐智能体"]
  }
].map((topic) => ({
  ...topic,
  aliases: topic.aliases.map(normalizeKeywordKey)
}));
const CLOUD_LABEL_ALIASES = new Map(
  [
    ["Generative Rec", "Generative Recommendation"],
    ["Sequential Rec", "Sequential Recommendation"],
    ["Conversational Rec", "Conversational Recommendation"],
    ["RAG Rec", "RAG Recommendation"],
    ["General Rec", ""],
    ["RecSys", ""]
  ].map(([from, to]) => [normalizeKeywordKey(from), to])
);
const GENERIC_CLOUD_KEYS = new Set(
  [
    "RecSys",
    "General Rec",
    "recommender",
    "recommenders",
    "recommender system",
    "recommender systems",
    "recommend",
    "recommendation",
    "recommendations",
    "recommendation system",
    "recommendation systems",
    "推荐",
    "推荐系统"
  ].map(normalizeKeywordKey)
);
const DISPLAY_TAGS = [
  "LLM4Rec",
  "Semantic ID",
  "Item Tokenization",
  "Vector Quantization",
  "Generative Rec",
  "Generative Retrieval",
  "Generative Ranking",
  "RAG Rec",
  "Agent4Rec",
  "User Modeling",
  "Sequential Rec",
  "Conversational Rec",
  "Online Eval",
  "Benchmark",
  "Dataset",
  "Evaluation",
  "General Rec"
];
const DISPLAY_TAG_BY_KEY = new Map(DISPLAY_TAGS.map((label) => [normalizeKeywordKey(label), label]));
const DISPLAY_TAG_ALIASES = new Map(
  [
    ["RecSys", "General Rec"],
    ["Recommendation", "General Rec"],
    ["Recommendation System", "General Rec"],
    ["Generative Recommendation", "Generative Rec"],
    ["Sequential Recommendation", "Sequential Rec"],
    ["Conversational Recommendation", "Conversational Rec"],
    ["RAG Recommendation", "RAG Rec"],
    ["Online A/B", "Online Eval"],
    ["Online Evaluation", "Online Eval"]
  ].map(([from, to]) => [normalizeKeywordKey(from), to])
);
const DISPLAY_TAG_PRIORITY = new Map(DISPLAY_TAGS.map((label, index) => [label, index]));

function App() {
  const [payload, setPayload] = useState(null);
  const [selectedTrack, setSelectedTrack] = useState("");
  const [activeTopic, setActiveTopic] = useState("All");
  const [activeView, setActiveView] = useState("latest");
  const [query, setQuery] = useState("");
  const [archiveMonth, setArchiveMonth] = useState("All");
  const [archiveDate, setArchiveDate] = useState("All");
  const [tag, setTag] = useState("All");
  const [venue, setVenue] = useState("All");
  const [importanceFilter, setImportanceFilter] = useState("All");
  const [abFilter, setAbFilter] = useState("All");
  const [marks, setMarks] = useState(() => loadMarks());

  useEffect(() => {
    fetch("./papers.json")
      .then((response) => response.json())
      .then(setPayload)
      .catch(() => setPayload({ papers: [], site: { title: "Daily Paper Digest" } }));
  }, []);

  useEffect(() => {
    window.localStorage.setItem(MARKS_KEY, JSON.stringify(marks));
  }, [marks]);

  const includeKeywords = useMemo(() => payload?.interests?.include_keywords || [], [payload]);
  const papers = useMemo(() => {
    return (payload?.papers || []).map((paper) => ({
      ...paper,
      tracks: paper.tracks?.length ? paper.tracks : ["generative_rec"],
      localMark: marks[paper.id] || paper.importance || "normal",
      displayTags: paperDisplayTags(paper, includeKeywords)
    }));
  }, [payload, marks, includeKeywords]);

  const tracks = useMemo(() => {
    const configured = Object.values(payload?.tracks || {});
    return configured.length
      ? configured
      : [{ key: "generative_rec", label: "Generative Recommendation", cadence: "weekly" }];
  }, [payload]);
  const activeTrack = selectedTrack || payload?.default_track || tracks[0]?.key || "generative_rec";
  const activeTrackConfig = tracks.find((track) => track.key === activeTrack) || tracks[0] || {};
  const topics = useMemo(() => trackTopics(papers, activeTrack), [papers, activeTrack]);
  const viewPapers = useMemo(
    () => papersForView(papers, activeTrack, activeTopic, activeView),
    [papers, activeTrack, activeTopic, activeView]
  );

  const tags = useMemo(() => unique(viewPapers.flatMap((paper) => paper.displayTags || [])), [viewPapers]);
  const venues = useMemo(() => unique(viewPapers.map((paper) => displayVenue(paper)).filter(Boolean)), [viewPapers]);
  const archiveMonths = useMemo(() => uniqueDesc(viewPapers.map((paper) => paperMonth(paper)).filter(Boolean)), [viewPapers]);
  const archiveDates = useMemo(() => uniqueDesc(viewPapers.map((paper) => paperDate(paper)).filter(Boolean)), [viewPapers]);
  const archiveMonthLabels = useMemo(() => optionLabels(archiveMonths, formatArchiveMonth, "全部月份"), [archiveMonths]);
  const archiveDateLabels = useMemo(() => optionLabels(archiveDates, formatArchiveDate, "全部日期"), [archiveDates]);
  const keywordCloud = useMemo(() => buildKeywordCloud(viewPapers, includeKeywords), [viewPapers, includeKeywords]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return viewPapers.filter((paper) => {
      const haystack = [
        paper.title,
        (paper.authors || []).join(" "),
        displayAffiliations(paper).join(" "),
        (paper.affiliations || []).join(" "),
        paper.generated_summary,
        paper.venue,
        (paper.displayTags || []).join(" "),
        paperKeywordLabels(paper, includeKeywords).join(" ")
      ]
        .join(" ")
        .toLowerCase();
      return (
        (!needle || haystack.includes(needle)) &&
        (archiveMonth === "All" || paperMonth(paper) === archiveMonth) &&
        (archiveDate === "All" || paperDate(paper) === archiveDate) &&
        (tag === "All" || (paper.displayTags || []).includes(tag)) &&
        (venue === "All" || displayVenue(paper) === venue) &&
        (importanceFilter === "All" || paper.localMark === importanceFilter) &&
        (!showAbEvidence(activeTrack) || abFilter === "All" || (paper.ab_test || "unknown") === abFilter)
      );
    });
  }, [viewPapers, query, archiveMonth, archiveDate, tag, venue, importanceFilter, abFilter, includeKeywords, activeTrack]);
  const groupedPapers = useMemo(() => groupPapersByMonth(filtered), [filtered]);

  const stats = useMemo(() => buildStats(viewPapers), [viewPapers]);
  const site = payload?.site || {};
  const cache = payload?.analysis_cache || {};

  function setMark(paperId, value) {
    setMarks((current) => ({ ...current, [paperId]: value }));
  }

  function chooseTrack(trackKey) {
    setSelectedTrack(trackKey);
    setActiveTopic("All");
    setActiveView("latest");
    setArchiveMonth("All");
    setArchiveDate("All");
    setTag("All");
    setVenue("All");
    setAbFilter("All");
  }

  function selectKeyword(item) {
    const tagLabel = canonicalDisplayTag(item.label);
    const matchingTag = tags.find(
      (value) => value.toLowerCase() === item.label.toLowerCase() || (tagLabel && value.toLowerCase() === tagLabel.toLowerCase())
    );
    if (matchingTag) {
      setTag(tag === matchingTag ? "All" : matchingTag);
      return;
    }
    setQuery(query.trim().toLowerCase() === item.label.toLowerCase() ? "" : item.label);
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">GitHub Pages Research Dashboard</div>
          <h1>{site.title || "Daily Paper Digest"}</h1>
          <p>{activeTrackConfig.label || site.subtitle || "Research Paper Digest"}</p>
        </div>
        <div className="metaBlock">
          <span>Updated</span>
          <strong>{formatGeneratedAt(payload?.generated_at)}</strong>
        </div>
      </header>

      <nav className="trackTabs" aria-label="Research tracks">
        {tracks.map((track) => (
          <button
            className={activeTrack === track.key ? "active" : ""}
            key={track.key}
            onClick={() => chooseTrack(track.key)}
          >
            <span>{track.label}</span>
            <small>{track.cadence === "daily" ? "日更" : "周更"}</small>
          </button>
        ))}
      </nav>

      <div className="viewControls">
        <div className="viewTabs" aria-label="Paper collection">
          <button className={activeView === "latest" ? "active" : ""} onClick={() => setActiveView("latest")}>每日最新</button>
          {activeTrack === "llm_systems" && (
            <button className={activeView === "foundations" ? "active" : ""} onClick={() => setActiveView("foundations")}>近一年经典</button>
          )}
        </div>
        {topics.length > 0 && (
          <div className="topicTabs" aria-label="LLM topics">
            <button className={activeTopic === "All" ? "active" : ""} onClick={() => setActiveTopic("All")}>全部</button>
            {topics.map((topic) => (
              <button className={activeTopic === topic.key ? "active" : ""} key={topic.key} onClick={() => setActiveTopic(topic.key)}>
                {TOPIC_LABELS[topic.key] || topic.key}<span>{topic.count}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <section className="statsGrid" aria-label="Digest statistics">
        <Stat label="Papers" value={stats.total} />
        <Stat label="Archive Months" value={archiveMonths.length} />
        <Stat label="Important" value={stats.important} />
        <Stat
          label={showAbEvidence(activeTrack) ? "A/B Evidence" : "Foundations"}
          value={showAbEvidence(activeTrack) ? stats.abTests : stats.foundations}
        />
        <Stat label="Analysis Cache" value={`${cache.reused || 0}/${(cache.reused || 0) + (cache.analyzed || 0)}`} />
      </section>

      <WordCloud items={keywordCloud} activeTag={tag} activeQuery={query} onSelect={selectKeyword} />

      {payload?.analysis_enabled === false && (
        <div className="notice">
          未检测到 DEEPSEEK_API_KEY，创新点、实验结果和 A/B 测试字段使用保守 fallback。本机构建请设置 .env.local 后重新运行 ./scripts/build_pages.sh；GitHub Actions 部署请添加同名 Repository Secret 后重新运行 workflow。
        </div>
      )}

      <section className="toolbar">
        <input
          className="searchInput"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索标题、作者、机构、标签..."
        />
        <FilterGroup label="月份" value={archiveMonth} onChange={setArchiveMonth} options={["All", ...archiveMonths]} optionLabels={archiveMonthLabels} />
        <FilterGroup label="日期" value={archiveDate} onChange={setArchiveDate} options={["All", ...archiveDates]} optionLabels={archiveDateLabels} />
        <FilterGroup label="标签" value={tag} onChange={setTag} options={["All", ...tags]} />
        <FilterGroup label="会议" value={venue} onChange={setVenue} options={["All", ...venues]} />
        {showAbEvidence(activeTrack) && (
          <FilterGroup
            label="A/B 实验"
            value={abFilter}
            onChange={setAbFilter}
            options={["All", "yes", "no", "unknown"]}
            optionLabels={AB_FILTER_LABELS}
          />
        )}
        <FilterGroup
          label="重要性"
          value={importanceFilter}
          onChange={setImportanceFilter}
          options={["All", "high", "saved", "read", "normal"]}
        />
      </section>

      <section className="archiveSummary">
        <span>
          {archiveMonth === "All" ? "全部月份" : formatArchiveMonth(archiveMonth)}
          {" · "}
          {archiveDate === "All" ? "全部日期" : formatArchiveDate(archiveDate)}
          {showAbEvidence(activeTrack) && ` · ${AB_FILTER_LABELS[abFilter] || AB_FILTER_LABELS.All}`}
        </span>
        <strong>{filtered.length} 篇论文</strong>
      </section>

      <section className="archiveList">
        {filtered.length ? (
          groupedPapers.map((group) => (
            <section className="archiveSection" key={group.month}>
              <div className="archiveSectionHeader">
                <h2>{formatArchiveMonth(group.month)}</h2>
                <span>{group.papers.length} 篇</span>
              </div>
              <div className="dateGroupList">
                {group.dateGroups.map((dateGroup) => (
                  <section className="dateGroup" key={dateGroup.date}>
                    <div className="dateGroupHeader">
                      <span>{formatDateWithinMonth(dateGroup.date, group.month)}</span>
                      <strong>{dateGroup.papers.length} 篇</strong>
                    </div>
                    <div className="paperGrid">
                      {dateGroup.papers.map((paper) => (
                        <PaperCard key={paper.id} paper={paper} track={activeTrack} onMark={setMark} />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </section>
          ))
        ) : (
          <div className="emptyState">没有匹配的论文。调整搜索或筛选条件。</div>
        )}
      </section>
    </main>
  );
}

function PaperCard({ paper, track, onMark }) {
  const mark = paper.localMark || "normal";
  const displayTags = paper.displayTags || paper.tags || [];
  const researchDetails = researchDetailEntries(paper);
  return (
    <article className={`paperCard mark-${mark}`}>
      <div className="cardHeader">
        <div className="tagRow">
          {mark === "high" && <span className="badge badgeImportant">重要</span>}
          {paper.foundation && <span className="badge badgeFoundation">经典基线</span>}
          {paper.primary_topic && <span className="badge badgeTopic">{TOPIC_LABELS[paper.primary_topic] || paper.primary_topic}</span>}
          {displayTags.slice(0, 5).map((item) => (
            <span className="badge" key={item}>
              {item}
            </span>
          ))}
        </div>
        <div className="markControls" aria-label="Importance controls">
          <button className={mark === "high" ? "active" : ""} title="标记重要" onClick={() => onMark(paper.id, mark === "high" ? "normal" : "high")}>
            ☆
          </button>
          <button className={mark === "saved" ? "active" : ""} title="保存稍后阅读" onClick={() => onMark(paper.id, mark === "saved" ? "normal" : "saved")}>
            ⌑
          </button>
          <button className={mark === "read" ? "active" : ""} title="标记已读" onClick={() => onMark(paper.id, mark === "read" ? "normal" : "read")}>
            ✓
          </button>
        </div>
      </div>

      <h2>{paper.title}</h2>
      <p className="authors">{compactList(paper.authors, 8) || "Unknown authors"}</p>
      <p className="affiliations">{compactList(displayAffiliations(paper), 4) || "Unknown affiliation"}</p>
      <div className="paperMeta">
        <span>{displayVenue(paper) || paper.status}</span>
        <span>{formatPaperDate(paper)}</span>
        <span>{paper.analysis_basis === "full_text" ? "全文分析" : "元数据分析"}</span>
      </div>
      <div className="statusLine"><span>{markLabel(mark)}</span></div>

      <TrackScoreCard paper={paper} track={track} />

      <p className="summary">{paper.generated_summary || paper.abstract || "No summary available."}</p>
      {paper.core_method && (
        <div className="methodLine">
          <span>核心方法</span>
          <p>{paper.core_method}</p>
        </div>
      )}

      <InfoSection title="创新点" items={paper.innovation_points} />
      <InfoSection title="实验结果" items={paper.experiment_results} />

      {track === "llm_systems" && researchDetails.length > 0 && (
        <section className="researchDetails">
          <h3>研究设置</h3>
          <dl>
            {researchDetails.map((detail) => (
              <div key={detail.key}>
                <dt>{detail.label}</dt>
                <dd>{detail.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {showAbEvidence(track) && (
        <div className={`abBox ab-${paper.ab_test || "unknown"}`}>
          <span>{AB_LABELS[paper.ab_test] || AB_LABELS.unknown}</span>
          <p>{paper.ab_test_evidence || "论文未报告线上 A/B 测试。"}</p>
        </div>
      )}

      {paper.practical_value && (
        <div className="valueLine">
          <span>实践价值</span>
          <p>{paper.practical_value}</p>
        </div>
      )}

      <div className="linkRow">
        {paper.abs_url && (
          <a href={paper.abs_url} target="_blank" rel="noreferrer">
            Paper
          </a>
        )}
        {paper.pdf_url && (
          <a href={paper.pdf_url} target="_blank" rel="noreferrer">
            PDF
          </a>
        )}
        {paper.doi && (
          <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer">
            DOI
          </a>
        )}
      </div>
    </article>
  );
}

function WordCloud({ items, activeTag, activeQuery, onSelect }) {
  if (!items.length) return null;
  const topCount = items[0]?.count || 0;
  return (
    <section className="keywordCloud" aria-label="Keyword cloud">
      <div className="keywordCloudHeader">
        <h2>关键词词云</h2>
        <span>{items.length} 个关键词 · 最高 {topCount} 篇</span>
      </div>
      <div className="cloudTerms">
        {items.map((item) => {
          const active =
            activeTag.toLowerCase() === item.label.toLowerCase() ||
            activeQuery.trim().toLowerCase() === item.label.toLowerCase();
          return (
            <button
              className={`cloudTerm cloudLevel-${item.level}${active ? " active" : ""}`}
              key={item.label}
              onClick={() => onSelect(item)}
              title={`${item.count} 篇论文`}
            >
              {item.label}
              <span>{item.count}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function TrackScoreCard({ paper, track }) {
  const score = trackScore(paper, track);
  const isGr = track === "generative_rec";
  const signals = isGr && Array.isArray(paper.preference_signals) ? paper.preference_signals.filter(Boolean) : [];
  const rationale = String(
    paper.track_score_rationales?.[track] || (isGr ? paper.llm_score_rationale : "") || ""
  ).trim();
  if (!score && !signals.length && !rationale) return null;
  return (
    <div className="preferenceScore">
      <div className="preferenceHead">
        <span>{isGr ? "偏好评分" : "Track 评分"}</span>
        <strong>{score || "N/A"}</strong>
      </div>
      {signals.length > 0 && (
        <div className="signalRow">
          {signals.map((signal) => (
            <span key={signal}>{signal}</span>
          ))}
        </div>
      )}
      {rationale && <p>{rationale}</p>}
    </div>
  );
}

function InfoSection({ title, items }) {
  const values = Array.isArray(items) ? items.filter(Boolean) : [];
  return (
    <section className="infoSection">
      <h3>{title}</h3>
      {values.length ? (
        <ul>
          {values.map((item, index) => (
            <li key={`${title}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>暂无明确证据。</p>
      )}
    </section>
  );
}

function Stat({ label, value }) {
  return (
    <div className="statCard">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FilterGroup({ label, value, onChange, options, optionLabels = {} }) {
  return (
    <label className="filterGroup">
      <span>{label}</span>
      <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {optionLabels[option] || option}
          </option>
        ))}
      </select>
    </label>
  );
}

function buildStats(papers) {
  return {
    total: papers.length,
    important: papers.filter((paper) => paper.localMark === "high" || paper.importance === "high").length,
    abTests: papers.filter((paper) => paper.ab_test === "yes").length,
    foundations: papers.filter((paper) => paper.foundation).length,
    venues: unique(papers.map((paper) => displayVenue(paper)).filter(Boolean)).slice(0, 3).join(" · ") || "N/A"
  };
}

function buildKeywordCloud(papers, includeKeywords = []) {
  const counts = new Map();
  const labels = new Map();

  papers.forEach((paper) => {
    const seen = new Set();
    paperKeywordLabels(paper, includeKeywords).forEach((value) => addKeyword(value, seen, labels));
    seen.forEach((key) => counts.set(key, (counts.get(key) || 0) + 1));
  });

  const values = Array.from(counts.entries())
    .map(([key, count]) => ({ label: labels.get(key), count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
    .slice(0, 36);
  const max = Math.max(...values.map((item) => item.count), 0);
  const min = Math.min(...values.map((item) => item.count), max);
  return values.map((item) => {
    const ratio = max === min ? 1 : (item.count - min) / (max - min);
    return { ...item, level: Math.max(1, Math.min(5, Math.round(ratio * 4) + 1)) };
  });
}

function paperDisplayTags(paper, includeKeywords = []) {
  const labels = [];
  const seen = new Set();
  const addLabel = (value) => {
    const label = canonicalDisplayTag(value);
    const key = normalizeKeywordKey(label);
    if (!label || !key || seen.has(key)) return;
    seen.add(key);
    labels.push(label);
  };

  paperKeywordLabels(paper, includeKeywords).forEach(addLabel);
  (paper.tags || []).forEach(addLabel);
  if (paper.ab_test === "yes") addLabel("Online Eval");

  const specificLabels = labels.filter((label) => label !== "General Rec");
  const finalLabels = specificLabels.length ? specificLabels : labels;
  const fallbackTag = fallbackDisplayTag(paper);
  if (!finalLabels.length && fallbackTag) finalLabels.push(fallbackTag);

  return finalLabels
    .slice()
    .sort((left, right) => (DISPLAY_TAG_PRIORITY.get(left) ?? 999) - (DISPLAY_TAG_PRIORITY.get(right) ?? 999) || left.localeCompare(right))
    .slice(0, 5);
}

function canonicalDisplayTag(value) {
  const key = normalizeKeywordKey(value);
  if (!key) return "";
  if (DISPLAY_TAG_ALIASES.has(key)) return DISPLAY_TAG_ALIASES.get(key);
  return DISPLAY_TAG_BY_KEY.get(key) || "";
}

function paperKeywordLabels(paper, includeKeywords = []) {
  const text = paperKeywordText(paper);
  const labels = [];
  const seen = new Set();
  const addLabel = (value) => {
    const label = canonicalCloudLabel(value);
    const key = normalizeKeywordKey(label);
    if (!label || !key || seen.has(key)) return;
    seen.add(key);
    labels.push(label);
  };

  CLOUD_TOPIC_GROUPS.forEach((topic) => {
    if (topic.aliases.some((alias) => keywordTextIncludes(text, alias))) addLabel(topic.label);
  });
  (paper.tags || []).forEach(addLabel);
  includeKeywords.forEach((value) => {
    const keyword = normalizeKeywordKey(value);
    if (keyword && keywordTextIncludes(text, keyword)) addLabel(value);
  });

  return labels;
}

function paperKeywordText(paper) {
  return normalizeKeywordKey(
    [
      paper.title,
      paper.abstract,
      paper.generated_summary,
      paper.core_method,
      paper.practical_value,
      paper.ab_test_evidence,
      ...arrayValues(paper.innovation_points),
      ...arrayValues(paper.experiment_results),
      arrayValues(paper.preference_signals).join(" "),
      (paper.tags || []).join(" ")
    ].join(" ")
  );
}

function canonicalCloudLabel(value) {
  const label = String(value || "").replace(/\s+/g, " ").trim();
  const key = normalizeKeywordKey(label);
  if (!label || !key || GENERIC_CLOUD_KEYS.has(key)) return "";
  if (CLOUD_LABEL_ALIASES.has(key)) return CLOUD_LABEL_ALIASES.get(key);
  const topic = CLOUD_TOPIC_GROUPS.find((item) => normalizeKeywordKey(item.label) === key || item.aliases.includes(key));
  return topic ? topic.label : label;
}

function normalizeKeywordKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[-_/]+/g, " ")
    .replace(/[^\w\u4e00-\u9fff]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function keywordTextIncludes(text, keyword) {
  return Boolean(keyword && ` ${text} `.includes(` ${keyword} `));
}

function arrayValues(value) {
  if (Array.isArray(value)) return value;
  return value ? [value] : [];
}

function addKeyword(value, seen, labels) {
  const label = String(value || "").replace(/\s+/g, " ").trim();
  if (!label || label.length > 48) return;
  const key = label.toLowerCase();
  if (!key || seen.has(key)) return;
  seen.add(key);
  if (!labels.has(key)) labels.set(key, label);
}

function groupPapersByMonth(papers) {
  const groups = new Map();
  papers.forEach((paper) => {
    const month = paperMonth(paper) || "Unknown";
    const date = paperDate(paper) || "Unknown";
    if (!groups.has(month)) groups.set(month, { papers: [], dates: new Map() });
    const group = groups.get(month);
    group.papers.push(paper);
    if (!group.dates.has(date)) group.dates.set(date, []);
    group.dates.get(date).push(paper);
  });
  return Array.from(groups.entries())
    .sort(([left], [right]) => compareArchiveKeys(left, right))
    .map(([month, group]) => ({
      month,
      papers: group.papers,
      dateGroups: Array.from(group.dates.entries())
        .sort(([left], [right]) => compareArchiveKeys(left, right))
        .map(([date, values]) => ({ date, papers: values }))
    }));
}

function paperDate(paper) {
  return paperDateParts(paper).date;
}

function paperMonth(paper) {
  return paperDateParts(paper).month;
}

function paperDateParts(paper) {
  const candidates = [paper.published_date, paper.published];
  const ranks = { year: 1, month: 2, day: 3 };
  return candidates.reduce((best, value) => {
    const parsed = parseArchiveDate(value);
    if (!parsed) return best;
    if (!best || ranks[parsed.precision] > ranks[best.precision]) return parsed;
    return best;
  }, null) || { date: "", month: "", year: "", precision: "unknown" };
}

function parseArchiveDate(value) {
  const match = String(value || "").trim().match(/^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?/);
  if (!match) return null;
  const year = match[1];
  const month = match[2];
  const day = match[3];
  if (month && day) return { year, month: `${year}-${month}`, date: `${year}-${month}-${day}`, precision: "day" };
  if (month) return { year, month: `${year}-${month}`, date: `${year}-${month}`, precision: "month" };
  return { year, month: year, date: year, precision: "year" };
}

function compareArchiveKeys(left, right) {
  if (left === "Unknown") return 1;
  if (right === "Unknown") return -1;
  return right.localeCompare(left);
}

function displayVenue(paper) {
  let value = paper.venue_key || paper.venue || "";
  if (Array.isArray(value)) return value[0] || "";
  value = String(value);
  if (value.startsWith("[")) return paper.venue_key || "";
  return value;
}

function markLabel(mark) {
  if (mark === "high") return "当前状态：重要";
  if (mark === "saved") return "当前状态：稍后阅读";
  if (mark === "read") return "当前状态：已读";
  return "当前状态：未标记";
}

function loadMarks() {
  try {
    return JSON.parse(window.localStorage.getItem(MARKS_KEY) || "{}");
  } catch (error) {
    return {};
  }
}

function unique(values) {
  return Array.from(new Set(values)).sort((a, b) => a.localeCompare(b));
}

function uniqueDesc(values) {
  return Array.from(new Set(values)).sort((a, b) => b.localeCompare(a));
}

function optionLabels(options, formatter, allLabel) {
  return options.reduce((labels, option) => ({ ...labels, [option]: formatter(option) }), { All: allLabel });
}

function compactList(values, limit) {
  const items = (values || []).filter(Boolean);
  if (!items.length) return "";
  const visible = items.slice(0, limit).join(", ");
  return items.length > limit ? `${visible} et al.` : visible;
}

function displayAffiliations(paper) {
  const values = Array.isArray(paper.display_affiliations) && paper.display_affiliations.length
    ? paper.display_affiliations
    : paper.affiliations || [];
  const seen = new Set();
  return values.filter((value) => {
    const text = String(value || "").trim();
    const key = text.toLowerCase().replace(/^the\s+/, "").replace(/[^a-z0-9]+/g, "");
    if (!text || !key || key === "unknown" || key === "unknownaffiliation" || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function formatGeneratedAt(value) {
  if (!value) return "Not generated";
  try {
    return new Date(value).toLocaleString();
  } catch (error) {
    return value;
  }
}

function formatArchiveDate(value) {
  if (!value || value === "Unknown") return "未知日期";
  const parsed = parseArchiveDate(value);
  if (!parsed) return value;
  if (parsed.precision === "year") return `${parsed.year} 年`;
  const month = Number(parsed.month.slice(5, 7));
  if (parsed.precision === "month") return `${parsed.year} 年 ${month} 月`;
  const day = Number(parsed.date.slice(8, 10));
  return `${parsed.year} 年 ${month} 月 ${day} 日`;
}

function formatArchiveMonth(value) {
  if (!value || value === "Unknown") return "未知月份";
  const parsed = parseArchiveDate(value);
  if (!parsed) return value;
  if (parsed.precision === "year") return `${parsed.year} 年 · 月份未标注`;
  return `${parsed.year} 年 ${Number(parsed.month.slice(5, 7))} 月`;
}

function formatDateWithinMonth(date, month) {
  if (!date || date === "Unknown") return "未知日期";
  if (date === month) return "日期未细分";
  const parsed = parseArchiveDate(date);
  if (!parsed || parsed.precision !== "day") return formatArchiveDate(date);
  return `${Number(parsed.date.slice(8, 10))} 日`;
}

function formatPaperDate(paper) {
  return formatArchiveDate(paperDate(paper));
}

ReactDOM.render(<App />, document.getElementById("root"));
