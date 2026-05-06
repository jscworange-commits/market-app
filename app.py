from datetime import datetime, timedelta
from pathlib import Path
import json

import pandas as pd
import streamlit as st
import yfinance as yf

try:
    from pykrx import stock
    PYKRX_AVAILABLE = True
    PYKRX_ERROR = None
except Exception as e:
    PYKRX_AVAILABLE = False
    PYKRX_ERROR = str(e)


APP_TITLE = "Daily Market Assistant Auto"
HISTORY_FILE = Path("market_history.csv")
SNAPSHOT_FILE = Path("today_market_snapshot.md")
CONFIG_FILE = Path("settings.json")

US_TICKERS = {
    "Dow Jones": "^DJI",
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "SOX": "^SOX",
    "NVIDIA": "NVDA",
    "Tesla": "TSLA",
    "Apple": "AAPL",
    "Microsoft": "MSFT",
    "VIX": "^VIX",
    "US 10Y Yield": "^TNX",
    "Dollar Index": "DX-Y.NYB",
    "WTI Oil": "CL=F",
    "USD/KRW": "KRW=X",
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
}

SECTOR_STOCKS = {
    "반도체": [
        "삼성전자", "SK하이닉스", "한미반도체", "리노공업", "HPSP",
        "이오테크닉스", "주성엔지니어링", "원익IPS", "테스", "피에스케이홀딩스",
        "가온칩스", "칩스앤미디어", "DB하이텍"
    ],
    "AI/데이터센터": [
        "NAVER", "카카오", "더존비즈온", "이수페타시스", "가온칩스",
        "솔트룩스", "코난테크놀로지", "마음AI"
    ],
    "에너지/전력망": [
        "HD현대일렉트릭", "LS ELECTRIC", "효성중공업", "대한전선", "일진전기",
        "제룡전기", "LS", "가온전선", "대원전선", "제룡산업"
    ],
    "조선": [
        "HD현대중공업", "한화오션", "삼성중공업", "HD한국조선해양", "세진중공업",
        "현대미포조선", "HD현대마린솔루션", "STX엔진", "한국카본", "동성화인텍"
    ],
    "방산": [
        "한화에어로스페이스", "현대로템", "LIG넥스원", "한국항공우주", "풍산",
        "한화시스템", "SNT다이내믹스", "퍼스텍", "빅텍", "휴니드"
    ],
    "2차전지": [
        "LG에너지솔루션", "삼성SDI", "POSCO홀딩스", "에코프로비엠", "포스코퓨처엠",
        "엘앤에프", "에코프로", "나노신소재", "천보", "윤성에프앤씨", "피엔티"
    ],
    "원전": [
        "두산에너빌리티", "한전기술", "한전KPS", "비에이치아이", "우리기술",
        "서전기전", "우진", "보성파워텍", "오르비텍", "일진파워"
    ],
}

NEWS_TO_SECTOR = {
    "반도체 호재": "반도체",
    "AI 호재": "AI/데이터센터",
    "전력망 투자": "에너지/전력망",
    "조선 수주": "조선",
    "방산 수출": "방산",
    "2차전지 호재": "2차전지",
    "원전 정책": "원전",
}


def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(config):
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def previous_business_dates(days_back=18):
    today = datetime.now()
    dates = []
    for i in range(days_back):
        d = today - timedelta(days=i)
        if d.weekday() < 5:
            dates.append(d.strftime("%Y%m%d"))
    return dates


def fetch_yfinance_change_pct(ticker, period="7d"):
    try:
        data = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
        if data is None or data.empty:
            return None, None, "no data"

        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"].iloc[:, 0].dropna()
        else:
            close = data["Close"].dropna()

        if len(close) < 2:
            return None, None, "not enough data"

        last = float(close.iloc[-1])
        prev = float(close.iloc[-2])

        if prev == 0:
            return None, None, "prev close zero"

        return (last - prev) / prev * 100, last, None
    except Exception as e:
        return None, None, str(e)


@st.cache_data(ttl=60 * 15)
def fetch_us_market_data():
    rows = []
    values = {}

    for name, ticker in US_TICKERS.items():
        pct, last, err = fetch_yfinance_change_pct(ticker)
        values[name] = pct

        rows.append({
            "지표": name,
            "티커": ticker,
            "종가/값": None if last is None else round(last, 4),
            "전일 대비(%)": None if pct is None else round(pct, 2),
            "상태": "OK" if err is None else err[:80],
        })

    return pd.DataFrame(rows), values


@st.cache_data(ttl=60 * 10)
def fetch_krx_value_top(market_choice, top_n):
    if not PYKRX_AVAILABLE:
        return pd.DataFrame(), None, PYKRX_ERROR

    try:
        market = "ALL"
        if market_choice == "KOSPI":
            market = "KOSPI"
        elif market_choice == "KOSDAQ":
            market = "KOSDAQ"

        today_dt = datetime.today()

        last_error = None
        df = pd.DataFrame()
        used_date = None

        # 최근 10일 중 정상 조회되는 날짜 찾기
        for i in range(0, 10):
            date_str = (today_dt - timedelta(days=i)).strftime("%Y%m%d")

            try:
                temp = stock.get_market_ohlcv_by_ticker(date_str, market=market)

                if temp is not None and not temp.empty:
                    df = temp.copy()
                    used_date = date_str
                    break

            except Exception as e:
                last_error = str(e)
                continue

        if df is None or df.empty:
            return pd.DataFrame(), None, f"KRX 데이터 조회 실패: {last_error}"

        df = df.reset_index()

        if "티커" not in df.columns:
            df = df.rename(columns={df.columns[0]: "티커"})

        def get_name_safe(ticker):
            try:
                return stock.get_market_ticker_name(ticker)
            except Exception:
                return ticker

        df["종목명"] = df["티커"].apply(get_name_safe)

        for col in ["시가", "고가", "저가", "종가", "거래량", "거래대금", "등락률"]:
            if col not in df.columns:
                df[col] = 0

        df = df.sort_values("거래대금", ascending=False).head(top_n)

        return df, used_date, None

    except Exception as e:
        return pd.DataFrame(), None, str(e)
        
def pct_score(x, strong=1.0):
    if x is None:
        return 0
    if x >= strong:
        return 2
    if x > 0:
        return 1
    if x <= -strong:
        return -2
    if x < 0:
        return -1
    return 0


def trend_score(value, good="down"):
    if value == "flat":
        return 0
    return 1 if value == good else -1


def sector_score(value):
    if value == "강세":
        return 1
    if value == "약세":
        return -1
    return 0


def classify(score):
    if score >= 8:
        return "Strong Risk ON / 주도주 매매 가능", "거래대금 상위 + 강세 섹터 교집합 1~2개만 압축합니다."
    if score >= 4:
        return "Selective Risk ON / 선별 매수", "시초 추격은 피하고, 10시 이후 거래량 유지 종목만 접근합니다."
    if score > -3:
        return "Neutral / 관망 우위", "매수보다 확인이 우선입니다. 거래대금 TOP 단타만 제한적으로 접근합니다."
    return "Risk OFF / 매매 회피", "신규 매수 금지. 보유 종목 리스크 관리가 우선입니다."


def infer_sector_defaults(market):
    defaults = {s: "보합" for s in SECTOR_STOCKS}

    nasdaq = market.get("Nasdaq")
    sox = market.get("SOX")
    nvda = market.get("NVIDIA")
    tesla = market.get("Tesla")
    oil = market.get("WTI Oil")

    if (sox is not None and sox > 0.5) or (nvda is not None and nvda > 1.0):
        defaults["반도체"] = "강세"
        defaults["AI/데이터센터"] = "강세"
    elif (sox is not None and sox < -0.5) or (nvda is not None and nvda < -1.0):
        defaults["반도체"] = "약세"
        defaults["AI/데이터센터"] = "약세"

    if nasdaq is not None and nasdaq > 0.7:
        defaults["AI/데이터센터"] = "강세"
    elif nasdaq is not None and nasdaq < -0.7:
        defaults["AI/데이터센터"] = "약세"

    if tesla is not None and tesla > 1.0:
        defaults["2차전지"] = "강세"
    elif tesla is not None and tesla < -1.0:
        defaults["2차전지"] = "약세"

    if oil is not None and oil > 1.0:
        defaults["에너지/전력망"] = "강세"

    return defaults


def generate_candidates(strong_sectors, news_triggers):
    candidates = []

    for sector in strong_sectors:
        candidates.extend(SECTOR_STOCKS.get(sector, []))

    for news in news_triggers:
        sector = NEWS_TO_SECTOR.get(news)
        if sector:
            candidates.extend(SECTOR_STOCKS.get(sector, []))

    return list(dict.fromkeys(candidates))


def rank_candidates_with_value(candidates, value_df, score, weak_sectors):
    columns = ["순위", "종목명", "거래대금순위", "등락률", "거래대금", "점수", "판정"]

    if not candidates:
        return pd.DataFrame(columns=columns)

    value_map = {}

    if value_df is not None and not value_df.empty:
        for idx, row in value_df.reset_index(drop=True).iterrows():
            value_map[row["종목명"]] = {
                "rank": idx + 1,
                "등락률": float(row.get("등락률", 0)),
                "거래대금": float(row.get("거래대금", 0)),
            }

    weak_stock_set = set()

    for sector in weak_sectors:
        weak_stock_set.update(SECTOR_STOCKS.get(sector, []))

    rows = []

    for name in candidates:
        v = value_map.get(name)
        s = 0

        if v:
            if v["rank"] <= 20:
                s += 4
            elif v["rank"] <= 50:
                s += 3
            else:
                s += 1

            if v["등락률"] > 0:
                s += 1
            if v["등락률"] >= 3:
                s += 1
        else:
            s -= 1

        if name in weak_stock_set:
            s -= 3

        if score < 0 and name in ["카카오", "엘앤에프", "에코프로비엠", "솔트룩스", "마음AI"]:
            s -= 2

        if s >= 5:
            verdict = "최우선"
        elif s >= 3:
            verdict = "관심"
        elif s >= 1:
            verdict = "관찰"
        else:
            verdict = "제외/관망"

        rows.append({
            "종목명": name,
            "거래대금순위": v["rank"] if v else None,
            "등락률": round(v["등락률"], 2) if v else None,
            "거래대금": round(v["거래대금"], 0) if v else None,
            "점수": s,
            "판정": verdict,
        })

    out = pd.DataFrame(rows)

    if out.empty:
        return pd.DataFrame(columns=columns)

    out = out.sort_values(["점수", "거래대금순위"], ascending=[False, True], na_position="last")
    out = out.head(10).reset_index(drop=True)
    out.insert(0, "순위", range(1, len(out) + 1))

    return out


def load_history():
    if HISTORY_FILE.exists():
        return pd.read_csv(HISTORY_FILE)

    return pd.DataFrame(columns=["date", "score", "judgment", "top_pick", "strong_sectors", "weak_sectors", "memo"])


def save_history(row):
    hist = load_history()
    hist = pd.concat([pd.DataFrame([row]), hist], ignore_index=True)
    hist.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")


def build_snapshot(score, judgment, strategy, positives, negatives, strong_sectors, weak_sectors, ranked, ban_reasons, memo):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    top = "없음" if ranked.empty else str(ranked.iloc[0]["종목명"])

    lines = []
    lines.append(f"# Daily Market Snapshot - {now}")
    lines.append("")
    lines.append("## BLUF")
    lines.append(f"- 판단: {judgment}")
    lines.append(f"- 점수: {score:.1f}")
    lines.append(f"- 핵심 후보: {top}")
    lines.append(f"- 전략: {strategy}")
    lines.append("")

    lines.append("## 긍정 요인")
    if positives:
        for x in positives:
            lines.append(f"- {x}")
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("## 부정 요인")
    if negatives:
        for x in negatives:
            lines.append(f"- {x}")
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("## 강세 섹터")
    if strong_sectors:
        lines.append(f"- {', '.join(strong_sectors)}")
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("## 약세 섹터")
    if weak_sectors:
        lines.append(f"- {', '.join(weak_sectors)}")
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("## 매매 금지 조건")
    if ban_reasons:
        lines.append(f"- {', '.join(ban_reasons)}")
    else:
        lines.append("- 주요 금지 조건 없음")
    lines.append("")

    lines.append("## 최종 후보")
    if ranked.empty:
        lines.append("- 없음")
    else:
        for _, r in ranked.head(5).iterrows():
            lines.append(
                f"- {r['종목명']} / 판정: {r['판정']} / "
                f"거래대금순위: {r['거래대금순위']} / 등락률: {r['등락률']}%"
            )
    lines.append("")

    lines.append("## 메모")
    if memo:
        lines.append(memo)
    else:
        lines.append("- 없음")

    return "\n".join(lines)


st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide")
st.title("📊 Daily Market Assistant Auto")
st.caption("데이터 수집 → 시장 판단 → 거래대금 필터 → 최종 후보 → 기록/스냅샷까지 자동화한 트레이딩 보조 시스템입니다.")

# ===============================
# Top Guide
# ===============================
st.markdown("## 📘 사용 가이드")

with st.expander("앱 해석법과 실전 사용 순서 보기", expanded=True):
    st.markdown("""
### BLUF
이 앱은 **실제 주문을 자동 실행하지 않습니다.**  
대신 매일 아침 필요한 정보를 자동 수집하고, **오늘 매매해도 되는 장인지 / 어떤 섹터와 종목을 볼지 / 언제 피해야 하는지**를 정리합니다.

### 1. 전체 흐름
`미국시장 → 매크로 → 한국 거래대금 → 수급·뉴스 → 섹터 → 최종 후보 → 리스크 가이드`

### 2. 점수 해석
| 점수 | 해석 | 행동 |
|---:|---|---|
| 8 이상 | Strong Risk ON | 주도주 1~2개 압축 매매 가능 |
| 4~7 | Selective Risk ON | 시초 추격 금지, 거래대금 유지 종목만 |
| -2~3 | Neutral | 관망 우위, 단타만 제한 |
| -3 이하 | Risk OFF | 신규 매수 금지 |

### 3. 최종 후보 해석
- **최우선**: 강세 섹터 + 거래대금 확인 + 등락률 양호
- **관심**: 조건은 좋으나 장중 확인 필요
- **관찰**: 보기만 하고 추격 금지
- **제외/관망**: 매수 우선순위 낮음

### 4. 절대 금지 조건
- VIX 급등
- Nasdaq 급락
- 외국인 순매도 + 거래량 약함
- 점수 낮은데 급등주 추격

### 5. 실행 원칙
TOP10을 모두 사는 앱이 아닙니다. **최종 후보 중 1~2개만 보고, 손절 기준을 먼저 정한 뒤 진입**하는 용도입니다.
""")

with st.sidebar:
    st.header("자동화 옵션")
    config = load_config()

    auto_refresh = st.toggle("자동 새로고침", value=config.get("auto_refresh", False))
    refresh_minutes = st.number_input(
        "새로고침 간격(분)",
        min_value=5,
        max_value=120,
        value=int(config.get("refresh_minutes", 15)),
        step=5,
    )
    auto_save_snapshot = st.toggle("스냅샷 파일 자동 생성", value=config.get("auto_save_snapshot", True))

    if st.button("설정 저장"):
        save_config({
            "auto_refresh": auto_refresh,
            "refresh_minutes": refresh_minutes,
            "auto_save_snapshot": auto_save_snapshot,
        })
        st.success("설정 저장 완료")

    st.divider()
    st.write("- 미국/매크로: yfinance")
    st.write("- 한국 거래대금: pykrx")

    if st.button("전체 데이터 새로고침", type="primary"):
        fetch_us_market_data.clear()
        fetch_krx_value_top.clear()
        st.rerun()

if auto_refresh:
    st.info(f"자동 새로고침 활성화: {refresh_minutes}분 간격")
    st.markdown(f"<meta http-equiv='refresh' content='{int(refresh_minutes) * 60}'>", unsafe_allow_html=True)

us_df, us_values = fetch_us_market_data()

st.subheader("1. 미국 증시·매크로 자동 수집")
st.dataframe(us_df, use_container_width=True, hide_index=True)

st.subheader("2. 핵심 입력값 보정")
cols = st.columns(4)
manual_values = {}
names = [
    "Dow Jones", "S&P 500", "Nasdaq", "SOX", "NVIDIA", "Tesla",
    "VIX", "US 10Y Yield", "Dollar Index", "WTI Oil", "USD/KRW"
]

for i, name in enumerate(names):
    default = us_values.get(name)

    with cols[i % 4]:
        manual_values[name] = st.number_input(
            f"{name} 전일 대비(%)",
            value=0.0 if default is None else float(round(default, 2)),
            step=0.01,
            format="%.2f",
        )

st.subheader("3. 한국 거래대금 TOP 자동 연동")
market_choice = st.selectbox("시장", ["ALL", "KOSPI", "KOSDAQ"], index=0)
top_n = st.slider("거래대금 상위 조회 개수", 20, 100, 50, 10)

krx_df, krx_date, krx_err = fetch_krx_value_top(market_choice, top_n)

if krx_err:
    st.warning(f"한국 거래대금 데이터 로드 제한: {krx_err}")
else:
    st.caption(f"조회 기준일: {krx_date}")
    st.dataframe(krx_df, use_container_width=True, hide_index=True)

st.subheader("4. 매크로 방향")


def infer_trend(name):
    v = manual_values.get(name)

    if v is None or abs(v) < 0.05:
        return "flat"

    return "up" if v > 0 else "down"


m1, m2, m3, m4 = st.columns(4)

with m1:
    rate = st.selectbox(
        "미국 10년물 금리",
        ["down", "flat", "up"],
        index=["down", "flat", "up"].index(infer_trend("US 10Y Yield")),
    )

with m2:
    dollar = st.selectbox(
        "달러 인덱스",
        ["down", "flat", "up"],
        index=["down", "flat", "up"].index(infer_trend("Dollar Index")),
    )

with m3:
    oil = st.selectbox(
        "국제유가",
        ["down", "flat", "up"],
        index=["down", "flat", "up"].index(infer_trend("WTI Oil")),
    )

with m4:
    vix = st.selectbox(
        "VIX",
        ["down", "flat", "up"],
        index=["down", "flat", "up"].index(infer_trend("VIX")),
    )

st.subheader("5. 수급·뉴스·섹터")

f1, f2, f3 = st.columns(3)

with f1:
    foreign_flow = st.selectbox("외국인 수급 입력", ["순매수", "중립", "순매도"], index=1)

with f2:
    volume_strength = st.selectbox("체감 거래량", ["강함", "보통", "약함"], index=1)

with f3:
    korea_gap = st.selectbox("한국시장 갭 예상", ["갭상승", "보합", "갭하락"], index=1)

news_triggers = st.multiselect("뉴스 트리거", list(NEWS_TO_SECTOR.keys()))

sector_defaults = infer_sector_defaults(manual_values)
sector_inputs = {}
sector_cols = st.columns(4)

for i, sector in enumerate(SECTOR_STOCKS.keys()):
    default = sector_defaults.get(sector, "보합")

    with sector_cols[i % 4]:
        sector_inputs[sector] = st.selectbox(
            sector,
            ["강세", "보합", "약세"],
            index=["강세", "보합", "약세"].index(default),
        )

memo = st.text_area("오늘 메모", placeholder="예: 외국인 선물 매수, 방산 수출 뉴스, 조선 수주 뉴스 등")

score = 0
positives = []
negatives = []

for name in ["Dow Jones", "S&P 500", "Nasdaq", "SOX", "NVIDIA", "Tesla"]:
    v = manual_values.get(name)
    s = pct_score(v)
    score += s

    if s > 0:
        positives.append(f"{name} {v:+.2f}%")
    elif s < 0:
        negatives.append(f"{name} {v:+.2f}%")

for label, value in [("미국 10년물 금리", rate), ("달러 인덱스", dollar), ("VIX", vix)]:
    s = trend_score(value, good="down")
    score += s

    if s > 0:
        positives.append(f"{label} 하락")
    elif s < 0:
        negatives.append(f"{label} 상승")

if oil == "down":
    score += 0.5
    positives.append("유가 하락")
elif oil == "up":
    score -= 0.5
    negatives.append("유가 상승 부담")

if foreign_flow == "순매수":
    score += 1.5
    positives.append("외국인 순매수")
elif foreign_flow == "순매도":
    score -= 1.5
    negatives.append("외국인 순매도")

if volume_strength == "강함":
    score += 1
    positives.append("거래량 강함")
elif volume_strength == "약함":
    score -= 1
    negatives.append("거래량 약함")

if korea_gap == "갭상승":
    score += 0.5
    positives.append("한국시장 갭상승 예상")
elif korea_gap == "갭하락":
    score -= 0.5
    negatives.append("한국시장 갭하락 예상")

strong_sectors = []
weak_sectors = []

for sector, value in sector_inputs.items():
    s = sector_score(value)
    score += s

    if s > 0:
        strong_sectors.append(sector)
    elif s < 0:
        weak_sectors.append(sector)

for news in news_triggers:
    sector = NEWS_TO_SECTOR.get(news)

    if sector:
        score += 1
        positives.append(f"뉴스 트리거: {news}")

judgment, strategy = classify(score)
candidates = generate_candidates(strong_sectors, news_triggers)
ranked = rank_candidates_with_value(candidates, krx_df, score, weak_sectors)

ban_reasons = []

if manual_values.get("VIX", 0) > 25:
    ban_reasons.append("VIX 급등")

if manual_values.get("Nasdaq", 0) < -2:
    ban_reasons.append("나스닥 급락")

if foreign_flow == "순매도" and volume_strength == "약함":
    ban_reasons.append("외국인 순매도 + 거래량 약함")

st.subheader("6. 최종 분석")

r1, r2, r3, r4 = st.columns(4)
r1.metric("종합 점수", f"{score:.1f}")
r2.metric("판단", judgment)
r3.metric("강세 섹터", len(strong_sectors))
r4.metric("거래대금 연동 후보", 0 if ranked.empty else len(ranked))

st.markdown("### 🧠 오늘 한줄 가이드")

if ban_reasons:
    st.error(" / ".join(ban_reasons) + " → 매매 금지 또는 규모 축소")
elif score >= 8:
    st.success("강한 장입니다. 거래대금 상위와 강세 섹터가 겹치는 1~2개 후보만 압축하세요.")
elif score >= 4:
    st.info("선별 장입니다. 시초 추격을 피하고 10시 이후 거래대금 유지 여부를 확인하세요.")
elif score > -3:
    st.warning("관망 우위입니다. 단타 외 신규 진입은 제한하세요.")
else:
    st.error("Risk OFF입니다. 신규 매수 금지 구간입니다.")

st.markdown("### 📌 시장 판단")
st.write(f"**오늘 판단:** {judgment}")
st.write(f"**전략:** {strategy}")

left, right = st.columns(2)

with left:
    st.markdown("#### 긍정 요인")

    if positives:
        for p in positives:
            st.write(f"- {p}")
    else:
        st.write("- 뚜렷한 긍정 요인 없음")

with right:
    st.markdown("#### 부정 요인")

    if negatives:
        for n in negatives:
            st.write(f"- {n}")
    else:
        st.write("- 뚜렷한 부정 요인 없음")

st.markdown("### 🚀 거래대금 필터 반영 최종 후보")

if ranked.empty:
    st.warning("최종 후보가 없습니다. 강세 섹터/뉴스 트리거를 확인하거나 오늘은 관망이 적절합니다.")
else:
    st.dataframe(ranked, use_container_width=True, hide_index=True)
    top_pick = ranked.iloc[0]["종목명"]
    top_verdict = ranked.iloc[0]["판정"]

    if score >= 8 and top_verdict == "최우선":
        st.success(f"오늘 핵심 후보: {top_pick} / 조건: 강세장 + 거래대금 확인")
    elif score >= 4:
        st.info(f"오늘 관심 후보: {top_pick} / 조건: 10시 이후 거래량 유지 확인")
    else:
        st.warning(f"관찰 후보: {top_pick} / 시장 점수가 낮아 추격 매수 금지")

st.markdown("### ⏱️ 진입·리스크 가이드")

if score >= 8:
    st.write("- 진입: 시초 20~30% → 눌림 30% → 고점 돌파 확인 후 나머지")
    st.write("- 손절: -3% 또는 VWAP/당일 저점 이탈")
    st.write("- 익절: +5~8% 또는 거래량 둔화")
elif score >= 4:
    st.write("- 진입: 시초 추격 금지, 10시 이후 거래량 유지 종목만")
    st.write("- 손절: -2% 또는 5분봉 추세 이탈")
    st.write("- 익절: +3~5%")
elif score > -3:
    st.write("- 진입: 원칙적 관망. 단타는 거래대금 TOP 중 양봉 유지 종목만")
    st.write("- 손절: 짧게 -1.5~2%")
else:
    st.write("- 신규 매수 금지. 현금 비중 유지")

with st.expander("섹터별 확장 종목 풀"):
    sector_df = pd.DataFrame([
        {"섹터": k, "종목 풀": ", ".join(v)}
        for k, v in SECTOR_STOCKS.items()
    ])
    st.dataframe(sector_df, use_container_width=True, hide_index=True)

snapshot = build_snapshot(
    score=score,
    judgment=judgment,
    strategy=strategy,
    positives=positives,
    negatives=negatives,
    strong_sectors=strong_sectors,
    weak_sectors=weak_sectors,
    ranked=ranked,
    ban_reasons=ban_reasons,
    memo=memo,
)

if auto_save_snapshot:
    SNAPSHOT_FILE.write_text(snapshot, encoding="utf-8")

col_a, col_b, col_c = st.columns(3)

with col_a:
    if st.button("오늘 분석 기록 저장"):
        save_history({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "score": round(score, 1),
            "judgment": judgment,
            "top_pick": "" if ranked.empty else ranked.iloc[0]["종목명"],
            "strong_sectors": ", ".join(strong_sectors),
            "weak_sectors": ", ".join(weak_sectors),
            "memo": memo,
        })
        st.success("저장했습니다.")

with col_b:
    st.download_button(
        "오늘 요약 다운로드",
        data=snapshot,
        file_name="today_market_snapshot.md",
        mime="text/markdown",
    )

with col_c:
    if st.button("스냅샷 파일 다시 생성"):
        SNAPSHOT_FILE.write_text(snapshot, encoding="utf-8")
        st.success("today_market_snapshot.md 생성 완료")

st.subheader("7. 저장된 기록")

history = load_history()
st.dataframe(history, use_container_width=True, hide_index=True)

if not history.empty:
    csv = history.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "기록 CSV 다운로드",
        data=csv,
        file_name="market_history.csv",
        mime="text/csv",
    )
