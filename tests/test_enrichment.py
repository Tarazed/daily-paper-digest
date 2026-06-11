import json

from daily_paper.config import EnrichmentConfig
from daily_paper.enrichment import (
    enrich_papers,
    extract_affiliations,
    extract_crossref_affiliations,
    extract_semantic_scholar_affiliations,
    extract_tex_affiliations,
    lookup_confirmed_affiliations,
    normalize_affiliations,
)
from daily_paper.models import Paper


def make_paper():
    return Paper(
        id="arxiv:2606.01234",
        title="LLM4Rec for Sequential Recommendation",
        authors=["Alice Zhang"],
        affiliations=[],
        published="2026-06-07T00:00:00Z",
        updated="2026-06-07T00:00:00Z",
        abstract="A recommendation paper.",
        categories=["cs.IR"],
        primary_category="cs.IR",
        abs_url="https://arxiv.org/abs/2606.01234",
        pdf_url="https://arxiv.org/pdf/2606.01234",
    )


def config(**overrides):
    values = {
        "enabled": True,
        "provider": "openalex",
        "mailto": "",
        "max_results": 3,
        "confirm_providers": ["openalex", "crossref", "semantic_scholar", "arxiv_source"],
        "confirmed_min_sources": 2,
        "source_enabled": True,
        "source_max_papers": 5,
        "source_timeout_seconds": 8,
    }
    values.update(overrides)
    return EnrichmentConfig(**values)


def test_extract_affiliations_from_openalex_authorships():
    work = {
        "authorships": [
            {
                "raw_affiliation_strings": ["Stanford University"],
                "institutions": [{"display_name": "Stanford University"}],
            },
            {
                "raw_affiliation_strings": [],
                "institutions": [{"display_name": "Google DeepMind"}],
            },
        ]
    }

    assert extract_affiliations(work) == ["Stanford University", "Google DeepMind"]


def test_enrich_papers_uses_openalex_title_match(monkeypatch):
    paper = make_paper()
    payload = {
        "results": [
            {
                "display_name": "LLM4Rec for Sequential Recommendation",
                "authorships": [
                    {
                        "raw_affiliation_strings": [],
                        "institutions": [{"display_name": "Tsinghua University"}],
                    }
                ],
            }
        ]
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        assert "api.openalex.org/works" in request.full_url
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    enriched = enrich_papers(
        [paper],
        EnrichmentConfig(
            enabled=True,
            provider="openalex",
            mailto="",
            max_results=3,
            confirm_providers=["openalex"],
            confirmed_min_sources=1,
            source_enabled=True,
            source_max_papers=5,
            source_timeout_seconds=8,
        ),
    )

    assert enriched[0].affiliations == ["Tsinghua University"]


def test_enrich_papers_replaces_unknown_or_invalid_affiliations(monkeypatch):
    paper = make_paper()
    paper.affiliations = ["Unknown affiliation", "Klara"]

    monkeypatch.setattr(
        "daily_paper.enrichment.lookup_confirmed_affiliations",
        lambda *args, **kwargs: (["The Chinese University of Hong Kong"], False),
    )

    enriched = enrich_papers([paper], config(confirm_providers=["openalex"]))

    assert enriched[0].affiliations == ["The Chinese University of Hong Kong"]


def test_normalize_affiliations_removes_duplicate_location_variants():
    affiliations = normalize_affiliations(
        [
            "The Chinese University of Hong Kong, Hong Kong, Hong Kong",
            "Chinese University of Hong Kong",
            "McGill University, Montreal, Canada",
            "McGill University",
            "Klara",
        ]
    )

    assert affiliations == ["Chinese University of Hong Kong", "McGill University"]


def test_extract_affiliations_from_crossref_authors():
    work = {
        "author": [
            {"affiliation": [{"name": "Tsinghua University"}]},
            {"affiliation": [{"name": "Google DeepMind"}]},
        ]
    }

    assert extract_crossref_affiliations(work) == ["Tsinghua University", "Google DeepMind"]


def test_extract_affiliations_from_semantic_scholar_authors():
    work = {
        "authors": [
            {"name": "Alice", "affiliations": ["Tsinghua University"]},
            {"name": "Bob", "affiliations": ["Google DeepMind"]},
        ]
    }

    assert extract_semantic_scholar_affiliations(work) == [
        "Tsinghua University",
        "Google DeepMind",
    ]


def test_lookup_confirmed_affiliations_prefers_multi_source_confirmation(monkeypatch):
    paper = make_paper()

    monkeypatch.setattr(
        "daily_paper.enrichment.lookup_openalex_affiliations",
        lambda paper, config: ["Tsinghua University", "Unconfirmed Lab"],
    )
    monkeypatch.setattr(
        "daily_paper.enrichment.lookup_crossref_affiliations",
        lambda paper, config: ["Tsinghua University"],
    )
    monkeypatch.setattr(
        "daily_paper.enrichment.lookup_semantic_scholar_affiliations",
        lambda paper, config: [],
    )
    monkeypatch.setattr(
        "daily_paper.enrichment.lookup_arxiv_source_affiliations",
        lambda *args, **kwargs: ["Another University"],
    )

    affiliations, used_source_lookup = lookup_confirmed_affiliations(
        paper,
        config(confirm_providers=["openalex", "crossref", "semantic_scholar", "arxiv_source"]),
    )

    assert used_source_lookup is True
    assert affiliations == ["Tsinghua University"]


def test_lookup_confirmed_affiliations_falls_back_to_trusted_single_source(monkeypatch):
    paper = make_paper()

    monkeypatch.setattr(
        "daily_paper.enrichment.lookup_openalex_affiliations",
        lambda paper, config: ["Tsinghua University"],
    )
    monkeypatch.setattr(
        "daily_paper.enrichment.lookup_crossref_affiliations",
        lambda paper, config: [],
    )

    affiliations, used_source_lookup = lookup_confirmed_affiliations(
        paper,
        config(confirm_providers=["openalex", "crossref"], confirmed_min_sources=2),
    )

    assert used_source_lookup is False
    assert affiliations == ["Tsinghua University"]


def test_extract_tex_affiliations_from_common_commands():
    tex = r"""
\author{Alice}
\affiliation{Department of Computer Science, Tsinghua University}
\author{Bob}
\institute{Google DeepMind}
\thanks{Work done at Microsoft Research. alice@example.com}
"""

    affiliations = extract_tex_affiliations(tex)

    assert "Department of Computer Science, Tsinghua University" in affiliations
    assert "Google DeepMind" in affiliations
    assert "Work done at Microsoft Research." in affiliations


def test_extract_tex_affiliations_removes_email_tail():
    tex = r"""
\affiliation{Institute of Information Engineering, Chinese Academy of Sciences, Beijing, China
\\ \ zhouxi, limingming, guotao\ @iie.ac.cn}
"""

    affiliations = extract_tex_affiliations(tex)

    assert affiliations == [
        "Institute of Information Engineering, Chinese Academy of Sciences, Beijing, China"
    ]


def test_extract_tex_affiliations_from_author_blocks():
    tex = r"""
\author{Alice Zhang\\Tsinghua University\\alice@example.com \and
Bob Lee\\Google DeepMind}
"""

    affiliations = extract_tex_affiliations(tex)

    assert "Tsinghua University" in affiliations
    assert "Google DeepMind" in affiliations


def test_extract_tex_affiliations_from_ieee_author_block():
    tex = r"""
\author{\IEEEauthorblockN{Alice Zhang}
\IEEEauthorblockA{Department of Computer Science\\Stanford University}}
"""

    affiliations = extract_tex_affiliations(tex)

    assert any("Stanford University" in affiliation for affiliation in affiliations)
