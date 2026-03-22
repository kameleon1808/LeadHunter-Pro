"""
E2E tests for the Phase 4 export module.

Run with:
    pytest tests/test_export.py -v

All tests use a temporary SQLite database and temporary output directory —
no permanent files are created.
"""

import os
from datetime import datetime, timezone

import openpyxl
import pytest

from database import DatabaseManager
from database.models import Lead, URL
from export import ExcelExporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test_export.db")
    db = DatabaseManager(db_path)
    db.initialize_db()
    return db


@pytest.fixture
def campaign(tmp_db):
    return tmp_db.create_campaign(
        name="Test Export Campaign",
        niche="marketing agencies",
        target_country="Serbia",
    )


@pytest.fixture
def campaign_with_leads(tmp_db, campaign):
    """Campaign with 3 leads and 2 failed URLs."""
    leads_data = [
        {
            "company_name":     "Acme Marketing",
            "company_size":     "10-50",
            "industry":         "Digital Marketing",
            "website_url":      "https://acme.rs",
            "description":      "Full-service agency",
            "contact_name":     "Marko Nikolic",
            "contact_title":    "CEO",
            "contact_email":    "marko@acme.rs",
            "contact_linkedin": "https://linkedin.com/in/marko",
            "company_email":    "info@acme.rs",
            "company_phone":    "+381 11 123 456",
            "address":          "Belgrade, Serbia",
            "clients_info":     "SMEs in retail",
            "quality_score":    9,
        },
        {
            "company_name":     "Beta Agency",
            "industry":         "SEO",
            "website_url":      "https://beta.rs",
            "description":      "SEO specialists",
            "contact_name":     None,
            "company_email":    "hello@beta.rs",
            "quality_score":    5,
        },
        {
            "company_name":     "Gamma Studio d.o.o.",
            "industry":         "Branding",
            "website_url":      "https://gamma.rs",
            "description":      "Brand identity experts",
            "quality_score":    7,
        },
    ]

    for i, lead_data in enumerate(leads_data):
        url_rec = tmp_db.add_url(campaign.id, f"https://company{i}.rs")
        tmp_db.update_url_status(url_rec.id, "completed")
        tmp_db.add_lead(campaign.id, url_rec.id, lead_data)

    # Two failed URLs
    for j in range(2):
        failed_url = tmp_db.add_url(campaign.id, f"https://failed{j}.rs")
        tmp_db.update_url_status(
            failed_url.id, "failed",
            error_message=f"Connection timeout on attempt {j + 1}",
        )

    return campaign


@pytest.fixture
def exporter(tmp_db):
    return ExcelExporter(tmp_db)


@pytest.fixture
def exported_file(tmp_path, tmp_db, campaign_with_leads, exporter):
    """Export the campaign and return the file path."""
    out_dir = str(tmp_path / "exports")
    return exporter.export_campaign(campaign_with_leads.id, out_dir)


# ---------------------------------------------------------------------------
# File creation
# ---------------------------------------------------------------------------

class TestExcelFileCreated:
    def test_file_exists_after_export(self, exported_file):
        assert os.path.isfile(exported_file)

    def test_file_has_xlsx_extension(self, exported_file):
        assert exported_file.endswith(".xlsx")

    def test_returns_absolute_path(self, exported_file):
        assert os.path.isabs(exported_file)


# ---------------------------------------------------------------------------
# Sheet structure
# ---------------------------------------------------------------------------

class TestExcelSheets:
    def test_has_correct_number_of_sheets(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        assert len(wb.sheetnames) == 3

    def test_has_leads_sheet(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        assert "Leads" in wb.sheetnames

    def test_has_stats_sheet(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        assert "Stats" in wb.sheetnames

    def test_has_failed_urls_sheet(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        assert "Failed URLs" in wb.sheetnames


# ---------------------------------------------------------------------------
# Leads sheet columns
# ---------------------------------------------------------------------------

class TestLeadsSheetColumns:
    EXPECTED_HEADERS = [
        "#", "Company Name", "Industry", "Size", "Description",
        "Contact Name", "Contact Title", "Contact Email", "Contact LinkedIn",
        "Company Email", "Company Phone", "Address", "Website",
        "Clients Info", "Quality Score",
    ]

    def test_all_required_columns_present(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Leads"]
        headers = [ws.cell(row=1, column=c).value for c in range(1, len(self.EXPECTED_HEADERS) + 1)]
        assert headers == self.EXPECTED_HEADERS

    def test_header_count_matches(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Leads"]
        non_empty = [ws.cell(row=1, column=c).value for c in range(1, 20) if ws.cell(row=1, column=c).value]
        assert len(non_empty) == len(self.EXPECTED_HEADERS)


# ---------------------------------------------------------------------------
# Leads data correctness
# ---------------------------------------------------------------------------

class TestLeadsDataCorrect:
    def test_correct_number_of_data_rows(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Leads"]
        # Row 1 = header; rows 2-4 = 3 leads
        data_rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if any(v is not None for v in r)]
        assert len(data_rows) == 3

    def test_company_name_in_leads(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Leads"]
        company_names = [ws.cell(row=r, column=2).value for r in range(2, 5)]
        assert "Acme Marketing" in company_names

    def test_quality_score_in_correct_column(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Leads"]
        # Quality Score is column 15
        scores = [ws.cell(row=r, column=15).value for r in range(2, 5)]
        assert 9 in scores
        assert 5 in scores

    def test_row_numbers_sequential(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Leads"]
        row_nums = [ws.cell(row=r, column=1).value for r in range(2, 5)]
        assert row_nums == [1, 2, 3]


# ---------------------------------------------------------------------------
# Stats sheet
# ---------------------------------------------------------------------------

class TestStatsSheetPopulated:
    def test_stats_title_cell(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Stats"]
        assert ws["A1"].value == "Campaign Statistics"

    def test_campaign_name_in_stats(self, exported_file, campaign_with_leads):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Stats"]
        all_values = [ws.cell(row=r, column=2).value for r in range(2, 20)]
        assert campaign_with_leads.name in all_values

    def test_leads_count_in_stats(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Stats"]
        all_values = [ws.cell(row=r, column=2).value for r in range(2, 20)]
        assert 3 in all_values   # 3 leads

    def test_stats_has_key_column(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Stats"]
        keys = [ws.cell(row=r, column=1).value for r in range(2, 10) if ws.cell(row=r, column=1).value]
        assert "Campaign Name" in keys


# ---------------------------------------------------------------------------
# Failed URLs sheet
# ---------------------------------------------------------------------------

class TestFailedUrlsSheet:
    def test_failed_urls_count(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Failed URLs"]
        data_rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if any(v is not None for v in r)]
        assert len(data_rows) == 2

    def test_failed_url_headers(self, exported_file):
        wb = openpyxl.load_workbook(exported_file)
        ws = wb["Failed URLs"]
        assert ws.cell(row=1, column=2).value == "URL"
        assert ws.cell(row=1, column=3).value == "Error Message"


# ---------------------------------------------------------------------------
# Empty campaign
# ---------------------------------------------------------------------------

class TestEmptyCampaignExport:
    def test_empty_campaign_creates_file(self, tmp_path, tmp_db, campaign, exporter):
        """Export with 0 leads should still produce a valid file."""
        out_dir = str(tmp_path / "empty_exports")
        file_path = exporter.export_campaign(campaign.id, out_dir)
        assert os.path.isfile(file_path)

    def test_empty_leads_sheet_has_only_header(self, tmp_path, tmp_db, campaign, exporter):
        out_dir = str(tmp_path / "empty_exports2")
        file_path = exporter.export_campaign(campaign.id, out_dir)
        wb = openpyxl.load_workbook(file_path)
        ws = wb["Leads"]
        data_rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if any(v is not None for v in r)]
        assert len(data_rows) == 0


# ---------------------------------------------------------------------------
# Output filename format
# ---------------------------------------------------------------------------

class TestOutputFilenameFormat:
    def test_filename_contains_campaign_id(self, exported_file, campaign_with_leads):
        filename = os.path.basename(exported_file)
        assert f"campaign{campaign_with_leads.id}" in filename

    def test_filename_contains_date(self, exported_file):
        from datetime import date
        filename = os.path.basename(exported_file)
        today = date.today().strftime("%Y-%m-%d")
        assert today in filename

    def test_filename_starts_with_leads(self, exported_file):
        filename = os.path.basename(exported_file)
        assert filename.startswith("leads_")

    def test_explicit_file_path_respected(self, tmp_path, tmp_db, campaign_with_leads, exporter):
        """If a full file path is given, it should be used as-is."""
        custom_path = str(tmp_path / "my_custom_export.xlsx")
        result = exporter.export_campaign(campaign_with_leads.id, custom_path)
        assert result == os.path.abspath(custom_path)
        assert os.path.isfile(result)


# ---------------------------------------------------------------------------
# Special characters / unicode
# ---------------------------------------------------------------------------

class TestSpecialCharactersInData:
    def test_unicode_company_name_exported(self, tmp_path, tmp_db, exporter):
        camp = tmp_db.create_campaign(name="Ünïcödé Tëst", niche="testing")
        url_rec = tmp_db.add_url(camp.id, "https://unicode-test.com")
        tmp_db.update_url_status(url_rec.id, "completed")
        tmp_db.add_lead(camp.id, url_rec.id, {
            "company_name": "Ünïcödé Corp Ñ",
            "quality_score": 6,
        })

        out_dir = str(tmp_path / "unicode_exports")
        file_path = exporter.export_campaign(camp.id, out_dir)

        wb = openpyxl.load_workbook(file_path)
        ws = wb["Leads"]
        names = [ws.cell(row=r, column=2).value for r in range(2, 4)]
        assert "Ünïcödé Corp Ñ" in names

    def test_special_chars_in_campaign_name_safe_filename(self, tmp_path, tmp_db, exporter):
        camp = tmp_db.create_campaign(name="Test & Co. / Ltd.", niche="testing")
        out_dir = str(tmp_path / "special_exports")
        file_path = exporter.export_campaign(camp.id, out_dir)
        filename = os.path.basename(file_path)
        # Filename must not contain & / .
        assert "&" not in filename
        assert "/" not in filename
        assert os.path.isfile(file_path)
