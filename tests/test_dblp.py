from daily_paper.config import DblpConfig, DblpVenueConfig
from daily_paper.dblp import filter_dblp_papers, parse_results, parse_toc_xml


SAMPLE_DBLP = {
    "result": {
        "hits": {
            "hit": [
                {
                    "info": {
                        "key": "conf/recsys/Sample26",
                        "title": "Generative Recommendation with Large Language Models.",
                        "authors": {
                            "author": [
                                {"text": "Alice Zhang"},
                                {"text": "Bob Lee"},
                            ]
                        },
                        "venue": "RecSys",
                        "year": "2026",
                        "doi": "10.1145/example",
                        "ee": "https://doi.org/10.1145/example",
                        "url": "https://dblp.org/rec/conf/recsys/Sample26",
                    }
                },
                {
                    "info": {
                        "key": "conf/recsys/Other26",
                        "title": "A Database Indexing Paper.",
                        "authors": {"author": "Carol Smith"},
                        "venue": "RecSys",
                        "year": "2026",
                        "url": "https://dblp.org/rec/conf/recsys/Other26",
                    }
                },
                {
                    "info": {
                        "key": "conf/recsys/HR24",
                        "title": "Proceedings of the 4th Workshop on Recommender Systems for Human Resources (RecSys-in-HR 2024) co-located with the 18th ACM Conference on Recommender Systems (RecSys 2024), Bari, Italy, 14th-18th October 2024.",
                        "authors": {"author": "Editor Name"},
                        "venue": ["HR@RecSys", "CEUR Workshop Proceedings"],
                        "year": "2024",
                        "url": "https://dblp.org/rec/conf/recsys/HR24",
                    }
                },
            ]
        }
    }
}


def config():
    return DblpConfig(
        enabled=True,
        venues=[DblpVenueConfig(name="RecSys", query="RecSys")],
        include_keywords=["recommendation", "recommender", "LLM4Rec"],
        max_results_per_query=20,
        years_back=2,
        timeout_seconds=4,
        max_failures=2,
        max_total_results=20,
    )


SAMPLE_TOC = b"""<bht>
<dblpcites><r><proceedings key="conf/recsys/2025">
<title>Proceedings of the Nineteenth ACM Conference on Recommender Systems, RecSys 2025.</title>
<booktitle>RecSys</booktitle><year>2025</year>
</proceedings></r></dblpcites>
<dblpcites><r><inproceedings key="conf/recsys/Sample25">
<author>Alice Zhang</author>
<author>Bob Lee</author>
<title>A Language Model-Based Playlist Generation Recommender System.</title>
<year>2025</year>
<booktitle>RecSys</booktitle>
<ee>https://doi.org/10.1145/3705328.3748053</ee>
<url>db/conf/recsys/recsys2025.html#Sample25</url>
</inproceedings></r></dblpcites>
</bht>"""


def test_parse_results_maps_dblp_to_paper():
    papers = parse_results(SAMPLE_DBLP, DblpVenueConfig(name="RecSys", query="RecSys"))

    assert all(not paper.title.startswith("Proceedings of") for paper in papers)
    assert papers[0].id == "dblp:conf/recsys/Sample26"
    assert papers[0].source == "DBLP"
    assert papers[0].status == "conference"
    assert papers[0].venue == "RecSys"
    assert papers[0].doi == "10.1145/example"
    assert papers[0].authors == ["Alice Zhang", "Bob Lee"]
    assert papers[0].abs_url == "https://doi.org/10.1145/example"


def test_filter_dblp_papers_keeps_recommendation_titles():
    papers = parse_results(SAMPLE_DBLP, DblpVenueConfig(name="RecSys", query="RecSys"))

    filtered = filter_dblp_papers(papers, config())

    assert [paper.title for paper in filtered] == ["Generative Recommendation with Large Language Models"]


def test_parse_toc_xml_keeps_only_inproceedings_and_normalizes_venue():
    papers = parse_toc_xml(SAMPLE_TOC, DblpVenueConfig(name="RecSys", query="RecSys"))

    assert len(papers) == 1
    assert papers[0].title == "A Language Model-Based Playlist Generation Recommender System"
    assert papers[0].venue == "RecSys"
    assert papers[0].venue_key == "RecSys"
    assert papers[0].doi == "10.1145/3705328.3748053"
    assert papers[0].authors == ["Alice Zhang", "Bob Lee"]
