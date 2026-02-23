import streamlit as st
import sqlite3
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re
import time

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")

# 모바일 대응 CSS
st.markdown("""
    <style>
    /* 메인 타이틀 크기 조절 */
    h1 { font-size: 1.8rem !important; }
    
    /* 입력 필드 레이블 폰트 크기 */
    .stTextInput label, .stTextArea label, .stSelectbox label {
        font-size: 0.9rem !important;
        font-weight: bold !important;
    }

    /* 모바일용 이미지 박스 및 뱃지 */
    .cal-img-box { 
        position: relative; width: 100%; aspect-ratio: 1/1.4; 
        overflow: hidden; border-radius: 8px; margin-top: 5px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
    
    .badge { 
        position: absolute; top: 5px; right: 5px; 
        background: rgba(0, 0, 0, 0.7); color: white; 
        padding: 2px 6px; border-radius: 4px; font-size: 10px; 
        z-index: 10; font-weight: bold;
    }

    /* 버튼 가독성 향상 */
    button[data-testid="stBaseButton-secondary"] {
        height: 2.2rem !important;
        padding: 0 !important;
    }
    button[data-testid="stBaseButton-secondary"] p {
        font-size: 0.8rem !important;
        text-align: center !important;
        width: 100%;
    }
    
    /* 탭 간격 조절 */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 12px; font-size: 0.9rem; }
    </style>
""", unsafe_allow_html=True)

st.title("🌈 PRISM")

# --- [데이터베이스 및 API 로직] ---
# (기존의 init_db, search_books, search_tmdb 등 함수는 동일하게 유지합니다.)
# (공간 절약을 위해 로직 핵심 부분 위주로 구성했습니다.)

if 'api_data' not in st.session_state: st.session_state.api_data = {}
DB_NAME = 'archive_prism_total_v5.db'

# --- [3. 팝업 함수 (모바일 최적화)] ---
@st.dialog("📋 기록 상세보기", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    # 상단 액션바
    c1, c2 = st.columns([1, 1])
    with c1: edit_mode = st.toggle("✏️ 수정 모드", key=f"tog_{item['id']}")
    with c2: 
        if st.button("🗑️ 기록 삭제", key=f"del_{item['id']}", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()

    st.divider()

    if edit_mode:
        with st.form(key=f"edit_form_{item['id']}"):
            n_img = st.text_input("🖼️ 이미지 URL", value=str(item.get('img_url', '')))
            n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
            n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
            
            c_rel, c_ven = st.columns(2)
            n_rel = c_rel.text_input("📅 제작일", value=str(item.get('rel_date', '')))
            n_venue = c_ven.text_input("📍 장소/플랫폼", value=str(item.get('venue', '')))
            
            n_view_date = st.date_input("🍿 감상일", value=pd.to_datetime(item.get('view_date')).date())
            n_note = st.text_area("💬 나의 감상", value=str(item.get('note', '')), height=150)
            
            if st.form_submit_button("💾 정보 업데이트", use_container_width=True):
                # SQL UPDATE 로직 실행 후 st.rerun()
                st.success("수정되었습니다.")
                st.rerun()
    else:
        # 조회 모드 (모바일 수직 배치)
        if item.get('img_url'):
            st.image(item['img_url'], use_container_width=True)
        
        st.subheader(item.get('title'))
        st.caption(f"**{item.get('category')}** | {item.get('creator')}")
        st.info(f"📅 {item.get('rel_date')} | 📍 {item.get('venue')}")
        st.markdown(f"#### 🍿 {item.get('view_date')}")
        
        if item.get('note'):
            st.success(f"**나의 감상**\n\n{item.get('note')}")

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ 기록하기", "📂 아카이브"])

with tab1:
    category = st.radio("CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    
    # 검색 결과 및 가져오기 로직 (생략 - 기존 코드와 동일)
    
    st.divider()
    # 모바일은 한 줄에 하나씩 배치 (cl, cr 구분 없이 순차 배치)
    data = st.session_state.get('api_data', {})
    
    img_url_val = st.text_input("🖼️ 이미지 URL", value=data.get('img', ''))
    if img_url_val: st.image(img_url_val, width=150)
    
    title = st.text_input("📌 작품 제목", value=data.get('title', ''))
    creator = st.text_input("👤 창작자/아티스트", value=data.get('creator', ''))
    
    col1, col2 = st.columns(2)
    rel_date = col1.text_input("📅 공개/발매일", value=data.get('date', str(date.today())))
    venue = col2.text_input("📍 장소/플랫폼", value=data.get('venue', ''))
    
    view_date = st.date_input("🍿 감상일 선택", value=date.today())
    note = st.text_area("💬 감상평", height=150)
    
    if st.button("✅ 아카이브 저장", use_container_width=True, type="primary"):
        # 저장 로직 및 구글 시트 백업 실행
        st.success("기록이 저장되었습니다!")
        time.sleep(0.5)
        st.rerun()

with tab2:
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    if not all_df.empty:
        # 상단 통계 요약 (모바일용)
        st.caption(f"총 {len(all_df)}개의 기록이 보관 중입니다.")
        
        cat_list = ["ALL", "BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sub_tabs = st.tabs([f"{c}" for c in cat_list])

        for idx, c_name in enumerate(cat_list):
            with sub_tabs[idx]:
                df = all_df if c_name == "ALL" else all_df[all_df['category'] == c_name]
                df['v_dt'] = pd.to_datetime(df['view_date'], errors='coerce')
                
                # 정렬 및 출력 (모바일은 2~3열이 적당함)
                sorted_df = df.sort_values('v_dt', ascending=False)
                items = sorted_df.to_dict('records')
                
                # 모바일 화면 공간상 2열(또는 3열)로 배치
                cols_per_row = 3
                for i in range(0, len(items), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for j in range(cols_per_row):
                        if i + j < len(items):
                            row = items[i + j]
                            with cols[j]:
                                # 뱃지 날짜 처리
                                raw_v = str(row.get('view_date') or "")
                                badge_txt = raw_v[-5:] if len(raw_v) > 5 else "미상"
                                
                                st.markdown(f'''
                                    <div class="cal-img-box">
                                        <div class="badge">{badge_txt}</div>
                                        <img src="{row["img_url"]}">
                                    </div>
                                ''', unsafe_allow_html=True)
                                
                                short_title = row['title'][:6] + ".." if len(row['title']) > 6 else row['title']
                                if st.button(short_title, key=f"btn_{c_name}_{row['id']}", use_container_width=True):
                                    show_details(row)
