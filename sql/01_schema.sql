-- RetailMind :: schema
--
-- NOTE ON INDEXES: this schema deliberately ships with NOTHING but primary keys.
-- That is the "before" state. Every index in 03_optimize.sql was added because a
-- real query was measured, found slow, and diagnosed -- not guessed at up front.
-- The Query Lab shows the plan before and after each one.

DROP TABLE IF EXISTS campaign_sends, campaigns, orders, customers, stores, brands CASCADE;

CREATE TABLE brands (
    brand_id    smallint PRIMARY KEY,
    brand_name  text NOT NULL,
    category    text NOT NULL,             -- QSR / Apparel / Beauty / Cafe
    avg_ticket  numeric(10,2) NOT NULL
);

CREATE TABLE stores (
    store_id    smallint PRIMARY KEY,
    brand_id    smallint NOT NULL REFERENCES brands(brand_id),
    store_name  text NOT NULL,
    city        text NOT NULL,
    region      text NOT NULL,             -- North / South / East / West
    opened_date date NOT NULL
);

CREATE TABLE customers (
    customer_id         integer PRIMARY KEY,
    brand_id            smallint NOT NULL REFERENCES brands(brand_id),
    signup_date         date NOT NULL,
    city                text NOT NULL,
    age_band            text NOT NULL,     -- 18-24 / 25-34 / 35-44 / 45-54 / 55+
    gender              char(1) NOT NULL,
    acquisition_channel text NOT NULL,     -- store / instagram / google / referral / app
    loyalty_tier        text NOT NULL      -- none / silver / gold / platinum
);

-- The fact table. No foreign keys: bulk loads stay fast, and an unindexed join
-- column is one of the lessons in the Query Lab.
CREATE TABLE orders (
    order_id    bigint PRIMARY KEY,
    customer_id integer NOT NULL,
    store_id    smallint NOT NULL,
    brand_id    smallint NOT NULL,
    order_date  date NOT NULL,
    channel     text NOT NULL,             -- store / web / app
    items       smallint NOT NULL,
    amount      numeric(10,2) NOT NULL
);

CREATE TABLE campaigns (
    campaign_id   smallint PRIMARY KEY,
    brand_id      smallint NOT NULL REFERENCES brands(brand_id),
    campaign_name text NOT NULL,
    campaign_type text NOT NULL,           -- festival / bogo / loyalty_bonus / winback
    channel       text NOT NULL,           -- sms / email / whatsapp
    start_date    date NOT NULL,
    end_date      date NOT NULL,
    cost          numeric(12,2) NOT NULL
);

-- Every campaign holds out a random slice of its audience. Without a holdout you
-- can only measure response; with one you can measure incremental lift, which is
-- the only number that tells you whether the campaign actually made money.
CREATE TABLE campaign_sends (
    send_id     bigint PRIMARY KEY,
    campaign_id smallint NOT NULL,
    customer_id integer NOT NULL,
    sent_at     date NOT NULL,
    opened      boolean NOT NULL,
    clicked     boolean NOT NULL,
    is_holdout  boolean NOT NULL
);
