import zipfile

from shared.inspector import (
    InspectionResult,
    detect_format,
    inspect_dataset,
    inspect_zip_contents,
)


class TestDetectFormat:
    """detect_format(file_path) returns the detected format string."""

    def test_csv_file(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30\n")
        assert detect_format(f) == "csv"

    def test_json_file(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}')
        assert detect_format(f) == "json"

    def test_json_array(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('[{"key": "value"}]')
        assert detect_format(f) == "json"

    def test_xml_file(self, tmp_path):
        f = tmp_path / "data.xml"
        f.write_text('<?xml version="1.0"?><root/>')
        assert detect_format(f) == "xml"

    def test_pdf_file(self, tmp_path):
        f = tmp_path / "data.pdf"
        f.write_bytes(b"%PDF-1.4 fake pdf content")
        assert detect_format(f) == "pdf"

    def test_zip_file(self, tmp_path):
        f = tmp_path / "data.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("inner.csv", "a,b\n1,2\n")
        assert detect_format(f) == "zip"

    def test_empty_file(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_bytes(b"")
        assert detect_format(f) == "empty"

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "missing.csv"
        assert detect_format(f) == "missing"

    def test_xlsx_file(self, tmp_path):
        """XLSX files are ZIP-based but should be detected as xlsx."""
        f = tmp_path / "data.xlsx"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("xl/workbook.xml", "<workbook/>")
            zf.writestr("[Content_Types].xml", "<Types/>")
        assert detect_format(f) == "xlsx"


class TestInspectZipContents:
    """inspect_zip_contents returns list of detected formats inside a ZIP."""

    def test_zip_with_csv(self, tmp_path):
        f = tmp_path / "data.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("data.csv", "a,b\n1,2\n")
        result = inspect_zip_contents(f)
        assert result == ["csv"]

    def test_zip_with_mixed_formats(self, tmp_path):
        f = tmp_path / "data.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("data.csv", "a,b\n1,2\n")
            zf.writestr("report.pdf", "%PDF-1.4 fake")
        result = sorted(inspect_zip_contents(f))
        assert result == ["csv", "pdf"]

    def test_zip_with_nested_zip(self, tmp_path):
        """Nested ZIPs are reported as 'zip', not recursed into."""
        inner = tmp_path / "inner.zip"
        with zipfile.ZipFile(inner, "w") as zf:
            zf.writestr("x.csv", "a\n1\n")
        f = tmp_path / "outer.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.write(inner, "inner.zip")
        result = inspect_zip_contents(f)
        assert result == ["zip"]

    def test_corrupt_zip(self, tmp_path):
        f = tmp_path / "bad.zip"
        f.write_bytes(b"not a zip")
        result = inspect_zip_contents(f)
        assert result == []

    def test_zip_ignores_directories(self, tmp_path):
        """Directory entries inside ZIP should be skipped."""
        f = tmp_path / "data.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("subdir/data.json", '{"a": 1}')
        result = inspect_zip_contents(f)
        assert result == ["json"]


class TestInspectDataset:
    """inspect_dataset checks a single dataset entry against its files."""

    def test_csv_dataset_single_file(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "1001.csv").write_text("a,b\n1,2\n")

        dataset = {"id": "1001", "name": "Test", "format": "csv", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert isinstance(result, InspectionResult)
        assert result.dataset_id == "1001"
        assert result.declared_format == "csv"
        assert result.detected_formats == ["csv"]
        assert result.file_exists is True
        assert result.file_empty is False
        assert result.issues == []

    def test_missing_file(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()

        dataset = {"id": "9999", "name": "Missing", "format": "csv", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.file_exists is False
        assert result.detected_formats == ["missing"]
        assert "DOWNLOAD_FAILED" in result.issues

    def test_empty_file(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "1001.csv").write_bytes(b"")

        dataset = {"id": "1001", "name": "Empty", "format": "csv", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.file_empty is True
        assert "EMPTY_FILE" in result.issues

    def test_format_mismatch(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "1001.csv").write_bytes(b"%PDF-1.4 fake pdf")

        dataset = {"id": "1001", "name": "Sneaky PDF", "format": "csv", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.declared_format == "csv"
        assert result.detected_formats == ["pdf"]
        assert "FORMAT_MISMATCH" in result.issues

    def test_zip_dataset_inspects_contents(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        zf_path = datasets_dir / "2001.zip"
        with zipfile.ZipFile(zf_path, "w") as zf:
            zf.writestr("data.csv", "a,b\n1,2\n")

        dataset = {"id": "2001", "name": "Zipped CSV", "format": "zip", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.detected_formats == ["csv"]
        assert result.zip_contents == ["csv"]

    def test_multi_url_dataset(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "3001-1.csv").write_text("a\n1\n")
        (datasets_dir / "3001-2.csv").write_text("b\n2\n")

        dataset = {"id": "3001", "name": "Multi", "format": "csv", "urls": ["http://a", "http://b"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert result.file_exists is True
        assert result.detected_formats == ["csv", "csv"]

    def test_pdf_dataset_issue(self, tmp_path):
        datasets_dir = tmp_path / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "5001.pdf").write_bytes(b"%PDF-1.4 real pdf")

        dataset = {"id": "5001", "name": "Report", "format": "pdf", "urls": ["http://x"]}
        result = inspect_dataset(dataset, datasets_dir)

        assert "PDF_DATASET" in result.issues
