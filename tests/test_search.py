"""Unit tests for Tender Radar Advanced Search & Intelligence Engine."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from radar.models import (
    Award,
    Base,
    Classification,
    LotItem,
    Organization,
    OrganizationAlias,
    Procedure,
)
from radar.search import (
    search_competitor_intelligence,
    search_customer_intelligence,
    search_keywords,
)


@pytest.fixture
def search_db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    tables = [
        Organization.__table__,
        OrganizationAlias.__table__,
        Procedure.__table__,
        LotItem.__table__,
        Award.__table__,
        Classification.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        # Create Customers
        bank = Organization(
            name_canonical="Aloqabank ATB", stir="200111222", region="Toshkent shahri"
        )
        gidro = Organization(
            name_canonical="O'zbekgidroenergo AJ", stir="200333444", region="Toshkent viloyati"
        )

        # Create Suppliers / Competitors
        smart = Organization(name_canonical="Smart Server MCHJ", stir="305111222")
        komp = Organization(name_canonical="Kompyuter Servis XK", stir="305333444")

        session.add_all([bank, gidro, smart, komp])
        session.flush()

        # Procedure 1: Server purchased by Aloqabank from Smart Server
        p1 = Procedure(
            source="ebirja",
            source_id="ebirja_c_101",
            source_url="https://ebirja.uz/contracts/101",
            title="Dell PowerEdge Server yetkazib berish",
            procedure_type="E-Birja Shop",
            customer_org_id=bank.id,
            status="COMPLETED",
            start_price=Decimal("120000000"),
            currency="UZS",
        )
        session.add(p1)
        session.flush()

        session.add(
            LotItem(
                procedure_id=p1.id,
                raw_name="Dell PowerEdge R750 Server",
                brand="Dell",
                product_family="PowerEdge",
                quantity=Decimal("2"),
            )
        )
        session.add(
            Award(
                procedure_id=p1.id,
                supplier_org_id=smart.id,
                amount=Decimal("118000000"),
            )
        )
        session.add(
            Classification(
                procedure_id=p1.id,
                is_it=True,
                category="Server & Storage",
                brand="Dell",
                method="rule",
            )
        )

        # Procedure 2: Kaspersky Anti-virus purchased by Aloqabank from Kompyuter Servis
        p2 = Procedure(
            source="xt_xarid",
            source_id="xt_202",
            source_url="https://xt-xarid.uz/lot/202",
            title="Kaspersky Endpoint Security litsenziyalari",
            procedure_type="Auksion",
            customer_org_id=bank.id,
            status="COMPLETED",
            start_price=Decimal("45000000"),
            currency="UZS",
        )
        session.add(p2)
        session.flush()

        session.add(
            LotItem(
                procedure_id=p2.id,
                raw_name="Kaspersky Total Security for Business",
                brand="Kaspersky",
                product_family="Endpoint Security",
                quantity=Decimal("100"),
            )
        )
        session.add(
            Award(
                procedure_id=p2.id,
                supplier_org_id=komp.id,
                amount=Decimal("44000000"),
            )
        )
        session.add(
            Classification(
                procedure_id=p2.id,
                is_it=True,
                category="Antivirus & Security",
                brand="Kaspersky",
                method="rule",
            )
        )

        # Procedure 3: Fortinet Firewall purchased by O'zbekgidroenergo from Smart Server
        p3 = Procedure(
            source="ebirja",
            source_id="ebirja_c_303",
            source_url="https://ebirja.uz/contracts/303",
            title="Fortinet FortiGate 100F tarmoq xavfsizligi",
            procedure_type="E-Birja Tender",
            customer_org_id=gidro.id,
            status="COMPLETED",
            start_price=Decimal("95000000"),
            currency="UZS",
        )
        session.add(p3)
        session.flush()

        session.add(
            LotItem(
                procedure_id=p3.id,
                raw_name="Fortinet FortiGate 100F",
                brand="Fortinet",
                product_family="FortiGate",
                quantity=Decimal("1"),
            )
        )
        session.add(
            Award(
                procedure_id=p3.id,
                supplier_org_id=smart.id,
                amount=Decimal("92000000"),
            )
        )
        session.add(
            Classification(
                procedure_id=p3.id,
                is_it=True,
                category="Networking & Firewall",
                brand="Fortinet",
                method="rule",
            )
        )

        session.commit()
        yield session


def test_search_keywords(search_db_session: Session) -> None:
    # 1. Search by brand
    res_kaspersky = search_keywords(search_db_session, "Kaspersky")
    assert len(res_kaspersky) == 1
    assert res_kaspersky[0]["customer"]["name"] == "Aloqabank ATB"
    assert res_kaspersky[0]["supplier"]["name"] == "Kompyuter Servis XK"
    assert res_kaspersky[0]["amount"] == 44000000.0

    # 2. Search by title keyword
    res_server = search_keywords(search_db_session, "Server")
    assert len(res_server) >= 1
    assert any("Dell" in r["title"] for r in res_server)

    # 3. Search by category
    res_net = search_keywords(search_db_session, "Networking")
    assert len(res_net) == 1
    assert res_net[0]["customer"]["name"] == "O'zbekgidroenergo AJ"


def test_search_customer_intelligence(search_db_session: Session) -> None:
    # Search by customer name
    intel = search_customer_intelligence(search_db_session, "Aloqabank")
    assert intel["found"] is True
    assert intel["count"] == 1

    org = intel["organizations"][0]
    assert org["name"] == "Aloqabank ATB"
    assert org["stir"] == "200111222"
    assert org["total_purchases_count"] == 2
    assert org["total_spent"] == 162000000.0  # 118m + 44m
    assert len(org["purchases"]) == 2

    # Verify top suppliers for this customer
    suppliers = [s["supplier"] for s in org["top_suppliers"]]
    assert "Smart Server MCHJ" in suppliers
    assert "Kompyuter Servis XK" in suppliers

    # Search by STIR
    intel_stir = search_customer_intelligence(search_db_session, "200333444")
    assert intel_stir["found"] is True
    assert intel_stir["organizations"][0]["name"] == "O'zbekgidroenergo AJ"
    assert intel_stir["organizations"][0]["total_spent"] == 92000000.0


def test_search_competitor_intelligence(search_db_session: Session) -> None:
    # Search competitor by name
    comp = search_competitor_intelligence(search_db_session, "Smart Server")
    assert comp["found"] is True
    assert comp["count"] == 1

    c = comp["competitors"][0]
    assert c["name"] == "Smart Server MCHJ"
    assert c["total_wins_count"] == 2
    assert c["total_won_amount"] == 210000000.0  # 118m + 92m
    assert len(c["deals"]) == 2

    # Verify who they sold to
    customers = [cust["customer"] for cust in c["top_customers"]]
    assert "Aloqabank ATB" in customers
    assert "O'zbekgidroenergo AJ" in customers


def test_web_api_search_endpoints(tmp_path, monkeypatch) -> None:
    from contextlib import contextmanager

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from radar import web

    db_path = tmp_path / "web_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    tables = [
        Organization.__table__,
        OrganizationAlias.__table__,
        Procedure.__table__,
        LotItem.__table__,
        Award.__table__,
        Classification.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)

    with Session(engine) as s:
        bank = Organization(name_canonical="Aloqabank ATB", stir="200111222")
        smart = Organization(name_canonical="Smart Server MCHJ", stir="305111222")
        s.add_all([bank, smart])
        s.flush()
        p = Procedure(
            source="ebirja",
            source_id="eb_101",
            title="Kaspersky Endpoint Security",
            customer_org_id=bank.id,
            start_price=Decimal("50000000"),
        )
        s.add(p)
        s.flush()
        s.add(LotItem(procedure_id=p.id, raw_name="Kaspersky Total Security", brand="Kaspersky"))
        s.add(Award(procedure_id=p.id, supplier_org_id=smart.id, amount=Decimal("49000000")))
        s.commit()

    @contextmanager
    def mock_scope(*args, **kwargs):
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(web, "session_scope", mock_scope)
    client = TestClient(web.app)

    # 1. Keyword search API
    res_kw = client.get("/api/search?q=Kaspersky&type=keyword")
    assert res_kw.status_code == 200
    assert len(res_kw.json()["results"]) == 1
    assert res_kw.json()["results"][0]["customer"]["name"] == "Aloqabank ATB"

    # 2. Customer search API
    res_cust = client.get("/api/search?q=Aloqabank&type=customer")
    assert res_cust.status_code == 200
    assert res_cust.json()["found"] is True
    assert res_cust.json()["organizations"][0]["stir"] == "200111222"

    # 3. Competitor search API
    res_comp = client.get("/api/search?q=Smart&type=competitor")
    assert res_comp.status_code == 200
    assert res_comp.json()["found"] is True
    assert res_comp.json()["competitors"][0]["name"] == "Smart Server MCHJ"

    # 4. E-IMZO status API
    res_eimzo = client.get("/api/eimzo/status")
    assert res_eimzo.status_code == 200
    assert "daemon" in res_eimzo.json()
    assert "session" in res_eimzo.json()

