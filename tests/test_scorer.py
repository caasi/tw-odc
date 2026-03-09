import json

from shared.inspector import InspectionResult
from shared.scorer import score_dataset, score_provider


class TestScoreDataset:
    """score_dataset(InspectionResult) -> DatasetScore with star rating."""

    def test_csv_gets_3_stars(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["csv"],
            file_exists=True, file_empty=False,
        )
        score = score_dataset(inspection)
        assert score.star_score == 3
        assert score.stars["available_online"] is True
        assert score.stars["machine_readable"] is True
        assert score.stars["open_format"] is True

    def test_json_gets_3_stars(self):
        inspection = InspectionResult(
            dataset_id="1002", dataset_name="Test",
            declared_format="json", detected_formats=["json"],
            file_exists=True, file_empty=False,
        )
        assert score_dataset(inspection).star_score == 3

    def test_xml_gets_3_stars(self):
        inspection = InspectionResult(
            dataset_id="1003", dataset_name="Test",
            declared_format="xml", detected_formats=["xml"],
            file_exists=True, file_empty=False,
        )
        assert score_dataset(inspection).star_score == 3

    def test_xlsx_gets_2_stars(self):
        inspection = InspectionResult(
            dataset_id="1004", dataset_name="Test",
            declared_format="xlsx", detected_formats=["xlsx"],
            file_exists=True, file_empty=False,
        )
        score = score_dataset(inspection)
        assert score.star_score == 2
        assert score.stars["machine_readable"] is True
        assert score.stars["open_format"] is False

    def test_pdf_gets_1_star(self):
        inspection = InspectionResult(
            dataset_id="1005", dataset_name="Test",
            declared_format="pdf", detected_formats=["pdf"],
            file_exists=True, file_empty=False,
            issues=["PDF_DATASET"],
        )
        score = score_dataset(inspection)
        assert score.star_score == 1
        assert score.stars["available_online"] is True
        assert score.stars["machine_readable"] is False

    def test_missing_file_gets_0_stars(self):
        inspection = InspectionResult(
            dataset_id="1006", dataset_name="Test",
            declared_format="csv", detected_formats=["missing"],
            file_exists=False, file_empty=False,
            issues=["DOWNLOAD_FAILED"],
        )
        score = score_dataset(inspection)
        assert score.star_score == 0
        assert score.stars["available_online"] is False

    def test_empty_file_gets_0_stars(self):
        inspection = InspectionResult(
            dataset_id="1007", dataset_name="Test",
            declared_format="csv", detected_formats=["empty"],
            file_exists=True, file_empty=True,
            issues=["EMPTY_FILE"],
        )
        score = score_dataset(inspection)
        assert score.star_score == 0

    def test_zip_with_csv_gets_3_stars(self):
        inspection = InspectionResult(
            dataset_id="2001", dataset_name="Test",
            declared_format="zip", detected_formats=["csv"],
            file_exists=True, file_empty=False,
            zip_contents=["csv"],
        )
        assert score_dataset(inspection).star_score == 3

    def test_zip_with_pdf_gets_1_star(self):
        inspection = InspectionResult(
            dataset_id="2002", dataset_name="Test",
            declared_format="zip", detected_formats=["pdf"],
            file_exists=True, file_empty=False,
            zip_contents=["pdf"],
            issues=["PDF_DATASET", "ZIP_CONTAINS_NON_OPEN"],
        )
        assert score_dataset(inspection).star_score == 1

    def test_zip_with_mixed_uses_minimum(self):
        """ZIP with CSV + PDF -> score by worst format (PDF = 1 star)."""
        inspection = InspectionResult(
            dataset_id="2003", dataset_name="Test",
            declared_format="zip", detected_formats=["csv", "pdf"],
            file_exists=True, file_empty=False,
            zip_contents=["csv", "pdf"],
            issues=["ZIP_CONTAINS_NON_OPEN"],
        )
        assert score_dataset(inspection).star_score == 1

    def test_multi_url_uses_minimum(self):
        """Multiple files -> score by worst file."""
        inspection = InspectionResult(
            dataset_id="3001", dataset_name="Test",
            declared_format="csv", detected_formats=["csv", "csv"],
            file_exists=True, file_empty=False,
        )
        assert score_dataset(inspection).star_score == 3

    def test_multi_url_partial_missing_gets_0_stars(self):
        """Multi-URL dataset where one file is missing → weakest link = 0."""
        inspection = InspectionResult(
            dataset_id="3002", dataset_name="Test",
            declared_format="csv", detected_formats=["csv", "missing"],
            file_exists=True, file_empty=False,
            issues=["DOWNLOAD_FAILED"],
        )
        score = score_dataset(inspection)
        assert score.star_score == 0

    def test_multi_url_partial_empty_gets_0_stars(self):
        """Multi-URL dataset where one file is empty → weakest link = 0."""
        inspection = InspectionResult(
            dataset_id="3003", dataset_name="Test",
            declared_format="csv", detected_formats=["csv", "empty"],
            file_exists=True, file_empty=True,
            issues=["EMPTY_FILE"],
        )
        score = score_dataset(inspection)
        assert score.star_score == 0

    def test_unknown_format_gets_1_star(self):
        inspection = InspectionResult(
            dataset_id="4001", dataset_name="Test",
            declared_format="其他", detected_formats=["octet-stream"],
            file_exists=True, file_empty=False,
        )
        assert score_dataset(inspection).star_score == 1

    def test_score_preserves_issues(self):
        inspection = InspectionResult(
            dataset_id="5001", dataset_name="Test",
            declared_format="csv", detected_formats=["pdf"],
            file_exists=True, file_empty=False,
            issues=["FORMAT_MISMATCH", "PDF_DATASET"],
        )
        score = score_dataset(inspection)
        assert "FORMAT_MISMATCH" in score.issues
        assert "PDF_DATASET" in score.issues


class TestDatasetScoreToDict:
    """DatasetScore.to_dict() produces the scores.json entry format."""

    def test_to_dict(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test Data",
            declared_format="csv", detected_formats=["csv"],
            file_exists=True, file_empty=False,
        )
        score = score_dataset(inspection)
        d = score.to_dict()

        assert d["id"] == "1001"
        assert d["name"] == "Test Data"
        assert d["declared_format"] == "csv"
        assert d["detected_format"] == "csv"
        assert d["star_score"] == 3
        assert d["stars"]["available_online"] is True
        assert d["stars"]["machine_readable"] is True
        assert d["stars"]["open_format"] is True
        assert d["issues"] == []


class TestScoreProvider:
    """score_provider reads manifest + datasets, writes scores.json."""

    def test_scores_json_output(self, tmp_path):
        pkg_dir = tmp_path / "test_provider"
        pkg_dir.mkdir()

        manifest = {
            "provider": "測試機關",
            "slug": "test_provider",
            "datasets": [
                {"id": "1001", "name": "CSV Data", "format": "csv", "urls": ["http://x"]},
                {"id": "1002", "name": "PDF Report", "format": "pdf", "urls": ["http://y"]},
            ],
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))

        datasets_dir = pkg_dir / "datasets"
        datasets_dir.mkdir()
        (datasets_dir / "1001.csv").write_text("a,b\n1,2\n")
        (datasets_dir / "1002.pdf").write_bytes(b"%PDF-1.4 content")

        score_provider(pkg_dir)

        scores_path = pkg_dir / "scores.json"
        assert scores_path.exists()
        scores = json.loads(scores_path.read_text())

        assert scores["provider"] == "測試機關"
        assert scores["slug"] == "test_provider"
        assert "scored_at" in scores
        assert len(scores["datasets"]) == 2

        csv_score = next(d for d in scores["datasets"] if d["id"] == "1001")
        assert csv_score["star_score"] == 3

        pdf_score = next(d for d in scores["datasets"] if d["id"] == "1002")
        assert pdf_score["star_score"] == 1
        assert "PDF_DATASET" in pdf_score["issues"]
