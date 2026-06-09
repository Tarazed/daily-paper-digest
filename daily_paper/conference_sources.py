import datetime as _dt
import json
import os
import re
import urllib.parse
import urllib.request
from typing import Dict, Iterable, List, Optional

from .config import DblpConfig, DblpVenueConfig
from .models import Paper

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


def fetch_fallback_venue_papers(venue: DblpVenueConfig, config: DblpConfig) -> List[Paper]:
    if not config.fallback_enabled:
        return []
    providers = [provider.lower().replace("-", "_") for provider in config.fallback_providers]
    current_year = _dt.date.today().year
    years = range(current_year, current_year - config.years_back - 1, -1)
    papers = []
    seen = set()
    for year in years:
        for provider in providers:
            fetched = []
            if provider == "openalex":
                fetched = fetch_openalex_venue_papers(venue, year, config)
            elif provider in ("semantic_scholar", "semanticscholar", "s2"):
                fetched = fetch_semantic_scholar_venue_papers(venue, year, config)
            for paper in fetched:
                key = paper.doi.lower() if paper.doi else _normalize_title(paper.title)
                if not key or key in seen:
                    continue
                seen.add(key)
                papers.append(paper)
                if len(papers) >= config.max_results_per_query:
                    return papers
    return papers


def fetch_openalex_venue_papers(venue: DblpVenueConfig, year: int, config: DblpConfig) -> List[Paper]:
    query = _fallback_query(venue, config)
    filters = ["publication_year:%s" % year]
    params = {
        "search": query,
        "filter": ",".join(filters),
        "per-page": str(config.max_results_per_query),
        "sort": "cited_by_count:desc",
    }
    works = _get_json(OPENALEX_WORKS_URL, params, timeout=config.timeout_seconds).get("results", []) or []
    papers = [_openalex_work_to_paper(work, venue) for work in works]
    return _local_filter([paper for paper in papers if paper], venue, config)


def fetch_semantic_scholar_venue_papers(venue: DblpVenueConfig, year: int, config: DblpConfig) -> List[Paper]:
    fields = [
        "paperId",
        "title",
        "abstract",
        "authors",
        "year",
        "venue",
        "url",
        "externalIds",
        "publicationVenue",
        "publicationDate",
        "openAccessPdf",
        "publicationTypes",
    ]
    params = {
        "query": _fallback_query(venue, config),
        "year": str(year),
        "venue": venue.query,
        "limit": str(config.max_results_per_query),
        "fields": ",".join(fields),
    }
    payload = _get_json(SEMANTIC_SCHOLAR_SEARCH_URL, params, timeout=config.timeout_seconds)
    papers = [_semantic_scholar_work_to_paper(work, venue) for work in payload.get("data", []) or []]
    return _local_filter([paper for paper in papers if paper], venue, config)


def _openalex_work_to_paper(work: Dict[str, object], venue: DblpVenueConfig) -> Optional[Paper]:
    title = _clean_title(str(work.get("display_name", "")))
    if not title:
        return None
    work_id = str(work.get("id", "")).rstrip("/").split("/")[-1] or _normalize_title(title)
    doi = _clean_doi(str(work.get("doi", "")))
    year = str(work.get("publication_year", "") or "")
    link = _openalex_landing_url(work) or str(work.get("id", ""))
    pdf = _openalex_pdf_url(work) or link
    venue_name = _openalex_venue_name(work) or venue.name
    return Paper(
        id="openalex:%s" % work_id,
        title=title,
        authors=_openalex_authors(work),
        affiliations=_openalex_affiliations(work),
        published=str(work.get("publication_date", "") or year),
        updated=str(work.get("updated_date", "") or work.get("publication_date", "") or year),
        abstract=_openalex_abstract(work),
        categories=["OpenAlex", venue.name],
        primary_category=venue.name,
        abs_url=link,
        pdf_url=pdf,
        doi=doi,
        source="OpenAlex",
        status="conference",
        venue=venue_name,
        venue_key=venue.name,
    )


def _semantic_scholar_work_to_paper(work: Dict[str, object], venue: DblpVenueConfig) -> Optional[Paper]:
    title = _clean_title(str(work.get("title", "")))
    if not title:
        return None
    paper_id = str(work.get("paperId", "") or _normalize_title(title))
    external_ids = work.get("externalIds", {}) or {}
    doi = _clean_doi(str(external_ids.get("DOI", "")))
    arxiv_id = str(external_ids.get("ArXiv", "") or "")
    link = str(work.get("url", "") or "")
    if not link and doi:
        link = "https://doi.org/%s" % doi
    if not link and arxiv_id:
        link = "https://arxiv.org/abs/%s" % arxiv_id
    pdf = ""
    if isinstance(work.get("openAccessPdf"), dict):
        pdf = str(work.get("openAccessPdf", {}).get("url", "") or "")
    venue_info = work.get("publicationVenue", {}) or {}
    venue_name = str(venue_info.get("name", "") or work.get("venue", "") or venue.name)
    published = str(work.get("publicationDate", "") or work.get("year", "") or "")
    return Paper(
        id="s2:%s" % paper_id,
        title=title,
        authors=[str(author.get("name", "")).strip() for author in work.get("authors", []) or [] if author.get("name")],
        affiliations=[],
        published=published,
        updated=published,
        abstract=str(work.get("abstract", "") or ""),
        categories=["Semantic Scholar", venue.name],
        primary_category=venue.name,
        abs_url=link,
        pdf_url=pdf or link,
        doi=doi,
        source="Semantic Scholar",
        status="conference",
        venue=venue_name,
        venue_key=venue.name,
    )


def _get_json(url: str, params: Dict[str, str], timeout: int) -> Dict[str, object]:
    request_url = url + "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": "daily-paper-digest/0.1"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if api_key and "semanticscholar.org" in url:
        headers["x-api-key"] = api_key
    request = urllib.request.Request(request_url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _fallback_query(venue: DblpVenueConfig, config: DblpConfig) -> str:
    terms = []
    for keyword in config.include_keywords:
        lower = keyword.lower()
        if any(token in lower for token in ("recommender", "recommendation", "llm4rec", "generative")):
            terms.append(keyword)
        if len(terms) >= 4:
            break
    return "%s %s" % (venue.query, " ".join(terms or config.include_keywords[:3]))


def _local_filter(papers: Iterable[Paper], venue: DblpVenueConfig, config: DblpConfig) -> List[Paper]:
    filtered = []
    cutoff_year = _dt.date.today().year - config.years_back
    for paper in papers:
        year = _paper_year(paper)
        if year and year < cutoff_year:
            continue
        text = " ".join([paper.title, paper.abstract, paper.venue, " ".join(paper.categories)]).lower()
        if not any(keyword.lower() in text for keyword in config.include_keywords):
            continue
        if not _venue_matches(paper, venue):
            continue
        filtered.append(paper)
    return filtered


def _venue_matches(paper: Paper, venue: DblpVenueConfig) -> bool:
    haystack = " ".join([paper.venue, " ".join(paper.categories)]).lower()
    needles = {venue.name.lower(), venue.query.lower()}
    aliases = {
        "www": ["the web conference", "world wide web"],
        "neurips": ["nips", "neural information processing systems"],
        "recsys": ["acm conference on recommender systems"],
    }
    for alias in aliases.get(venue.name.lower(), []):
        needles.add(alias)
    return any(needle and needle in haystack for needle in needles)


def _openalex_landing_url(work: Dict[str, object]) -> str:
    for location_key in ("primary_location", "best_oa_location"):
        location = work.get(location_key)
        if isinstance(location, dict):
            for key in ("landing_page_url", "pdf_url"):
                value = str(location.get(key, "") or "")
                if value:
                    return value
    return ""


def _openalex_pdf_url(work: Dict[str, object]) -> str:
    for location_key in ("best_oa_location", "primary_location"):
        location = work.get(location_key)
        if isinstance(location, dict):
            value = str(location.get("pdf_url", "") or "")
            if value:
                return value
    return ""


def _openalex_venue_name(work: Dict[str, object]) -> str:
    location = work.get("primary_location", {})
    if isinstance(location, dict):
        source = location.get("source", {})
        if isinstance(source, dict):
            return str(source.get("display_name", "") or "")
    return ""


def _openalex_authors(work: Dict[str, object]) -> List[str]:
    authors = []
    for authorship in work.get("authorships", []) or []:
        author = authorship.get("author", {}) or {}
        name = str(author.get("display_name", "") or "").strip()
        if name:
            authors.append(name)
    return authors


def _openalex_affiliations(work: Dict[str, object]) -> List[str]:
    affiliations = []
    for authorship in work.get("authorships", []) or []:
        for value in authorship.get("raw_affiliation_strings", []) or []:
            _append_unique(affiliations, value)
        for institution in authorship.get("institutions", []) or []:
            _append_unique(affiliations, institution.get("display_name", ""))
    return affiliations


def _openalex_abstract(work: Dict[str, object]) -> str:
    index = work.get("abstract_inverted_index")
    if not isinstance(index, dict):
        return ""
    words = []
    for word, positions in index.items():
        for position in positions or []:
            try:
                words.append((int(position), word))
            except (TypeError, ValueError):
                continue
    return " ".join(word for _, word in sorted(words))


def _append_unique(values: List[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def _clean_doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://doi\.org/", "", value, flags=re.I)
    return value


def _clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().rstrip(".")


def _normalize_title(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _paper_year(paper: Paper) -> int:
    try:
        return int(paper.published[:4])
    except (TypeError, ValueError):
        return 0
