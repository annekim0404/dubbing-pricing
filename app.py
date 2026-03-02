import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import re

st.set_page_config(page_title="가우디오랩 더빙 가격 산정기", page_icon="🎙️", layout="wide")

# 스타일
st.markdown(
    """
    <style>
    .block-container {
        max-width: 1600px;
        margin: 0 auto;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    h1 {
        font-size: 2rem !important;
        margin-bottom: 1.5rem !important;
        margin-top: -4rem !important;
        text-align: center;
        white-space: nowrap;
    }
    h2, [data-testid="stSubheader"] {
        font-size: 0.8rem !important;
        text-align: center;
        margin-top: 0.3rem !important;
        margin-bottom: -0.6rem !important;
    }
    h4 {
        font-size: 0.9rem !important;
        margin-top: 0.6rem !important;
        margin-bottom: 0.05rem !important;
    }
    .stSelectbox label p {
        font-size: 13px !important;
    }
    .stSelectbox {
        margin-bottom: -0.5rem;
    }
    .stSelectbox [data-baseweb="select"] {
        min-width: 100% !important;
    }
    .stSelectbox [data-baseweb="select"] span {
        white-space: normal !important;
        word-break: break-word !important;
        font-size: 11px !important;
    }
    .stNumberInput label p {
        font-size: 13px !important;
    }
    .stNumberInput {
        margin-bottom: -0.5rem;
    }
    hr {
        margin-top: 0.3rem !important;
        margin-bottom: 0.3rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("가우디오랩 더빙 가격 산정기")

# ---------------------------------------------------------------------------
# 가격 영향 요인 정의
# ---------------------------------------------------------------------------
FACTORS = [
    {
        "category": "연기 / 기술",
        "name": "연기력 난이도",
        "description": "얼마나 다양한 감정을 어느정도의 깊이로 표현해야 하는가",
        "weight": 0.20,
        "scores": {
            1: "단순 정보 전달 (예: 기업 소개 영상, 건조한 다큐멘터리, ARS, 기본 교육용 내레이션)",
            2: "가벼운 감정 표현 및 대화형 톤 (예: 밝은 톤의 홍보/광고 영상, 유튜브 콘텐츠, 가벼운 대화형 e러닝)",
            3: "일반적인 생활 연기 (일반적인 현대극 드라마, 로맨스물, 시트콤, 오디오북(소설))",
            4: "역동적이고 짙은 감정 연기 (스릴러, 액션물, 갈등이 고조되는 법정/의학 드라마, 개성이 강한 애니메이션/게임 캐릭터)",
            5: "극한의 감정 표현 (하드코어 호러, 재난물, 처절한 전투씬이 많은 장르물)",
        },
    },
    {
        "category": "연기 / 기술",
        "name": "립싱크 난이도",
        "description": "입이 많이 나와서 싱크에 공수가 많이 드는지 여부",
        "weight": 0.10,
        "scores": {
            1: "영상의 10% 이하에 세밀한 립싱크 필요",
            2: "영상의 11-25%에 세밀한 립싱크 필요",
            3: "영상의 26-40%에 세밀한 립싱크 필요",
            4: "영상의 41-65%에 세밀한 립싱크 필요",
            5: "영상의 66% 이상에 세밀한 립싱크 필요",
        },
    },
    {
        "category": "연기 / 기술",
        "name": "음질 난이도",
        "description": "DME SEP 등 기존 영상의 음질 수준에 따른 난이도",
        "weight": 0.15,
        "scores": {
            1: "클린한 D 트랙이 따로 제공되는 경우",
            3: "일반 퀄리티의 D 트랙이 따로 제공되는 경우",
            5: "원본의 음질이 좋지 않거나 D트랙이 따로 제공되지 않는 경우",
        },
    },
    {
        "category": "콘텐츠 특성",
        "name": "시리즈 vs. 단편",
        "description": "동일하게 10시간 작업해도 한시간짜리 시리즈물 10편과 단편 10편은 공수가 다름",
        "weight": 0.10,
        "scores": {
            1: "에피소드 10개 이상의 시리즈물",
            3: "에피소드 3개 이상의 시리즈물",
            5: "단편 영화 혹은 에피소드",
        },
    },
    {
        "category": "콘텐츠 특성",
        "name": "등장 인물 수",
        "description": "등장 인물 수에 따른 난이도",
        "weight": 0.10,
        "scores": {
            1: "1명",
            2: "2~4명",
            3: "5~10명",
            4: "20명 이상",
            5: "50명 이상",
        },
    },
    {
        "category": "콘텐츠 특성",
        "name": "특수 목소리 구현 필요성",
        "description": "아역, 노인 등 특수 목소리 — 특정 발성이 어려운 점 감안",
        "weight": 0.05,
        "scores": {
            0: "해당 사항 없음",
            1: "아역/노인 캐릭터 1명 등장",
            3: "아역/노인 캐릭터 3명 이상 등장",
            5: "아역/노인 캐릭터 5명 이상 등장",
        },
    },
    {
        "category": "언어 특성",
        "name": "Input/Output 언어 종류",
        "description": "희귀 언어 여부 (우선 한/일/영 기준)",
        "weight": 0.20,
        "scores": {
            1: "input 한국어 → output 영어",
            2: "input 일본어 → output 영어",
            3: "input 한국어 → output 일본어",
            4: "input 기타 언어 → output 영어/일어",
            5: "input 기타 언어 → output 기타 언어",
        },
    },
    {
        "category": "언어 특성",
        "name": "번역 난이도",
        "description": "의학, 법률, IT 등 전문 용어 비중 / 문화적 전문성",
        "weight": 0.05,
        "scores": {
            0: "해당 사항 없음",
            1: "전문 용어 비중 1-10%",
            2: "전문 용어 비중 11-20%",
            3: "전문 용어 비중 21-30%",
            4: "전문 용어 비중 31-40%",
            5: "전문 용어 비중 41% 이상",
        },
    },
    {
        "category": "언어 특성",
        "name": "발음/억양 난이도",
        "description": "특정 지역 방언, 나이, 시대적 말투 구현 필요성",
        "weight": 0.05,
        "scores": {
            0: "해당 사항 없음",
            1: "특수 발음/억양 비중 1-10%",
            2: "특수 발음/억양 비중 11-20%",
            3: "특수 발음/억양 비중 21-30%",
            4: "특수 발음/억양 비중 31-40%",
            5: "특수 발음/억양 비중 41% 이상",
        },
    },
]

SONG_DUB_LEVELS = {
    0: ("없음", 0),
    1: ("1단계 (하): 단순한 동요, 코러스, 박자가 평이한 곡", 70),
    2: ("2단계 (중): 보편적인 캐릭터 송, 일반 가요풍의 삽입곡", 100),
    3: ("3단계 (상): 고음역대, 화려한 기교가 필요한 뮤지컬, 랩 등", 150),
}

ONSCREEN_TEXT_COST_PER_MIN = 10  # $

TIERS = [
    (1.0, 21, 30),
    (2.0, 31, 40),
    (3.0, 41, 50),
    (4.0, 51, 60),
    (5.0, 61, 70),
]

def score_to_tier(score: float):
    for tier_score, low, high in TIERS:
        if score <= tier_score:
            return tier_score, low, high
    return 5.0, 61, 70


# ---------------------------------------------------------------------------
# 좌우 2단 레이아웃 (왼쪽: 입력, 오른쪽: 결과)
# gap=200px은 Streamlit columns에서 직접 지원하지 않으므로 빈 컬럼으로 구현
# ---------------------------------------------------------------------------
left_col, gap_col, right_col = st.columns([5, 1, 3])

# ===========================================================================
# 왼쪽: 입력 항목
# ===========================================================================
with left_col:
    st.subheader("1. 단가 산정 기준")

    selections: dict[str, int] = {}
    current_category = None
    col_idx = 0

    for factor in FACTORS:
        cat = factor["category"]
        if cat != current_category:
            current_category = cat
            st.markdown(f"#### {cat}")
            cols = st.columns(3)
            col_idx = 0

        with cols[col_idx % 3]:
            score_options = sorted(factor["scores"].keys())
            labels = [f"{s}점 — {factor['scores'][s]}" for s in score_options]

            chosen_label = st.selectbox(
                f"**{factor['name']}** ({factor['weight']:.0%})",
                labels,
                index=0,
                help=factor["description"],
                key=factor["name"],
            )
            chosen_score = score_options[labels.index(chosen_label)]
            selections[factor["name"]] = chosen_score
        col_idx += 1

    # -------------------------------------------------------------------
    st.markdown("---")
    st.subheader("2. 특수 작업")

    row2 = st.columns(3)
    with row2[0]:
        song_labels = [f"{k} — {v[0]}" for k, v in SONG_DUB_LEVELS.items()]
        song_choice = st.selectbox(
            "**노래 더빙** (난이도)",
            song_labels,
            index=0,
            help="노래를 나레이션이 아닌 더빙으로 처리할 경우 난이도를 선택하세요.",
        )
        song_level = int(song_choice.split(" — ")[0])
        song_cost_per_min = SONG_DUB_LEVELS[song_level][1]

    with row2[1]:
        song_duration_min = st.number_input(
            "**총 노래 길이 (분)**",
            min_value=0.0,
            value=0.0,
            step=0.5,
            help="더빙 대상 노래의 총 길이(분)",
            disabled=(song_level == 0),
        )
        song_price = song_cost_per_min * song_duration_min
        if song_level > 0 and song_duration_min > 0:
            st.markdown(f"<div style='font-size:0.85rem; font-weight:600; color:#0969da; margin-top:-0.8rem;'>추가 비용: ${int(song_price):,}</div>", unsafe_allow_html=True)

    with row2[2]:
        onscreen_text = st.selectbox(
            "**온스크린 텍스트 더빙**",
            ["N — 해당 없음", "Y — 적용"],
            index=0,
            help="영상 내 텍스트를 성우 음성으로 추가 번역/녹음. 적용 시 분당 $10 추가.",
        )
        onscreen_yes = onscreen_text.startswith("Y")

    row3 = st.columns(3)
    with row3[0]:
        rush_days = st.number_input(
            "**긴급 작업 — 납기 단축 일수**",
            min_value=0,
            value=0,
            step=1,
            help="표준 납기일(TAT) 기준, 하루 앞당길 때마다 전체 비용의 10%씩 할증",
        )
    with row3[1]:
        rush_pct = rush_days * 10
        if rush_days > 0:
            st.markdown(f"<div style='padding-top:2rem; font-size:0.9rem; font-weight:600; color:#d9534f;'>+{rush_pct}% 할증 적용</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='padding-top:2rem; font-size:0.9rem; color:#888;'>할증 없음</div>", unsafe_allow_html=True)

# ===========================================================================
# 오른쪽: 산출 결과
# ===========================================================================
with right_col:
    st.subheader("3. 산출 결과")

    # 영상 분량은 산출결과 영역에서 입력받되, 계산에 먼저 사용하기 위해 session_state 활용
    if "duration_input" not in st.session_state:
        st.session_state["duration_input"] = 60
    duration_min = st.session_state["duration_input"]

    # 계산
    weighted_sum = 0.0
    breakdown_rows = []
    for factor in FACTORS:
        s = selections[factor["name"]]
        w = factor["weight"]
        contrib = s * w
        weighted_sum += contrib
        breakdown_rows.append({"항목": factor["name"], "점수": s, "가중치": f"{w:.0%}", "기여값": round(contrib, 3)})

    tier_score, price_low, price_high = score_to_tier(weighted_sum)

    base_low = price_low * duration_min
    base_high = price_high * duration_min

    extra_song = song_cost_per_min * song_duration_min if song_level > 0 else 0
    extra_onscreen = ONSCREEN_TEXT_COST_PER_MIN * duration_min if onscreen_yes else 0
    extra_total = extra_song + extra_onscreen

    subtotal_low = base_low + extra_total
    subtotal_high = base_high + extra_total
    rush_rate = rush_days * 0.10
    total_low = int(subtotal_low * (1 + rush_rate))
    total_high = int(subtotal_high * (1 + rush_rate))

    card_html = f"""
    <div style="
        background: #e8f4fd;
        border-radius: 14px;
        padding: 1.2rem 1rem;
        margin: 0.3rem 0;
        border: 1px solid #b8ddf0;
        text-align: center;
    ">
        <div style="margin-bottom:0.8rem;">
            <div style="font-size:0.75rem; color:#666; margin-bottom:2px;">가중 합산 점수</div>
            <div style="font-size:1.4rem; font-weight:700; color:#1a1a2e;">{weighted_sum:.2f} <span style="font-size:0.8rem; color:#999;">/ 5.00</span></div>
        </div>
        <div style="margin-bottom:0.8rem;">
            <div style="font-size:0.75rem; color:#666; margin-bottom:2px;">Pricing Tier</div>
            <div style="font-size:1.4rem; font-weight:700; color:#1a1a2e;">{int(tier_score)}</div>
        </div>
        <div style="margin-bottom:0.8rem;">
            <div style="font-size:0.75rem; color:#666; margin-bottom:2px;">분당 가격 범위</div>
            <div style="font-size:1.4rem; font-weight:700; color:#1a1a2e;">${price_low} – ${price_high}</div>
        </div>
        <hr style="border:none; border-top:1px solid #b8ddf0; margin:0.6rem 0;">
        <div style="font-size:1.1rem; font-weight:700; color:#1a1a2e;">
            예상 총 비용
        </div>
        <div style="font-size:1.3rem; font-weight:700; color:#0969da; margin-top:0.3rem;">
            ${total_low:,} – ${total_high:,}
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

    duration_min = st.number_input("**영상 분량 (분)**", min_value=1, value=60, step=1, key="duration_input")

    # --- 시트 저장 ---
    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
    content_name = st.text_input("**콘텐츠 이름**", placeholder="예: Nosy's Inspiration", key="content_name")

    btn_col1, btn_col2 = st.columns([1, 2])
    with btn_col1:
        is_final = st.checkbox("최종", key="is_final")
    with btn_col2:
        save_clicked = st.button("📊 시트에 저장", disabled=(not content_name))

    if save_clicked:
        try:
            # 서비스 계정 인증
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds_path = os.path.join(os.path.dirname(__file__), "gaudio-dubbing-price-111e0a56f688.json")
            if os.path.exists(creds_path):
                creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
            else:
                # Streamlit Cloud: secrets에서 로드
                creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"], strict=False)
                if "private_key" in creds_dict:
                    pk = creds_dict["private_key"]
                    # 리터럴 \n(백슬래시+n)을 실제 줄바꿈으로 변환
                    pk = pk.replace("\\n", "\n")
                    # 헤더/푸터 복원
                    pk = re.sub(r'-----BEGIN\s+PRIVATE\s+KEY-----', '-----BEGIN PRIVATE KEY-----', pk)
                    pk = re.sub(r'-----END\s+PRIVATE\s+KEY-----', '-----END PRIVATE KEY-----', pk)
                    creds_dict["private_key"] = pk
                creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)

            gc = gspread.authorize(creds)
            sh = gc.open_by_key("1CbSzVgQBD1HAa_pnGASNB76vb2fyJ_eDG3mXqt6Cxqs")
            ws = sh.worksheet("log")

            # 다음 빈 열 찾기 (Row 1 기준)
            header_row = ws.row_values(1)
            next_col = len(header_row) + 1

            # 데이터 구성 (log 시트 Row 1~16에 맞춤)
            song_price = song_cost_per_min * song_duration_min if song_level > 0 else 0
            col_data = [
                f"{content_name} (최종)" if is_final else content_name,  # Row 1: 콘텐츠 이름
                str(selections["연기력 난이도"]),                      # Row 2: 연기력
                str(selections["립싱크 난이도"]),                      # Row 3: 립싱크
                str(selections["음질 난이도"]),                        # Row 4: 음질
                str(selections["시리즈 vs. 단편"]),                   # Row 5: 시리즈
                str(selections["등장 인물 수"]),                       # Row 6: 등장인물
                str(selections["특수 목소리 구현 필요성"]),             # Row 7: 특수목소리
                str(selections["Input/Output 언어 종류"]),            # Row 8: 언어종류
                str(selections["번역 난이도"]),                        # Row 9: 번역
                str(selections["발음/억양 난이도"]),                   # Row 10: 발음/억양
                f"{song_level}단계 (${int(song_price)})" if song_level > 0 else "없음",  # Row 11: 노래 더빙
                "Y" if onscreen_yes else "N",                        # Row 12: 온스크린 텍스트
                f"{rush_days}일" if rush_days > 0 else "없음",       # Row 13: 긴급작업
                str(int(tier_score)),                                # Row 14: TIER
                f"{duration_min}분",                                 # Row 15: 영상 길이
                f"${total_low:,} – ${total_high:,}",                 # Row 16: 최종 가격 범위
            ]

            # 열에 데이터 쓰기
            cells = []
            for i, val in enumerate(col_data):
                cells.append(gspread.Cell(row=i + 1, col=next_col, value=val))
            ws.update_cells(cells)

            st.success(f"'{content_name}' 저장 완료!")
        except Exception as e:
            st.error(f"저장 실패: {e}")

    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
    with st.expander("점수 상세 내역"):
        df = pd.DataFrame(breakdown_rows)
        # 숫자를 문자열로 변환하여 왼쪽 정렬
        df["점수"] = df["점수"].astype(str)
        df["기여값"] = df["기여값"].astype(str)
        st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("Pricing Tier 참조표"):
        tier_html = """
        <table style="width:100%; border-collapse:collapse; text-align:center;">
            <thead>
                <tr style="border-bottom:2px solid #ddd;">
                    <th style="padding:6px; text-align:center;">Tier</th>
                    <th style="padding:6px; text-align:center;">Price Range ($)</th>
                </tr>
            </thead>
            <tbody>
        """
        for t, lo, hi in TIERS:
            tier_html += f'<tr style="border-bottom:1px solid #eee;"><td style="padding:6px; text-align:center;">{int(t)}</td><td style="padding:6px; text-align:center;">{lo} – {hi}</td></tr>'
        tier_html += "</tbody></table>"
        st.markdown(tier_html, unsafe_allow_html=True)
