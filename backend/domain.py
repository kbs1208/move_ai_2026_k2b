# 도메인 로직: 요금계산 / 스케줄 전개 / 후보 검색 / offload 안전성
from datetime import date, datetime, timedelta

TODAY = date(2026, 8, 8)          # 데모 시계 고정
CONFIRM_LEAD_DAYS = 3             # 출발 D-3까지 예약 필요
BOOKING_OPEN_DAYS = 21            # 출발 3주 전 예약 오픈
GROUND_HOURS = {"ATL": 10, "DFW": 20}  # 도착공항 -> 공장 육상운송(통관 포함)
PAX_MAX_HEIGHT = 160              # 여객기 높이 제한(cm)
CGO_MAX_HEIGHT = 300              # 화물기 높이 제한(cm)


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


# ---------- 요금 ----------

def rate_per_kg(tariff, cw):
    """weight-break 단가 (kg당). 항공 관례: 상위 브레이크 요율이 유리하면 그대로 적용."""
    if cw >= 1000: return tariff["1000"]
    if cw >= 500: return tariff["500"]
    if cw >= 300: return tariff["300"]
    if cw >= 100: return tariff["100"]
    if cw >= 45: return tariff["45"]
    return tariff["N"]


def surcharge_per_kg(surcharges, carrier, region, on):
    """항공사별 유류+보안 할증 (kg당)."""
    for s in surcharges:
        if (s["carrier"] == carrier and s["ARRV_REGION"] == region
                and d(s["SUR_EFFECTIVE_START_DATE"]) <= on <= d(s["SUR_EFFECTIVE_END_DATE"])):
            return s["FUEL_SURCHARGE_KG"] + s["SEC_SURCHARGE_KG"]
    return 0.0


def find_tariff(rates, carrier, origin, dest, on):
    """해당 항공사/구간/기간의 표준 tariff. Standard 우선, 없으면 첫 번째.
    (여객편 belly cargo도 동일 항공사 tariff 적용)"""
    cands = [r for r in rates
             if r["carrier"] == carrier and r["DPRT_AIRPORT"] == origin and r["ARRV_AIRPORT"] == dest
             and d(r["EFFECTIVE_START_DATE"]) <= on <= d(r["EFFECTIVE_END_DATE"])]
    if not cands:
        return None
    std = [r for r in cands if r["SERVICE_LEVEL"] == "Standard"]
    return (std or cands)[0]


def standard_quote(tariff, surcharges, cw, on):
    """표준가 all-in: max(MIN, 요율*CW) + 항공사별 할증*CW. kg당 환산 단가도 반환."""
    rate = rate_per_kg(tariff, cw)
    freight = max(tariff["MIN"], rate * cw)
    sur = surcharge_per_kg(surcharges, tariff["carrier"], tariff["ARRV_REGION"], on) * cw
    total = freight + sur
    return {
        "rate_per_kg": rate,
        "freight_krw": round(freight),
        "surcharge_krw": round(sur),
        "total_krw": round(total),
        "allin_per_kg": round(total / cw) if cw else 0,
    }


# ---------- 스케줄 ----------

def expand_flights(schedules, origin, dest, date_from, date_to):
    """요일 패턴 × 유효기간 -> 일자별 운항 인스턴스.
    도착일 = 출발일 + date_differ (0=당일, 1=익일, -1=전일 / 도착시각은 한국시간 기준)."""
    out = []
    for s in schedules:
        if s["origin_airport"] != origin or s["dest_airport"] != dest:
            continue
        differ = int(s.get("date_differ") or 0)
        lo, hi = max(d(s["start_date"]), date_from), min(d(s["end_date"]), date_to)
        cur = lo
        while cur <= hi:
            if s["ops"][cur.weekday()]:
                out.append({
                    "flight_number": s["flight_number"],
                    "carrier": s["carrier"],
                    "airline_name": s["airline_name"],
                    "flight_type": s["flight_type"],
                    "origin": origin, "dest": dest,
                    "dep_date": cur.isoformat(),
                    "dep_time": s["departure_time"],
                    "arr_date": (cur + timedelta(days=differ)).isoformat(),
                    "arr_time": s["arrival_time"],
                })
            cur += timedelta(days=1)
    # 같은 편명+일자 중복 스케줄 행 제거 (KE8255가 겹치는 기간 존재)
    seen, dedup = set(), []
    for f in sorted(out, key=lambda x: (x["dep_date"], x["dep_time"], x["flight_number"])):
        key = (f["flight_number"], f["dep_date"])
        if key not in seen:
            seen.add(key)
            dedup.append(f)
    return dedup


# ---------- 후보 검색 ----------

def cargo_fits(order, flight_type):
    if order["is_dg"] and flight_type == "PASSENGER":
        return False
    limit = PAX_MAX_HEIGHT if flight_type == "PASSENGER" else CGO_MAX_HEIGHT
    return order["max_height_cm"] <= limit


def next_flight_arrival(schedules, carrier, origin, dest, after_dep):
    """동일 항공사 차기편 도착일 (offload 대비). after_dep 다음날부터 14일 탐색."""
    flights = expand_flights(schedules, origin, dest,
                             after_dep + timedelta(days=1), after_dep + timedelta(days=14))
    for f in flights:
        if f["carrier"] == carrier:
            return d(f["arr_date"])
    return None


def find_candidates(store, order, today=TODAY):
    """제약조건 통과한 운항 인스턴스 + 표준가 + offload 안전성."""
    ready, deadline = d(order["cargo_ready_date"]), d(order["deadline_date"])
    desired = d(order["desired_arr_date"])
    cw = order["chargeable_weight_kg"]
    flights = expand_flights(store.schedules, order["origin"], order["dest"], ready, deadline)
    out = []
    for f in flights:
        dep, arr = d(f["dep_date"]), d(f["arr_date"])
        if not cargo_fits(order, f["flight_type"]):
            continue
        if arr > deadline:
            continue
        if (dep - today).days < CONFIRM_LEAD_DAYS:
            continue  # 컨펌 리드타임 부족
        if (dep - today).days > BOOKING_OPEN_DAYS:
            continue  # 예약 미오픈
        tariff = find_tariff(store.rates, f["carrier"], order["origin"], order["dest"], dep)
        if not tariff:
            continue
        std = standard_quote(tariff, store.surcharges, cw, dep)
        nxt = next_flight_arrival(store.schedules, f["carrier"], order["origin"], order["dest"], dep)
        ground_h = GROUND_HOURS.get(order["dest"], 12)
        out.append({
            **f,
            "meets_desired": arr <= desired,
            "offload_safe": nxt is not None and nxt <= deadline,
            "next_flight_arr": nxt.isoformat() if nxt else None,
            "confirm_by": (dep - timedelta(days=CONFIRM_LEAD_DAYS)).isoformat(),
            "factory_eta_hours": ground_h,
            "std": std,
            "tariff_service": tariff["SERVICE_LEVEL"],
        })
    return out


if __name__ == "__main__":
    # 셀프체크: 주문 001 (ICN->ATL, CW 1460.64, ready 8/10, deadline 8/12)
    from store import store

    o = store.orders["GLV-KD-20260810-001"]
    assert o["chargeable_weight_kg"] == 1460.64, o["chargeable_weight_kg"]
    assert o["max_height_cm"] == 170  # 여객기 한계(160) 초과 -> 화물기 전용

    cands = find_candidates(store, o)
    assert cands, "후보가 있어야 함"
    assert all(c["flight_type"] == "CARGO" for c in cands), "높이 170cm는 화물기만 가능"
    for c in cands:
        assert d(c["arr_date"]) <= d(o["deadline_date"])
        assert (d(c["dep_date"]) - TODAY).days >= 3
    # KE 요율 검증: ICN->ATL Standard, CW>=1000 -> 3900/kg + KE USA 할증 (1890+450)/kg
    t = find_tariff(store.rates, "KE", "ICN", "ATL", date(2026, 8, 13))
    q = standard_quote(t, store.surcharges, 1460.64, date(2026, 8, 13))
    assert q["rate_per_kg"] == 3900, q["rate_per_kg"]
    assert q["total_krw"] == round(1460.64 * (3900 + 1890 + 450)), q["total_krw"]
    # 항공사별 할증 상이 검증 (KE 2340 vs DL 2450)
    assert surcharge_per_kg(store.surcharges, "KE", "USA", date(2026, 8, 13)) == 2340
    assert surcharge_per_kg(store.surcharges, "DL", "USA", date(2026, 8, 13)) == 2450
    # ZET->KJ alias 할증 매칭 (Air Zetta USA 1840+450)
    assert surcharge_per_kg(store.surcharges, "KJ", "USA", date(2026, 8, 13)) == 2290
    # DG 주문(전 라인 Y)은 여객기 배제
    dg = store.orders["GLV-KD-20260810-002"]
    dg_c = find_candidates(store, dg)
    assert dg_c and all(c["flight_type"] == "CARGO" for c in dg_c)
    # 혼재 DG 주문(Y+N 라인): 주문 전체가 DG 취급 -> 화물기만
    mixed = store.orders["GLV-KD-20260811-005"]
    assert mixed["is_dg"] and any(not l["is_dg"] for l in mixed["lines"])
    assert "외 1건" in mixed["item_name"]
    mixed_c = find_candidates(store, mixed)
    assert mixed_c and all(c["flight_type"] == "CARGO" for c in mixed_c)
    # date_differ: KJ248(23:00 출발)은 익일 도착
    kj = [f for f in expand_flights(store.schedules, "ICN", "ATL", date(2026, 8, 12), date(2026, 8, 12))
          if f["flight_number"] == "KJ248"]
    assert kj and kj[0]["arr_date"] == "2026-08-13" and kj[0]["arr_time"], kj
    # 당일 도착 편 확인 (KE033 08:45 -> 09:45 당일)
    ke = [f for f in expand_flights(store.schedules, "ICN", "ATL", date(2026, 8, 12), date(2026, 8, 12))
          if f["flight_number"] == "KE033"]
    assert ke[0]["arr_date"] == "2026-08-12"
    print(f"OK — 주문 {len(store.orders)}건 / 001 후보 {len(cands)}편 / DG 후보 {len(dg_c)}편 / "
          f"혼재DG 후보 {len(mixed_c)}편(전부 화물기) / KJ248 익일도착 검증")
    for c in mixed_c:
        print(f'  {c["flight_number"]} dep {c["dep_date"]} arr {c["arr_date"]} {c["arr_time"]} '
              f'std={c["std"]["allin_per_kg"]}/kg safe={c["offload_safe"]}')
