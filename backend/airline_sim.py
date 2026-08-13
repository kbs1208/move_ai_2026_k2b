# 항공사 응답 시뮬레이터: 결정(수락/카운터)은 숨겨진 하한가 규칙, 메일 문면은 LLM 롤플레이
import hashlib

from llm import chat

# 숨겨진 네고 성향 (floor = 표준가 대비 하한 비율)
CARRIER_PROFILES = {
    "KE": {"floor": 0.90, "style": "보수적이고 정중함. 프리미엄 서비스와 스케줄 신뢰성 강조."},
    "DL": {"floor": 0.88, "style": "사무적이고 간결함. 미국 내 연결 네트워크 강조."},
    "AA": {"floor": 0.87, "style": "실용적, 빠르고 직설적."},
    "MH": {"floor": 0.83, "style": "물량 유치에 적극적. 저가 공세로 시작."},
    "5Y": {"floor": 0.81, "style": "차터 전문. 공격적 할인, 스페이스 유연성 강조."},
    "KJ": {"floor": 0.85, "style": "포워더 친화적이고 유연함."},
    "C8": {"floor": 0.92, "style": "유럽계 프리미엄. 고품질 고가 포지션."},
}


def load_factor(flight_number, dep_date):
    """편별 탑재율 0.45~0.95 (해시 시드 → 데모 재현성)."""
    h = int(hashlib.md5(f"{flight_number}{dep_date}".encode()).hexdigest(), 16)
    return 0.45 + (h % 1000) / 1000 * 0.5


def round10(x):
    return int(round(x / 10.0) * 10)


def floor_rate(carrier, std_allin, lf):
    """항공사가 절대 안 깨는 kg당 하한가. 탑재율 높으면 상승."""
    base = CARRIER_PROFILES[carrier]["floor"]
    return round10(std_allin * min(0.97, base + (lf - 0.7) * 0.15))


def initial_quote(carrier, std_allin, lf):
    """RFQ 첫 견적: floor~표준가 사이, 탑재율 낮을수록 공격적."""
    fl = floor_rate(carrier, std_allin, lf)
    return round10(fl + (std_allin - fl) * (0.30 + lf * 0.45))


def decide(carrier, flight_number, dep_date, std_allin, proposed=None, last_quote=None):
    """네고 결정. proposed 없으면 첫 견적. 반환 {decision, rate}."""
    lf = load_factor(flight_number, dep_date)
    fl = floor_rate(carrier, std_allin, lf)
    if proposed is None:
        return {"decision": "quote", "rate": initial_quote(carrier, std_allin, lf), "lf": lf}
    if proposed >= fl:
        return {"decision": "accept", "rate": round10(proposed), "lf": lf}
    prev = last_quote or initial_quote(carrier, std_allin, lf)
    counter = round10(max(fl, (proposed + prev) / 2))
    if counter >= prev:  # 더 못 내리면 기존가 고수
        counter = prev
    return {"decision": "counter", "rate": counter, "lf": lf}


def write_reply_email(contact, ctx, decision):
    """항공사 담당자 페르소나로 회신 메일 본문 생성 (전부 한국어, kg당 단가 필수 포함)."""
    action = {
        "quote": f"견적 제시: kg당 {decision['rate']:,} KRW (all-in, 유류/보안할증 포함)",
        "accept": f"제안가 수락: kg당 {decision['rate']:,} KRW 확정",
        "counter": f"역제안: 제안가는 어렵고 kg당 {decision['rate']:,} KRW까지 가능",
        "confirm_request": (
            f"최종 합의 확인: kg당 {decision['rate']:,} KRW로 스페이스 홀드 완료. "
            "감사 인사 직전 마지막 문장은 반드시 다음 문구 그대로 쓸 것: "
            "'예약확정을 위해 당사시스템에 예약한 AWB 번호를 회신하여 주시기 바랍니다.'"
        ),
    }[decision["decision"]]
    lf_note = "스페이스 여유 있음" if decision["lf"] < 0.65 else ("스페이스 보통" if decision["lf"] < 0.8 else "스페이스 타이트, 강하게 어필")
    signature = f"감사합니다.\n\n{contact['airline']} 화물예약팀\n담당자 {contact['name']}"
    system = (f"당신은 {contact['airline']} 화물 예약 담당자 {contact['name']}입니다. "
              f"성향: {CARRIER_PROFILES[ctx['carrier']]['style']} "
              "현대글로비스의 항공화물 예약 요청 메일에 회신합니다. 반드시 한국어로 작성 (담당자가 외국인이어도 한국어). "
              "비즈니스 메일 본문만 출력 (제목 제외). 6문장 이내로 간결하게. "
              "kg당 단가(KRW)를 본문에 반드시 명시. "
              f"메일의 끝은 반드시 다음 형식 그대로 마무리할 것:\n{signature}")
    user = (f"[회신할 내용] {action}\n[내부 참고-비공개] {lf_note}\n"
            f"[요청 정보] 편명 {ctx['flight_number']} / {ctx['origin']}->{ctx['dest']} "
            f"{ctx['dep_date']} 출발 / 물량 {ctx['cw']:,.0f}kg (chargeable)\n"
            f"수신자: 현대글로비스 항공수입팀 김글로 매니저")
    try:
        return chat(system, user, max_tokens=600)
    except Exception:
        # ponytail: 데모 보험용 최소 폴백
        if decision["decision"] == "confirm_request":
            return (f"안녕하세요, {contact['airline']} {contact['name']}입니다.\n"
                    f"{ctx['flight_number']} ({ctx['dep_date']}) 건 kg당 {decision['rate']:,} KRW로 확정 진행합니다.\n"
                    f"예약확정을 위해 당사시스템에 예약한 AWB 번호를 회신하여 주시기 바랍니다.\n{signature}")
        return (f"안녕하세요, {contact['airline']} {contact['name']}입니다.\n"
                f"{ctx['flight_number']} ({ctx['dep_date']}) 건, kg당 {decision['rate']:,} KRW (all-in) 안내드립니다.\n"
                f"{signature}")
