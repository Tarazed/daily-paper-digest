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
    assert config.enrichment.source_max_papers == 30
    assert config.site.title == "Daily Paper Digest"


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
