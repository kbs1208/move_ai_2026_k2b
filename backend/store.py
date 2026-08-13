# CSV -> SQLite 적재(원본 테이블) + 실행 상태(스레드/딜/예약/추천) 영속화
# 참조 데이터 갱신이 필요하면 nego.db 삭제 후 재기동 (CSV에서 재적재)
import csv
import json
import sqlite3
import threading
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = Path(__file__).parent / "nego.db"
HISTORY_PATH = Path(__file__).parent / "history_emails.json"

# 요율표 코드 -> 스케줄/이메일 코드 통일 (ZET==KJ 에어제타, CV==C8 카고룩스)
CARRIER_ALIAS = {"ZET": "KJ", "CV": "C8"}

# 항공사별 AWB prefix 3자리 (IATA 코드 관례 + 가상 항공사는 임의 배정)
AWB_PREFIX = {"KE": "180", "DL": "006", "AA": "001", "5Y": "369", "KJ": "988", "MH": "232", "C8": "172"}

CSV_TABLES = {
    "order_lines": DATA_DIR / "KD 주문정보" / "KD_Orders.csv",
    "freight_rates": DATA_DIR / "항공사 가격표" / "Freight_Rates_KRW.csv",
    "surcharges": DATA_DIR / "항공사 가격표" / "Surcharge_Requested_KRW.csv",
    "schedules": DATA_DIR / "항공사 스케줄" / "flight_schedules_raw.csv",
    "contacts": DATA_DIR / "항공사 이메일" / "airline_email_info_final.csv",
}

STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads(thread_id TEXT PRIMARY KEY, live INTEGER, last_ts TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS deals(id INTEGER PRIMARY KEY AUTOINCREMENT, json TEXT);
CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS recommendations(order_no TEXT PRIMARY KEY, json TEXT);
CREATE TABLE IF NOT EXISTS order_status(order_no TEXT PRIMARY KEY, status TEXT);
"""


def connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db(con):
    cur = con.cursor()
    # CSV 원본 적재 (테이블 없을 때만)
    for table, path in CSV_TABLES.items():
        if cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            continue
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        cols = list(rows[0].keys())
        col_defs = ", ".join('"' + c + '" TEXT' for c in cols)
        cur.execute('CREATE TABLE "%s" (%s)' % (table, col_defs))
        cur.executemany('INSERT INTO "%s" VALUES (%s)' % (table, ",".join("?" * len(cols))),
                        [[r[c] for c in cols] for r in rows])
    cur.executescript(STATE_SCHEMA)
    # 메일/네고 이력은 초기 상태 비움 (과거 목데이터 시드 안 함 — 필요 시 seed_history.py 산출물 별도 적재)
    con.commit()


def rows_of(con, table):
    return [dict(r) for r in con.execute('SELECT * FROM "%s"' % table)]


# ---------- 파싱 (CSV/DB 공통: 문자열 row -> 도메인 구조) ----------

def parse_orders(rows, status_map):
    orders = {}
    for r in rows:
        o = orders.setdefault(r["order_no"], {
            "order_no": r["order_no"],
            "origin": r["origin_airport"],
            "dest": r["dest_airport"],
            "item_name": r["item_name"],
            "is_dg": False,  # 라인 중 하나라도 DG면 True (아래에서 OR)
            "cargo_ready_date": r["cargo_ready_date"],
            "desired_arr_date": r["desired_arr_date"],
            "deadline_date": r["deadline_date"],
            "status": status_map.get(r["order_no"], r["order_status"]),
            "pieces": 0, "gross_weight_kg": 0.0, "chargeable_weight_kg": 0.0,
            "size_cbm": 0.0, "max_height_cm": 0.0, "lines": [], "_items": [],
        })
        # 혼재 DG 주문: DG 라인이 하나라도 있으면 주문 전체가 화물기 제약 (동일 편 탑재)
        o["is_dg"] = o["is_dg"] or r["is_dg"] == "Y"
        if r["item_name"] not in o["_items"]:
            o["_items"].append(r["item_name"])
        o["pieces"] += int(r["piece"])
        o["gross_weight_kg"] += float(r["weight_kg"])
        o["chargeable_weight_kg"] += float(r["chargeable_weight_kg"])
        o["size_cbm"] += float(r["size_cbm"])
        o["max_height_cm"] = max(o["max_height_cm"], float(r["height"]))
        o["lines"].append({
            "item_name": r["item_name"], "is_dg": r["is_dg"] == "Y",
            "piece": int(r["piece"]), "weight_kg": float(r["weight_kg"]),
            "width": float(r["width"]), "length": float(r["lenght"]), "height": float(r["height"]),
            "cbm": float(r["size_cbm"]), "cw": float(r["chargeable_weight_kg"]),
        })
    for o in orders.values():
        o["gross_weight_kg"] = round(o["gross_weight_kg"], 2)
        o["chargeable_weight_kg"] = round(o["chargeable_weight_kg"], 2)
        o["size_cbm"] = round(o["size_cbm"], 2)
        items = o.pop("_items")
        o["item_name"] = items[0] if len(items) == 1 else f"{items[0]} 외 {len(items) - 1}건"
    return orders


def parse_rates(rows):
    for r in rows:
        for k in ("MIN", "N", "45", "100", "300", "500", "1000"):
            r[k] = float(r[k])
        r["carrier"] = CARRIER_ALIAS.get(r["CARRIER_CD"], r["CARRIER_CD"])
    return rows


def parse_surcharges(rows):
    for r in rows:
        r["FUEL_SURCHARGE_KG"] = float(r["FUEL_SURCHARGE_KG"])
        r["SEC_SURCHARGE_KG"] = float(r["SEC_SURCHARGE_KG"])
        # 항공사별 할증 (스케줄 코드로 통일)
        r["carrier"] = CARRIER_ALIAS.get(r["CARRIER_CD"], r["CARRIER_CD"])
    return rows


def parse_schedules(rows):
    for r in rows:
        r["carrier"] = r["flight_number"][:2]  # 편명 prefix == 항공사 코드 (KE, DL, AA, MH, 5Y, KJ, C8)
        r["ops"] = [int(r["op_" + d]) for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")]
    return rows


def parse_contacts(rows):
    return {r["항공사 코드"]: {"code": r["항공사 코드"], "airline": r["항공사명"],
                            "name": r["담당자 명"], "email": r["이메일"],
                            "awb_prefix": AWB_PREFIX.get(r["항공사 코드"], "000")} for r in rows}


class Store:
    def __init__(self):
        self.con = connect()
        self._lock = threading.Lock()
        init_db(self.con)
        # 참조 데이터 (DB -> 메모리, 도메인 코드는 기존 구조 그대로 사용)
        status_map = {r["order_no"]: r["status"] for r in rows_of(self.con, "order_status")}
        self.orders = parse_orders(rows_of(self.con, "order_lines"), status_map)
        self.rates = parse_rates(rows_of(self.con, "freight_rates"))
        self.surcharges = parse_surcharges(rows_of(self.con, "surcharges"))
        self.schedules = parse_schedules(rows_of(self.con, "schedules"))
        self.contacts = parse_contacts(rows_of(self.con, "contacts"))
        # 실행 상태 (영속)
        self.threads = [json.loads(r["json"]) for r in
                        self.con.execute("SELECT json FROM threads ORDER BY last_ts")]
        self.deals = [json.loads(r["json"]) for r in self.con.execute("SELECT json FROM deals")]
        self.bookings = [json.loads(r["json"]) for r in self.con.execute("SELECT json FROM bookings")]
        self.recommendations = {r["order_no"]: json.loads(r["json"]) for r in
                                self.con.execute("SELECT order_no, json FROM recommendations")}

    def next_id(self, prefix):
        return "%s-%s" % (prefix, uuid.uuid4().hex[:8])

    # ---------- 실행 상태 저장 ----------

    def save_thread(self, thread):
        with self._lock:
            self.con.execute("INSERT OR REPLACE INTO threads VALUES(?,?,?,?)",
                             (thread["thread_id"], 1 if thread.get("live") else 0,
                              thread["messages"][-1]["ts"] if thread["messages"] else "",
                              json.dumps(thread, ensure_ascii=False)))
            self.con.commit()

    def save_recommendation(self, order_no, rec):
        """추천 저장 + 상태 AWAITING (추천 도출 즉시, 확정 대기)."""
        self.recommendations[order_no] = rec
        self.orders[order_no]["status"] = "AWAITING"
        with self._lock:
            self.con.execute("INSERT OR REPLACE INTO recommendations VALUES(?,?)",
                             (order_no, json.dumps(rec, ensure_ascii=False)))
            self.con.execute("INSERT OR REPLACE INTO order_status VALUES(?,?)", (order_no, "AWAITING"))
            self.con.commit()

    def add_booking(self, rec):
        self.bookings.append(rec)
        self.orders[rec["order_no"]]["status"] = "BOOKED"
        with self._lock:
            self.con.execute("INSERT INTO bookings(order_no, json) VALUES(?,?)",
                             (rec["order_no"], json.dumps(rec, ensure_ascii=False)))
            self.con.execute("INSERT OR REPLACE INTO order_status VALUES(?,?)",
                             (rec["order_no"], "BOOKED"))
            self.con.commit()

    def cancel_booking(self, order_no):
        """예약 취소: 추천 정보까지 삭제하고 PENDING 복귀 (메일 이력은 유지)."""
        self.bookings = [b for b in self.bookings if b["order_no"] != order_no]
        self.recommendations.pop(order_no, None)
        self.orders[order_no]["status"] = "PENDING"
        with self._lock:
            self.con.execute("DELETE FROM bookings WHERE order_no=?", (order_no,))
            self.con.execute("DELETE FROM recommendations WHERE order_no=?", (order_no,))
            self.con.execute("INSERT OR REPLACE INTO order_status VALUES(?,?)", (order_no, "PENDING"))
            self.con.commit()


store = Store()
