from flask import Blueprint, render_template, request, abort

from db import get_db

bp = Blueprint("public", __name__)

REGIONS = ["港岛", "九龙", "新界", "离岛"]
ROOM_TYPES = ["单间", "开放式", "一房", "两房", "三房+", "合租床位"]
UNIVERSITIES = ["HKU", "CUHK", "HKUST", "PolyU", "CityU", "BU"]

PRICE_BUCKETS = [
    ("any", "不限"),
    ("0-6000", "6,000 以下"),
    ("6000-10000", "6,000 – 10,000"),
    ("10000-15000", "10,000 – 15,000"),
    ("15000-25000", "15,000 – 25,000"),
    ("25000-", "25,000 以上"),
]


def _parse_price_range(bucket: str):
    if not bucket or bucket == "any":
        return None, None
    parts = bucket.split("-")
    lo = int(parts[0]) if parts[0] else None
    hi = int(parts[1]) if len(parts) > 1 and parts[1] else None
    return lo, hi


def _load_houses(filters: dict):
    db = get_db()
    sql = ["SELECT * FROM houses WHERE status = '在租'"]
    params = []

    if filters.get("region") and filters["region"] != "all":
        sql.append("AND region = ?")
        params.append(filters["region"])

    if filters.get("room_type") and filters["room_type"] != "all":
        sql.append("AND room_type = ?")
        params.append(filters["room_type"])

    if filters.get("university") and filters["university"] != "all":
        sql.append("AND near_university = ?")
        params.append(filters["university"])

    lo, hi = _parse_price_range(filters.get("price", "any"))
    if lo is not None:
        sql.append("AND price_hkd >= ?")
        params.append(lo)
    if hi is not None:
        sql.append("AND price_hkd <= ?")
        params.append(hi)

    q = (filters.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        sql.append("AND (title LIKE ? OR district LIKE ? OR mtr_station LIKE ? OR description LIKE ?)")
        params.extend([like, like, like, like])

    sql.append("ORDER BY created_at DESC")
    houses = db.execute(" ".join(sql), params).fetchall()

    if not houses:
        return []

    ids = [h["id"] for h in houses]
    placeholders = ",".join(["?"] * len(ids))

    tag_rows = db.execute(
        f"SELECT house_id, tag FROM house_tags WHERE house_id IN ({placeholders})", ids
    ).fetchall()
    tags_by_house = {}
    for r in tag_rows:
        tags_by_house.setdefault(r["house_id"], []).append(r["tag"])

    image_rows = db.execute(
        f"SELECT house_id, url FROM house_images WHERE house_id IN ({placeholders}) ORDER BY sort_order",
        ids,
    ).fetchall()
    cover_by_house = {}
    for r in image_rows:
        cover_by_house.setdefault(r["house_id"], r["url"])

    result = []
    for h in houses:
        d = dict(h)
        d["tags"] = tags_by_house.get(h["id"], [])
        d["cover_image"] = cover_by_house.get(h["id"]) or "https://picsum.photos/seed/default/800/600"
        result.append(d)
    return result


def _load_house_detail(house_id: int):
    db = get_db()
    house = db.execute("SELECT * FROM houses WHERE id = ?", (house_id,)).fetchone()
    if not house:
        return None
    tags = [r["tag"] for r in db.execute(
        "SELECT tag FROM house_tags WHERE house_id = ? ORDER BY tag", (house_id,)
    ).fetchall()]
    images = [dict(r) for r in db.execute(
        "SELECT * FROM house_images WHERE house_id = ? ORDER BY sort_order", (house_id,)
    ).fetchall()]
    d = dict(house)
    d["tags"] = tags
    d["images"] = images
    return d


@bp.route("/")
def index():
    filters = {
        "q": request.args.get("q", ""),
        "region": request.args.get("region", "all"),
        "room_type": request.args.get("room_type", "all"),
        "university": request.args.get("university", "all"),
        "price": request.args.get("price", "any"),
    }
    houses = _load_houses(filters)
    return render_template(
        "public/index.html",
        houses=houses,
        filters=filters,
        regions=REGIONS,
        room_types=ROOM_TYPES,
        universities=UNIVERSITIES,
        price_buckets=PRICE_BUCKETS,
    )


@bp.route("/house/<int:house_id>")
def house_detail(house_id):
    house = _load_house_detail(house_id)
    if not house:
        abort(404)
    return render_template("public/detail.html", house=house)
