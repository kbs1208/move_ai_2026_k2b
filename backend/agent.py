# 네고 에이전트 오케스트레이션: 후보검색 -> RFQ -> 시장가 파악 -> 네고 -> 추천
# LLM 호출은 배치로 묶어 데모 속도 확보 (call 수 ~7회)
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from airline_sim import CARRIER_PROFILES, decide, write_reply_email, round10
from domain import TODAY, find_candidates
from llm import chat, chat_json

GLOVIS = {"name": "김글로 매니저", "email": "kim.glovis@glovis.com", "team": "현대글로비스 항공수입팀"}
MAX_RFQ_CARRIERS = 5
NEGO_TOP_N = 2
OFFLOAD_RISK_PENALTY = 600  # kg당 페널티: offload 시 차기편이 데드라인 못 지키는 후보 (컨셉 핵심 규칙)
DESIRED_MISS_PENALTY = 100  # 희망도착일 미충족 페널티


KST = timezone(timedelta(hours=9))


def _now():
    """메일함 표시용: 날짜는 데모 시계(TODAY) 고정, 시각은 실제 실행 시각(KST).
    서버 TZ(UTC 등)와 무관하게 항상 한국시간으로 표기."""
    return f"{TODAY.isoformat()} {datetime.now(KST).strftime('%H:%M')} KST"


def pick_carrier_candidates(cands):
    """항공사별 대표 후보 1편: 희망일 충족 > offload 안전 > 빠른 출발 > 낮은 표준가."""
    best = {}
    for c in sorted(cands, key=lambda c: (not c["meets_desired"], not c["offload_safe"],
                                          c["dep_date"], c["std"]["allin_per_kg"])):
        best.setdefault(c["carrier"], c)
    return list(best.values())[:MAX_RFQ_CARRIERS]


def gen_rfq_emails(order, picks):
    """글로비스 페르소나로 항공사별 RFQ 메일 일괄 생성. {carrier: body}"""
    system = (f"당신은 {GLOVIS['team']} {GLOVIS['name']}입니다. "
              "항공사 화물 예약 담당자에게 보낼 견적요청(RFQ) 메일 본문을 작성합니다. "
              "정중한 비즈니스 한국어, 5문장 이내, 서명 포함. "
              "구간/편명/출발일/chargeable weight를 명시하고 kg당 all-in 단가 견적을 요청하세요. "
              "가격 여지를 탐색하는 뉘앙스를 담되 구체적 금액은 제시하지 마세요.")
    items = [{"carrier": p["carrier"], "airline": p["airline_name"], "flight": p["flight_number"],
              "dep_date": p["dep_date"], "route": f"{order['origin']}->{order['dest']}",
              "cw_kg": order["chargeable_weight_kg"], "pieces": order["pieces"],
              "item": order["item_name"], "dg": order["is_dg"]} for p in picks]
    user = ("다음 각 항공사에 보낼 메일을 JSON으로 작성하세요. "
            '형식: {"emails": [{"carrier": "코드", "body": "본문"}]}\n' + json.dumps(items, ensure_ascii=False))
    try:
        res = chat_json(system, user, max_tokens=3000)
        return {e["carrier"]: e["body"] for e in res["emails"]}
    except Exception:
        return {p["carrier"]: (
            f"안녕하세요, {GLOVIS['team']} {GLOVIS['name']}입니다.\n"
            f"{order['origin']}->{order['dest']} {p['flight_number']} ({p['dep_date']} 출발) 편에 "
            f"chargeable {order['chargeable_weight_kg']:,.0f}kg 예약을 검토 중입니다.\n"
            f"kg당 all-in 단가 견적 부탁드립니다.\n감사합니다.") for p in picks}


def parse_quote_emails(replies):
    """수신 메일 body 해석 -> [{carrier, rate_per_kg, decision}] (컨셉의 AI 기능 시연)."""
    system = ("항공사 회신 메일에서 kg당 단가(KRW)와 의사결정을 추출하는 파서입니다. "
              'decision은 quote(견적제시)/counter(역제안)/accept(수락) 중 하나. '
              '형식: {"parsed": [{"carrier": "코드", "rate_per_kg": 숫자, "decision": "..."}]}')
    user = json.dumps([{"carrier": c, "body": b} for c, b in replies], ensure_ascii=False)
    res = chat_json(system, user, max_tokens=1000)
    return {p["carrier"]: p for p in res["parsed"]}


def gen_counter_emails(order, offers):
    """카운터오퍼 메일 일괄 생성. offers: [{carrier, flight, dep_date, their_rate, our_rate, reason}]"""
    system = (f"당신은 {GLOVIS['team']} {GLOVIS['name']}입니다. "
              "항공사의 견적에 대한 카운터오퍼 메일 본문을 작성합니다. "
              "정중하지만 단호한 비즈니스 한국어, 4문장 이내, 서명 포함. "
              "제시된 our_rate(kg당 KRW)를 명시하고 reason을 근거로 활용하세요.")
    user = ('형식: {"emails": [{"carrier": "코드", "body": "본문"}]}\n'
            + json.dumps(offers, ensure_ascii=False))
    try:
        res = chat_json(system, user, max_tokens=2000)
        return {e["carrier"]: e["body"] for e in res["emails"]}
    except Exception:
        return {o["carrier"]: (
            f"안녕하세요, {GLOVIS['name']}입니다.\n제시해주신 kg당 {o['their_rate']:,}원은 수용이 어렵습니다.\n"
            f"kg당 {o['our_rate']:,}원에 진행 가능하시면 바로 확정하겠습니다.\n감사합니다.") for o in offers}


def gen_rationale(order, rec, market, hist_ratio):
    """추천 근거 문단 생성."""
    facts = {
        "주문": order["order_no"], "구간": f"{order['origin']}->{order['dest']}",
        "추천편": f"{rec['flight_number']} {rec['dep_date']} 출발 ({rec['flight_type']})",
        "합의단가": f"kg당 {rec['rate_per_kg']:,}원 (all-in)",
        "표준가": f"kg당 {rec['std_allin_per_kg']:,}원",
        "절감": f"{rec['saving_krw']:,}원 ({rec['saving_pct']}%)",
        "시장견적범위": f"kg당 {market['low']:,}~{market['high']:,}원 ({market['n']}개사)",
        "최근한달합의수준": f"표준가 대비 평균 {round((1-hist_ratio)*100)}% 할인" if hist_ratio else "이력 없음",
        "도착일": rec["arr_date"], "희망도착일": order["desired_arr_date"], "데드라인": order["deadline_date"],
        "offload안전": ("동일 항공사 차기편이 " + rec["next_flight_arr"] + " 도착으로 데드라인 내 커버")
                      if rec["offload_safe"] else "차기편이 데드라인을 넘어 offload 시 리스크 있음",
        "예약컨펌기한": rec["confirm_by"],
    }
    try:
        return chat("항공화물 예약 추천의 근거를 실무자에게 설명합니다. 한국어 4~6문장, 담백하게. "
                    "가격 경쟁력, 스케줄 적합성, offload 리스크, 컨펌 기한을 짚어주세요.",
                    json.dumps(facts, ensure_ascii=False), max_tokens=8000)  # opus-5 reasoning 토큰 포함 예산 — 잘림 방지
    except Exception:
        return (f"{rec['flight_number']} ({rec['dep_date']}) 편을 kg당 {rec['rate_per_kg']:,}원에 예약 권고. "
                f"표준가 대비 {rec['saving_pct']}% 절감, 시장 범위 하단. 컨펌 기한 {rec['confirm_by']}.")


def run_agent(store, order_no, today=TODAY):
    """이벤트 제너레이터. 각 yield가 SSE 이벤트."""
    order = store.orders[order_no]
    cw = order["chargeable_weight_kg"]
    yield {"type": "start", "order": {k: v for k, v in order.items() if k != "lines"},
           "message": f"주문 {order_no} 분석 시작 — CW {cw:,.0f}kg, {order['origin']}->{order['dest']}, "
                      f"준비일 {order['cargo_ready_date']}, 데드라인 {order['deadline_date']}"}

    # 1) 후보 탐색
    cands = find_candidates(store, order, today)
    if not cands:
        yield {"type": "error", "message": "제약조건(준비일/데드라인/D-3 컨펌/기재제약)을 만족하는 운항편이 없습니다."}
        return
    picks = pick_carrier_candidates(cands)
    yield {"type": "candidates", "candidates": cands, "picks": picks,
           "message": f"운항 후보 {len(cands)}편 → {len(picks)}개 항공사에 견적 요청 예정"}

    # 2) 과거 합의 수준 (시장가 사전 정보)
    ratios = [dl["final_rate"] / dl["std_rate"] for dl in store.deals if dl["dest"] == order["dest"]]
    hist_ratio = round(statistics.median(ratios), 4) if ratios else None
    yield {"type": "history", "hist_ratio": hist_ratio, "n_deals": len(ratios),
           "message": (f"최근 1개월 {order['dest']} 구간 합의 {len(ratios)}건 — 표준가 대비 중앙값 "
                       f"{round((1-hist_ratio)*100, 1)}% 할인 수준" if hist_ratio else "과거 합의 이력 없음")}

    # 3) RFQ 발송 + 회신 수신
    yield {"type": "progress", "message": "RFQ 메일 작성 중 (AI)..."}
    rfq_bodies = gen_rfq_emails(order, picks)
    threads = {}
    for p in picks:
        contact = store.contacts[p["carrier"]]
        thread = {
            "thread_id": store.next_id("T"), "order_no": order_no,
            "subject": f"[RFQ] {order['origin']}-{order['dest']} {p['flight_number']} / {p['dep_date']} / {cw:,.0f}kg",
            "carrier": p["carrier"], "airline": contact["airline"], "contact": contact,
            "live": True, "messages": [],
        }
        thread["messages"].append({"from": GLOVIS["email"], "from_name": GLOVIS["name"],
                                   "to": contact["email"], "ts": _now(),
                                   "direction": "out", "body": rfq_bodies[p["carrier"]]})
        threads[p["carrier"]] = thread
        store.threads.append(thread)
        yield {"type": "email", "thread": thread, "message": f"→ {contact['airline']} RFQ 발송"}

    yield {"type": "progress", "message": "항공사 회신 대기 중..."}
    sims, replies = {}, []
    for p in picks:
        std = p["std"]["allin_per_kg"]
        dec = decide(p["carrier"], p["flight_number"], p["dep_date"], std)
        sims[p["carrier"]] = {"pick": p, "std": std, "last": dec["rate"], "dec": dec}
    with ThreadPoolExecutor(len(picks)) as ex:  # 항공사별 회신 병렬 생성 (데모 속도)
        futs = {p["carrier"]: ex.submit(
            write_reply_email, store.contacts[p["carrier"]],
            {"carrier": p["carrier"], "flight_number": p["flight_number"],
             "origin": order["origin"], "dest": order["dest"],
             "dep_date": p["dep_date"], "cw": cw}, sims[p["carrier"]]["dec"]) for p in picks}
        for p in picks:
            body = futs[p["carrier"]].result()
            replies.append((p["carrier"], body))
            threads[p["carrier"]]["messages"].append({
                "from": store.contacts[p["carrier"]]["email"], "from_name": store.contacts[p["carrier"]]["name"],
                "to": GLOVIS["email"], "ts": _now(), "direction": "in", "body": body})
            yield {"type": "email", "thread": threads[p["carrier"]],
                   "message": f"← {store.contacts[p['carrier']]['airline']} 회신 수신"}

    # 4) 수신 메일 해석 -> 시장 range / 타깃
    yield {"type": "progress", "message": "회신 메일 해석 중 (AI)..."}
    try:
        parsed = parse_quote_emails(replies)
    except Exception:
        parsed = {}
    quotes = {}
    for c, sim in sims.items():
        p_rate = parsed.get(c, {}).get("rate_per_kg")
        # 파싱값 검증: 시뮬레이터 실제 제시가와 1% 이상 어긋나면 시뮬레이터 값 사용
        rate = p_rate if p_rate and abs(p_rate - sim["last"]) / sim["last"] < 0.01 else sim["last"]
        quotes[c] = round10(rate)
        sim["last"] = quotes[c]
    low, high = min(quotes.values()), max(quotes.values())
    market = {"low": low, "high": high, "n": len(quotes), "quotes": quotes}
    # 타깃: 최저 견적 -4.5% 와 과거 합의 중앙값 중 낮은 쪽 (설명 가능 정책)
    targets = {}
    for c, sim in sims.items():
        t = low * 0.955
        if hist_ratio:
            t = min(t, sim["std"] * hist_ratio)
        targets[c] = round10(t)
    yield {"type": "quotes", "market": market, "targets": targets,
           "message": f"견적 수신 완료 — 시장 range kg당 {low:,}~{high:,}원. "
                      f"타깃 kg당 {min(targets.values()):,}원 설정"}

    # 5) 상위 후보와 네고 (가격 + 안전성 스코어)
    def score(c):
        pick = sims[c]["pick"]
        return (quotes[c] + (0 if pick["offload_safe"] else OFFLOAD_RISK_PENALTY)
                + (0 if pick["meets_desired"] else DESIRED_MISS_PENALTY))
    nego_list = sorted(quotes, key=score)[:NEGO_TOP_N]
    finals = dict(quotes)  # 네고 안 한 곳은 초기 견적이 최종
    for rnd in (1, 2):
        offers = []
        for c in nego_list:
            our = targets[c] if rnd == 1 else round10((targets[c] + sims[c]["last"]) / 2)
            if our >= sims[c]["last"]:  # 이미 타깃 이하면 수락
                continue
            offers.append({"carrier": c, "flight": sims[c]["pick"]["flight_number"],
                           "dep_date": sims[c]["pick"]["dep_date"],
                           "their_rate": sims[c]["last"], "our_rate": our,
                           "reason": f"타 항공사 견적 kg당 {low:,}원 및 최근 시장 합의 수준 감안"})
        if not offers:
            break
        yield {"type": "progress", "message": f"네고 라운드 {rnd} — 카운터오퍼 발송 중 (AI)..."}
        bodies = gen_counter_emails(order, offers)
        decs = {}
        for o in offers:
            c = o["carrier"]
            pick = sims[c]["pick"]
            decs[c] = decide(c, pick["flight_number"], pick["dep_date"], sims[c]["std"],
                             proposed=o["our_rate"], last_quote=sims[c]["last"])
        with ThreadPoolExecutor(len(offers)) as ex:  # 회신 병렬 생성
            futs = {o["carrier"]: ex.submit(
                write_reply_email, store.contacts[o["carrier"]],
                {"carrier": o["carrier"], "flight_number": sims[o["carrier"]]["pick"]["flight_number"],
                 "origin": order["origin"], "dest": order["dest"],
                 "dep_date": sims[o["carrier"]]["pick"]["dep_date"], "cw": cw},
                decs[o["carrier"]]) for o in offers}
            reply_bodies = {c: f.result() for c, f in futs.items()}
        done = []
        for o in offers:
            c = o["carrier"]
            contact = store.contacts[c]
            threads[c]["messages"].append({"from": GLOVIS["email"], "from_name": GLOVIS["name"],
                                           "to": contact["email"], "ts": _now(),
                                           "direction": "out", "body": bodies[c]})
            yield {"type": "email", "thread": threads[c],
                   "message": f"→ {contact['airline']} 카운터오퍼 kg당 {o['our_rate']:,}원"}
            dec = decs[c]
            threads[c]["messages"].append({"from": contact["email"], "from_name": contact["name"],
                                           "to": GLOVIS["email"], "ts": _now(),
                                           "direction": "in", "body": reply_bodies[c]})
            sims[c]["last"] = dec["rate"]
            finals[c] = dec["rate"]
            yield {"type": "email", "thread": threads[c],
                   "message": f"← {contact['airline']} {'수락' if dec['decision'] == 'accept' else '역제안'} "
                              f"kg당 {dec['rate']:,}원"}
            yield {"type": "nego", "carrier": c, "round": rnd, "offer": o["our_rate"],
                   "decision": dec["decision"], "rate": dec["rate"],
                   "message": f"{contact['airline']} 라운드{rnd}: 제안 {o['our_rate']:,} → "
                              f"{'수락' if dec['decision'] == 'accept' else '역제안 ' + format(dec['rate'], ',')}"}
            if dec["decision"] == "accept":
                done.append(c)
            elif dec["rate"] <= o["our_rate"] * 1.02:  # 2% 이내 근접 -> 수용
                done.append(c)
        nego_list = [c for c in nego_list if c not in done]
        if not nego_list:
            break

    # 6) 최종 추천
    def final_score(c):
        pick = sims[c]["pick"]
        return (finals[c] + (0 if pick["offload_safe"] else OFFLOAD_RISK_PENALTY)
                + (0 if pick["meets_desired"] else DESIRED_MISS_PENALTY))
    winner = min(finals, key=final_score)
    pick, std = sims[winner]["pick"], sims[winner]["std"]
    rate = finals[winner]
    rec = {
        "order_no": order_no, "carrier": winner,
        "airline_name": pick["airline_name"], "flight_number": pick["flight_number"],
        "flight_type": pick["flight_type"], "dep_date": pick["dep_date"], "dep_time": pick["dep_time"],
        "arr_date": pick["arr_date"], "arr_time": pick["arr_time"], "confirm_by": pick["confirm_by"],
        "offload_safe": pick["offload_safe"], "next_flight_arr": pick["next_flight_arr"],
        "meets_desired": pick["meets_desired"], "factory_eta_hours": pick["factory_eta_hours"],
        "cw": cw, "rate_per_kg": rate, "total_krw": round(rate * cw),
        "std_allin_per_kg": std, "std_total_krw": pick["std"]["total_krw"],
        "saving_krw": round(pick["std"]["total_krw"] - rate * cw),
        "saving_pct": round((1 - rate * cw / pick["std"]["total_krw"]) * 100, 1),
        "market": market,
    }
    yield {"type": "progress", "message": "추천 근거 정리 중 (AI)..."}
    rec["rationale"] = gen_rationale(order, rec, market, hist_ratio)
    store.last_recommendation = rec
    yield {"type": "recommendation", "recommendation": rec,
           "message": f"추천: {pick['airline_name']} {pick['flight_number']} / {pick['dep_date']} / "
                      f"kg당 {rate:,}원 (표준가 대비 {rec['saving_pct']}% 절감)"}
    yield {"type": "done", "message": "에이전트 실행 완료"}
