from pacs_adpkd.dicom_ops import normalize_scan_type, sanitize_folder_name


def test_scan_type_detects_t2_haste():
    assert normalize_scan_type("AX T2 HASTE", "", "") == "T2 HASTE"


def test_sanitize_folder_name():
    assert sanitize_folder_name("T2/HASTE (Kidney)") == "T2 HASTE Kidney"
