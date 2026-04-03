# pacs-adpkd

Automated ADPKD PACS reorganizer and confidential T2-weighted indexer.

## What it does

1. Crawls patient folders under `HALT_Data` for `ST-<16-20 digits>` study directories and `FO-<16-20 digits>` series directories.
2. Uses an adaptive, fitness-guided crawl order inspired by the pre-print at <https://arxiv.org/abs/2507.21937>:
   - parallel metadata probes
   - priority frontier for high-fitness nodes
   - small exploration budget for lower-fitness nodes
3. Reorganizes DICOM files to:

```text
<output_root>/
  <patient_id>/
    <scan_date>/
      <scan_type>/
        *.dcm
```

4. Writes a confidential CSV with one row per patient and all detected T2-weighted scan paths.

## Confidentiality defaults

- CSV includes `patient_token` (SHA-256 salt hash) by default.
- Raw `patient_id` is omitted unless `--include-patient-id` is set.
- Set `PACS_PATIENT_SALT` for deterministic private tokenization.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python scripts/reorganize_halt_data.py \
  --halt-root /path/to/HALT_Data \
  --output-root /path/to/reorganized_data \
  --csv-out /path/to/reorganized_data/t2_index.csv \
  --patients A1041373 A1111060 A1111111 A1128977 A1251362 \
  --workers 12 \
  --transfer-mode copy
```

## Notes

- `--transfer-mode` supports `copy`, `move`, and `hardlink`.
- Scan type is inferred from DICOM metadata (`SeriesDescription`, `ProtocolName`, `SequenceName`) and normalized for folder-safe naming.
- When multiple scans map to the same date and scan-type folder, unique suffixes are added automatically.

## License

This repository is licensed under:
- `LICENSE-NEXQ-CONFIDENTIAL-NONCOMMERCIAL.md`

Licensing contact: `license@nexq.us`
