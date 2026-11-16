"""E-Birja cabinet export importer.

The real export's headers were never available (CLAUDE.md forbids logging in to ebirja.uz), so
these tests pin the mechanism -- header matching, grouping, number parsing -- rather than any
claim about what a real file looks like.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from radar.source.ebirja_export import (
    SOURCE,
    load_ebirja_export,
    match_columns,
    normalize_header,
    parse_amount,
    read_table,
)

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "ebirja" / "export_SYNTHETIC.csv"


def test_the_longest_synonym_wins_the_column():
    """"Buyurtmachi INN" must be the STIR, not a second customer name."""
    match = match_columns(["Shartnoma raqami", "Buyurtmachi", "Buyurtmachi INN", "Mahsulot nomi"])
    assert match.columns["contract_number"] == 0
    assert match.columns["customer_name"] == 1
    assert match.columns["customer_stir"] == 2
    assert match.columns["product_name"] == 3


def test_each_column_is_claimed_by_at_most_one_field():
    match = match_columns(["Shartnoma raqami", "Mahsulot nomi", "Summa"])
    assert sorted(match.columns.values()) == [0, 1, 2]


def test_a_missing_required_column_is_refused_with_the_report():
    """Silently importing a file with no product name would produce unclassifiable rows."""
    match = match_columns(["Shartnoma raqami", "Summa"])
    assert "product_name" in match.missing_required


def test_normalize_header_folds_case_punctuation_and_apostrophes():
    assert normalize_header("O‘lchov birligi") == "o lchov birligi"
    assert normalize_header("  Shartnoma   №  ") == "shartnoma"
    assert normalize_header(None) == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("48 000 000", Decimal("48000000")),
        ("120 500 000", Decimal("120500000")),
        ("15750000,50", Decimal("15750000.50")),
        ("1 234.56", Decimal("1234.56")),
        (48000000, Decimal("48000000")),
        ("", None),
        ("—", None),
        (None, None),
    ],
)
def test_parse_amount_tolerates_how_the_file_was_generated(raw, expected):
    assert parse_amount(raw) == expected


def test_read_table_skips_a_title_line_before_the_header():
    headers, rows = read_table(SAMPLE)
    assert headers[0] == "Shartnoma raqami"
    assert len(rows) == 5


def test_load_groups_line_items_under_one_contract():
    records, report, match = load_ebirja_export(SAMPLE)
    assert not match.missing_required
    assert report.rows == 5
    assert report.skipped == 1  # the row with no contract number
    assert report.contracts == 3
    assert report.items == 4
    assert report.multi_row_contracts == 1
    # The amount column repeats the contract total on every row, so it must not be summed.
    assert report.varying_amount_contracts == 0

    by_id = {r.source_id: r for r in records}
    two = by_id["ebirja_x_XD-SYN-0002"]
    assert len(two.items) == 2
    assert two.start_price == Decimal("120500000")
    assert {i.raw_name for i in two.items} == {
        "Microsoft Office 365 E3 litsenziyasi 12 oy",
        "Kaspersky Endpoint Security for Business",
    }
    assert two.award is not None
    assert two.award.supplier_stir == "900000004"
    assert two.customer_stir == "900000003"
    # A finished contract: these are what put it on the renewal radar.
    assert two.status == "COMPLETED"
    assert two.completed_at is not None


def test_export_contracts_keep_their_own_source_and_the_number_in_the_key():
    """The 32 489 API-era rows are keyed on an internal id an export does not carry, so the
    two key spaces cannot be merged; the number stays recoverable for a future dedupe."""
    assert SOURCE == "ebirja_export"
    records, _report, _match = load_ebirja_export(SAMPLE)
    assert all(r.source_id.startswith("ebirja_x_") for r in records)


# --- worker stage -----------------------------------------------------------------------


@pytest.fixture
def staged(tmp_path, monkeypatch):
    """Point the worker's export folder and marker at a temp directory."""
    from radar import worker

    folder = tmp_path / "ebirja"
    folder.mkdir()
    monkeypatch.setattr(worker, "EBIRJA_EXPORT_DIR", folder)
    monkeypatch.setattr(worker, "EBIRJA_EXPORT_MARKER", tmp_path / "marker")
    monkeypatch.delenv("EBIRJA_EXPORT_PATH", raising=False)
    monkeypatch.delenv("EBIRJA_EXPORT_IMPORT", raising=False)

    import contextlib

    monkeypatch.setattr(worker, "session_scope", lambda: contextlib.nullcontext(object()))
    return worker, folder


def test_stage_does_nothing_when_no_export_has_been_left(staged):
    worker, _folder = staged
    assert worker.sync_ebirja_export() == 0
    assert not worker.EBIRJA_EXPORT_MARKER.exists()


def test_stage_imports_a_new_export_and_records_its_mtime(staged, monkeypatch):
    worker, folder = staged
    target = folder / "shartnomalar.csv"
    target.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    seen = []
    monkeypatch.setattr(
        "radar.source.ebirja_export.import_ebirja_export",
        lambda s, r: (seen.append(r), {"inserted": len(r), "updated": 0, "items": 0})[1],
    )

    assert worker.sync_ebirja_export() == 3
    assert len(seen[0]) == 3
    assert worker.EBIRJA_EXPORT_MARKER.exists()

    # Second cycle, same file: the marker must stop it re-importing.
    seen.clear()
    assert worker.sync_ebirja_export() == 0
    assert seen == []


def test_stage_leaves_the_marker_alone_when_a_required_column_is_missing(staged, monkeypatch):
    """Nothing is written, so the next cycle must retry once the mapping is corrected."""
    worker, folder = staged
    (folder / "wrong.csv").write_text("Shartnoma raqami,Summa\nXD-1,100\n", encoding="utf-8")

    called = []
    monkeypatch.setattr(
        "radar.source.ebirja_export.import_ebirja_export",
        lambda s, r: called.append(r) or {},
    )

    assert worker.sync_ebirja_export() == 0
    assert called == []
    assert not worker.EBIRJA_EXPORT_MARKER.exists()


def test_stage_can_be_switched_off(staged, monkeypatch):
    worker, folder = staged
    (folder / "shartnomalar.csv").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("EBIRJA_EXPORT_IMPORT", "0")
    assert worker.sync_ebirja_export() == 0
    assert not worker.EBIRJA_EXPORT_MARKER.exists()


def test_export_path_takes_the_newest_file_and_ignores_excel_lock_files(staged):
    worker, folder = staged
    old = folder / "oktyabr.xlsx"
    new = folder / "noyabr.xlsx"
    lock = folder / "~$noyabr.xlsx"
    for f in (old, new, lock):
        f.write_bytes(b"x")
    import os as _os

    _os.utime(old, (1_700_000_000, 1_700_000_000))
    _os.utime(new, (1_800_000_000, 1_800_000_000))
    _os.utime(lock, (1_900_000_000, 1_900_000_000))

    assert worker.ebirja_export_path() == new


def test_run_once_reports_the_export_stage(monkeypatch):
    from radar import worker

    for name in (
        "sync_ebirja",
        "sync_uzex",
        "sync_cooperation",
        "refresh_renewals",
        "rebuild_and_deploy",
    ):
        monkeypatch.setattr(worker, name, lambda: 0)
    monkeypatch.setattr(worker, "dispatch_alerts", lambda: {"sent": 0})
    monkeypatch.setattr(worker, "sync_ebirja_export", lambda: 11)

    result = worker.run_once()
    assert result["ebirja_export_inserted"] == 11
