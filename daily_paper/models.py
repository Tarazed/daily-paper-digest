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
    )
    institution_parts = [part for part in parts if any(marker in part for marker in markers)]
    if institution_parts:
        text = institution_parts[-1]
    text = re.sub(r"\b(hong kong|beijing|shanghai|montreal|toronto|canada|china|usa|united states|uk|united kingdom)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", "", text)
