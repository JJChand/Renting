PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    display_name    TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS houses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT NOT NULL,
    price_hkd        INTEGER NOT NULL,
    region           TEXT NOT NULL,           -- 港岛 / 九龙 / 新界 / 离岛
    district         TEXT NOT NULL,           -- 坑口, 九龙塘, 红磡, ...
    address_detail   TEXT,                    -- 屋苑/楼宇名
    room_type        TEXT NOT NULL,           -- 单间 / 开放式 / 一房 / 两房 / 三房+ / 合租床位
    area_sqft        INTEGER,
    near_university  TEXT,                    -- HKU / CUHK / HKUST / PolyU / CityU / BU / 无
    mtr_station      TEXT,
    transport_info   TEXT,                    -- 自由文字，例如「小巴15分钟到科大」
    description      TEXT NOT NULL,
    deposit_months   INTEGER DEFAULT 2,
    min_lease_months INTEGER DEFAULT 12,
    agency_fee       TEXT DEFAULT '无中介费',  -- 无中介费 / 半个月 / 一个月
    bills_included   INTEGER DEFAULT 0,        -- boolean: 0/1
    contact_wechat   TEXT,
    contact_whatsapp TEXT,
    status           TEXT NOT NULL DEFAULT '在租',  -- 在租 / 已租出 / 下架
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_houses_status     ON houses(status);
CREATE INDEX IF NOT EXISTS idx_houses_region     ON houses(region);
CREATE INDEX IF NOT EXISTS idx_houses_university ON houses(near_university);
CREATE INDEX IF NOT EXISTS idx_houses_price      ON houses(price_hkd);

CREATE TABLE IF NOT EXISTS house_tags (
    house_id  INTEGER NOT NULL,
    tag       TEXT NOT NULL,
    PRIMARY KEY (house_id, tag),
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tags_house ON house_tags(house_id);

CREATE TABLE IF NOT EXISTS house_images (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    house_id   INTEGER NOT NULL,
    url        TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    alt_text   TEXT,
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_images_house ON house_images(house_id, sort_order);
