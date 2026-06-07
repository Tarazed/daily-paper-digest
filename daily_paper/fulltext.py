import re
from typing import List

from .enrichment import _fetch_arxiv_tex_documents, _strip_tex_comments
from .models import Paper


def extract_full_text_for_analysis(
    paper: Paper, max_chars: int = 30000, timeout_seconds: int = 10
) -> str:
    if not paper.id.startswith("arxiv:"):
        return ""
    arxiv_id = paper.id.replace("arxiv:", "")
    if not arxiv_id:
        return ""
    try:
        documents = _fetch_arxiv_tex_documents(arxiv_id, timeout_seconds=timeout_seconds)
    except Exception:
        return ""
    cleaned = [_clean_latex_document(document) for document in documents]
    cleaned = [text for text in cleaned if text]
    if not cleaned:
        return ""
    combined = "\n\n".join(_rank_documents(cleaned))
    return combined[:max_chars].strip()


def _rank_documents(documents: List[str]) -> List[str]:
    return sorted(
        documents,
        key=lambda text: (
            -score_analysis_text(text),
            -len(text),
        ),
    )


def score_analysis_text(text: str) -> int:
    lowered = text.lower()
    score = 0
    for marker in (
        "abstract",
        "introduction",
        "method",
        "approach",
        "experiment",
        "evaluation",
        "result",
        "ablation",
        "conclusion",
        "online",
        "a/b",
    ):
        if marker in lowered:
            score += 1
    return score


def _clean_latex_document(text: str) -> str:
    text = _strip_tex_comments(text)
    text = _drop_latex_environments(text)
    text = _replace_section_commands(text)
    text = re.sub(r"\\(?:cite|citep|citet|ref|eqref|label|url|href)\*?(?:\[[^\]]*\])?\{[^{}]*\}", " ", text)
    text = re.sub(r"\\(?:textbf|textit|emph|underline)\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"[{}$^_~]", " ", text)
    text = text.replace("\\&", "&")
    text = re.sub(r"\s+", " ", text)
    text = _focus_analysis_sections(text)
    return text.strip()


def _drop_latex_environments(text: str) -> str:
    for env in ("table", "figure", "algorithm", "equation", "align", "tikzpicture", "lstlisting"):
        text = re.sub(
            r"\\begin\{" + env + r"\*?\}.*?\\end\{" + env + r"\*?\}",
            " ",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
    return text


def _replace_section_commands(text: str) -> str:
    pattern = re.compile(r"\\(?:section|subsection|subsubsection)\*?(?:\[[^\]]*\])?\{([^{}]+)\}")
    return pattern.sub(lambda match: "\n\nSECTION: %s\n" % match.group(1), text)


def _focus_analysis_sections(text: str) -> str:
    markers = [
        "abstract",
        "introduction",
        "method",
        "approach",
        "model",
        "experiment",
        "evaluation",
        "result",
        "ablation",
        "online",
        "conclusion",
    ]
    chunks = re.split(r"(?=SECTION:)", text)
    selected = []
    for chunk in chunks:
        lowered = chunk[:140].lower()
        if not selected or any(marker in lowered for marker in markers):
            selected.append(chunk.strip())
    return "\n\n".join(part for part in selected if part)
