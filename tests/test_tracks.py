from daily_paper.config import load_config
from daily_paper.models import Paper
from daily_paper.tracks import apply_track_match, classify_deterministically


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
