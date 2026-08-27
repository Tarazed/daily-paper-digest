import assert from "node:assert/strict";
import test from "node:test";

import {
  fallbackDisplayTag,
  papersForView,
  researchDetailEntries,
  showAbEvidence,
  trackScore,
  trackTopics
} from "../src/paper-utils.mjs";


test("track and foundation views stay isolated", () => {
  const papers = [
    {
      id: "a",
      tracks: ["llm_systems"],
      topics: ["llm_rl"],
      foundation: true,
      track_scores: { llm_systems: 88 }
    },
    {
      id: "b",
      tracks: ["generative_rec"],
      topics: [],
      foundation: false,
      track_scores: { generative_rec: 77 }
    }
  ];

  assert.deepEqual(
    papersForView(papers, "llm_systems", "llm_rl", "foundations").map((paper) => paper.id),
    ["a"]
  );
  assert.deepEqual(
    papersForView(papers, "generative_rec", "All", "latest").map((paper) => paper.id),
    ["b"]
  );
  assert.equal(trackScore(papers[0], "llm_systems"), 88);
});


test("latest and foundation views use their own ranking", () => {
  const papers = [
    { id: "low", tracks: ["llm_systems"], topics: ["llm_rl"], published: "2026-08-27", foundation: true, foundation_score: 70, track_scores: { llm_systems: 70 } },
    { id: "classic", tracks: ["llm_systems"], topics: ["llm_rl"], published: "2026-07-01", foundation: true, foundation_score: 95, track_scores: { llm_systems: 80 } },
    { id: "high", tracks: ["llm_systems"], topics: ["llm_rl"], published: "2026-08-20", foundation: false, foundation_score: 0, track_scores: { llm_systems: 92 } }
  ];

  assert.deepEqual(
    papersForView(papers, "llm_systems", "All", "latest").map((paper) => paper.id),
    ["high", "classic", "low"]
  );
  assert.deepEqual(
    papersForView(papers, "llm_systems", "All", "foundations").map((paper) => paper.id),
    ["classic", "low"]
  );
});


test("topics are counted only inside the active track", () => {
  const papers = [
    { id: "a", tracks: ["llm_systems"], topics: ["llm_rl", "llm_agent"] },
    { id: "b", tracks: ["llm_systems"], topics: ["llm_rl"] },
    { id: "c", tracks: ["generative_rec"], topics: ["llm_agent"] }
  ];

  assert.deepEqual(trackTopics(papers, "llm_systems"), [
    { key: "llm_rl", count: 2 },
    { key: "llm_agent", count: 1 }
  ]);
});


test("track score safely handles legacy records", () => {
  assert.equal(trackScore({ llm_score: 72 }, "generative_rec"), 72);
  assert.equal(trackScore({}, "llm_systems"), 0);
});


test("track-specific evidence stays isolated", () => {
  const paper = {
    research_details: {
      training_objective: "verifiable reasoning",
      key_benchmarks: ["AIME", "MATH"],
      ignored: "not public"
    }
  };

  assert.equal(showAbEvidence("llm_systems"), false);
  assert.equal(showAbEvidence("generative_rec"), true);
  assert.deepEqual(researchDetailEntries(paper), [
    { key: "training_objective", label: "训练目标", value: "verifiable reasoning" },
    { key: "key_benchmarks", label: "关键基准", value: "AIME · MATH" }
  ]);
});


test("LLM papers never receive a Generative Recommendation fallback tag", () => {
  assert.equal(fallbackDisplayTag({ tracks: ["llm_systems"] }), "");
  assert.equal(fallbackDisplayTag({ tracks: ["generative_rec"] }), "General Rec");
  assert.equal(fallbackDisplayTag({}), "General Rec");
});
