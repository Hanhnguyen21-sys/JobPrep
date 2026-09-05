"""spaCy PhraseMatcher over the ESCO taxonomy (esco.py). Pure rule-based
string matching -- no ML model download, no network, no OpenAI. Built once
per process (`get_skill_matcher()` is cached) since assembling the
PhraseMatcher takes a moment.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import spacy
from spacy.matcher import PhraseMatcher

from app.taxonomy.esco import SkillEntry, load_or_build_taxonomy

# Evidence snippet cap -- the sentence a skill was found in, trimmed so one
# runaway sentence can't bloat a job_posting_skill row.
_EVIDENCE_MAX_CHARS = 240


@dataclass(frozen=True)
class SkillHit:
    """One taxonomy skill found in a text, with every character offset it
    occurred at (the caller uses those to bucket it required vs preferred)
    and the sentence around its first occurrence as evidence.
    """

    id: str
    name: str
    evidence: str
    offsets: tuple[int, ...]


class SkillMatcher:
    def __init__(self, taxonomy: list[SkillEntry] | None = None) -> None:
        entries = taxonomy if taxonomy is not None else load_or_build_taxonomy()

        # Blank English: just the tokenizer + a rule-based sentence
        # splitter (for evidence). No statistical model, so nothing to
        # download and load is deterministic.
        self.nlp = spacy.blank("en")
        self.nlp.add_pipe("sentencizer")

        self._by_key: dict[str, SkillEntry] = {}
        self._matcher = PhraseMatcher(self.nlp.vocab, attr="LOWER")
        for entry in entries:
            if not entry.labels:
                continue
            self._by_key[entry.id] = entry
            self._matcher.add(
                entry.id, [self.nlp.make_doc(label) for label in entry.labels]
            )

    def extract(self, text: str) -> list[SkillHit]:
        if not text or not text.strip():
            return []

        doc = self.nlp(text)

        # skill id -> (all start-char offsets, first evidence sentence)
        by_id: dict[str, tuple[list[int], str]] = {}
        for match_id, start, end in self._matcher(doc):
            key = self.nlp.vocab.strings[match_id]
            entry = self._by_key.get(key)
            if entry is None:
                continue
            span = doc[start:end]
            offsets, evidence = by_id.get(entry.id, ([], ""))
            offsets.append(span.start_char)
            if not evidence:
                evidence = span.sent.text.strip()[:_EVIDENCE_MAX_CHARS]
            by_id[entry.id] = (offsets, evidence)

        hits = [
            SkillHit(
                id=skill_id,
                name=self._by_key[skill_id].name,
                evidence=evidence,
                offsets=tuple(sorted(offsets)),
            )
            for skill_id, (offsets, evidence) in by_id.items()
        ]
        # Deterministic order: earliest mention first.
        hits.sort(key=lambda h: h.offsets[0])
        return hits


@lru_cache(maxsize=1)
def get_skill_matcher() -> SkillMatcher:
    return SkillMatcher()
