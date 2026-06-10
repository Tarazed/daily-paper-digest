import json
import gzip
import io
import os
import re
import tarfile
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from typing import Dict, Iterable, List

from .config import EnrichmentConfig
from .models import Paper

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
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
        if _has_affiliations(paper):
            continue
        try:
            affiliations = lookup_openalex_affiliations(paper, config)
        except Exception:
            affiliations = []
        if affiliations:
            paper.affiliations = affiliations
            continue
        if not config.source_enabled or source_attempts >= config.source_max_papers:
            continue
        source_attempts += 1
        source_affiliations = lookup_arxiv_source_affiliations(
            paper,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            timeout_seconds=config.source_timeout_seconds,
        )
        if source_affiliations:
            paper.affiliations = source_affiliations
    return items


def lookup_openalex_affiliations(paper: Paper, config: EnrichmentConfig) -> List[str]:
    works = []
    if paper.doi:
        works = _fetch_works({"filter": "doi:%s" % paper.doi}, config)
    if not works:
        works = _fetch_works({"search": paper.title}, config)
    work = _best_title_match(paper.title, works)
    if not work:
        return []
    return extract_affiliations(work)


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


def _fetch_works(params: Dict[str, str], config: EnrichmentConfig) -> List[Dict[str, object]]:
    query = dict(params)
    query["per-page"] = str(config.max_results)
    if config.mailto:
        query["mailto"] = config.mailto
    url = OPENALEX_WORKS_URL + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"User-Agent": "daily-paper-digest/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("results", []) or []


def _fetch_arxiv_tex_documents(arxiv_id: str, timeout_seconds: int = 8) -> List[str]:
    url = ARXIV_EPRINT_URL % urllib.parse.quote(arxiv_id)
    request = urllib.request.Request(url, headers={"User-Agent": "daily-paper-digest/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
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
    return _dedupe([str(value).strip() for value in parsed.get("affiliations", []) if value])


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


def _dedupe(values: List[str]) -> List[str]:
    cleaned = []
    for value in values:
        _append_unique(cleaned, value)
    return cleaned


def _best_title_match(title: str, works: List[Dict[str, object]]) -> Dict[str, object]:
    normalized_title = _normalize_title(title)
    best = None
    best_score = 0.0
    for work in works:
        candidate = _normalize_title(str(work.get("display_name", "")))
        if not candidate:
            continue
        score = SequenceMatcher(None, normalized_title, candidate).ratio()
        if score > best_score:
            best = work
            best_score = score
    return best if best_score >= 0.88 else {}


def _has_affiliations(paper: Paper) -> bool:
    return any(value.strip() for value in paper.affiliations)


def _append_unique(values: List[str], value: str) -> None:
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if cleaned and cleaned not in values:
        values.append(cleaned)


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
