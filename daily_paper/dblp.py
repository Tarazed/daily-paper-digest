import datetime as _dt
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import urllib.parse
import urllib.request
from typing import Dict, Iterable, List

from .config import DblpConfig, DblpVenueConfig
from .models import Paper

API_URL = "https://dblp.org/search/publ/api"
VENUE_SLUGS = {
    "RecSys": ("recsys", "recsys"),
    "SIGIR": ("sigir", "sigir"),
    "WWW": ("www", "www"),
    "KDD": ("kdd", "kdd"),
    "WSDM": ("wsdm", "wsdm"),
    "CIKM": ("cikm", "cikm"),
    "ICLR": ("iclr", "iclr"),
    "AAAI": ("aaai", "aaai"),
    "ICML": ("icml", "icml"),
    "NeurIPS": ("nips", "neurips"),
}


def fetch_dblp_papers(config: DblpConfig) -> List[Paper]:
    if not config.enabled:
        return []
    papers = []
    seen = set()
    failures = 0
    for venue in config.venues:
        if failures >= config.max_failures:
            print("Warning: DBLP skipped remaining venues after repeated failures.", file=sys.stderr)
            break
        try:
            venue_papers = fetch_venue_papers(venue, config)
        except Exception as exc:
            failures += 1
            print("Warning: DBLP fetch failed for %s. %s" % (venue.name, exc), file=sys.stderr)
            continue
        failures = 0
        for paper in venue_papers:
            if paper.id in seen:
                continue
            seen.add(paper.id)
            papers.append(paper)
            if len(papers) >= config.max_total_results:
                return papers
    return papers


def fetch_venue_papers(venue: DblpVenueConfig, config: DblpConfig) -> List[Paper]:
    toc_papers = fetch_venue_toc_papers(venue, config)
    if toc_papers:
        return filter_dblp_papers(toc_papers, config)
    return fetch_venue_search_papers(venue, config)


def fetch_venue_search_papers(venue: DblpVenueConfig, config: DblpConfig) -> List[Paper]:
    params = {
        "q": venue.query,
        "format": "json",
        "h": str(config.max_results_per_query),
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "daily-paper-digest/0.1"})
    with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return filter_dblp_papers(parse_results(payload, venue), config)


def fetch_venue_toc_papers(venue: DblpVenueConfig, config: DblpConfig) -> List[Paper]:
    current_year = _dt.date.today().year
    years = range(current_year, current_year - config.years_back - 1, -1)
    papers = []
    for year in years:
        for url in _toc_urls(venue, year):
            try:
                body = _fetch_url(url, timeout=config.timeout_seconds)
            except Exception:
                continue
            parsed = parse_toc_xml(body, venue)
            if parsed:
                papers.extend(filter_dblp_papers(parsed, config))
                break
        if len(papers) >= config.max_results_per_query:
            break
    return papers[: config.max_results_per_query]


def parse_toc_xml(body: bytes, venue: DblpVenueConfig) -> List[Paper]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        body = b"<root>" + body + b"</root>"
        root = ET.fromstring(body)
    papers = []
    for node in root.iter("inproceedings"):
        title = _clean_title(_child_text(node, "title"))
        if not title or _is_non_paper_record(title, {"type": "inproceedings"}):
            continue
        key = node.attrib.get("key", title)
        year = _child_text(node, "year")
        doi = _extract_doi([child.text or "" for child in node.findall("ee")])
        ee = _first_nonempty([child.text or "" for child in node.findall("ee")])
        url = _child_text(node, "url")
        link = ee or _doi_url(doi) or ("https://dblp.org/rec/%s" % key)
        papers.append(
            Paper(
                id="dblp:%s" % key,
                title=title,
                authors=[_clean_author_name(author.text) for author in node.findall("author") if author.text],
                affiliations=[],
                published=_published_from_year(year),
                updated=_published_from_year(year),
                abstract="",
                categories=["DBLP", venue.name],
                primary_category=venue.name,
                abs_url=link,
                pdf_url=link,
                doi=doi,
                source="DBLP",
                status="conference",
                venue=venue.name,
                venue_key=venue.name,
            )
        )
    return papers


def parse_results(payload: Dict[str, object], venue: DblpVenueConfig) -> List[Paper]:
    hits = payload.get("result", {}).get("hits", {}).get("hit", [])
    if isinstance(hits, dict):
        hits = [hits]
    papers = []
    for hit in hits or []:
        info = hit.get("info", {}) or {}
        title = _clean_title(str(info.get("title", "")))
        if not title:
            continue
        if _is_non_paper_record(title, info):
            continue
        year = str(info.get("year", "")).strip()
        key = str(info.get("key", "") or hit.get("@id", "") or title)
        doi = str(info.get("doi", "")).strip()
        ee = _first_value(info.get("ee", ""))
        dblp_url = str(info.get("url", "")).strip()
        link = ee or _doi_url(doi) or dblp_url
        papers.append(
            Paper(
                id="dblp:%s" % key,
                title=title,
                authors=_parse_authors(info.get("authors", {})),
                affiliations=[],
                published=_published_from_year(year),
                updated=_published_from_year(year),
                abstract="",
                categories=["DBLP", venue.name],
                primary_category=venue.name,
                abs_url=link or dblp_url,
                pdf_url=link or dblp_url,
                doi=doi,
                source="DBLP",
                status="conference",
                venue=venue.name,
                venue_key=venue.name,
            )
        )
    return papers


def filter_dblp_papers(papers: Iterable[Paper], config: DblpConfig) -> List[Paper]:
    cutoff_year = _dt.date.today().year - config.years_back
    filtered = []
    for paper in papers:
        year = _paper_year(paper)
        if year and year < cutoff_year:
            continue
        if _is_non_paper_record(paper.title, {"type": paper.status}):
            continue
        text = (paper.title + " " + paper.venue + " " + " ".join(paper.categories)).lower()
        if any(keyword.lower() in text for keyword in config.include_keywords):
            filtered.append(paper)
    return filtered


def _parse_authors(authors_value) -> List[str]:
    authors = authors_value.get("author", []) if isinstance(authors_value, dict) else authors_value
    if isinstance(authors, (str, int)):
        authors = [authors]
    parsed = []
    for author in authors or []:
        if isinstance(author, dict):
            name = author.get("text") or author.get("#text") or author.get("name") or ""
        else:
            name = author
        value = str(name).strip()
        if value:
            parsed.append(_clean_author_name(value))
    return parsed


def _clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().rstrip(".")


def _clean_author_name(value: str) -> str:
    return re.sub(r"\s+\d{4}$", "", re.sub(r"\s+", " ", str(value)).strip())


def _is_non_paper_record(title: str, info: Dict[str, object]) -> bool:
    text = title.lower()
    record_type = str(info.get("type", "")).lower()
    if record_type in ("editorship", "proceedings"):
        return True
    blocked_starts = (
        "proceedings of",
        "proceedings,",
        "adjunct proceedings",
        "companion proceedings",
        "front matter",
        "preface",
        "editorial",
        "introduction to the proceedings",
        "table of contents",
    )
    blocked_terms = (
        " co-located with ",
        "ceur workshop proceedings",
        "workshop on recommender systems",
        "doctoral consortium",
        "tutorial",
        "challenge proceedings",
    )
    return text.startswith(blocked_starts) or any(term in text for term in blocked_terms)


def _first_value(value) -> str:
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return str(value).strip()


def _first_nonempty(values) -> str:
    for value in values:
        text = str(value).strip()
        if text:
            return text
    return ""


def _child_text(node, tag: str) -> str:
    child = node.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def _extract_doi(values) -> str:
    for value in values:
        match = re.search(r"10\.\d{4,9}/\S+", str(value))
        if match:
            return match.group(0).rstrip(".")
    return ""


def _fetch_url(url: str, timeout: int) -> bytes:
    try:
        return _fetch_url_with_curl(url, timeout=timeout)
    except Exception:
        request = urllib.request.Request(url, headers={"User-Agent": "daily-paper-digest/0.1"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()


def _fetch_url_with_curl(url: str, timeout: int) -> bytes:
    command = [
        "curl",
        "--noproxy",
        "*",
        "--silent",
        "--show-error",
        "--fail",
        "--max-time",
        str(max(timeout, 2)),
        url,
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout


def _toc_urls(venue: DblpVenueConfig, year: int) -> List[str]:
    conf_slug, file_prefix = VENUE_SLUGS.get(venue.name, (venue.query.lower(), venue.query.lower()))
    return ["https://dblp.org/db/conf/%s/%s%s.xml" % (conf_slug, file_prefix, year)]


def _doi_url(doi: str) -> str:
    return "https://doi.org/%s" % doi if doi else ""


def _published_from_year(year: str) -> str:
    return year if year else ""


def _paper_year(paper: Paper) -> int:
    try:
        return int(paper.published[:4])
    except (TypeError, ValueError):
        return 0
