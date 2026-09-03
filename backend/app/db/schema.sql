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
