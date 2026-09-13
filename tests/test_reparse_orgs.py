"""Re-parsing from snapshots, organization matching and coverage metrics."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from radar.importer import (
    find_similar_organization,
    reparse_from_snapshots,
    run_import,
    upsert_organization,
)
from radar.models import Organization, OrganizationAlias, Procedure, RawSnapshot
from radar.snapshots import compress
from radar.source.client import FixtureSource
from radar.stats import collect_stats

THRESHOLD = 0.92


def test_exact_name_match_is_case_insensitive(session):
    first = upsert_organization(session, "Buxoro Davlat Universiteti", None)
    second = upsert_organization(session, "buxoro davlat universiteti", None)
    session.commit()
    assert first.id == second.id
    assert session.scalar(select(func.count()).select_from(Organization)) == 1
    # Spellings that differ only in case are one alias, not two near-identical rows.
    assert session.scalar(select(func.count()).select_from(OrganizationAlias)) == 1
    # A genuinely different spelling is kept, so later matching has something to work with.
    upsert_organization(session, "Buxoro davlat universiteti (BuxDU)", None)
    session.commit()
    assert session.scalar(select(func.count()).select_from(OrganizationAlias)) == 2


def test_stir_identifies_an_organization_across_name_changes(session):
    first = upsert_organization(session, "Toshkent shahar hokimligi", "301234567")
    second = upsert_organization(session, "Toshkent shahri hokimligi apparati", "301234567")
    session.commit()
    assert first.id == second.id and second.stir == "301234567"


def test_a_stir_is_adopted_by_an_existing_nameless_match(session):
    without = upsert_organization(session, "Andijon viloyat hokimligi", None)
    session.commit()
    assert without.stir is None
    with_stir = upsert_organization(session, "Andijon viloyat hokimligi", "300000001")
    session.commit()
    assert with_stir.id == without.id and with_stir.stir == "300000001"


def test_near_duplicate_names_merge_only_without_a_stir(session):
    upsert_organization(session, "Samarqand viloyati tibbiyot birlashmasi", None)
    session.commit()
    merged = upsert_organization(session, "Samarqand viloyat tibbiyot birlashmasi", None,
                                 match_threshold=THRESHOLD)
    session.commit()
    assert session.scalar(select(func.count()).select_from(Organization)) == 1
    assert merged.name_canonical == "Samarqand viloyati tibbiyot birlashmasi"


def test_different_organizations_are_never_merged(session):
    upsert_organization(session, "Buxoro davlat universiteti", None)
    upsert_organization(session, "Buxoro davlat tibbiyot instituti", None,
                        match_threshold=THRESHOLD)
    session.commit()
    assert session.scalar(select(func.count()).select_from(Organization)) == 2


def test_identified_organizations_are_not_candidates_for_fuzzy_merging(session):
    upsert_organization(session, "Navoiy kon metallurgiya kombinati", "300000002")
    session.commit()
    assert find_similar_organization(session, "Navoiy kon metallurgiya kombinat",
                                     THRESHOLD) is None
    other = upsert_organization(session, "Navoiy kon metallurgiya kombinat", None,
                                match_threshold=THRESHOLD)
    session.commit()
    assert other.stir is None
    assert session.scalar(select(func.count()).select_from(Organization)) == 2


def test_matching_is_off_unless_a_threshold_is_given(session):
    upsert_organization(session, "Xorazm viloyati soliq boshqarmasi", None)
    upsert_organization(session, "Xorazm viloyat soliq boshqarmasi", None)
    session.commit()
    assert session.scalar(select(func.count()).select_from(Organization)) == 2


def test_reparse_rebuilds_rows_without_the_network(session, samples_dir):
    run_import(session, FixtureSource(samples_dir))
    before = session.scalar(select(func.count()).select_from(Procedure))
    snapshots = session.scalar(select(func.count()).select_from(RawSnapshot))

    # Wipe derived fields; only the snapshots remain.
    session.execute(Procedure.__table__.update().values(title="", start_price=None))
    session.commit()

    stats = reparse_from_snapshots(session)
    assert stats.considered == before and stats.reparsed == before
    assert stats.checksum_failures == 0 and stats.parse_failures == 0
    restored = session.scalars(select(Procedure)).all()
    assert all(p.title for p in restored)
    assert any(p.start_price is not None for p in restored)
    # No refetch, so no new snapshots and no duplicate procedures.
    assert session.scalar(select(func.count()).select_from(RawSnapshot)) == snapshots
    assert session.scalar(select(func.count()).select_from(Procedure)) == before


def test_reparse_dry_run_writes_nothing(session, samples_dir):
    run_import(session, FixtureSource(samples_dir))
    session.execute(Procedure.__table__.update().values(title=""))
    session.commit()
    stats = reparse_from_snapshots(session, dry_run=True)
    assert stats.reparsed > 0
    assert all(p.title == "" for p in session.scalars(select(Procedure)))


def test_corrupted_snapshot_is_reported_not_reparsed(session, samples_dir):
    run_import(session, FixtureSource(samples_dir), limit=1)
    snap = session.scalar(select(RawSnapshot).order_by(RawSnapshot.id.desc()))
    snap.body = compress(b'{"id": "TAMPERED"}')
    session.commit()
    stats = reparse_from_snapshots(session)
    assert stats.checksum_failures == 1 and stats.errors
    assert not session.scalar(select(Procedure).where(Procedure.source_id == "TAMPERED"))


def test_reparse_limit(session, samples_dir):
    run_import(session, FixtureSource(samples_dir))
    assert reparse_from_snapshots(session, limit=3).considered == 3


def test_coverage_metrics(session, samples_dir):
    empty = collect_stats(session)
    assert empty["coverage_amount_pct"] == 0.0
    run_import(session, FixtureSource(samples_dir))
    stats = collect_stats(session)
    assert stats["coverage_completed_at_pct"] == 100.0
    assert stats["coverage_customer_pct"] == 100.0
    assert stats["coverage_amount_pct"] == 100.0
    assert 0 < stats["coverage_award_pct"] <= 100.0
    assert stats["coverage_quantity_pct"] == 100.0


def test_coverage_reports_missing_amounts(session):
    session.add(Procedure(source="synthetic", source_id="NOAMOUNT", title="x"))
    session.add(Procedure(source="synthetic", source_id="AMOUNT", title="y",
                          start_price=Decimal("5")))
    session.commit()
    stats = collect_stats(session)
    assert stats["coverage_amount_pct"] == 50.0
    assert stats["coverage_award_pct"] == 0.0
    assert stats["coverage_completed_at_pct"] == 0.0
