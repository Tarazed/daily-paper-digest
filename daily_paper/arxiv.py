import datetime as _dt
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Iterable, List

from .config import ArxivConfig
from .models import Paper

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
API_URL = "https://export.arxiv.org/api/query"


def build_search_query(config: ArxivConfig, now: _dt.datetime = None) -> str:
    keyword_query = " OR ".join('all:"%s"' % keyword for keyword in config.include_keywords)
    category_query = " OR ".join("cat:%s" % category for category in config.categories)
    query = "(%s) AND (%s)" % (keyword_query, category_query)
    if config.days_back > 0:
        end = now or _dt.datetime.utcnow()
        start = end - _dt.timedelta(days=config.days_back)
        query = "(%s) AND submittedDate:[%s TO %s]" % (
            query,
            _format_arxiv_date(start),
            _format_arxiv_date(end),
        )
    return query


def fetch_papers(config: ArxivConfig) -> List[Paper]:
    params = {
        "search_query": build_search_query(config),
        "start": 0,
        "max_results": config.max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    body = _fetch_feed_with_retries(url, timeout=45, attempts=4)
    return filter_recent(parse_feed(body), config.days_back)


def _fetch_feed_with_retries(url: str, timeout: int, attempts: int) -> bytes:
    last_error = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={"User-Agent": "daily-paper-digest/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            print(
                "Warning: arXiv fetch attempt %d/%d failed; retrying. %s"
                % (attempt, attempts, exc),
                file=sys.stderr,
            )
            time.sleep(min(2 * attempt, 5))
    raise last_error


def parse_feed(body: bytes) -> List[Paper]:
    root = ET.fromstring(body)
    papers = []
    seen = set()
    for entry in root.findall(ATOM_NS + "entry"):
        paper = _parse_entry(entry)
        if paper.id not in seen:
            seen.add(paper.id)
            papers.append(paper)
    return papers


def filter_recent(papers: Iterable[Paper], days_back: int) -> List[Paper]:
    if days_back <= 0:
        return list(papers)
    cutoff = _dt.datetime.utcnow() - _dt.timedelta(days=days_back)
    recent = []
    for paper in papers:
        try:
            published = _parse_datetime(paper.published)
        except ValueError:
            recent.append(paper)
            continue
        if published >= cutoff:
            recent.append(paper)
    return recent


def _parse_entry(entry) -> Paper:
    abs_url = _text(entry, ATOM_NS + "id")
    arxiv_id = _extract_arxiv_id(abs_url)
    authors = []
    affiliations = []
    for author in entry.findall(ATOM_NS + "author"):
        name = _text(author, ATOM_NS + "name")
        if name:
            authors.append(name)
        affiliation = _text(author, ARXIV_NS + "affiliation")
        if affiliation:
            affiliations.append(affiliation)
    categories = [
        item.attrib.get("term", "")
        for item in entry.findall(ATOM_NS + "category")
        if item.attrib.get("term")
    ]
    primary = entry.find(ARXIV_NS + "primary_category")
    primary_category = primary.attrib.get("term", "") if primary is not None else ""
    pdf_url = ""
    for link in entry.findall(ATOM_NS + "link"):
        if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
            pdf_url = link.attrib.get("href", "")
            break
    doi = _text(entry, ARXIV_NS + "doi")
    return Paper(
        id="arxiv:%s" % arxiv_id,
        title=_clean_text(_text(entry, ATOM_NS + "title")),
        authors=authors,
        affiliations=affiliations,
        published=_text(entry, ATOM_NS + "published"),
        updated=_text(entry, ATOM_NS + "updated"),
        abstract=_clean_text(_text(entry, ATOM_NS + "summary")),
        categories=categories,
        primary_category=primary_category,
        abs_url=abs_url,
        pdf_url=pdf_url or abs_url.replace("/abs/", "/pdf/"),
        doi=doi,
    )


def _text(node, tag: str) -> str:
    child = node.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _extract_arxiv_id(url: str) -> str:
    value = url.rstrip("/").split("/")[-1]
    return re.sub(r"v\d+$", "", value)


def _parse_datetime(value: str) -> _dt.datetime:
    return _dt.datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")


def _format_arxiv_date(value: _dt.datetime) -> str:
    return value.strftime("%Y%m%d%H%M")
