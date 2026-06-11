"""
One-shot setup script.
Run once after `pip install -r requirements.txt`:

    python seed.py

Creates the SQLite DB, applies schema.sql, makes the admin user from .env,
and inserts a few demo listings derived from the real sample posts so the
public page has something to show on first run.
"""
import sqlite3
import sys
from pathlib import Path

import bcrypt

from config import Config
from db import init_schema

BASE_DIR = Path(__file__).resolve().parent


DEMO_HOUSES = [
    {
        "title": "坑口东港城上盖 五房合租 小巴15分钟直达科大",
        "price_hkd": 8000,
        "region": "新界",
        "district": "坑口",
        "address_detail": "东港城上盖",
        "room_type": "合租床位",
        "area_sqft": None,
        "near_university": "HKUST",
        "mtr_station": "坑口",
        "transport_info": "楼下小巴站，15分钟直达科大校园；港铁坑口站步行3分钟",
        "description": (
            "科大内地生专属合租房！位于坑口东港城商场上盖，下楼即大型商场、超市、餐厅全齐，"
            "5分钟到菜市场，做饭超方便。\n\n"
            "🏠 五房两厕，室友均为内地生，空间宽敞不挤迫\n"
            "🍳 大厨房 + 全屋家电（冰箱/洗衣机/干衣机/饮水机）\n"
            "🧴 沐浴露、洗衣珠、卫生纸全部备好，拎包入住\n"
            "💰 月租 HK$8000 起，一价全包（水电煤气网络地租地税）\n"
            "💸 介绍朋友入住即送 HK$300 现金奖励\n\n"
            "房东直租，无中介费，名额有限，手慢无！"
        ),
        "deposit_months": 2,
        "min_lease_months": 12,
        "agency_fee": "无中介费",
        "bills_included": 1,
        "contact_wechat": "Jason1201703",
        "contact_whatsapp": "+85264632608",
        "status": "在租",
        "tags": ["无中介费", "一价全包", "包水电网煤", "近港铁", "科大专线", "学生合租", "拎包入住"],
        "images": [
            "https://picsum.photos/seed/hkust1/800/600",
            "https://picsum.photos/seed/hkust2/800/600",
            "https://picsum.photos/seed/hkust3/800/600",
        ],
    },
    {
        "title": "九龙塘 单间 全屋家电 早8-10校巴送学",
        "price_hkd": 8000,
        "region": "九龙",
        "district": "九龙塘",
        "address_detail": "九龙塘住宅区",
        "room_type": "单间",
        "area_sqft": None,
        "near_university": "CityU",
        "mtr_station": "九龙塘",
        "transport_info": "早 8:00-10:00 专车送上学；九龙塘港铁站可达多所大学",
        "description": (
            "九龙塘性价比单间，全屋公共区域配齐家电：洗衣机、干衣机、雪柜、煤气炉。\n\n"
            "✅ 水电网煤气全包\n"
            "✅ 每天早 8 至 10 点专车送上学\n"
            "✅ 12 个月起租，两个月按金，半个月中介费\n\n"
            "适合九龙塘片区上学的内地生，安静、生活方便。"
        ),
        "deposit_months": 2,
        "min_lease_months": 12,
        "agency_fee": "半个月",
        "bills_included": 1,
        "contact_wechat": "",
        "contact_whatsapp": "+85290000000",
        "status": "在租",
        "tags": ["全屋家电", "包水电网煤", "校巴送学", "学生合租"],
        "images": [
            "https://picsum.photos/seed/kln1/800/600",
            "https://picsum.photos/seed/kln2/800/600",
        ],
    },
    {
        "title": "坚尼地城 港大旁 独立卫浴单间",
        "price_hkd": 7800,
        "region": "港岛",
        "district": "坚尼地城",
        "address_detail": "西宝城旁",
        "room_type": "单间",
        "area_sqft": 120,
        "near_university": "HKU",
        "mtr_station": "坚尼地城",
        "transport_info": "港铁坚尼地城站 A 出口步行 3 分钟；步行 8 分钟到港大",
        "description": (
            "降价急租！坚尼地城西宝城旁独立卫浴单间，步行可达港大校园。\n\n"
            "🛁 独立卫浴，私密性高\n"
            "🚇 港铁 A 出口 3 分钟，回校园不挤地铁\n"
            "🛒 楼下西宝城商场，超市餐厅一应俱全\n"
            "📚 港大同学首选位置"
        ),
        "deposit_months": 2,
        "min_lease_months": 12,
        "agency_fee": "无中介费",
        "bills_included": 0,
        "contact_wechat": "hku_rent",
        "contact_whatsapp": "+85261111111",
        "status": "在租",
        "tags": ["独立卫浴", "近港铁", "港大专线", "无中介费", "降价急租"],
        "images": [
            "https://picsum.photos/seed/hku1/800/600",
            "https://picsum.photos/seed/hku2/800/600",
            "https://picsum.photos/seed/hku3/800/600",
        ],
    },
    {
        "title": "大围名城 两室一厅 中大同学首选",
        "price_hkd": 14500,
        "region": "新界",
        "district": "大围",
        "address_detail": "名城 (Festival City)",
        "room_type": "两房",
        "area_sqft": 480,
        "near_university": "CUHK",
        "mtr_station": "大围",
        "transport_info": "大围港铁站步行 3 分钟；2 站直达中大",
        "description": (
            "大围名城两室一厅，全新装修，楼下大型商场、超市、餐厅齐备。\n\n"
            "🏙 高层景观房\n"
            "🛏 两间睡房均可放双人床\n"
            "🚇 大围港铁站直达，2 站到中大\n"
            "🎓 适合中大研究生 / 内地访问学者合租"
        ),
        "deposit_months": 2,
        "min_lease_months": 12,
        "agency_fee": "半个月",
        "bills_included": 0,
        "contact_wechat": "cuhk_rent",
        "contact_whatsapp": "+85262222222",
        "status": "在租",
        "tags": ["近港铁", "中大专线", "全新装修", "景观房"],
        "images": [
            "https://picsum.photos/seed/cuhk1/800/600",
            "https://picsum.photos/seed/cuhk2/800/600",
        ],
    },
    {
        "title": "红磡海韵轩 单间 步行可达理大",
        "price_hkd": 5500,
        "region": "九龙",
        "district": "红磡",
        "address_detail": "海韵轩",
        "room_type": "单间",
        "area_sqft": None,
        "near_university": "PolyU",
        "mtr_station": "黄埔",
        "transport_info": "黄埔港铁站步行 5 分钟；步行 8 分钟到理工大学",
        "description": (
            "红磡海韵轩单间，理大同学专属价位！\n\n"
            "✅ 步行可达理大主校园\n"
            "✅ 楼下黄埔花园商场，生活方便\n"
            "✅ 全屋包水电网\n"
            "✅ 房东直租"
        ),
        "deposit_months": 2,
        "min_lease_months": 12,
        "agency_fee": "无中介费",
        "bills_included": 1,
        "contact_wechat": "polyu_rent",
        "contact_whatsapp": "+85263333333",
        "status": "在租",
        "tags": ["近港铁", "理大专线", "包水电网煤", "无中介费"],
        "images": [
            "https://picsum.photos/seed/polyu1/800/600",
            "https://picsum.photos/seed/polyu2/800/600",
        ],
    },
    {
        "title": "日出康城 首都海景两房 全新装修",
        "price_hkd": 14500,
        "region": "新界",
        "district": "日出康城",
        "address_detail": "首都 (Capitol)",
        "room_type": "两房",
        "area_sqft": 520,
        "near_university": "无",
        "mtr_station": "康城",
        "transport_info": "港铁康城站直达；可换乘到科大区域",
        "description": (
            "日出康城首都两房，正海景！全新装修，会所设施齐全。\n\n"
            "🌊 海景客厅 + 主睡房海景\n"
            "🏊 大型会所：泳池、健身房、儿童乐园\n"
            "🛒 楼下 PopCorn 商场\n"
            "🚇 康城港铁站直达"
        ),
        "deposit_months": 2,
        "min_lease_months": 12,
        "agency_fee": "半个月",
        "bills_included": 0,
        "contact_wechat": "tko_rent",
        "contact_whatsapp": "+85264444444",
        "status": "在租",
        "tags": ["海景房", "全新装修", "近港铁", "会所设施"],
        "images": [
            "https://picsum.photos/seed/lohas1/800/600",
            "https://picsum.photos/seed/lohas2/800/600",
            "https://picsum.photos/seed/lohas3/800/600",
        ],
    },
]


def upsert_admin(conn: sqlite3.Connection):
    username = Config.ADMIN_USERNAME
    password = Config.ADMIN_PASSWORD
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    cur = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if row:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (pw_hash, username),
        )
        print(f"  • Admin user '{username}' already existed — password reset from .env")
    else:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
            (username, pw_hash, "管理员"),
        )
        print(f"  • Created admin user '{username}'")


def insert_demo_houses(conn: sqlite3.Connection):
    cur = conn.execute("SELECT COUNT(*) AS c FROM houses")
    if cur.fetchone()["c"] > 0:
        print("  • Houses already exist — skipping demo data")
        return

    for h in DEMO_HOUSES:
        cur = conn.execute(
            """
            INSERT INTO houses (
                title, price_hkd, region, district, address_detail, room_type, area_sqft,
                near_university, mtr_station, transport_info, description,
                deposit_months, min_lease_months, agency_fee, bills_included,
                contact_wechat, contact_whatsapp, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                h["title"], h["price_hkd"], h["region"], h["district"], h["address_detail"],
                h["room_type"], h["area_sqft"], h["near_university"], h["mtr_station"],
                h["transport_info"], h["description"], h["deposit_months"], h["min_lease_months"],
                h["agency_fee"], h["bills_included"], h["contact_wechat"], h["contact_whatsapp"],
                h["status"],
            ),
        )
        house_id = cur.lastrowid

        for tag in h["tags"]:
            conn.execute(
                "INSERT INTO house_tags (house_id, tag) VALUES (?, ?)",
                (house_id, tag),
            )

        for i, url in enumerate(h["images"]):
            conn.execute(
                "INSERT INTO house_images (house_id, url, sort_order) VALUES (?, ?, ?)",
                (house_id, url, i),
            )

    print(f"  • Inserted {len(DEMO_HOUSES)} demo listings")


def main():
    row_factory = sqlite3.Row
    print("🏗  Initializing database…")
    init_schema(Config.DATABASE_PATH, str(BASE_DIR / "schema.sql"))

    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = row_factory
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        upsert_admin(conn)
        insert_demo_houses(conn)
        conn.commit()
    finally:
        conn.close()

    print("✅  Done. Run `python app.py` and visit http://localhost:5000")


if __name__ == "__main__":
    sys.exit(main())
