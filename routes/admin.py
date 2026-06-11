from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, abort, jsonify, current_app
)
from flask_login import login_required

from db import get_db
from storage import upload_image, delete_image, is_allowed

bp = Blueprint("admin", __name__)

REGIONS = ["港岛", "九龙", "新界", "离岛"]

DISTRICTS_BY_REGION = {
    "港岛": ["中环", "上环", "西环", "坚尼地城", "湾仔", "铜锣湾", "天后", "北角", "鲗鱼涌", "太古", "西湾河", "筲箕湾", "柴湾", "杏花邨", "薄扶林", "香港仔", "鸭脷洲"],
    "九龙": ["尖沙咀", "佐敦", "油麻地", "旺角", "太子", "深水埗", "长沙湾", "美孚", "九龙塘", "石硖尾", "红磡", "土瓜湾", "何文田", "黄大仙", "九龙湾", "牛头角", "观塘", "蓝田", "油塘"],
    "新界": ["荃湾", "葵芳", "青衣", "沙田", "大围", "马鞍山", "大埔", "粉岭", "上水", "屯门", "元朗", "天水围", "将军澳", "坑口", "日出康城", "调景岭", "西贡", "清水湾"],
    "离岛": ["东涌", "愉景湾", "梅窝", "长洲", "南丫岛", "坪洲"],
}

ROOM_TYPES = ["单间", "开放式", "一房", "两房", "三房+", "合租床位"]
UNIVERSITIES = ["HKU", "CUHK", "HKUST", "PolyU", "CityU", "BU", "无"]
AGENCY_FEES = ["无中介费", "半个月", "一个月"]
STATUSES = ["在租", "已租出", "下架"]

COMMON_TAGS = [
    "无中介费", "一价全包", "包水电网煤", "独立卫浴", "近港铁",
    "校巴送学", "全屋家电", "全新装修", "拎包入住", "海景房",
    "景观房", "会所设施", "学生合租", "港大专线", "中大专线",
    "科大专线", "理大专线", "城大专线", "降价急租",
]


def _load_house_full(house_id: int):
    db = get_db()
    house = db.execute("SELECT * FROM houses WHERE id = ?", (house_id,)).fetchone()
    if not house:
        return None
    tags = [r["tag"] for r in db.execute(
        "SELECT tag FROM house_tags WHERE house_id = ?", (house_id,)
    ).fetchall()]
    images = [dict(r) for r in db.execute(
        "SELECT * FROM house_images WHERE house_id = ? ORDER BY sort_order", (house_id,)
    ).fetchall()]
    d = dict(house)
    d["tags"] = tags
    d["images"] = images
    return d


def _form_choices():
    return {
        "regions": REGIONS,
        "districts_by_region": DISTRICTS_BY_REGION,
        "room_types": ROOM_TYPES,
        "universities": UNIVERSITIES,
        "agency_fees": AGENCY_FEES,
        "statuses": STATUSES,
        "common_tags": COMMON_TAGS,
    }


def _parse_form(form):
    """Pull values from request.form into a dict matching the houses schema."""
    def s(name, default=""):
        return (form.get(name, default) or "").strip()

    def i(name, default=None):
        raw = form.get(name)
        if raw is None or raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    return {
        "title": s("title"),
        "price_hkd": i("price_hkd", 0),
        "region": s("region"),
        "district": s("district"),
        "address_detail": s("address_detail"),
        "room_type": s("room_type"),
        "area_sqft": i("area_sqft"),
        "near_university": s("near_university") or "无",
        "mtr_station": s("mtr_station"),
        "transport_info": s("transport_info"),
        "description": s("description"),
        "deposit_months": i("deposit_months", 2),
        "min_lease_months": i("min_lease_months", 12),
        "agency_fee": s("agency_fee") or "无中介费",
        "bills_included": 1 if form.get("bills_included") in ("on", "1", "true") else 0,
        "contact_wechat": s("contact_wechat"),
        "contact_whatsapp": s("contact_whatsapp"),
        "status": s("status") or "在租",
    }


def _validate(data):
    errors = {}
    if not data["title"]:                  errors["title"]    = "请填写标题"
    if not data["price_hkd"] or data["price_hkd"] <= 0: errors["price_hkd"] = "请设定月租金额"
    if data["region"] not in REGIONS:      errors["region"]   = "请选择区域"
    if not data["district"]:               errors["district"] = "请填写所在地区"
    if data["room_type"] not in ROOM_TYPES: errors["room_type"] = "请选择房型"
    if not data["description"]:            errors["description"] = "请填写房源介绍"
    if not (data["contact_wechat"] or data["contact_whatsapp"]):
        errors["contact"] = "微信或 WhatsApp 至少留一个联系方式"
    return errors


@bp.route("/")
@login_required
def dashboard():
    db = get_db()
    rows = db.execute("""
        SELECT h.*, (
            SELECT url FROM house_images WHERE house_id = h.id ORDER BY sort_order LIMIT 1
        ) AS cover
        FROM houses h
        ORDER BY h.created_at DESC
    """).fetchall()
    houses = [dict(r) for r in rows]
    return render_template("admin/dashboard.html", houses=houses)


@bp.route("/houses/new", methods=["GET", "POST"])
@login_required
def new_house():
    if request.method == "POST":
        return _handle_house_save(house_id=None)

    return render_template(
        "admin/house_form.html",
        mode="new",
        house=None,
        selected_tags=set(),
        existing_images=[],
        errors={},
        choices=_form_choices(),
    )


@bp.route("/houses/<int:house_id>/edit", methods=["GET", "POST"])
@login_required
def edit_house(house_id):
    house = _load_house_full(house_id)
    if not house:
        abort(404)

    if request.method == "POST":
        return _handle_house_save(house_id=house_id)

    return render_template(
        "admin/house_form.html",
        mode="edit",
        house=house,
        selected_tags=set(house["tags"]),
        existing_images=house["images"],
        errors={},
        choices=_form_choices(),
    )


def _handle_house_save(house_id):
    db = get_db()
    data = _parse_form(request.form)
    errors = _validate(data)

    if errors:
        flash("表单有 " + str(len(errors)) + " 处需要修正", "error")
        existing_images = []
        if house_id:
            existing_images = [dict(r) for r in db.execute(
                "SELECT * FROM house_images WHERE house_id = ? ORDER BY sort_order", (house_id,)
            ).fetchall()]
        return render_template(
            "admin/house_form.html",
            mode="edit" if house_id else "new",
            house={**data, "id": house_id},
            selected_tags=set(request.form.getlist("tags")),
            existing_images=existing_images,
            errors=errors,
            choices=_form_choices(),
        ), 400

    now = datetime.utcnow().isoformat(timespec="seconds")
    if house_id:
        db.execute("""
            UPDATE houses SET
                title=?, price_hkd=?, region=?, district=?, address_detail=?, room_type=?, area_sqft=?,
                near_university=?, mtr_station=?, transport_info=?, description=?,
                deposit_months=?, min_lease_months=?, agency_fee=?, bills_included=?,
                contact_wechat=?, contact_whatsapp=?, status=?, updated_at=?
            WHERE id=?
        """, (
            data["title"], data["price_hkd"], data["region"], data["district"], data["address_detail"],
            data["room_type"], data["area_sqft"], data["near_university"], data["mtr_station"],
            data["transport_info"], data["description"], data["deposit_months"], data["min_lease_months"],
            data["agency_fee"], data["bills_included"], data["contact_wechat"], data["contact_whatsapp"],
            data["status"], now, house_id,
        ))
    else:
        cur = db.execute("""
            INSERT INTO houses (
                title, price_hkd, region, district, address_detail, room_type, area_sqft,
                near_university, mtr_station, transport_info, description,
                deposit_months, min_lease_months, agency_fee, bills_included,
                contact_wechat, contact_whatsapp, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["title"], data["price_hkd"], data["region"], data["district"], data["address_detail"],
            data["room_type"], data["area_sqft"], data["near_university"], data["mtr_station"],
            data["transport_info"], data["description"], data["deposit_months"], data["min_lease_months"],
            data["agency_fee"], data["bills_included"], data["contact_wechat"], data["contact_whatsapp"],
            data["status"],
        ))
        house_id = cur.lastrowid

    db.execute("DELETE FROM house_tags WHERE house_id = ?", (house_id,))
    for tag in request.form.getlist("tags"):
        tag = tag.strip()
        if tag:
            db.execute(
                "INSERT OR IGNORE INTO house_tags (house_id, tag) VALUES (?, ?)",
                (house_id, tag),
            )

    keep_urls = set(request.form.getlist("keep_image_urls"))
    if keep_urls:
        existing = db.execute(
            "SELECT id, url FROM house_images WHERE house_id = ?", (house_id,)
        ).fetchall()
        for row in existing:
            if row["url"] not in keep_urls:
                db.execute("DELETE FROM house_images WHERE id = ?", (row["id"],))
                delete_image(row["url"])
    else:
        old = db.execute("SELECT url FROM house_images WHERE house_id = ?", (house_id,)).fetchall()
        db.execute("DELETE FROM house_images WHERE house_id = ?", (house_id,))
        for row in old:
            delete_image(row["url"])

    new_urls = request.form.getlist("new_image_urls")
    if new_urls:
        cur = db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) AS m FROM house_images WHERE house_id = ?",
            (house_id,),
        )
        next_order = cur.fetchone()["m"] + 1
        for url in new_urls:
            if url.strip():
                db.execute(
                    "INSERT INTO house_images (house_id, url, sort_order) VALUES (?, ?, ?)",
                    (house_id, url.strip(), next_order),
                )
                next_order += 1

    db.commit()
    flash("房源已保存", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/houses/<int:house_id>/status", methods=["POST"])
@login_required
def update_status(house_id):
    new_status = request.form.get("status", "").strip()
    if new_status not in STATUSES:
        abort(400)
    db = get_db()
    db.execute("UPDATE houses SET status = ?, updated_at = ? WHERE id = ?",
               (new_status, datetime.utcnow().isoformat(timespec="seconds"), house_id))
    db.commit()
    flash(f"房源状态已更新为 {new_status}", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/houses/<int:house_id>/delete", methods=["POST"])
@login_required
def delete_house(house_id):
    db = get_db()
    images = db.execute("SELECT url FROM house_images WHERE house_id = ?", (house_id,)).fetchall()
    db.execute("DELETE FROM houses WHERE id = ?", (house_id,))
    db.commit()
    for row in images:
        delete_image(row["url"])
    flash("房源已删除", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/upload", methods=["POST"])
@login_required
def upload():
    """AJAX endpoint called by the form's drag-drop uploader. Returns JSON with the public URL."""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "未选择文件"}), 400
    if not is_allowed(file.filename):
        allowed = ", ".join(sorted(current_app.config["ALLOWED_IMAGE_EXTENSIONS"]))
        return jsonify({"error": f"仅支持 {allowed} 格式"}), 400
    try:
        url = upload_image(file)
    except Exception as e:
        current_app.logger.exception("upload failed")
        return jsonify({"error": f"上传失败：{e}"}), 500
    return jsonify({"url": url})
