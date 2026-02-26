from __future__ import annotations

import heapq
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from pacs_adpkd.dicom_ops import DicomMeta, read_dicom_metadata

ST_RE = re.compile(r"^ST-\d{16,20}$")
FO_RE = re.compile(r"^FO-\d{16,20}$")


@dataclass
class SeriesCandidate:
    patient_id: str
    study_dir: Path
    series_dir: Path
    dicom_files: list[Path]
    seed_score: float


@dataclass
class SeriesRecord:
    patient_id: str
    study_dir: Path
    series_dir: Path
    dicom_files: list[Path]
    metadata: DicomMeta
    priority_score: float


def _scan_dir_entries(root: Path) -> list[Path]:
    stack: list[Path] = [root]
    out: list[Path] = []
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.name.startswith("."):
                        continue
                    p = Path(entry.path)
                    out.append(p)
                    stack.append(p)
        except FileNotFoundError:
            continue
    return out


def _discover_study_dirs(patient_dir: Path) -> list[Path]:
    found = []
    for d in _scan_dir_entries(patient_dir):
        if ST_RE.match(d.name):
            found.append(d)
    return sorted(found)


def _discover_series_dirs(study_dir: Path) -> list[Path]:
    found = []
    for d in _scan_dir_entries(study_dir):
        if FO_RE.match(d.name):
            found.append(d)
    return sorted(found)


def _dicom_files(series_dir: Path) -> list[Path]:
    try:
        files = [p for p in series_dir.iterdir() if p.is_file() and p.suffix.lower() == ".dcm"]
    except FileNotFoundError:
        return []
    return sorted(files)


def _seed_score(series_dir: Path, dicom_count: int) -> float:
    score = 1.0
    if "T2" in series_dir.name.upper():
        score += 2.5
    if "HASTE" in series_dir.name.upper():
        score += 2.0
    score += min(dicom_count, 2000) / 1000.0
    return score


def discover_candidates(patient_dir: Path, patient_id: str) -> list[SeriesCandidate]:
    candidates: list[SeriesCandidate] = []
    for study_dir in _discover_study_dirs(patient_dir):
        for series_dir in _discover_series_dirs(study_dir):
            try:
                dcm_files = _dicom_files(series_dir)
            except FileNotFoundError:
                continue
            if not dcm_files:
                continue
            candidates.append(
                SeriesCandidate(
                    patient_id=patient_id,
                    study_dir=study_dir,
                    series_dir=series_dir,
                    dicom_files=dcm_files,
                    seed_score=_seed_score(series_dir, len(dcm_files)),
                )
            )
    return candidates


def _resolve_candidate(candidate: SeriesCandidate) -> SeriesRecord | None:
    sample = candidate.dicom_files[0]
    try:
        meta = read_dicom_metadata(sample, fallback_patient_id=candidate.patient_id)
    except Exception:
        return None

    priority_score = candidate.seed_score + meta.fitness_score
    return SeriesRecord(
        patient_id=meta.patient_id or candidate.patient_id,
        study_dir=candidate.study_dir,
        series_dir=candidate.series_dir,
        dicom_files=candidate.dicom_files,
        metadata=meta,
        priority_score=priority_score,
    )


def adaptive_priority_crawl(candidates: list[SeriesCandidate], workers: int = 12, exploration_ratio: float = 0.12) -> list[SeriesRecord]:
    """
    Fitness-guided frontier inspired by adaptive search strategies:
    1) parallel metadata probes score each series,
    2) high-fitness nodes are expanded first,
    3) a small exploration budget keeps lower-score scans discoverable.
    """
    if not candidates:
        return []

    resolved: list[SeriesRecord] = []
    max_workers = max(1, min(workers, 32))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_resolve_candidate, c) for c in candidates]
        for fut in as_completed(futures):
            r = fut.result()
            if r is not None:
                resolved.append(r)

    if not resolved:
        return []

    top_bucket = []
    explore_bucket = []

    scores = sorted((r.priority_score for r in resolved), reverse=True)
    cutoff_idx = max(0, min(len(scores) - 1, int(len(scores) * exploration_ratio)))
    adaptive_cutoff = scores[cutoff_idx]

    counter = 0
    for record in resolved:
        if record.priority_score >= adaptive_cutoff:
            heapq.heappush(top_bucket, (-record.priority_score, counter, record))
        else:
            heapq.heappush(explore_bucket, (-record.priority_score, counter, record))
        counter += 1

    ordered: list[SeriesRecord] = []
    steps = 0
    while top_bucket or explore_bucket:
        use_explore = explore_bucket and (steps % max(4, int(1.0 / max(0.01, exploration_ratio))) == 0)
        bucket = explore_bucket if use_explore else top_bucket
        if not bucket:
            bucket = top_bucket if top_bucket else explore_bucket
        _, _, rec = heapq.heappop(bucket)
        ordered.append(rec)
        steps += 1

    return ordered
