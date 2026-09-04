from app.engine.data_sources import VALID_CLASSIFICATIONS, build_data_sources
from app.db.connection import db_session


def _flat_entries(payload):
    return [e for cat in payload["categories"] for e in cat["entries"]]


def test_build_data_sources_shape():
    with db_session() as conn:
        payload = build_data_sources(conn)

    assert "categories" in payload
    assert len(payload["categories"]) == 8
    for cat in payload["categories"]:
        assert cat["category"]
        assert isinstance(cat["entries"], list)
        assert len(cat["entries"]) > 0


def test_every_entry_has_a_valid_classification():
    with db_session() as conn:
        payload = build_data_sources(conn)

    for entry in _flat_entries(payload):
        assert entry["classification"] in VALID_CLASSIFICATIONS
        assert entry["label"]


def test_commodity_prices_are_real_and_sourced():
    with db_session() as conn:
        payload = build_data_sources(conn)

    cat = next(c for c in payload["categories"] if c["category"] == "Commodity prices")
    for entry in cat["entries"]:
        assert entry["classification"] == "REAL"
        # Either genuinely sourced (real history loaded) or the honest
        # "nothing loaded yet" fallback — never silently blank.
        assert entry["source"] or entry["detail"]


def test_ports_reflect_their_own_verified_flag():
    with db_session() as conn:
        payload = build_data_sources(conn)

    cat = next(
        c for c in payload["categories"] if c["category"] == "East Coast India ports (destination)"
    )
    assert len(cat["entries"]) == 6
    for entry in cat["entries"]:
        # A verified port must be labelled REAL, not ASSUMPTION — the two
        # must never disagree, since `verified` is what the Overview page's
        # own badge is driven by.
        if entry["verified"]:
            assert entry["classification"] == "REAL"
        else:
            assert entry["classification"] == "ASSUMPTION"


def test_origin_ports_present():
    with db_session() as conn:
        payload = build_data_sources(conn)

    cat = next(
        c for c in payload["categories"] if c["category"] == "Overseas loading ports (origin)"
    )
    assert len(cat["entries"]) == 3
    for entry in cat["entries"]:
        assert entry["classification"] == "REAL"
        assert entry["source"]


def test_vessel_classes_are_assumptions():
    with db_session() as conn:
        payload = build_data_sources(conn)

    cat = next(c for c in payload["categories"] if c["category"] == "Vessel class specifications")
    assert len(cat["entries"]) == 4
    for entry in cat["entries"]:
        assert entry["classification"] == "ASSUMPTION"
        assert entry["source"]


def test_voyage_cost_inputs_cite_the_same_constants_voyage_engine_uses():
    from app.engine.voyage import BUNKER_PRICE_SOURCE, TIME_CHARTER_SOURCE

    with db_session() as conn:
        payload = build_data_sources(conn)

    cat = next(c for c in payload["categories"] if c["category"] == "Voyage cost inputs")
    sources = {entry["source"] for entry in cat["entries"]}
    assert BUNKER_PRICE_SOURCE in sources
    assert TIME_CHARTER_SOURCE in sources
    for entry in cat["entries"]:
        assert entry["classification"] == "ASSUMPTION"


def test_port_traffic_entries_are_real_and_individually_captioned():
    with db_session() as conn:
        payload = build_data_sources(conn)

    cat = next(
        c for c in payload["categories"] if c["category"].startswith("Port cargo-handling")
    )
    assert len(cat["entries"]) == 6  # one real reported event per port
    for entry in cat["entries"]:
        assert entry["classification"] == "REAL"
        assert entry["source"]
        # every entry must explain what it actually measures -- these are
        # single events, never a monthly aggregate, so the caption is not
        # optional the way it is for, say, a vessel spec row.
        assert entry["detail"]


def test_currency_entry_cites_the_same_rate_the_endpoint_uses():
    from app.engine.currency import USD_TO_INR_RATE, USD_TO_INR_SOURCE

    with db_session() as conn:
        payload = build_data_sources(conn)

    cat = next(c for c in payload["categories"] if c["category"] == "Currency conversion")
    assert len(cat["entries"]) == 1
    entry = cat["entries"][0]
    assert entry["classification"] == "CALCULATED"
    assert entry["source"] == USD_TO_INR_SOURCE
    assert str(USD_TO_INR_RATE) in entry["detail"] or f"{USD_TO_INR_RATE:.2f}" in entry["detail"]


def test_methodology_entries_are_calculated_with_no_external_source():
    with db_session() as conn:
        payload = build_data_sources(conn)

    cat = next(c for c in payload["categories"] if c["category"].startswith("Calculated methodology"))
    assert len(cat["entries"]) == 5
    for entry in cat["entries"]:
        assert entry["classification"] == "CALCULATED"
        # These are methodology notes, not citations to an external row —
        # they should never carry a source_url (that would misleadingly
        # imply an outside citation for something that's just arithmetic).
        assert entry["source_url"] is None
