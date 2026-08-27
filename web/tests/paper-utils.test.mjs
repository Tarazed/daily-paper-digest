import assert from "node:assert/strict";
import test from "node:test";

import {
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
