"""Tests for gov-tw quality scoring method."""

from tw_odc.gov_tw_scorer import (
    GovTwScore,
    check_link_valid,
    check_direct_download,
    check_structured,
)
from tw_odc.inspector import InspectionResult


class TestCheckLinkValid:
    def test_existing_file_is_valid(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["csv"],
            file_exists=True, file_empty=False,
        )
        assert check_link_valid(inspection) is True

    def test_missing_file_is_invalid(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["missing"],
            file_exists=False, file_empty=False,
        )
        assert check_link_valid(inspection) is False


class TestCheckDirectDownload:
    def test_existing_csv_is_downloadable(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["csv"],
            file_exists=True, file_empty=False,
        )
        assert check_direct_download(inspection) is True

    def test_html_response_is_not_downloadable(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["html"],
            file_exists=True, file_empty=False,
        )
        assert check_direct_download(inspection) is False

    def test_missing_file_is_not_downloadable(self):
        inspection = InspectionResult(
            dataset_id="1001", dataset_name="Test",
            declared_format="csv", detected_formats=["missing"],
            file_exists=False, file_empty=False,
        )
        assert check_direct_download(inspection) is False


class TestCheckStructured:
    def test_csv_is_structured(self):
        assert check_structured(["csv"]) is True

    def test_json_is_structured(self):
        assert check_structured(["json"]) is True

    def test_xml_is_structured(self):
        assert check_structured(["xml"]) is True

    def test_xlsx_is_structured(self):
        assert check_structured(["xlsx"]) is True

    def test_geojson_is_structured(self):
        assert check_structured(["geojson"]) is True

    def test_pdf_is_not_structured(self):
        assert check_structured(["pdf"]) is False

    def test_missing_is_not_structured(self):
        assert check_structured(["missing"]) is False

    def test_mixed_uses_intersection(self):
        """If any format is unstructured, result is False (intersection rule)."""
        assert check_structured(["csv", "pdf"]) is False

    def test_all_structured(self):
        assert check_structured(["csv", "json"]) is True
