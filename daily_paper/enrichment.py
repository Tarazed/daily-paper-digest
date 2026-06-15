import gzip
import io
import json
import os
import re
import ssl
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from typing import Dict, Iterable, List

from .config import EnrichmentConfig
from .models import Paper, _affiliation_display_key

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
ARXIV_EPRINT_URL = "https://arxiv.org/e-print/%s"


def enrich_papers(
    papers: Iterable[Paper],
    config: EnrichmentConfig,
    llm_model: str = "deepseek-v4-flash",
    llm_base_url: str = "https://api.deepseek.com",
) -> List[Paper]:
    items = list(papers)
    if not config.enabled or config.provider.lower() != "openalex":
        return items
    source_attempts = 0
    for paper in items:
        paper.affiliations = normalize_affiliations(paper.affiliations)
        if _has_affiliations(paper):
            continue
        allow_source_lookup = config.source_enabled and source_attempts < config.source_max_papers
        affiliations, used_source_lookup = lookup_confirmed_affiliations(
            paper,
            config,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            include_arxiv_source=allow_source_lookup,
        )
        if used_source_lookup:
            source_attempts += 1
        if affiliations:
            paper.affiliations = normalize_affiliations(affiliations)
    return items


def normalize_affiliations(values: Iterable[str]) -> List[str]:
    affiliations = []
    for value in values or []:
        cleaned = _clean_affiliation_name(value)
        if not cleaned or not _looks_like_institution_name(cleaned):
            continue
        _append_affiliation_unique(affiliations, cleaned)
    return affiliations


def lookup_confirmed_affiliations(
    paper: Paper,
    config: EnrichmentConfig,
    llm_model: str = "deepseek-v4-flash",
    llm_base_url: str = "https://api.deepseek.com",
    include_arxiv_source: bool = True,
) -> tuple[List[str], bool]:
    providers = [str(value).lower().replace("-", "_") for value in config.confirm_providers]
    providers = providers or ["openalex", "crossref", "semantic_scholar", "arxiv_source"]
    candidates: Dict[str, List[str]] = {}
    used_source_lookup = False
    for provider in providers:
        affiliations = []
        try:
            if provider == "openalex":
                affiliations = lookup_openalex_affiliations(paper, config)
            elif provider == "crossref":
                affiliations = lookup_crossref_affiliations(paper, config)
            elif provider in ("semantic_scholar", "semanticscholar", "s2"):
                affiliations = lookup_semantic_scholar_affiliations(paper, config)
            elif provider == "arxiv_source" and include_arxiv_source:
                used_source_lookup = True
                affiliations = lookup_arxiv_source_affiliations(
                    paper,
                    llm_model=llm_model,
                    llm_base_url=llm_base_url,
                    timeout_seconds=config.source_timeout_seconds,
                )
        except Exception:
            affiliations = []
        cleaned = [_clean_affiliation_name(value) for value in affiliations]
        cleaned = [value for value in cleaned if value]
        if cleaned:
            candidates[provider] = normalize_affiliations(cleaned)
    return _select_confirmed_affiliations(candidates, config.confirmed_min_sources), used_source_lookup


def lookup_openalex_affiliations(paper: Paper, config: EnrichmentConfig) -> List[str]:
    works = []
    if paper.doi:
        works = _fetch_works({"filter": "doi:%s" % paper.doi}, config)
    if not works:
        works = _fetch_works({"search": paper.title}, config)
    work = _best_openalex_title_match(paper.title, works)
    if not work:
        return []
    return extract_affiliations(work)


def lookup_crossref_affiliations(paper: Paper, config: EnrichmentConfig) -> List[str]:
    works = []
    if paper.doi:
        try:
            payload = _fetch_crossref_work(paper.doi, config)
            message = payload.get("message", {}) if isinstance(payload, dict) else {}
            if message:
                works = [message]
        except Exception:
            works = []
    if not works:
        works = _fetch_crossref_works({"query.title": paper.title}, config)
    work = _best_crossref_title_match(paper.title, works)
    if not work:
        return []
    return extract_crossref_affiliations(work)


def lookup_semantic_scholar_affiliations(paper: Paper, config: EnrichmentConfig) -> List[str]:
    fields = ["title", "externalIds", "authors", "authors.affiliations"]
    params = {
        "query": paper.doi or paper.title,
        "limit": str(config.max_results),
        "fields": ",".join(fields),
    }
    payload = _fetch_semantic_scholar(params, config)
    work = _best_semantic_scholar_title_match(paper.title, payload.get("data", []) or [])
    if not work:
        return []
    return extract_semantic_scholar_affiliations(work)


def lookup_arxiv_source_affiliations(
    paper: Paper,
    llm_model: str = "deepseek-v4-flash",
    llm_base_url: str = "https://api.deepseek.com",
    timeout_seconds: int = 8,
) -> List[str]:
    arxiv_id = paper.id.replace("arxiv:", "")
    if not arxiv_id:
        return []
    try:
        tex_documents = _fetch_arxiv_tex_documents(arxiv_id, timeout_seconds=timeout_seconds)
    except Exception:
        return []
    raw_values = []
    for document in tex_documents:
        raw_values.extend(extract_tex_affiliations(document))
    raw_values = _dedupe(raw_values)
    if not raw_values:
        return []
    cleaned = _clean_affiliations_with_llm(raw_values, model=llm_model, base_url=llm_base_url)
    return cleaned or raw_values


def extract_affiliations(work: Dict[str, object]) -> List[str]:
    names = []
    for authorship in work.get("authorships", []) or []:
        raw = authorship.get("raw_affiliation_strings") or []
        for value in raw:
            _append_unique(names, value)
        for institution in authorship.get("institutions", []) or []:
            name = institution.get("display_name")
            if name:
                _append_unique(names, name)
    return names


def extract_crossref_affiliations(work: Dict[str, object]) -> List[str]:
    affiliations = []
    for author in work.get("author", []) or []:
        for affiliation in author.get("affiliation", []) or []:
            if isinstance(affiliation, dict):
                _append_unique(affiliations, affiliation.get("name", ""))
            else:
                _append_unique(affiliations, str(affiliation))
    return affiliations


def extract_semantic_scholar_affiliations(work: Dict[str, object]) -> List[str]:
    affiliations = []
    for author in work.get("authors", []) or []:
        for value in author.get("affiliations", []) or []:
            _append_unique(affiliations, value)
    return affiliations


def extract_tex_affiliations(tex: str) -> List[str]:
    text = _strip_tex_comments(tex)
    values = []
    command_names = [
        "affiliation",
        "affil",
        "institute",
        "institution",
        "orgname",
        "orgdiv",
        "orgaddress",
        "address",
        "affaddr",
        "IEEEauthorblockA",
    ]
    for command in command_names:
        for value in _extract_braced_command_values(text, command):
            if _looks_like_affiliation(value):
                _append_unique(values, _clean_tex(value))
    for value in _extract_braced_command_values(text, "author"):
        for candidate in _extract_author_block_affiliations(value):
            _append_unique(values, candidate)
    for value in _extract_braced_command_values(text, "thanks"):
        if _looks_like_affiliation(value):
            _append_unique(values, _clean_tex(value))
    return values[:12]


def _select_confirmed_affiliations(
    candidates: Dict[str, List[str]], min_sources: int = 2
) -> List[str]:
    if not candidates:
        return []
    by_name: Dict[str, Dict[str, object]] = {}
    for provider, affiliations in candidates.items():
        for affiliation in affiliations:
            normalized = _normalize_affiliation(affiliation)
            if not normalized:
                continue
            bucket = by_name.setdefault(normalized, {"value": affiliation, "sources": set()})
            bucket["sources"].add(provider)
    confirmed = []
    required = max(1, int(min_sources))
    for bucket in by_name.values():
        if len(bucket["sources"]) >= required:
            _append_unique(confirmed, str(bucket["value"]))
    if confirmed:
        return confirmed

    fallback = []
    trusted_order = ("openalex", "crossref", "semantic_scholar", "semanticscholar", "s2", "arxiv_source")
    for provider in trusted_order:
        for affiliation in candidates.get(provider, []):
            _append_unique(fallback, affiliation)
        if fallback:
            return fallback
    for affiliations in candidates.values():
        for affiliation in affiliations:
            _append_unique(fallback, affiliation)
    return fallback


def _fetch_works(params: Dict[str, str], config: EnrichmentConfig) -> List[Dict[str, object]]:
    query = dict(params)
    query["per-page"] = str(config.max_results)
    if config.mailto:
        query["mailto"] = config.mailto
    url = OPENALEX_WORKS_URL + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers=_headers_for_url(url, config))
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("results", []) or []


def _fetch_crossref_work(doi: str, config: EnrichmentConfig) -> Dict[str, object]:
    url = CROSSREF_WORKS_URL + "/" + urllib.parse.quote(doi)
    request = urllib.request.Request(url, headers=_headers_for_url(url, config))
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_crossref_works(params: Dict[str, str], config: EnrichmentConfig) -> List[Dict[str, object]]:
    query = dict(params)
    query["rows"] = str(config.max_results)
    url = CROSSREF_WORKS_URL + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers=_headers_for_url(url, config))
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    message = payload.get("message", {}) or {}
    return message.get("items", []) or []


def _fetch_semantic_scholar(params: Dict[str, str], config: EnrichmentConfig) -> Dict[str, object]:
    url = SEMANTIC_SCHOLAR_SEARCH_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers=_headers_for_url(url, config))
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_arxiv_tex_documents(arxiv_id: str, timeout_seconds: int = 8) -> List[str]:
    url = ARXIV_EPRINT_URL % urllib.parse.quote(arxiv_id)
    request = urllib.request.Request(url, headers={"User-Agent": "daily-paper-digest/0.1"})
    with _open_arxiv_eprint(request, timeout_seconds) as response:
        payload = response.read()
    documents = _read_tar_tex_documents(payload)
    if documents:
        return documents
    for decoder in (gzip.decompress,):
        try:
            decoded = decoder(payload)
        except Exception:
            continue
        documents = _read_tar_tex_documents(decoded)
        if documents:
            return documents
        text = _decode_text(decoded)
        if text:
            return [text]
    text = _decode_text(payload)
    return [text] if text else []


def _open_arxiv_eprint(request: urllib.request.Request, timeout_seconds: int):
    try:
        return urllib.request.urlopen(request, timeout=timeout_seconds)
    except urllib.error.URLError as exc:
        if not _is_ssl_cert_error(exc):
            raise
        context = ssl._create_unverified_context()
        return urllib.request.urlopen(request, timeout=timeout_seconds, context=context)


def _is_ssl_cert_error(exc: urllib.error.URLError) -> bool:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    return "CERTIFICATE_VERIFY_FAILED" in str(exc)


def _headers_for_url(url: str, config: EnrichmentConfig) -> Dict[str, str]:
    headers = {"User-Agent": "daily-paper-digest/0.1"}
    if config.mailto and "crossref.org" in url:
        headers["User-Agent"] = "daily-paper-digest/0.1 (mailto:%s)" % config.mailto
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if api_key and "semanticscholar.org" in url:
        headers["x-api-key"] = api_key
    return headers


def _read_tar_tex_documents(payload: bytes) -> List[str]:
    documents = []
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
            for member in archive.getmembers():
                if not member.isfile() or not member.name.lower().endswith(".tex"):
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                text = _decode_text(extracted.read())
                if text:
                    documents.append(text)
    except tarfile.TarError:
        return []
    return documents


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            text = payload.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\\begin{document}" in text or "\\author" in text or "\\affiliation" in text:
            return text
    return ""


def _best_openalex_title_match(title: str, works: List[Dict[str, object]]) -> Dict[str, object]:
    return _best_title_match(title, works, "display_name")


def _best_semantic_scholar_title_match(title: str, works: List[Dict[str, object]]) -> Dict[str, object]:
    return _best_title_match(title, works, "title")


def _best_crossref_title_match(title: str, works: List[Dict[str, object]]) -> Dict[str, object]:
    normalized_title = _normalize_title(title)
    best = None
    best_score = 0.0
    for work in works:
        titles = work.get("title", []) or []
        candidate_title = titles[0] if titles else ""
        candidate = _normalize_title(str(candidate_title))
        if not candidate:
            continue
        score = SequenceMatcher(None, normalized_title, candidate).ratio()
        if score > best_score:
            best = work
            best_score = score
    return best if best_score >= 0.88 else {}


def _best_title_match(title: str, works: List[Dict[str, object]], title_key: str) -> Dict[str, object]:
    normalized_title = _normalize_title(title)
    best = None
    best_score = 0.0
    for work in works:
        candidate = _normalize_title(str(work.get(title_key, "")))
        if not candidate:
            continue
        score = SequenceMatcher(None, normalized_title, candidate).ratio()
        if score > best_score:
            best = work
            best_score = score
    return best if best_score >= 0.88 else {}


def _extract_braced_command_values(text: str, command: str) -> List[str]:
    values = []
    pattern = re.compile(r"\\" + re.escape(command) + r"(?:\[[^\]]*\])?\s*\{")
    for match in pattern.finditer(text):
        value, _ = _read_balanced_braces(text, match.end() - 1)
        if value:
            values.append(value)
    return values


def _read_balanced_braces(text: str, start: int):
    if start >= len(text) or text[start] != "{":
        return "", start
    depth = 0
    escaped = False
    chunks = []
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            chunks.append(char)
            escaped = False
            continue
        if char == "\\":
            chunks.append(char)
            escaped = True
            continue
        if char == "{":
            depth += 1
            if depth > 1:
                chunks.append(char)
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return "".join(chunks), index
            chunks.append(char)
            continue
        chunks.append(char)
    return "", start


def _clean_affiliations_with_llm(values: List[str], model: str, base_url: str) -> List[str]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return []
    prompt = (
        "Extract institution names from the following LaTeX affiliation snippets. "
        "Return strict JSON only: {\"affiliations\": [\"Institution name\"]}. "
        "Remove departments, street addresses, emails, and duplicate institutions. "
        "Do not invent institutions.\n\n"
        + "\n".join("- " + value for value in values[:12])
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Extract clean institution names. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "max_tokens": 400,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        output = _extract_chat_output_text(data)
        parsed = json.loads(output)
    except Exception:
        return []
    return normalize_affiliations([str(value).strip() for value in parsed.get("affiliations", []) if value])


def _extract_chat_output_text(data: Dict[str, object]) -> str:
    choices = data.get("choices", []) or []
    if not choices:
        return ""
    message = choices[0].get("message", {}) or {}
    return str(message.get("content", "")).strip()


def _strip_tex_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        cut = None
        escaped = False
        for index, char in enumerate(line):
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == "%":
                cut = index
                break
        lines.append(line[:cut] if cut is not None else line)
    return "\n".join(lines)


def _clean_tex(value: str) -> str:
    cleaned = value
    cleaned = re.split(r"\\\\|\\newline|\\and", cleaned, maxsplit=1)[0]
    cleaned = re.sub(r"[A-Za-z0-9._%+\-]+(?:\\?\s*)?@[\w.\-]+", " ", cleaned)
    cleaned = re.sub(r"\\(?:textsuperscript|thanks|email|url|href)\s*\{[^{}]*\}", " ", cleaned)
    cleaned = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", cleaned)
    cleaned = re.sub(r"[{}$^_~\\]", " ", cleaned)
    cleaned = cleaned.replace("\\&", "&")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    return cleaned.strip(" ,;")


def _looks_like_affiliation(value: str) -> bool:
    cleaned = _clean_tex(value).lower()
    if "@" in cleaned and len(cleaned.split()) <= 4:
        return False
    markers = [
        "university",
        "institute",
        "college",
        "school",
        "laboratory",
        "lab",
        "department",
        "academy",
        "polytechnic",
        "research",
        "centre",
        "center",
        "cnrs",
        "inria",
        "eth ",
        "epfl",
        "kaist",
        "mit ",
        "stanford",
        "corporation",
        "technology",
        "technologies",
        "kuaishou",
        "google",
        "deepmind",
        "microsoft",
        "meta",
        "openai",
        "amazon",
        "apple",
        "nvidia",
        "huawei",
        "baidu",
        "alibaba",
        "tencent",
        "bytedance",
    ]
    return any(marker in cleaned for marker in markers)


def _extract_author_block_affiliations(value: str) -> List[str]:
    text = value
    text = re.sub(r"\\\\|\\newline|\\par|\\and\b", "\n", text)
    text = re.sub(r"\\(?:inst|textsuperscript|thanks|email|url|href)\s*(?:\[[^\]]*\])?\{[^{}]*\}", " ", text)
    text = re.sub(r"[A-Za-z0-9._%+\-]+(?:\\?\s*)?@[\w.\-]+", " ", text)
    candidates = []
    for line in text.splitlines():
        candidate = _clean_tex_preserving_block_text(line)
        if not candidate or not _looks_like_affiliation(candidate):
            continue
        _append_unique(candidates, candidate)
    return candidates


def _clean_tex_preserving_block_text(value: str) -> str:
    cleaned = value
    cleaned = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", cleaned)
    cleaned = re.sub(r"[{}$^_~\\]", " ", cleaned)
    cleaned = cleaned.replace("\\&", "&")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    return cleaned.strip(" ,;")


def _clean_affiliation_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" ,;")
    if not cleaned:
        return ""
    if cleaned.lower() in ("unknown", "unknown affiliation", "n/a", "none", "null"):
        return ""
    if "@" in cleaned and len(cleaned.split()) <= 4:
        return ""
    return cleaned


def _normalize_affiliation(value: str) -> str:
    return _affiliation_match_key(value)


def _dedupe(values: List[str]) -> List[str]:
    cleaned = []
    for value in values:
        _append_affiliation_unique(cleaned, value)
    return cleaned


def _has_affiliations(paper: Paper) -> bool:
    return bool(normalize_affiliations(paper.affiliations))


def _append_unique(values: List[str], value: str) -> None:
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _append_affiliation_unique(values: List[str], value: str) -> None:
    cleaned = re.sub(r"\s+", " ", str(value)).strip(" ,;")
    if not cleaned:
        return
    key = _affiliation_match_key(cleaned)
    if not key:
        return
    for index, existing in enumerate(values):
        existing_key = _affiliation_match_key(existing)
        if not existing_key:
            continue
        if key == existing_key or _similar_affiliation_key(key, existing_key):
            if _prefer_affiliation_value(cleaned, existing):
                values[index] = cleaned
            return
    values.append(cleaned)


def _prefer_affiliation_value(candidate: str, existing: str) -> bool:
    candidate_acronym = _looks_like_affiliation_acronym(candidate)
    existing_acronym = _looks_like_affiliation_acronym(existing)
    if candidate_acronym != existing_acronym:
        return existing_acronym
    candidate_parts = len([part for part in candidate.split(",") if part.strip()])
    existing_parts = len([part for part in existing.split(",") if part.strip()])
    if candidate_parts != existing_parts:
        return candidate_parts < existing_parts
    return len(candidate) < len(existing)


def _looks_like_affiliation_acronym(value: str) -> bool:
    words = re.findall(r"[A-Za-z]+", str(value or ""))
    if not words or len(words) > 3:
        return False
    if words[0].isupper() and len(words[0]) >= 2 and len(words) <= 2:
        return True
    return all(word.isupper() and len(word) >= 2 for word in words)


def _similar_affiliation_key(left: str, right: str) -> bool:
    if not left or not right:
        return False
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= 8 and shorter in longer


def _affiliation_match_key(value: str) -> str:
    return _affiliation_display_key(value)


def _looks_like_institution_name(value: str) -> bool:
    text = str(value or "").lower().strip()
    if not text:
        return False
    markers = [
        "university",
        "institute",
        "college",
        "school",
        "laboratory",
        "lab",
        "academy",
        "polytechnic",
        "research",
        "centre",
        "center",
        "cnrs",
        "inria",
        "corporation",
        "technology",
        "technologies",
        "group",
        "inc",
        "ltd",
        "llc",
        "company",
    ]
    known_short_names = [
        "google",
        "deepmind",
        "microsoft",
        "meta",
        "openai",
        "amazon",
        "apple",
        "nvidia",
        "huawei",
        "baidu",
        "alibaba",
        "tencent",
        "bytedance",
        "netflix",
        "spotify",
        "yandex",
        "kuaishou",
        "cuhk",
        "cmu",
        "ucla",
        "uiuc",
        "ntu",
        "nus",
        "mit",
        "eth",
        "epfl",
        "kaist",
    ]
    return any(marker in text for marker in markers) or any(
        re.search(r"\b%s\b" % re.escape(name), text) for name in known_short_names
    )


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
