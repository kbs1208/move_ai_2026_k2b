# FastAPI 앱: REST + SSE (에이전트 실행 스트림)
import json
import random
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent import GLOVIS, _now, run_agent
from domain import TODAY, GROUND_HOURS, find_candidates
from store import AWB_PREFIX, store

app = FastAPI(title="Air Cargo Nego Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/meta")
def meta():
    return {"today": TODAY.isoformat(), "ground_hours": GROUND_HOURS,
            "glovis": "현대글로비스 항공수입팀 김글로 매니저 <kim.glovis@glovis.com>"}


@app.get("/api/orders")
def orders():
    # 저장된 추천(영속) + 확정 AWB 포함
    awbs = {b["order_no"]: b.get("awb") for b in store.bookings}
    return [{**o, "recommendation": store.recommendations.get(no), "awb": awbs.get(no)}
            for no, o in store.orders.items()]


@app.get("/api/rates")
def rates():
    return {"rates": store.rates, "surcharges": store.surcharges}


@app.get("/api/schedules")
def schedules():
    return store.schedules


@app.get("/api/contacts")
def contacts():
    return list(store.contacts.values())


@app.get("/api/orders/{order_no}/candidates")
def candidates(order_no: str):
    if order_no not in store.orders:
        raise HTTPException(404)
    return find_candidates(store, store.orders[order_no])


@app.get("/api/agent/run")
def agent_run(order_no: str):
    if order_no not in store.orders:
        raise HTTPException(404)

    def stream():
        try:
            for ev in run_agent(store, order_no):
                # 실행 결과 영속화: 메일 스레드 / 추천
                if ev["type"] == "email":
                    store.save_thread(ev["thread"])
                elif ev["type"] == "recommendation":
                    store.save_recommendation(order_no, ev["recommendation"])
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # 데모 중단 방지: 에러도 이벤트로
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/bookings")
def book(rec: dict):
    order_no = rec.get("order_no")
    if order_no not in store.orders:
        raise HTTPException(404)
    # AWB 채번: 항공사 prefix 3자리 + 시리얼 7자리 + 체크디짓 1자리 (mod 7) = 총 11자리
    serial = random.randint(0, 9999999)
    awb = f"{AWB_PREFIX.get(rec.get('carrier'), '000')}-{serial:07d}{serial % 7}"
    rec["awb"] = awb
    store.add_booking(rec)  # DB 영속화 + 주문 상태 BOOKED
    # AWB 회신 메일: 글로비스 -> 항공사 (네고 스레드에 이어서 저장)
    thread = next((t for t in reversed(store.threads)
                   if t.get("order_no") == order_no and t.get("carrier") == rec.get("carrier")), None)
    if thread:
        contact = store.contacts.get(rec["carrier"], {})
        thread["messages"].append({
            "from": GLOVIS["email"], "from_name": GLOVIS["name"],
            "to": contact.get("email", ""), "ts": _now(), "direction": "out",
            "body": (f"안녕하세요, {contact.get('name', '담당자')}님. {GLOVIS['team']} {GLOVIS['name']}입니다.\n"
                     f"협의드린 조건(kg당 {rec.get('rate_per_kg', 0):,}원, {rec.get('flight_number', '')} "
                     f"{rec.get('dep_date', '')} 출발)으로 예약을 확정합니다.\n"
                     f"당사 시스템에 예약한 AWB 번호는 {awb} 입니다. 부킹 확정 처리 부탁드립니다.\n"
                     f"감사합니다."),
        })
        store.save_thread(thread)
    return {"ok": True, "order_no": order_no, "awb": awb}


@app.delete("/api/bookings/{order_no}")
def cancel(order_no: str):
    if order_no not in store.orders:
        raise HTTPException(404)
    store.cancel_booking(order_no)  # DB 영속화 + 주문 상태 PENDING 복귀
    return {"ok": True, "order_no": order_no}


@app.get("/api/emails")
def emails():
    def last_ts(t):
        return t["messages"][-1]["ts"] if t["messages"] else ""
    return sorted(store.threads, key=last_ts, reverse=True)


@app.get("/api/dashboard")
def dashboard():
    # 과거 합의(deals) + 이번 세션 예약(bookings) 통합 집계
    rows = []
    for dl in store.deals:
        rows.append({"date": dl["date"], "order_no": dl.get("order_no", "-"), "carrier": dl["carrier"],
                     "airline": store.contacts.get(dl["carrier"], {}).get("airline", dl["carrier"]),
                     "flight": dl["flight_number"], "dest": dl["dest"], "dep_date": dl["dep_date"],
                     "cw": dl["cw"], "std_rate": dl["std_rate"], "final_rate": dl["final_rate"],
                     "saving_krw": round((dl["std_rate"] - dl["final_rate"]) * dl["cw"]),
                     "source": "history"})
    for b in store.bookings:
        rows.append({"date": TODAY.isoformat(), "order_no": b["order_no"], "carrier": b["carrier"],
                     "airline": b["airline_name"], "flight": b["flight_number"],
                     "dest": store.orders[b["order_no"]]["dest"],
                     "dep_date": b["dep_date"], "cw": b["cw"], "std_rate": b["std_allin_per_kg"],
                     "final_rate": b["rate_per_kg"], "saving_krw": b["saving_krw"], "source": "session"})
    total_saving = sum(r["saving_krw"] for r in rows)
    total_std = sum(r["std_rate"] * r["cw"] for r in rows)
    total_final = sum(r["final_rate"] * r["cw"] for r in rows)
    by_carrier, by_dest = {}, {}
    for r in rows:
        by_carrier.setdefault(r["airline"], {"count": 0, "saving": 0})
        by_carrier[r["airline"]]["count"] += 1
        by_carrier[r["airline"]]["saving"] += r["saving_krw"]
        by_dest.setdefault(r["dest"], {"count": 0, "saving": 0})
        by_dest[r["dest"]]["count"] += 1
        by_dest[r["dest"]]["saving"] += r["saving_krw"]
    return {
        "total_saving_krw": round(total_saving),
        "avg_discount_pct": round((1 - total_final / total_std) * 100, 1) if total_std else 0,
        "deal_count": len(rows),
        "by_carrier": by_carrier, "by_dest": by_dest,
        "rows": sorted(rows, key=lambda r: (r["date"], r["dep_date"]), reverse=True),
    }


# 프론트 정적 서빙 (단일 링크 배포): API 라우트 뒤에 마운트해야 /api가 우선
DIST = Path(__file__).parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
