import json

from daily_paper.config import EnrichmentConfig
from daily_paper.enrichment import enrich_papers, extract_affiliations, extract_tex_affiliations
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
            source_enabled=True,
            source_max_papers=5,
            source_timeout_seconds=8,
        ),
    )

    assert enriched[0].affiliations == ["Tsinghua University"]


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
