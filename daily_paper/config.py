import os
from dataclasses import dataclass, field
from typing import List

from . import simple_toml


@dataclass
class ArxivConfig:
    categories: List[str]
    include_keywords: List[str]
    exclude_keywords: List[str]
    max_results: int
    days_back: int


@dataclass
class EmailConfig:
    sender_name: str
    default_to: str
    subject_prefix: str
    top_n: int


@dataclass
class DblpVenueConfig:
    name: str
    query: str


@dataclass
class DblpConfig:
    enabled: bool
    venues: List[DblpVenueConfig]
    include_keywords: List[str]
    max_results_per_query: int
    years_back: int
    timeout_seconds: int
    max_failures: int
    max_total_results: int
    workers: int = 4
    fallback_enabled: bool = True
    fallback_providers: List[str] = field(default_factory=lambda: ["openalex", "semantic_scholar"])
    fallback_workers: int = 4


@dataclass
class SummaryConfig:
    provider: str
    base_url: str
    model: str
    analysis_model: str
    language: str
    max_sentences: int
    full_text_max_chars: int
    full_text_timeout_seconds: int
    analysis_workers: int
    summary_workers: int = 4


@dataclass
class EnrichmentConfig:
    enabled: bool
    provider: str
    mailto: str
    max_results: int
    confirm_providers: List[str]
    confirmed_min_sources: int
    source_enabled: bool
    source_max_papers: int
    source_timeout_seconds: int


@dataclass
class SiteConfig:
    title: str
    subtitle: str
    default_limit: int


@dataclass
class AppConfig:
    arxiv: ArxivConfig
    dblp: DblpConfig
    email: EmailConfig
    summary: SummaryConfig
    enrichment: EnrichmentConfig
    site: SiteConfig
    state_file: str


def load_config(path: str = "config.toml") -> AppConfig:
    if os.path.exists(path):
        raw = simple_toml.load(path)
    else:
        raw = {}
    arxiv = raw.get("arxiv", {})
    dblp = raw.get("dblp", {})
    email = raw.get("email", {})
    summary = raw.get("summary", {})
    enrichment = raw.get("enrichment", {})
    site = raw.get("site", {})
    return AppConfig(
        arxiv=ArxivConfig(
            categories=list(arxiv.get("categories", ["cs.IR", "cs.AI", "cs.LG", "cs.CL"])),
            include_keywords=list(
                arxiv.get(
                    "include_keywords",
                    [
                        "recommender system",
                        "recommendation",
                        "generative recommendation",
                        "sequential recommendation",
                        "LLM4Rec",
                        "large language model recommendation",
                        "agent recommendation",
                        "Agent4Rec",
                        "conversational recommendation",
                    ],
                )
            ),
            exclude_keywords=list(arxiv.get("exclude_keywords", ["advertising", "sponsored search"])),
            max_results=int(arxiv.get("max_results", 50)),
            days_back=int(arxiv.get("days_back", 14)),
        ),
        dblp=DblpConfig(
            enabled=bool(dblp.get("enabled", False)),
            venues=_parse_dblp_venues(
                dblp.get(
                    "venues",
                    ["RecSys", "SIGIR", "WWW", "KDD", "WSDM", "CIKM", "ICLR", "AAAI", "ICML", "NeurIPS"],
                )
            ),
            include_keywords=list(
                dblp.get(
                    "include_keywords",
                    [
                        "recommender",
                        "recommendation",
                        "recommend",
                        "LLM4Rec",
                        "generative recommendation",
                        "sequential recommendation",
                        "conversational recommendation",
                        "agent",
                    ],
                )
            ),
            max_results_per_query=int(dblp.get("max_results_per_query", 10)),
            years_back=int(dblp.get("years_back", 2)),
            timeout_seconds=int(dblp.get("timeout_seconds", 4)),
            max_failures=int(dblp.get("max_failures", 2)),
            max_total_results=int(dblp.get("max_total_results", 20)),
            workers=int(dblp.get("workers", 4)),
            fallback_enabled=bool(dblp.get("fallback_enabled", True)),
            fallback_providers=list(dblp.get("fallback_providers", ["openalex", "semantic_scholar"])),
            fallback_workers=int(dblp.get("fallback_workers", 4)),
        ),
        email=EmailConfig(
            sender_name=str(email.get("sender_name", "Daily Paper Digest")),
            default_to=str(email.get("default_to", "")),
            subject_prefix=str(email.get("subject_prefix", "Daily Paper Digest")),
            top_n=int(email.get("top_n", 10)),
        ),
        summary=SummaryConfig(
            provider=str(summary.get("provider", "deepseek")),
            base_url=str(summary.get("base_url", "https://api.deepseek.com")),
            model=str(summary.get("model", "deepseek-v4-flash")),
            analysis_model=str(summary.get("analysis_model", "deepseek-v4-pro")),
            language=str(summary.get("language", "zh")),
            max_sentences=int(summary.get("max_sentences", 3)),
            full_text_max_chars=int(summary.get("full_text_max_chars", 12000)),
            full_text_timeout_seconds=int(summary.get("full_text_timeout_seconds", 10)),
            analysis_workers=int(summary.get("analysis_workers", 3)),
            summary_workers=int(summary.get("summary_workers", 4)),
        ),
        enrichment=EnrichmentConfig(
            enabled=bool(enrichment.get("enabled", True)),
            provider=str(enrichment.get("provider", "openalex")),
            mailto=str(enrichment.get("mailto", "")),
            max_results=int(enrichment.get("max_results", 3)),
            confirm_providers=list(
                enrichment.get(
                    "confirm_providers",
                    ["openalex", "crossref", "semantic_scholar", "arxiv_source"],
                )
            ),
            confirmed_min_sources=int(enrichment.get("confirmed_min_sources", 2)),
            source_enabled=bool(enrichment.get("source_enabled", True)),
            source_max_papers=int(enrichment.get("source_max_papers", 30)),
            source_timeout_seconds=int(enrichment.get("source_timeout_seconds", 8)),
        ),
        site=SiteConfig(
            title=str(site.get("title", "Daily Paper Digest")),
            subtitle=str(
                site.get(
                    "subtitle",
                    "推荐系统、生成式推荐、LLM4Rec 与 Agent4Rec 论文追踪",
                )
            ),
            default_limit=int(site.get("default_limit", 10)),
        ),
        state_file=str(raw.get("state_file", "paper_state.toml")),
    )


def _parse_dblp_venues(values) -> List[DblpVenueConfig]:
    venues = []
    for item in values:
        value = str(item)
        if ":" in value:
            name, query = value.split(":", 1)
        else:
            name, query = value, value
        venues.append(DblpVenueConfig(name=name.strip(), query=query.strip()))
    return venues
