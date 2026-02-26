#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

DEFAULT_PATIENTS = [
    "A1041373",
    "A1111060",
    "A1111111",
    "A1128977",
    "A1251362",
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Reorganize HALT PACS DICOM folders by patient/date/scan-type and export confidential T2 index CSV."
    )
    ap.add_argument("--halt-root", required=True, help="Path to HALT_Data root directory")
    ap.add_argument("--patients", nargs="*", default=DEFAULT_PATIENTS, help="Patient folder names under HALT_Data")
    ap.add_argument("--output-root", required=True, help="Output root for reorganized DICOM tree")
    ap.add_argument("--csv-out", required=True, help="Output CSV path for per-patient T2 file index")
    ap.add_argument("--transfer-mode", choices=["copy", "move", "hardlink"], default="copy")
    ap.add_argument("--workers", type=int, default=12, help="Worker count for metadata probes (default: 12)")
    ap.add_argument("--salt", default=os.getenv("PACS_PATIENT_SALT", "pacs-adpkd-default-salt"))
    ap.add_argument("--include-patient-id", action="store_true", help="Include raw patient IDs in CSV (disabled by default)")
    return ap.parse_args()


def main() -> None:
    args = parse_args()

    # Delay heavy imports so `--help` works even before dependencies are installed.
    try:
        from pacs_adpkd.pipeline import PatientRow, process_patient, write_patient_csv
    except Exception as e:
        raise SystemExit(
            "Failed to import runtime dependencies. Install with `pip install -r requirements.txt` first. "
            f"Original error: {e}"
        ) from e

    halt_root = Path(args.halt_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    csv_out = Path(args.csv_out).expanduser().resolve()

    rows: list[PatientRow] = []
    missing: list[str] = []

    for patient in args.patients:
        src = halt_root / patient
        if not src.exists() or not src.is_dir():
            missing.append(patient)
            continue
        print(f"[crawl] {patient}: scanning {src}")
        row = process_patient(
            patient_dir=src,
            output_root=output_root,
            transfer_mode=args.transfer_mode,
            workers=args.workers,
            salt=args.salt,
        )
        print(
            f"[done]  {patient}: scans={row.total_scans} t2={len(row.t2_scan_paths)} token={row.patient_token}"
        )
        rows.append(row)

    write_patient_csv(rows, csv_path=csv_out, include_patient_id=bool(args.include_patient_id))

    print(f"[csv]   wrote {csv_out}")
    if missing:
        print(f"[warn]  missing patient folders: {', '.join(missing)}")


if __name__ == "__main__":
    main()
