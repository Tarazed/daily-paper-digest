from daily_paper.config import load_config
from daily_paper.models import Paper
from daily_paper.tracks import (
    apply_track_match,
    apply_track_score,
    classify_deterministically,
    select_track_digest,
)


def make_paper(title, abstract):
    return Paper(
        id="arxiv:test",
        title=title,
        authors=["Alice"],
        affiliations=[],
        published="2026-08-20T00:00:00Z",
        updated="2026-08-20T00:00:00Z",
        abstract=abstract,
        categories=["cs.CL"],
        primary_category="cs.CL",
        abs_url="https://arxiv.org/abs/test",
        pdf_url="https://arxiv.org/pdf/test",
    )


def llm_track():
    return load_config("config.toml").tracks["llm_systems"]


def test_grpo_reasoning_paper_is_llm_rl():
    paper = make_paper(
        "GRPO for Reinforcement Learning of Language Model Reasoning",
        "We train a large language model with verifiable rewards.",
    )

    match = classify_deterministically(paper, llm_track())

    assert match.primary_topic == "llm_rl"
    assert "llm_rl" in match.topics
    assert match.relevance >= 70


def test_sft_and_preference_paper_is_post_training():
    paper = make_paper(
        "Data-Efficient SFT and Direct Preference Optimization",
        "We post-train a large language model with supervised fine-tuning and DPO.",
    )

    match = classify_deterministically(paper, llm_track())

    assert match.primary_topic == "post_training"
    assert match.relevance >= 70


def test_reward_model_paper_is_post_training():
    paper = make_paper(
        "Process Reward Models for Language Model Reasoning",
        "We train a language model verifier with process rewards.",
    )

    match = classify_deterministically(paper, llm_track())

    assert match.primary_topic == "post_training"
    assert match.relevance >= 70


def test_tool_memory_paper_is_llm_agent():
    paper = make_paper(
        "Long-Horizon Tool Agents with Episodic Memory",
        "Language-model agents plan and call tools over long interactions.",
    )

    match = classify_deterministically(paper, llm_track())

    assert match.primary_topic == "llm_agent"
    assert match.topics == ["llm_agent"]


def test_robot_control_without_llm_context_is_rejected():
    paper = make_paper(
        "Offline Reinforcement Learning for Robot Control",
        "A policy learns locomotion from demonstrations.",
    )

    match = classify_deterministically(paper, llm_track())

    assert match.relevance < 70
    assert match.topics == []


def test_explicit_language_model_agent_survives_robotics_term():
    paper = make_paper(
        "Language Model Agents for Robot Manipulation",
        "An LLM agent plans tool use and evaluates its actions.",
    )

    match = classify_deterministically(paper, llm_track())

    assert match.primary_topic == "llm_agent"
    assert match.relevance >= 70


def test_apply_track_match_enforces_threshold_and_records_evidence():
    accepted = make_paper("LLM Agent Tool Use", "A language model agent calls tools.")
    rejected = make_paper("Robot Control", "Offline reinforcement learning for locomotion.")

    accepted_match = classify_deterministically(accepted, llm_track())
    rejected_match = classify_deterministically(rejected, llm_track())

    assert apply_track_match(accepted, accepted_match, threshold=70) is True
    assert apply_track_match(rejected, rejected_match, threshold=70) is False
    assert accepted.tracks == ["llm_systems"]
    assert accepted.primary_topic == "llm_agent"
    assert accepted.track_relevance_evidence["llm_systems"]
    assert rejected.tracks == []


def test_llm_score_uses_confirmed_100_point_dimensions():
    paper = make_paper("A language model paper", "A technical contribution.")

    score = apply_track_score(
        paper,
        "llm_systems",
        {
            "relevance": 30,
            "technical": 22,
            "evidence": 18,
            "novelty": 12,
            "reproducibility": 7,
        },
        "Strong evidence.",
    )

    assert score == 89
    assert paper.track_scores["llm_systems"] == 89
    assert paper.track_score_breakdowns["llm_systems"]["technical"] == 22
    assert paper.track_score_rationales["llm_systems"] == "Strong evidence."


def test_llm_score_clamps_each_dimension_to_its_cap():
    paper = make_paper("A language model paper", "A technical contribution.")

    score = apply_track_score(
        paper,
        "llm_systems",
        {
            "relevance": 99,
            "technical": 99,
            "evidence": 99,
            "novelty": 99,
            "reproducibility": 99,
        },
        "",
    )

    assert score == 100


def test_selector_reserves_topics_and_redistributes_empty_quota():
    papers = make_scored_papers("post_training", 5, 90)
    papers += make_scored_papers("llm_rl", 5, 80)
    papers += make_scored_papers("llm_agent", 1, 70)

    selected = select_track_digest(
        papers,
        "llm_systems",
        quota=9,
        topic_quotas={"post_training": 3, "llm_rl": 3, "llm_agent": 3},
    )

    assert len(selected) == 9
    assert sum(p.primary_topic == "post_training" for p in selected) == 5
    assert sum(p.primary_topic == "llm_rl" for p in selected) == 3
    assert sum(p.primary_topic == "llm_agent" for p in selected) == 1
    assert len({p.id for p in selected}) == 9


def test_selector_excludes_sent_ids_and_deduplicates_papers():
    papers = make_scored_papers("llm_rl", 3, 90)
    duplicate = make_scored_papers("llm_rl", 1, 99)[0]
    duplicate.id = papers[1].id
    papers.append(duplicate)

    selected = select_track_digest(
        papers,
        "llm_systems",
        quota=3,
        topic_quotas={"llm_rl": 3},
        sent_ids={papers[0].id},
    )

    assert [paper.id for paper in selected] == [papers[1].id, papers[2].id]


def make_scored_papers(topic, count, starting_score):
    papers = []
    for index in range(count):
        paper = make_paper(
            "%s paper %s" % (topic, index),
            "A language model contribution.",
        )
        paper.id = "%s:%s" % (topic, index)
        paper.tracks = ["llm_systems"]
        paper.primary_track = "llm_systems"
        paper.topics = [topic]
        paper.primary_topic = topic
        paper.track_relevance = {"llm_systems": 80}
        paper.track_scores = {"llm_systems": starting_score - index}
        papers.append(paper)
    return papers
