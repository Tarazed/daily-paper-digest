const TOPIC_ORDER = ["post_training", "llm_rl", "llm_agent"];
const RESEARCH_DETAIL_LABELS = new Map([
  ["training_objective", "训练目标"],
  ["feedback_source", "反馈 / 奖励来源"],
  ["model_data_scale", "模型 / 数据规模"],
  ["key_benchmarks", "关键基准"],
  ["artifacts", "开源产物"],
  ["agent_environment", "Agent 环境"],
  ["agent_mechanism", "Agent 机制"],
  ["interaction_horizon", "交互时域"],
  ["agent_evaluation", "Agent 评测"]
]);


export function papersForView(papers, track, topic = "All", view = "latest") {
  return (Array.isArray(papers) ? papers : [])
    .filter((paper) => {
      const tracks = Array.isArray(paper.tracks) ? paper.tracks : [];
      const topics = Array.isArray(paper.topics) ? paper.topics : [];
      return (
        tracks.includes(track) &&
        (topic === "All" || topics.includes(topic)) &&
        (view !== "foundations" || Boolean(paper.foundation))
      );
    })
    .sort((left, right) => {
      if (view === "foundations") {
        const foundationDifference = Number(right.foundation_score || 0) - Number(left.foundation_score || 0);
        if (foundationDifference) return foundationDifference;
      }
      const scoreDifference = trackScore(right, track) - trackScore(left, track);
      if (scoreDifference) return scoreDifference;
      return paperTimestamp(right) - paperTimestamp(left) || String(left.title || "").localeCompare(String(right.title || ""));
    });
}


export function trackScore(paper, track) {
  const score = paper?.track_scores?.[track];
  if (Number.isFinite(Number(score))) return Number(score);
  if (track === "generative_rec" && Number.isFinite(Number(paper?.llm_score))) {
    return Number(paper.llm_score);
  }
  return 0;
}


export function trackTopics(papers, track) {
  const counts = new Map();
  papersForView(papers, track).forEach((paper) => {
    (Array.isArray(paper.topics) ? paper.topics : []).forEach((topic) => {
      if (topic) counts.set(topic, (counts.get(topic) || 0) + 1);
    });
  });
  return Array.from(counts, ([key, count]) => ({ key, count })).sort(
    (left, right) =>
      right.count - left.count ||
      topicIndex(left.key) - topicIndex(right.key) ||
      left.key.localeCompare(right.key)
  );
}


export function showAbEvidence(track) {
  return track === "generative_rec";
}


export function fallbackDisplayTag(paper) {
  const tracks = Array.isArray(paper?.tracks) ? paper.tracks : [];
  return tracks.includes("llm_systems") && !tracks.includes("generative_rec")
    ? ""
    : "General Rec";
}


export function researchDetailEntries(paper) {
  const details = paper?.research_details || {};
  const result = [];
  RESEARCH_DETAIL_LABELS.forEach((label, key) => {
    const rawValue = details[key];
    if (rawValue === undefined || rawValue === null || rawValue === "") return;
    const value = Array.isArray(rawValue)
      ? rawValue.filter(Boolean).join(" · ")
      : String(rawValue).trim();
    if (value) result.push({ key, label, value });
  });
  return result;
}


function topicIndex(topic) {
  const index = TOPIC_ORDER.indexOf(topic);
  return index === -1 ? TOPIC_ORDER.length : index;
}


function paperTimestamp(paper) {
  const value = Date.parse(paper?.published || paper?.updated || "");
  return Number.isFinite(value) ? value : 0;
}
