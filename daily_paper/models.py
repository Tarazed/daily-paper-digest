from dataclasses import dataclass, field
import re
from typing import List


@dataclass
class Paper:
    id: str
    title: str
    authors: List[str]
    affiliations: List[str]
    published: str
    updated: str
    abstract: str
    categories: List[str]
    primary_category: str
    abs_url: str
    pdf_url: str
    doi: str = ""
    source: str = "arXiv"
    status: str = "preprint"
    venue: str = ""
    venue_key: str = ""
    generated_summary: str = ""
    core_method: str = ""
    innovation_points: List[str] = field(default_factory=list)
    experiment_results: List[str] = field(default_factory=list)
    ab_test: str = "unknown"
    ab_test_evidence: str = ""
    limitations: List[str] = field(default_factory=list)
    practical_value: str = ""
    analysis_basis: str = "metadata"
    analysis_status: str = ""
    analysis_signature: str = ""
    tags: List[str] = field(default_factory=list)
    llm_score: int = 0
    llm_score_rationale: str = ""
    preference_signals: List[str] = field(default_factory=list)
    importance: str = "normal"
    read_status: str = "unread"
    notes: str = ""
    score: int = 0

    @property
    def display_affiliations(self):
        seen = []
        for affiliation in self.affiliations:
            value = affiliation.strip()
            key = _affiliation_display_key(value)
            if not value or not key:
                continue
            existing_keys = [_affiliation_display_key(existing) for existing in seen]
            if key in existing_keys:
                continue
            seen.append(value)
        return seen or ["Unknown affiliation"]

    @property
    def published_date(self):
        return self.published[:10] if self.published else ""


def _affiliation_display_key(value: str) -> str:
    text = str(value or "").lower().strip()
    if text in ("unknown", "unknown affiliation", "n/a", "none", "null"):
        return ""
    alias = _known_affiliation_alias(text)
    if alias:
        return alias
    text = re.sub(r"\b(the|a|an)\b", " ", text)
    text = text.replace("&", "and")
    parts = [part.strip(" .;:-") for part in re.split(r",|\||/|\\\\|\\n", text) if part.strip()]
    markers = (
        "university",
        "institute",
        "college",
        "school",
        "laboratory",
        "lab",
        "academy",
        "research",
        "technology",
        "technologies",
        "centre",
        "center",
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
        "kuaishou",
    )
    institution_parts = [part for part in parts if any(marker in part for marker in markers)]
    if institution_parts:
        text = institution_parts[-1]
    text = re.sub(r"\b(department|dept|school|faculty|college|division) of [a-z0-9 and&.-]+?\b", " ", text)
    text = re.sub(
        r"\b(hong kong|beijing|shanghai|shenzhen|guangzhou|hangzhou|montreal|toronto|"
        r"singapore|canada|china|usa|united states|us|uk|united kingdom|germany|france|"
        r"japan|korea|india|australia|switzerland)\b",
        " ",
        text,
    )
    return re.sub(r"[^a-z0-9]+", "", text)


def _known_affiliation_alias(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    aliases = (
        ("googledeepmind", (r"\bgoogle deepmind\b", r"\bdeepmind\b")),
        ("microsoftresearch", (r"\bmicrosoft research\b", r"\bmsr\b")),
        ("meta", (r"\bmeta ai\b", r"\bfacebook ai\b", r"\bfair\b")),
        ("openai", (r"\bopenai\b",)),
        ("kuaishou", (r"\bkuaishou\b",)),
        ("mit", (r"\bmassachusetts institute of technology\b", r"\bmit\b")),
        ("ethzurich", (r"\beth zurich\b", r"\bswiss federal institute of technology zurich\b")),
        ("epfl", (r"\bepfl\b", r"\becole polytechnique federale de lausanne\b")),
        ("kaist", (r"\bkaist\b", r"\bkorea advanced institute of science and technology\b")),
        ("ucberkeley", (r"\buniversity of california berkeley\b", r"\buc berkeley\b")),
        ("ucla", (r"\buniversity of california los angeles\b", r"\bucla\b")),
        ("uiuc", (r"\buniversity of illinois urbana champaign\b", r"\buiuc\b")),
        ("cmu", (r"\bcarnegie mellon university\b", r"\bcmu\b")),
        ("cuhk", (r"\bchinese university of hong kong\b", r"\bcuhk\b")),
        ("ntu", (r"\bnanyang technological university\b", r"\bntu\b")),
        ("nus", (r"\bnational university of singapore\b", r"\bnus\b")),
    )
    for key, patterns in aliases:
        if any(re.search(pattern, text) for pattern in patterns):
            return key
    return ""
