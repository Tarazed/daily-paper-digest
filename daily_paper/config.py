import os
from dataclasses import dataclass, field
from typing import Dict, List

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
class TrackConfig:
    key: str
    label: str
    enabled: bool
    cadence: str
    weekly_day: str
    quota: int
    relevance_threshold: int
    topic_quotas: Dict[str, int]
    arxiv: ArxivConfig
    dblp: DblpConfig


@dataclass
class AppConfig:
    arxiv: ArxivConfig
    dblp: DblpConfig
    email: EmailConfig
    summary: SummaryConfig
    enrichment: EnrichmentConfig
    site: SiteConfig
    state_file: str
    tracks: Dict[str, TrackConfig]
    default_track: str
    digest_state_file: str


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
    legacy_arxiv = _parse_arxiv_config(arxiv)
    legacy_dblp = _parse_dblp_config(dblp)
    tracks = _parse_track_configs(raw.get("tracks", {}), legacy_arxiv, legacy_dblp)
    if not tracks:
        tracks["generative_rec"] = TrackConfig(
            key="generative_rec",
            label="Generative Recommendation",
            enabled=True,
            cadence="daily",
            weekly_day="friday",
            quota=int(email.get("top_n", 10)),
            relevance_threshold=70,
            topic_quotas={},
            arxiv=legacy_arxiv,
            dblp=legacy_dblp,
        )
    compatibility_track = tracks.get("generative_rec")
    if compatibility_track:
        legacy_arxiv = compatibility_track.arxiv
        legacy_dblp = compatibility_track.dblp
    default_track = str(
        raw.get(
            "default_track",
            "llm_systems" if "llm_systems" in tracks else "generative_rec",
        )
    )
    if default_track not in tracks:
        default_track = next(iter(tracks))
    return AppConfig(
        arxiv=legacy_arxiv,
        dblp=legacy_dblp,
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
        tracks=tracks,
        default_track=default_track,
        digest_state_file=str(raw.get("digest_state_file", "digest_state.json")),
    )


def _parse_arxiv_config(values) -> ArxivConfig:
    values = values or {}
    return ArxivConfig(
        categories=list(values.get("categories", ["cs.IR", "cs.AI", "cs.LG", "cs.CL"])),
        include_keywords=list(
            values.get(
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
        exclude_keywords=list(values.get("exclude_keywords", ["advertising", "sponsored search"])),
        max_results=int(values.get("max_results", 50)),
        days_back=int(values.get("days_back", 14)),
    )


def _parse_dblp_config(values) -> DblpConfig:
    values = values or {}
    return DblpConfig(
        enabled=bool(values.get("enabled", False)),
        venues=_parse_dblp_venues(
            values.get(
                "venues",
                ["RecSys", "SIGIR", "WWW", "KDD", "WSDM", "CIKM", "ICLR", "AAAI", "ICML", "NeurIPS"],
            )
        ),
        include_keywords=list(
            values.get(
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
        max_results_per_query=int(values.get("max_results_per_query", 10)),
        years_back=int(values.get("years_back", 2)),
        timeout_seconds=int(values.get("timeout_seconds", 4)),
        max_failures=int(values.get("max_failures", 2)),
        max_total_results=int(values.get("max_total_results", 20)),
        workers=int(values.get("workers", 4)),
        fallback_enabled=bool(values.get("fallback_enabled", True)),
        fallback_providers=list(values.get("fallback_providers", ["openalex", "semantic_scholar"])),
        fallback_workers=int(values.get("fallback_workers", 4)),
    )


def _parse_track_configs(values, legacy_arxiv, legacy_dblp) -> Dict[str, TrackConfig]:
    tracks = {}
    for key, item in (values or {}).items():
        if not isinstance(item, dict):
            continue
        arxiv_values = item.get("arxiv")
        dblp_values = item.get("dblp")
        tracks[str(key)] = TrackConfig(
            key=str(key),
            label=str(item.get("label", key)),
            enabled=bool(item.get("enabled", True)),
            cadence=str(item.get("cadence", "daily")),
            weekly_day=str(item.get("weekly_day", "friday")),
            quota=int(item.get("quota", 10)),
            relevance_threshold=int(item.get("relevance_threshold", 70)),
            topic_quotas={
                str(topic): int(quota)
                for topic, quota in (item.get("topic_quotas") or {}).items()
            },
            arxiv=_parse_arxiv_config(arxiv_values) if arxiv_values is not None else legacy_arxiv,
            dblp=_parse_dblp_config(dblp_values) if dblp_values is not None else legacy_dblp,
        )
    return tracks


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
