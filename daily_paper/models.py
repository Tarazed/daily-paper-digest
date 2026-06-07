from dataclasses import dataclass, field
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
    importance: str = "normal"
    read_status: str = "unread"
    notes: str = ""
    score: int = 0

    @property
    def display_affiliations(self):
        seen = []
        for affiliation in self.affiliations:
            value = affiliation.strip()
            if value and value not in seen:
                seen.append(value)
        return seen or ["Unknown affiliation"]

    @property
    def published_date(self):
        return self.published[:10] if self.published else ""
