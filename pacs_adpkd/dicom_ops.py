from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pydicom

DICOM_TAGS = [
    "PatientID",
    "StudyDate",
    "SeriesDescription",
    "ProtocolName",
    "SequenceName",
    "SeriesInstanceUID",
    "SeriesNumber",
    "Modality",
]

SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9 _-]+")
SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class DicomMeta:
    patient_id: str
    study_date: str
    series_description: str
    protocol_name: str
    sequence_name: str
    series_instance_uid: str
    series_number: str
    modality: str
    scan_type: str
    is_t2_weighted: bool
    fitness_score: float


def normalize_scan_type(series_description: str, protocol_name: str, sequence_name: str) -> str:
    raw = " ".join([series_description, protocol_name, sequence_name]).strip()
    raw_upper = raw.upper()

    if "T2" in raw_upper and "HASTE" in raw_upper:
        return "T2 HASTE"
    if "T2" in raw_upper and "SSFSE" in raw_upper:
        return "T2 SSFSE"
    if "T2" in raw_upper:
        return "T2 Weighted"
    if "DWI" in raw_upper:
        return "DWI"
    if "ADC" in raw_upper:
        return "ADC"
    if "T1" in raw_upper:
        return "T1 Weighted"
    if "FLAIR" in raw_upper:
        return "FLAIR"
    if "CINE" in raw_upper:
        return "CINE"
    if raw:
        return sanitize_folder_name(raw, fallback="Unknown Scan")
    return "Unknown Scan"


def sanitize_folder_name(name: str, fallback: str = "Unknown Scan") -> str:
    clean = SAFE_CHARS_RE.sub(" ", name)
    clean = SPACE_RE.sub(" ", clean).strip()
    return clean or fallback


def _fitness_score(series_description: str, protocol_name: str, sequence_name: str, modality: str) -> float:
    raw = f"{series_description} {protocol_name} {sequence_name}".upper()
    score = 1.0
    if modality.upper() in {"MR", "MRI"}:
        score += 0.5
    if "T2" in raw:
        score += 4.0
    if "HASTE" in raw:
        score += 3.0
    if "SSFSE" in raw:
        score += 2.5
    if "KIDNEY" in raw or "RENAL" in raw:
        score += 1.2
    if "LOCALIZER" in raw or "SCOUT" in raw:
        score -= 1.0
    return score


def read_dicom_metadata(sample_file: Path, fallback_patient_id: str = "") -> DicomMeta:
    ds = pydicom.dcmread(str(sample_file), stop_before_pixels=True, specific_tags=DICOM_TAGS, force=True)

    patient_id = str(getattr(ds, "PatientID", "") or fallback_patient_id).strip()
    study_date = str(getattr(ds, "StudyDate", "") or "").strip()
    series_description = str(getattr(ds, "SeriesDescription", "") or "").strip()
    protocol_name = str(getattr(ds, "ProtocolName", "") or "").strip()
    sequence_name = str(getattr(ds, "SequenceName", "") or "").strip()
    series_instance_uid = str(getattr(ds, "SeriesInstanceUID", "") or "").strip()
    series_number = str(getattr(ds, "SeriesNumber", "") or "").strip()
    modality = str(getattr(ds, "Modality", "") or "").strip()

    scan_type = normalize_scan_type(series_description, protocol_name, sequence_name)
    is_t2 = "T2" in scan_type.upper()

    return DicomMeta(
        patient_id=patient_id,
        study_date=study_date,
        series_description=series_description,
        protocol_name=protocol_name,
        sequence_name=sequence_name,
        series_instance_uid=series_instance_uid,
        series_number=series_number,
        modality=modality,
        scan_type=scan_type,
        is_t2_weighted=is_t2,
        fitness_score=_fitness_score(series_description, protocol_name, sequence_name, modality),
    )


def infer_date_folder(study_date: str, fallback: str) -> str:
    if len(study_date) == 8 and study_date.isdigit():
        return f"{study_date[0:4]}-{study_date[4:6]}-{study_date[6:8]}"
    return fallback
