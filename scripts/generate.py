"""
RetailMind :: synthetic retail warehouse generator

The point of this file is behavioural realism, not volume. Uniform-random orders
produce flat cohort curves, a meaningless RFM split, and campaigns that all look
identical -- every downstream dashboard then has nothing to find. So customers
here have latent traits (how often they buy, how long before they lapse, how much
they spend) and orders fall out of those traits.

What the data is built to reproduce:
  * heavy-tailed value       -- a small share of customers drives most revenue
  * a long single-visit tail -- the exact problem Xeno sells against
  * per-customer lapse       -- so retention curves decay instead of flatlining
  * festival seasonality     -- Diwali (Oct-Nov) and EOSS (Jan, Jul)
  * campaign holdouts        -- so lift is measurable, not just response rate

On campaigns specifically: each campaign is given a TRUE incremental lift, and
treated customers really do receive extra orders in the campaign window while the
holdout does not. A couple of campaigns are deliberately given near-zero lift, so
the campaign dashboard has something honest to find -- high open rates masking a
campaign that never actually caused a sale.
"""

import io
import os
import sys
import time
import numpy as np
import psycopg2

# ----------------------------------------------------------------------------- config
DSN = os.environ.get(
    "RETAILMIND_DSN", "postgresql://retail:retail@localhost:5433/retailmind"
)

N_CUSTOMERS = int(os.environ.get("RM_CUSTOMERS", 300_000))
TARGET_ORDERS = int(os.environ.get("RM_ORDERS", 10_000_000))
N_STORES = 240
CUST_CHUNK = 25_000  # customers per COPY batch, keeps memory flat

START_DAY = np.datetime64("2023-01-01")
END_DAY = np.datetime64("2025-12-31")
N_DAYS = int((END_DAY - START_DAY) / np.timedelta64(1, "D"))

RNG = np.random.default_rng(20260910)

BRANDS = [
    # id, name,            category,  avg ticket (INR)
    (1, "Subly", "QSR", 320.0),
    (2, "Taco Bandit", "QSR", 410.0),
    (3, "Fabrique", "Apparel", 2450.0),
    (4, "Kaya Naturals", "Beauty", 980.0),
    (5, "Third Wave Cafe", "Cafe", 265.0),
]

CITIES = [
    ("Delhi", "North"), ("Gurugram", "North"), ("Noida", "North"),
    ("Chandigarh", "North"), ("Mumbai", "West"), ("Pune", "West"),
    ("Ahmedabad", "West"), ("Bengaluru", "South"), ("Chennai", "South"),
    ("Hyderabad", "South"), ("Kochi", "South"), ("Kolkata", "East"),
    ("Bhubaneswar", "East"), ("Guwahati", "East"),
]

AGE_BANDS = np.array(["18-24", "25-34", "35-44", "45-54", "55+"])
AGE_W = np.array([0.22, 0.34, 0.23, 0.13, 0.08])
ACQ = np.array(["store", "instagram", "google", "referral", "app"])
ACQ_W = np.array([0.38, 0.24, 0.17, 0.11, 0.10])
CHANNELS = np.array(["store", "web", "app"])
SEND_CHANNELS = np.array(["sms", "email", "whatsapp"])


def log(msg):
    print(f"  {msg}", flush=True)


def seasonal_weight(dates):
    """Multiplier on order likelihood by month. Diwali and end-of-season sales."""
    months = dates.astype("datetime64[M]").astype(int) % 12 + 1
    w = np.ones(len(months))
    w[months == 10] = 1.55  # Diwali build-up
    w[months == 11] = 1.75  # Diwali peak
    w[months == 1] = 1.40   # EOSS
    w[months == 7] = 1.35   # mid-year sale
    w[months == 12] = 1.25  # festive tail
    w[months == 3] = 0.85
    w[months == 6] = 0.80   # monsoon lull
    return w


# ----------------------------------------------------------------------------- dimensions
def load_dimensions(cur):
    log("brands, stores")
    cur.executemany(
        "INSERT INTO brands (brand_id, brand_name, category, avg_ticket)"
        " VALUES (%s,%s,%s,%s)",
        BRANDS,
    )

    rows = []
    for sid in range(1, N_STORES + 1):
        brand = int(RNG.integers(1, len(BRANDS) + 1))
        city, region = CITIES[int(RNG.integers(0, len(CITIES)))]
        opened = START_DAY - np.timedelta64(int(RNG.integers(0, 2200)), "D")
        rows.append(
            (sid, brand, f"{BRANDS[brand - 1][1]} {city} {sid:03d}", city, region, str(opened))
        )
    cur.executemany(
        "INSERT INTO stores (store_id, brand_id, store_name, city, region, opened_date)"
        " VALUES (%s,%s,%s,%s,%s,%s)",
        rows,
    )
    return rows


def build_customers(cur):
    """Customers, plus the latent traits that drive their ordering behaviour."""
    log(f"customers ({N_CUSTOMERS:,})")

    n = N_CUSTOMERS
    brand_id = RNG.integers(1, len(BRANDS) + 1, n).astype(np.int16)

    # Signups skew later: the business is growing across the window.
    signup_off = (RNG.beta(1.6, 2.2, n) * (N_DAYS - 45)).astype(int)
    signup = START_DAY + signup_off.astype("timedelta64[D]")

    city_idx = RNG.integers(0, len(CITIES), n)

    # Latent frequency. Lognormal gives a fat tail of very engaged customers
    # alongside a large mass who buy once or twice and vanish.
    intensity = RNG.lognormal(mean=1.05, sigma=1.15, size=n)

    # How long they stay active before lapsing, in days. Correlated with
    # intensity -- engaged customers also stick around longer.
    lifetime = RNG.exponential(scale=120 + 40 * np.log1p(intensity)).astype(int)
    lifetime = np.clip(lifetime, 1, N_DAYS)

    # Spend multiplier, independent of frequency: some rare buyers spend big.
    spend_mult = RNG.lognormal(mean=0.0, sigma=0.45, size=n)

    tier = np.where(
        intensity > 12, "platinum",
        np.where(intensity > 6, "gold", np.where(intensity > 2.5, "silver", "none")),
    )

    ages = RNG.choice(AGE_BANDS, n, p=AGE_W)
    acqs = RNG.choice(ACQ, n, p=ACQ_W)
    genders = RNG.choice(np.array(["F", "M", "O"]), n, p=[0.49, 0.49, 0.02])

    buf = io.StringIO()
    for i in range(n):
        c, _ = CITIES[city_idx[i]]
        buf.write(
            f"{i + 1},{brand_id[i]},{signup[i]},{c},{ages[i]},"
            f"{genders[i]},{acqs[i]},{tier[i]}\n"
        )
    buf.seek(0)
    cur.copy_expert(
        "COPY customers (customer_id, brand_id, signup_date, city, age_band, gender,"
        " acquisition_channel, loyalty_tier) FROM STDIN WITH (FORMAT csv)",
        buf,
    )

    return dict(
        brand_id=brand_id,
        signup_off=signup_off,
        intensity=intensity,
        lifetime=lifetime,
        spend_mult=spend_mult,
    )


# ----------------------------------------------------------------------------- fact table
def build_orders(cur, cust, store_rows):
    """Baseline orders: a per-customer purchase sequence, truncated at lapse."""
    log(f"orders (target {TARGET_ORDERS:,})")

    n = N_CUSTOMERS
    stores_by_brand = {b[0]: [] for b in BRANDS}
    for sid, bid, *_ in store_rows:
        stores_by_brand[bid].append(sid)
    stores_by_brand = {k: np.array(v, dtype=np.int16) for k, v in stores_by_brand.items()}

    # Expected orders per customer, scaled so the run lands near TARGET_ORDERS.
    # Overshoot deliberately: seasonal rejection thins the result afterwards.
    raw = cust["intensity"] * (cust["lifetime"] / 90.0)
    scale = (TARGET_ORDERS * 1.63) / raw.sum()
    lam = raw * scale

    ticket = {b[0]: b[3] for b in BRANDS}
    order_id = 1
    written = 0

    for lo in range(0, n, CUST_CHUNK):
        hi = min(lo + CUST_CHUNK, n)
        idx = np.arange(lo, hi)

        n_orders = np.clip(RNG.poisson(lam[idx]), 0, 900)
        total = int(n_orders.sum())
        if total == 0:
            continue

        cust_row = np.repeat(idx, n_orders)
        cust_id = (cust_row + 1).astype(np.int64)

        # Purchase times: uniform across the customer's active window. Combined
        # with lognormal intensity and per-customer lifetime, this reproduces
        # retention decay without simulating each inter-purchase gap.
        span = np.repeat(cust["lifetime"][idx], n_orders)
        offs = np.repeat(cust["signup_off"][idx], n_orders)
        day = offs + (RNG.random(total) * span).astype(int)

        keep = day < N_DAYS
        cust_id, cust_row, day = cust_id[keep], cust_row[keep], day[keep]
        if len(day) == 0:
            continue

        dates = START_DAY + day.astype("timedelta64[D]")

        # Seasonal rejection: thin non-peak months so festivals stand out.
        w = seasonal_weight(dates)
        keep = RNG.random(len(w)) < (w / w.max())
        cust_id, cust_row, dates = cust_id[keep], cust_row[keep], dates[keep]
        if len(dates) == 0:
            continue

        order_id, count = _write_orders(
            cur, order_id, cust_id, cust_row, dates, cust, ticket, stores_by_brand
        )
        written += count
        if (lo // CUST_CHUNK) % 3 == 0:
            log(f"    {written:,}")

    log(f"    {written:,} baseline orders")
    return order_id, written


def _write_orders(cur, order_id, cust_id, cust_row, dates, cust, ticket, stores_by_brand):
    """Shared row-materialisation + COPY for baseline and campaign-driven orders."""
    brands = cust["brand_id"][cust_row]
    base = np.array([ticket[int(b)] for b in brands])
    amount = base * cust["spend_mult"][cust_row] * RNG.lognormal(0.0, 0.38, len(base))

    # Festival baskets are bigger, not merely more frequent.
    months = dates.astype("datetime64[M]").astype(int) % 12 + 1
    amount *= np.where(np.isin(months, [10, 11]), 1.22, 1.0)
    amount = np.round(amount, 2)

    items = np.clip(RNG.poisson(2.1, len(amount)) + 1, 1, 30).astype(np.int16)
    chans = RNG.choice(CHANNELS, len(amount), p=[0.58, 0.16, 0.26])

    store_ids = np.empty(len(amount), dtype=np.int16)
    for b, pool in stores_by_brand.items():
        m = brands == b
        if m.any():
            store_ids[m] = RNG.choice(pool, int(m.sum()))

    buf = io.StringIO()
    for i in range(len(amount)):
        buf.write(
            f"{order_id},{cust_id[i]},{store_ids[i]},{brands[i]},"
            f"{dates[i]},{chans[i]},{items[i]},{amount[i]}\n"
        )
        order_id += 1
    buf.seek(0)
    cur.copy_expert(
        "COPY orders (order_id, customer_id, store_id, brand_id, order_date,"
        " channel, items, amount) FROM STDIN WITH (FORMAT csv)",
        buf,
    )
    return order_id, len(amount)


# ----------------------------------------------------------------------------- campaigns
CAMPAIGN_PLAN = [
    # (type, label,             open rate, click rate, TRUE incremental lift)
    ("festival",      "Diwali Dhamaka",     0.42, 0.11, 0.085),
    ("festival",      "New Year Kickoff",   0.36, 0.09, 0.055),
    ("bogo",          "Buy One Get One",    0.31, 0.14, 0.110),
    ("loyalty_bonus", "2X Points Weekend",  0.48, 0.16, 0.070),
    # Deliberately dud campaigns: strong engagement, no incremental sales.
    ("winback",       "We Miss You",        0.44, 0.12, 0.004),
    ("bogo",          "Flash Sale Friday",  0.29, 0.10, 0.002),
]


def build_campaigns(cur):
    """Campaign definitions spread across brands and the three-year window."""
    log("campaigns")
    rows, meta = [], []
    cid = 1
    for year in (2023, 2024, 2025):
        for brand in range(1, len(BRANDS) + 1):
            for ctype, label, open_r, click_r, lift in CAMPAIGN_PLAN:
                if RNG.random() < 0.45:  # not every brand runs every campaign
                    continue
                month = int(RNG.integers(1, 13))
                start = np.datetime64(f"{year}-{month:02d}-01") + np.timedelta64(
                    int(RNG.integers(0, 18)), "D"
                )
                end = start + np.timedelta64(int(RNG.integers(7, 22)), "D")
                if start < START_DAY or end > END_DAY:
                    continue
                cost = float(np.round(RNG.uniform(40_000, 320_000), 2))
                chan = str(RNG.choice(SEND_CHANNELS, p=[0.34, 0.28, 0.38]))
                rows.append(
                    (cid, brand, f"{label} {year}", ctype, chan, str(start), str(end), cost)
                )
                meta.append(
                    dict(campaign_id=cid, brand_id=brand, start=start, end=end,
                         open_r=open_r, click_r=click_r, lift=lift)
                )
                cid += 1

    cur.executemany(
        "INSERT INTO campaigns (campaign_id, brand_id, campaign_name, campaign_type,"
        " channel, start_date, end_date, cost) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        rows,
    )
    log(f"    {len(rows)} campaigns")
    return meta


def build_campaign_sends(cur, camps, cust, store_rows, order_id):
    """
    Audience selection, holdout assignment, and the incremental orders the treated
    group actually generates. The lift is causal in the data: treated customers
    receive extra orders inside the campaign window, the holdout receives none.
    """
    log("campaign sends + incremental orders")

    stores_by_brand = {b[0]: [] for b in BRANDS}
    for sid, bid, *_ in store_rows:
        stores_by_brand[bid].append(sid)
    stores_by_brand = {k: np.array(v, dtype=np.int16) for k, v in stores_by_brand.items()}
    ticket = {b[0]: b[3] for b in BRANDS}

    brand_members = {
        b[0]: np.flatnonzero(cust["brand_id"] == b[0]) for b in BRANDS
    }

    send_id = 1
    n_sends = 0
    n_incr = 0

    for c in camps:
        pool = brand_members[c["brand_id"]]
        # Only customers who had signed up before the campaign ran.
        start_off = int((c["start"] - START_DAY) / np.timedelta64(1, "D"))
        eligible = pool[cust["signup_off"][pool] <= start_off]
        if len(eligible) < 500:
            continue

        size = min(len(eligible), int(RNG.integers(18_000, 55_000)))
        audience = RNG.choice(eligible, size, replace=False)

        holdout = RNG.random(size) < 0.15
        opened = RNG.random(size) < c["open_r"]
        clicked = opened & (RNG.random(size) < c["click_r"] / max(c["open_r"], 1e-6))

        buf = io.StringIO()
        for i in range(size):
            buf.write(
                f"{send_id},{c['campaign_id']},{audience[i] + 1},{c['start']},"
                f"{'t' if opened[i] else 'f'},{'t' if clicked[i] else 'f'},"
                f"{'t' if holdout[i] else 'f'}\n"
            )
            send_id += 1
        buf.seek(0)
        cur.copy_expert(
            "COPY campaign_sends (send_id, campaign_id, customer_id, sent_at,"
            " opened, clicked, is_holdout) FROM STDIN WITH (FORMAT csv)",
            buf,
        )
        n_sends += size

        # Incremental orders: treated only, and only among those who engaged.
        responds = (~holdout) & clicked & (RNG.random(size) < c["lift"] / 0.14)
        resp_rows = audience[responds]
        if len(resp_rows) == 0:
            continue

        window = max(int((c["end"] - c["start"]) / np.timedelta64(1, "D")), 1)
        offs = start_off + RNG.integers(0, window, len(resp_rows))
        dates = START_DAY + offs.astype("timedelta64[D]")

        order_id, count = _write_orders(
            cur, order_id, (resp_rows + 1).astype(np.int64), resp_rows, dates,
            cust, ticket, stores_by_brand,
        )
        n_incr += count

    log(f"    {n_sends:,} sends, {n_incr:,} campaign-driven orders")
    return n_sends, n_incr


# ----------------------------------------------------------------------------- main
def main():
    t0 = time.time()
    print(f"\nRetailMind generator -> {DSN}\n")

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor()

    schema = open(os.path.join(os.path.dirname(__file__), "..", "sql", "01_schema.sql")).read()
    log("applying schema")
    cur.execute(schema)
    conn.commit()

    store_rows = load_dimensions(cur)
    conn.commit()

    cust = build_customers(cur)
    conn.commit()

    camps = build_campaigns(cur)
    conn.commit()

    order_id, base_orders = build_orders(cur, cust, store_rows)
    conn.commit()

    sends, incr = build_campaign_sends(cur, camps, cust, store_rows, order_id)
    conn.commit()

    log("ANALYZE")
    conn.autocommit = True
    cur.execute("ANALYZE")

    cur.execute("SELECT count(*) FROM orders")
    total = cur.fetchone()[0]
    cur.execute("SELECT pg_size_pretty(pg_total_relation_size('orders'))")
    size = cur.fetchone()[0]

    print(
        f"\ndone in {time.time() - t0:.0f}s"
        f"\n  orders     {total:,}  ({size})"
        f"\n  baseline   {base_orders:,}"
        f"\n  campaign   {incr:,}"
        f"\n  sends      {sends:,}\n"
    )
    cur.close()
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
