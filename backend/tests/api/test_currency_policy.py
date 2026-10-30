"""Automatic currency resolution end to end: upload → extraction → policy → review."""

from __future__ import annotations

import random
from typing import Any

import pytest

from evaluation.synthetic import invoice_pdf_bytes, random_invoice
from tests.conftest import register_org, upload

pytestmark = pytest.mark.integration

NO_COUNTRY = "Unit 4, Harbour Road"


def _dollar_pdf(seed: int, supplier: str) -> bytes:
    """An invoice that prints only "$" and a supplier address without a country."""
    spec = random_invoice(
        random.Random(seed), seed, currency="$", supplier_name=supplier, supplier_address=NO_COUNTRY, supplier_tax_id=None
    )
    return invoice_pdf_bytes([spec])


async def _process(client: Any, h: dict[str, str], pipeline: Any, name: str, pdf: bytes) -> dict[str, Any]:
    r = await upload(client, h, [(name, pdf, "application/pdf")])
    assert r.status_code in (200, 201, 202), r.text
    doc_id = r.json()["results"][0]["document_id"]
    pipeline()
    (inv,) = (await client.get(f"/api/v1/documents/{doc_id}/invoices", headers=h)).json()
    return dict(inv)


async def _rules(client: Any, h: dict[str, str], inv_id: str) -> set[str]:
    issues = (await client.get(f"/api/v1/invoices/{inv_id}/validations", headers=h)).json()["items"]
    return {i["rule_code"] for i in issues if i["resolution_status"] == "OPEN"}


async def _correct_currency(client: Any, h: dict[str, str], inv: dict[str, Any], code: str) -> None:
    r = await client.patch(
        f"/api/v1/invoices/{inv['id']}/corrections",
        headers=h,
        json={
            "expected_version": inv["version"],
            "reason": "Confirmed with supplier",
            "changes": [{"field_path": "currency", "value": code}],
        },
    )
    assert r.status_code == 200, r.text


async def test_rule_resolves_waiting_and_new_invoices(client: Any, pipeline: Any) -> None:
    org = await register_org(client)
    h = org["headers"]

    waiting = await _process(client, h, pipeline, "a.pdf", _dollar_pdf(501, "Blue Fern Traders"))
    assert waiting["currency"] is None and waiting["currency_raw"] == "$" and waiting["currency_source"] is None
    assert waiting["currency_suggestions"][0] == "USD" and set(waiting["currency_suggestions"]) >= {"USD", "CAD", "AUD"}
    assert "INVALID_CURRENCY" in await _rules(client, h, waiting["id"])

    settings = (await client.get("/api/v1/organization/currency-settings", headers=h)).json()
    assert settings["pending_invoices"] == 1 and settings["default_currency"] is None
    dollar = next(s for s in settings["symbols"] if s["symbol"] == "$")
    assert dollar["rule"] is None and "USD" in dollar["candidates"]

    # A rule may only pick one of the symbol's currencies.
    r = await client.put("/api/v1/organization/currency-settings", headers=h, json={"symbol_rules": {"$": "EUR"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_CURRENCY_RULE"

    r = await client.put("/api/v1/organization/currency-settings", headers=h, json={"symbol_rules": {"$": "USD"}, "apply_to_pending": True})
    assert r.status_code == 200, r.text
    assert r.json()["resolved_invoices"] == 1 and r.json()["pending_invoices"] == 0
    pipeline()  # revalidation

    inv = (await client.get(f"/api/v1/invoices/{waiting['id']}", headers=h)).json()
    assert inv["currency"] == "USD" and inv["currency_source"] == "ORGANIZATION_RULE"
    assert "rule for '$'" in inv["currency_reason"] and inv["field_support_json"]["currency"] == "DERIVED"
    rules = await _rules(client, h, waiting["id"])
    assert "INVALID_CURRENCY" not in rules and "CURRENCY_INFERRED" in rules

    # New uploads are resolved during extraction.
    fresh = await _process(client, h, pipeline, "b.pdf", _dollar_pdf(502, "Kestrel Paper Co"))
    assert fresh["currency"] == "USD" and fresh["currency_source"] == "ORGANIZATION_RULE"
    assert "INVALID_CURRENCY" not in await _rules(client, h, fresh["id"])

    audit = (await client.get("/api/v1/admin/audit-events", headers=h, params={"action": "organization.currency_settings_updated"})).json()
    assert audit["total"] == 1


async def test_default_currency_and_printed_symbols(client: Any, pipeline: Any) -> None:
    org = await register_org(client)
    h = org["headers"]
    r = await client.put("/api/v1/organization/currency-settings", headers=h, json={"default_currency": "CAD"})
    assert r.status_code == 200 and r.json()["default_currency"] == "CAD"

    inv = await _process(client, h, pipeline, "c.pdf", _dollar_pdf(503, "Maple Ridge Supply"))
    assert inv["currency"] == "CAD" and inv["currency_source"] == "ORGANIZATION_DEFAULT"
    assert "default currency" in inv["currency_reason"]

    # A printed code is never overridden by the default.
    printed = await _process(client, h, pipeline, "d.pdf", invoice_pdf_bytes([random_invoice(random.Random(504), 504, currency="GBP")]))
    assert printed["currency"] == "GBP" and printed["currency_source"] == "PRINTED" and printed["currency_reason"] is None


async def test_supplier_history_and_learning_from_reviewers(client: Any, pipeline: Any) -> None:
    org = await register_org(client)
    h = org["headers"]

    # Supplier history: an earlier invoice from the same supplier printed "USD".
    first = await _process(
        client,
        h,
        pipeline,
        "e.pdf",
        invoice_pdf_bytes([random_invoice(random.Random(505), 505, supplier_name="Orbit Labs", currency="USD")]),
    )
    assert first["currency_source"] == "PRINTED"
    second = await _process(client, h, pipeline, "f.pdf", _dollar_pdf(506, "Orbit Labs"))
    assert second["currency"] == "USD" and second["currency_source"] == "SUPPLIER_HISTORY"
    assert "1 earlier invoice from this supplier" in second["currency_reason"]

    # Learning: reviewers resolve "$" as AUD twice; the third "$" invoice follows.
    for seed, supplier in ((507, "Wattle Freight"), (508, "Coral Bay Foods")):
        inv = await _process(client, h, pipeline, f"{seed}.pdf", _dollar_pdf(seed, supplier))
        assert inv["currency"] is None
        await _correct_currency(client, h, inv, "AUD")
        pipeline()
        corrected = (await client.get(f"/api/v1/invoices/{inv['id']}", headers=h)).json()
        assert corrected["currency_source"] == "HUMAN" and corrected["currency_reason"] is None
    settings = (await client.get("/api/v1/organization/currency-settings", headers=h)).json()
    dollar = next(s for s in settings["symbols"] if s["symbol"] == "$")
    assert dollar["learned"] == "AUD" and dollar["learned_from"] == settings["learn_threshold"] == 2

    third = await _process(client, h, pipeline, "g.pdf", _dollar_pdf(509, "Gum Tree Studio"))
    assert third["currency"] == "AUD" and third["currency_source"] == "LEARNED"
    assert "reviewers chose AUD for '$' on 2 earlier invoices" in third["currency_reason"]


async def test_only_admins_change_the_currency_policy(client: Any) -> None:
    org = await register_org(client)
    h = org["headers"]
    r = await client.post(
        "/api/v1/users",
        headers=h,
        json={"email": f"rev-{org['email']}", "password": "Correct-Horse-9-Battery", "full_name": "Reviewer", "role": "REVIEWER"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/v1/auth/login", json={"email": f"rev-{org['email']}", "password": "Correct-Horse-9-Battery"})
    reviewer = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/api/v1/organization/currency-settings", headers=reviewer)).status_code == 200
    r = await client.put("/api/v1/organization/currency-settings", headers=reviewer, json={"default_currency": "USD"})
    assert r.status_code == 403
