import json
from pathlib import Path

from daily_paper.config import load_config
from daily_paper.state import load_state


def test_load_config_supports_multiline_arrays(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
state_file = "paper_state.toml"

[arxiv]
categories = [
  "cs.IR",
  "cs.CL",
]
include_keywords = ["recommendation"]
exclude_keywords = ["advertising"]
max_results = 20
days_back = 7

[email]
sender_name = "Digest"
default_to = "reader@example.com"
subject_prefix = "Papers"
top_n = 5
""",
        encoding="utf-8",
    )

    config = load_config(str(path))

    assert config.arxiv.categories == ["cs.IR", "cs.CL"]
    assert config.email.default_to == "reader@example.com"
    assert config.email.top_n == 5
    assert config.dblp.enabled is False
    assert config.dblp.venues[0].name == "RecSys"
    assert "ICLR" in [venue.name for venue in config.dblp.venues]
    assert "AAAI" in [venue.name for venue in config.dblp.venues]
    assert "ICML" in [venue.name for venue in config.dblp.venues]
    assert "NeurIPS" in [venue.name for venue in config.dblp.venues]
    assert config.dblp.max_failures == 2
    assert config.dblp.max_total_results == 20
    assert config.dblp.fallback_enabled is True
    assert config.dblp.fallback_providers == ["openalex", "semantic_scholar"]
    assert config.dblp.fallback_workers == 4
    assert config.summary.provider == "deepseek"
    assert config.summary.base_url == "https://api.deepseek.com"
    assert config.summary.model == "deepseek-v4-flash"
    assert config.summary.analysis_model == "deepseek-v4-pro"
    assert config.enrichment.enabled is True
    assert config.enrichment.confirm_providers == [
        "openalex",
        "crossref",
        "semantic_scholar",
        "arxiv_source",
    ]
    assert config.enrichment.confirmed_min_sources == 2
    assert config.enrichment.source_max_papers == 30
    assert config.site.title == "Daily Paper Digest"


def test_load_config_builds_explicit_track_profiles(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '''
default_track = "llm_systems"
digest_state_file = "digest_state.json"

[tracks.llm_systems]
label = "RL · Post-training · Agent"
enabled = true
cadence = "daily"
quota = 12
relevance_threshold = 70

[tracks.llm_systems.topic_quotas]
post_training = 4
llm_rl = 4
llm_agent = 4

[tracks.llm_systems.arxiv]
categories = ["cs.CL", "cs.AI"]
include_keywords = ["RLHF", "tool use"]
exclude_keywords = ["robot control"]
max_results = 120
days_back = 7
''',
        encoding="utf-8",
    )

    config = load_config(str(path))
    track = config.tracks["llm_systems"]

    assert config.default_track == "llm_systems"
    assert config.digest_state_file == "digest_state.json"
    assert track.topic_quotas == {
        "post_training": 4,
        "llm_rl": 4,
        "llm_agent": 4,
    }
    assert track.arxiv.categories == ["cs.CL", "cs.AI"]
    assert track.arxiv.include_keywords == ["RLHF", "tool use"]


def test_load_config_synthesizes_gr_track_for_legacy_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '''
[arxiv]
categories = ["cs.IR"]
include_keywords = ["recommendation"]
exclude_keywords = []
max_results = 20
days_back = 7
''',
        encoding="utf-8",
    )

    config = load_config(str(path))

    assert config.default_track == "generative_rec"
    assert config.tracks["generative_rec"].arxiv is config.arxiv
    assert config.tracks["generative_rec"].dblp is config.dblp


def test_load_state_reads_paper_entries(tmp_path):
    path = tmp_path / "paper_state.toml"
    path.write_text(
        """
[paper.arxiv_2606_01234]
id = "arxiv:2606.01234"
importance = "high"
read_status = "saved"
notes = "重点看实验。"
""",
        encoding="utf-8",
    )

    state = load_state(str(path))

    assert state["arxiv:2606.01234"]["importance"] == "high"
    assert state["arxiv:2606.01234"]["read_status"] == "saved"


def test_workflow_and_script_persist_state_without_push_email():
    workflow = Path(".github/workflows/daily-pages.yml").read_text(encoding="utf-8")
    script = Path("scripts/build_pages.sh").read_text(encoding="utf-8")
    initial_state = json.loads(Path("digest_state.json").read_text(encoding="utf-8"))

    assert "digest_state.json" in workflow
    assert "github.event_name == 'schedule'" in workflow
    assert "inputs.send_email" in workflow
    assert "--track llm_systems" in script
    assert "--track generative_rec" in script
    assert "DAILY_PAPER_SEND" in script
    assert " backfill " in script
    assert initial_state["sent_ids"] == {}
    assert initial_state["cold_start_completed_at"] == ""


def test_production_site_subtitle_uses_new_primary_focus():
    config = load_config("config.toml")

    assert "RL" in config.site.subtitle
    assert "Post-training" in config.site.subtitle
    assert "Agent" in config.site.subtitle
