-- Freight Charter Compass — SQLite schema
-- Hour 0-2 scope: only the tables Module 2 (vessels) and Module 3 (ports) need.
-- More tables (commodity_price_history, freight_index_history, port_traffic_history,
-- routes_cache, voyage_estimates, scenario_log, assumptions_registry) are added when
-- the module that owns them is built — see DECISIONS.md and TODO.md.

CREATE TABLE IF NOT EXISTS vessel_classes (
    vessel_type     TEXT PRIMARY KEY,        -- Handysize | Supramax | Panamax | Capesize
    dwt_tonnes      REAL NOT NULL,
    draft_m         REAL NOT NULL,
    loa_m           REAL NOT NULL,
    beam_m          REAL NOT NULL,
    speed_knots     REAL NOT NULL,
    fuel_cons_tpd   REAL NOT NULL,            -- laden, at-sea, tonnes/day
    opex_usd_day    REAL,                     -- populated in Module 5; not vessel charter rate
    is_assumption   INTEGER NOT NULL DEFAULT 1, -- 1 = typical-class figure, not one specific hull
    source          TEXT,
    source_url      TEXT
);

CREATE TABLE IF NOT EXISTS ports (
    port_id                TEXT PRIMARY KEY,   -- VIZAG | PARADIP | DHAMRA | ...
    name                   TEXT NOT NULL,
    state                  TEXT,
    lat                    REAL,
    lon                    REAL,
    lat_lon_provenance     TEXT,               -- map-display precision note
    max_draft_m            REAL,
    max_loa_m              REAL,
    max_beam_m             REAL,
    coal_handling           INTEGER NOT NULL DEFAULT 0,
    berth_reference        TEXT,               -- which berth/terminal the figures describe
    annual_capacity_mtpa   REAL,
    verified               INTEGER NOT NULL DEFAULT 0, -- 1 = confirmed against an official source
    source                 TEXT,
    source_url             TEXT,
    source_date            TEXT
);

-- Added in the data-pipeline block (Hour 2-5). 'coking_coal' added at the
-- coking-coal-proxy fix (DECISIONS.md #23) -- the commodity SAIL actually
-- procures; 'coal_australian' is thermal coal, kept as a distinct series,
-- not replaced (see the labels each is given in the frontend/data-sources
-- catalog for the thermal/coking distinction).
CREATE TABLE IF NOT EXISTS commodity_price_history (
    date        TEXT NOT NULL,        -- ISO date, first-of-month for a monthly series; an exact date for a single dated snapshot
    commodity   TEXT NOT NULL,        -- 'coal_australian' | 'crude_oil_brent' | 'coking_coal'
    price_usd   REAL NOT NULL,        -- $/tonne (coal) or $/bbl (oil) — see unit per commodity
    unit        TEXT NOT NULL,        -- 'usd_per_tonne' | 'usd_per_bbl' | whatever ingest_rba_coking_coal.py's real run reports (see its docstring)
    source      TEXT,
    source_url  TEXT,
    PRIMARY KEY (date, commodity)
);

-- Populated at the Indian-port-traffic checkpoint (DECISIONS.md #26).
-- shipmin.gov.in / data.gov.in / IPA are network-blocked from every
-- environment this app has been built in (same organisation-level egress
-- block as thedocs.worldbank.org and rba.gov.au -- DECISIONS.md #10), and
-- no freely-accessible, structured, coal-specific MONTHLY series exists
-- for these 6 ports anywhere else either. What IS real and citable: one
-- individually-reported coal-handling record per port, found via
-- targeted research -- a 24-hour discharge record, a single shipment, a
-- berth record -- never a monthly aggregate. `month` holds the event's
-- own date (or the first of the month, if only the month is known), NOT
-- a full-month total unless `note` says so. Every row's `note` states
-- plainly what the figure actually measures; rows are NOT comparable to
-- each other (different years, different measurement windows) and are
-- NOT used by any ranking/decision logic in this app -- context only.
CREATE TABLE IF NOT EXISTS port_traffic_history (
    month       TEXT NOT NULL,        -- the event's own date, or first-of-month if only the month is known -- see table comment
    port_id     TEXT NOT NULL REFERENCES ports(port_id),
    commodity   TEXT NOT NULL,
    volume_tonnes REAL NOT NULL,
    note        TEXT,                 -- what this figure actually measures (24hr record / single shipment / berth record, scope caveats) -- required reading before treating it as a monthly total
    source      TEXT,
    source_url  TEXT,
    PRIMARY KEY (month, port_id, commodity)
);

-- Added in the voyage-calculator block (Hour 9-13, Module 5). Overseas
-- coal-loading ports — the origin side of every voyage this app costs out.
-- Fixed small set (Australia/Indonesia/South Africa), not a general port
-- database — see DECISIONS.md #8.
CREATE TABLE IF NOT EXISTS origin_ports (
    origin_id   TEXT PRIMARY KEY,    -- e.g. NEWCASTLE_AU
    name        TEXT NOT NULL,
    country     TEXT NOT NULL,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    source      TEXT,
    source_url  TEXT
);
