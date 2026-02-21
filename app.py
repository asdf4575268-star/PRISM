import streamlit as st
import sqlite3
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import date, datetime
import time

# --- [1. 페이지 설정 및 초기화] ---
st.set_page_config(layout="wide", page_title="PRISM")

# 데이터베이스 초기화 (안정성 강화)
DB_NAME = 'archive_prism_total_v4.db'
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# 세션 상태 관리
if 'api_data' not in st.session_state: st.session_state.api_data = {}

# --- [2. 사이드바: 커스텀 설정 및 메뉴] ---
with st.sidebar:
    st.header("🎨 STYLE & TOOLS")
    
    # 글자 크기 설정 (사용자 요청 기본값 반영)
    st.subheader("Text Size Control")
    sz_title = st.slider("활동명(Title) 크기", 10, 200, 90)
    sz_date = st.slider("날짜(Date) 크기", 10, 100, 30)
    sz_num = st.slider("숫자/단위 크기", 10, 150, 60)
    
    # 폰트 선택
    font_choice = st.selectbox("폰트 선택", ["Kirang Haerang", "Jolly Lodger", "Lacquer"])
    
    st.divider()
    st.subheader("📂 OCR & MENU")
    st.info("이미지 분석(OCR) 기능은 여기에 구성됩니다.")
    # 추후 OCR 기능 확장 시 여기에 코드 추가

# --- [3. 동적 CSS 주입] ---
# 구글 폰트 로드 및 사이드바 값 연동
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    
    html, body, [data-testid="stMarkdownContainer"] {{
        font-family: '{font_choice}', system-ui;
    }}
    
    /* 사용자 설정 크기 반영 클래스 */
    .custom-title {{ font-size: {sz_title}px !important; font-weight: bold; line-height: 1.1; }}
    .custom-date {{ font-size: {sz_date}px !important; color: gray; }}
    .custom-num {{ font-size: {sz_num}px !important; color: #ff4b4b; }}
    
    /* 카드 레이아웃 */
    .cal-img-box {{ 
        position: relative; width: 100%; aspect-ratio: 1/1; 
        overflow: hidden; border-radius: 8px; margin-bottom: 5px;
    }}
    .cal-img-box img {{ width: 100%; height: 100%; object-fit: cover; transition: 0.3s; }}
    .cal-img-box:hover img {{ transform: scale(1.05); }}
    
    .badge {{
        position: absolute; top: 5px; padding: 2px 8px;
        border-radius: 4px; font-size: 12px; z-index: 10; color: white;
    }}
    .badge-left {{ left: 5px; background: rgba(0,0,0,0.7); }}
    .badge-right {{ right: 5px; background: rgba(255,75,75,0.8); }}
    </style>
""", unsafe_allow_html=True)

# --- [4. 핵심 유틸리티 함수] ---
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url).json().get("results", [])
        return [{'display_name': f"🎵 {m.get('trackName', 'Unknown')}", 'title': m.get('trackName'), 'creator': m.get('artistName'), 'date': m.get('releaseDate', '')[:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'url': m.get('trackViewUrl')} for m in res]
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key=6e7c55b6259b7731655033f783f3fc5b&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

# 텍스트 내 KM/BPM 처리 및 숫자 강조
def format_note(text):
    if not text: return ""
    text = text.replace("KM", "km").replace("BPM", "bpm")
    # 숫자를 찾아 <span class="custom-num">으로 감싸기 (Regex)
    import re
    text = re.sub(r'(\d+)', r'<span class="custom-num">\1</span>', text)
    return text

# --- [5. 상세 정보 팝업 (조회/수정)] ---
@st.dialog("📋 ARCHIVE DETAIL", width="large")
def show_details(item):
    t_col1, _, t_col2 = st.columns([0.2, 0.6, 0.2])
    with t_col1:
        if st.button("🗑️ 삭제", key=f"del_{item['id']}"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()
    with t_col2:
        edit_mode = st.toggle("✏️ 수정", key=f"edit_{item['id']}")

    st.divider()
    col_img, col_txt = st.columns([0.4, 0.6])

    with col_img:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
        st.caption(f"Category: {item['category']}")

    with col_txt:
        if edit_mode:
            with st.form(f"f_edit_{item['id']}"):
                n_title = st.text_input("제목", value=item['title'])
                n_creator = st.text_input("창작자", value=item['creator'])
                n_note = st.text_area("감상", value=item['note'])
                if st.form_submit_button("💾 수정사항 저장"):
                    processed_note = n_note.replace("KM", "km").replace("BPM", "bpm")
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE archive SET title=?, creator=?, note=? WHERE id=?", (n_title, n_creator, processed_note, item['id']))
                    st.success("수정되었습니다.")
                    st.rerun()
        else:
            st.markdown(f'<div class="custom-title">{item["title"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="custom-date">📅 {item["view_date"]} | {item["creator"]}</div>', unsafe_allow_html=True)
            st.divider()
            if item.get('brief'): st.success(item['brief'])
            st.markdown(format_note(item['note']), unsafe_allow_html=True)

# --- [6. 메인 탭 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_q = st.text_input("검색어를 입력하세요")
    
    if search_q:
        # 검색 로직 (기존 기능 유지)
        if category == "BOOKS":
            res = search_books(search_q)
            if res:
                sel = st.selectbox("책 선택", [b['title'] for b in res])
                if st.button("가져오기"):
                    target = next(b for b in res if b['title'] == sel)
                    st.session_state.api_data = {'title': target['title'], 'creator': target['authors'][0], 'img': target['thumbnail'], 'date': target['datetime'][:10]}
                    st.rerun()
        # (기타 카테고리 검색 로직은 기존과 동일하므로 생략하거나 통합 유지 가능)

    st.divider()
    # 입력 폼
    c1, c2 = st.columns([0.4, 0.6])
    with c1:
        title = st.text_input("Title", value=st.session_state.api_data.get('title', ''))
        creator = st.text_input("Creator", value=st.session_state.api_data.get('creator', ''))
        img_url = st.text_input("Image URL", value=st.session_state.api_data.get('img', ''))
        if img_url: st.image(img_url, width=200)
    with c2:
        v_date = st.date_input("감상일", value=date.today())
        note = st.text_area("Note (KM, BPM은 자동 소문자 변환)", height=200)
        
        if st.button("✅ 최종 저장", use_container_width=True):
            processed_note = note.replace("KM", "km").replace("BPM", "bpm")
            # 로컬 DB 저장
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, note, img_url, view_date) VALUES (?,?,?,?,?,?)",
                             (category, title, creator, processed_note, img_url, str(v_date)))
            
            # 구글 폼 백업 (데이터 유실 방지)
            try:
                BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
                payload = {"entry.898076783": title, "entry.345368346": creator, "entry.891180756": processed_note, "entry.2056153041": img_url}
                requests.post(BACKUP_URL, data=payload, timeout=5)
            except: st.warning("구글 백업에 실패했습니다. (로컬에는 저장됨)")
            
            st.success("저장 완료!")
            st.session_state.api_data = {}
            st.rerun()

with tab2:
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)
    
    if all_df.empty:
        st.info("기록이 없습니다.")
    else:
        # 카테고리 필터
        target_cat = st.multiselect("필터", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], default=["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"])
        filtered_df = all_df[all_df['category'].isin(target_cat)]
        
        # 그리드 레이아웃
        items = filtered_df.to_dict('records')
        for i in range(0, len(items), 6):
            cols = st.columns(6)
            for j in range(6):
                if i + j < len(items):
                    item = items[i + j]
                    with cols[j]:
                        v_day = item['view_date'][-2:] # '일'만 추출
                        st.markdown(f'''
                            <div class="cal-img-box">
                                <div class="badge badge-left">{item['category']}</div>
                                <div class="badge badge-right">{v_day}일</div>
                                <img src="{item['img_url'] if item['img_url'] else 'https://via.placeholder.com/150'}">
                            </div>
                        ''', unsafe_allow_html=True)
                        if st.button(f"{item['title'][:8]}", key=f"btn_{item['id']}", use_container_width=True):
                            show_details(item)
