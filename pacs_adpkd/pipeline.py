from __future__ import annotations

import csv
import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pacs_adpkd.crawler import SeriesRecord, adaptive_priority_crawl, discover_candidates
from pacs_adpkd.dicom_ops import infer_date_folder, sanitize_folder_name


@dataclass
class PatientRow:
    patient_id: str
    patient_token: str
    t2_scan_paths: list[str]
    total_scans: int


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_token(value: str, salt: str) -> str:
    payload = f"{salt}:{value}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _safe_dir_name(name: str, fallback: str) -> str:
    clean = sanitize_folder_name(name, fallback=fallback)
    return clean.replace("/", "-")


def _fallback_date(study_dir: Path) -> str:
    ts = datetime.fromtimestamp(study_dir.stat().st_mtime, tz=timezone.utc)
    return ts.strftime("%Y-%m-%d")


def _next_unique_dir(path: Path) -> Path:
    if not path.exists():
        return path
    idx = 2
    while True:
        candidate = path.with_name(f"{path.name}__{idx}")
        if not candidate.exists():
            return candidate
        idx += 1


def _transfer_file(src: Path, dst: Path, transfer_mode: str) -> None:
    if transfer_mode == "move":
        shutil.move(str(src), str(dst))
    elif transfer_mode == "hardlink":
        os.link(src, dst)
    else:
        shutil.copy2(src, dst)


def materialize_series(record: SeriesRecord, output_root: Path, transfer_mode: str = "copy") -> Path:
    fallback_date = _fallback_date(record.study_dir)
    date_folder = infer_date_folder(record.metadata.study_date, fallback=fallback_date)
    scan_type = _safe_dir_name(record.metadata.scan_type, fallback="Unknown Scan")

    patient_folder = output_root / record.patient_id
    date_path = patient_folder / date_folder
    target = date_path / scan_type

    series_tag = record.metadata.series_number or record.series_dir.name
    if target.exists() and any(target.iterdir()):
        target = _next_unique_dir(target.with_name(f"{scan_type}__{series_tag}"))

    target.mkdir(parents=True, exist_ok=True)

    for src in record.dicom_files:
        dst = target / src.name
        if dst.exists():
            continue
        _transfer_file(src, dst, transfer_mode=transfer_mode)

    return target


def process_patient(
    patient_dir: Path,
    output_root: Path,
    transfer_mode: str,
    workers: int,
    salt: str,
) -> PatientRow:
    patient_id = patient_dir.name
    candidates = discover_candidates(patient_dir, patient_id=patient_id)
    ordered = adaptive_priority_crawl(candidates, workers=workers)

    t2_paths: list[str] = []
    for record in ordered:
        out_path = materialize_series(record, output_root=output_root, transfer_mode=transfer_mode)
        if record.metadata.is_t2_weighted:
            t2_paths.append(str(out_path))

    return PatientRow(
        patient_id=patient_id,
        patient_token=stable_token(patient_id, salt=salt),
        t2_scan_paths=sorted(set(t2_paths)),
        total_scans=len(ordered),
    )


def write_patient_csv(rows: list[PatientRow], csv_path: Path, include_patient_id: bool = False) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["patient_token", "t2_scan_count", "t2_scan_paths", "total_scan_count", "generated_at_utc"]
    if include_patient_id:
        fields.insert(0, "patient_id")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in sorted(rows, key=lambda r: r.patient_id):
            payload = {
                "patient_token": row.patient_token,
                "t2_scan_count": len(row.t2_scan_paths),
                "t2_scan_paths": "|".join(row.t2_scan_paths),
                "total_scan_count": row.total_scans,
                "generated_at_utc": now_utc(),
            }
            if include_patient_id:
                payload["patient_id"] = row.patient_id
            w.writerow(payload)
