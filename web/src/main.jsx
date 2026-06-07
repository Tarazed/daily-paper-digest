import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom";
import "./styles.css";

const MARKS_KEY = "daily-paper-marks-v1";
const AB_LABELS = {
  yes: "有线上 A/B",
  no: "无线上 A/B",
  unknown: "未说明"
};

function App() {
  const [payload, setPayload] = useState(null);
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("All");
  const [source, setSource] = useState("All");
  const [venue, setVenue] = useState("All");
  const [importanceFilter, setImportanceFilter] = useState("All");
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

  const papers = useMemo(() => {
    return (payload?.papers || []).map((paper) => ({
      ...paper,
      localMark: marks[paper.id] || paper.importance || "normal"
    }));
  }, [payload, marks]);

  const tags = useMemo(() => unique(papers.flatMap((paper) => paper.tags || [])), [papers]);
  const sources = useMemo(() => unique(papers.map((paper) => paper.source).filter(Boolean)), [papers]);
  const venues = useMemo(() => unique(papers.map((paper) => displayVenue(paper)).filter(Boolean)), [papers]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return papers.filter((paper) => {
      const haystack = [
        paper.title,
        (paper.authors || []).join(" "),
        (paper.affiliations || []).join(" "),
        paper.generated_summary,
        paper.venue,
        paper.source,
        (paper.tags || []).join(" ")
      ]
        .join(" ")
        .toLowerCase();
      return (
        (!needle || haystack.includes(needle)) &&
        (tag === "All" || (paper.tags || []).includes(tag)) &&
        (source === "All" || paper.source === source) &&
        (venue === "All" || displayVenue(paper) === venue) &&
        (importanceFilter === "All" || paper.localMark === importanceFilter)
      );
    });
  }, [papers, query, tag, source, venue, importanceFilter]);

  const stats = useMemo(() => buildStats(papers), [papers]);
  const site = payload?.site || {};

  function setMark(paperId, value) {
    setMarks((current) => ({ ...current, [paperId]: value }));
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">GitHub Pages Research Dashboard</div>
          <h1>{site.title || "Daily Paper Digest"}</h1>
          <p>{site.subtitle || "Recommendation Systems Paper Digest"}</p>
        </div>
        <div className="metaBlock">
          <span>Updated</span>
          <strong>{formatGeneratedAt(payload?.generated_at)}</strong>
        </div>
      </header>

      <section className="statsGrid" aria-label="Digest statistics">
        <Stat label="Papers" value={stats.total} />
        <Stat label="Important" value={stats.important} />
        <Stat label="A/B Evidence" value={stats.abTests} />
        <Stat label="Top Venues" value={stats.venues} />
      </section>

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
        <FilterGroup label="标签" value={tag} onChange={setTag} options={["All", ...tags]} />
        <FilterGroup label="来源" value={source} onChange={setSource} options={["All", ...sources]} />
        <FilterGroup label="会议" value={venue} onChange={setVenue} options={["All", ...venues]} />
        <FilterGroup
          label="重要性"
          value={importanceFilter}
          onChange={setImportanceFilter}
          options={["All", "high", "saved", "read", "normal"]}
        />
      </section>

      <section className="paperGrid">
        {filtered.length ? (
          filtered.map((paper) => <PaperCard key={paper.id} paper={paper} onMark={setMark} />)
        ) : (
          <div className="emptyState">没有匹配的论文。调整搜索或筛选条件。</div>
        )}
      </section>
    </main>
  );
}

function PaperCard({ paper, onMark }) {
  const mark = paper.localMark || "normal";
  return (
    <article className={`paperCard mark-${mark}`}>
      <div className="cardHeader">
        <div className="tagRow">
          {mark === "high" && <span className="badge badgeImportant">重要</span>}
          {(paper.tags || []).slice(0, 5).map((item) => (
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
      <p className="affiliations">{compactList(paper.affiliations, 4) || "Unknown affiliation"}</p>
      <div className="paperMeta">
        <span>{paper.source}</span>
        <span>{displayVenue(paper) || paper.status}</span>
        <span>{paper.published_date || (paper.published || "").slice(0, 10)}</span>
        <span>{paper.analysis_basis === "full_text" ? "全文分析" : "元数据分析"}</span>
      </div>
      <div className="statusLine"><span>{markLabel(mark)}</span></div>

      <p className="summary">{paper.generated_summary || paper.abstract || "No summary available."}</p>
      {paper.core_method && (
        <div className="methodLine">
          <span>核心方法</span>
          <p>{paper.core_method}</p>
        </div>
      )}

      <InfoSection title="创新点" items={paper.innovation_points} />
      <InfoSection title="实验结果" items={paper.experiment_results} />

      <div className={`abBox ab-${paper.ab_test || "unknown"}`}>
        <span>{AB_LABELS[paper.ab_test] || AB_LABELS.unknown}</span>
        <p>{paper.ab_test_evidence || "论文未报告线上 A/B 测试。"}</p>
      </div>

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

function FilterGroup({ label, value, onChange, options }) {
  return (
    <label className="filterGroup">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
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
    venues: unique(papers.map((paper) => displayVenue(paper)).filter(Boolean)).slice(0, 3).join(" · ") || "N/A"
  };
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

function compactList(values, limit) {
  const items = (values || []).filter(Boolean);
  if (!items.length) return "";
  const visible = items.slice(0, limit).join(", ");
  return items.length > limit ? `${visible} et al.` : visible;
}

function formatGeneratedAt(value) {
  if (!value) return "Not generated";
  try {
    return new Date(value).toLocaleString();
  } catch (error) {
    return value;
  }
}

ReactDOM.render(<App />, document.getElementById("root"));
