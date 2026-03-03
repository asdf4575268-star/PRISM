import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
import time
from bs4 import BeautifulSoup
from supabase import create_client, Client

# --- [1. 설정 및 UI 스타일링] ---
st.set_page_config(
    layout="wide", 
    page_title="PRISM ARCHIVE",
    page_icon="🌈",
    initial_sidebar_state="collapsed"
)

# API 키 및 DB 설정
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
DB_NAME = 'archive_prism_total_v5.db'
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 고정 캔버스 및 레이아웃 스타일링
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
        html, body, [data-testid="stAppViewContainer"] { font-family: 'Inter', sans-serif; background-color: #0E1117; }
        
        /* 로고 복구 */
        .logo-text { 
            font-size: 2.8rem; font-weight: 800; 
            background: linear-gradient(90deg, #FF0000, #FF7F00, #FFFF00, #00FF00, #0000FF, #4B0082, #8B00FF);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem; letter-spacing: -1px;
        }
        
        /* 고정형 캔버스 느낌을 위한 카드 스타일 */
        .cal-img-box { 
            position: relative; width: 100%; aspect-ratio: 1/1.44; 
            overflow: hidden; border-radius: 4px; margin-top: 5px; 
            background: #1a1a1a; transition: transform 0.2s;
            border: 1px solid #333;
        }
        .cal-img-box:hover { transform: translateY(-5px); border-color: #666; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .music-tab-style { aspect-ratio: 1/1 !important; border-radius: 50% !important; }
        
        .badge-cat { position: absolute; top: 5px; left: 5px; background: rgba(0,0,0,0.8); color: #eee; padding: 2px 6px; border-radius: 3px; font-size: 9px; font-weight: bold; }
        .badge-date { position: absolute; bottom: 5px; right: 5px; background: rgba(255,255,255,0.9); color: #000; padding: 1px 5px; border-radius: 3px; font-size: 10px; font-weight: bold; }
        
        /* 카테고리 탭 카운트 스타일 */
        .tab-count { font-size: 0.8rem; color: #888; margin-left: 4px; }
    </style>
""", unsafe_allow_html=True)

# --- [2. 기능 함수] ---
@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                     rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, 
                     img_url TEXT, img_url2 TEXT, save_date TEXT, view_date TEXT)''')
    conn.commit()

init_db()

@st.cache_data(ttl=60)
def get_all_data():
    conn = get_connection()
    return pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

# 기사 스크랩 (URL 기반)
def scrape_article(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        title = soup.find('meta', property='og:title')['content'] if soup.find('meta', property='og:title') else soup.title.string
        img = soup.find('meta', property='og:image')['content'] if soup.find('meta', property='og:image') else ""
        site = soup.find('meta', property='og:site_name')['content'] if soup.find('meta', property='og:site_name') else ""
        return {"title": title, "img": img, "venue": site, "summary": url}
    except Exception as e:
        return None

# --- [3. 메인 화면] ---
st.markdown('<div class="logo-text">PRISM ARCHIVE</div>', unsafe_allow_html=True)

# 세션 상태 관리
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "api_data" not in st.session_state: st.session_state.api_data = {}

# 사이드바 (관리자 및 백업)
with st.sidebar:
    if not st.session_state.is_logged_in:
        pw = st.text_input("Admin Password", type="password")
        if pw == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.is_logged_in = True; st.rerun()
    else:
        st.success("Admin Active")
        if st.button("📤 Cloud Backup", use_container_width=True):
            # (Supabase 백업 로직 생략 - 이전과 동일)
            st.toast("Backup triggered")

# 데이터 로드 및 통계 계산
df = get_all_data()
cat_list = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "ARTICLES"]
counts = {c: len(df[df['category'] == c]) for c in cat_list}

# 탭 구성
tabs = st.tabs([f"📅 ALL ({len(df)})"] + [f"{c} ({counts[c]})" for c in cat_list] + (["🖋️ WRITE"] if st.session_state.is_logged_in else []))

# --- [탭 1: ALL - 연도별/월별 목록 복구] ---
with tabs[0]:
    if df.empty:
        st.info("기록이 없습니다.")
    else:
        df['v_dt'] = pd.to_datetime(df['view_date'])
        df['year'] = df['v_dt'].dt.year
        df['month'] = df['v_dt'].dt.month
        
        years = sorted(df['year'].unique(), reverse=True)
        for y in years:
            with st.expander(f"📂 {y}년 기록", expanded=True):
                y_df = df[df['year'] == y]
                months = sorted(y_df['month'].unique(), reverse=True)
                for m in months:
                    st.markdown(f"#### 🗓️ {m}월")
                    m_df = y_df[y_df['month'] == m]
                    cols = st.columns(6)
                    for idx, row in enumerate(m_df.to_dict('records')):
                        with cols[idx % 6]:
                            m_style = "music-tab-style" if row['category'] == "MUSIC" else ""
                            st.markdown(f'''
                                <div class="cal-img-box {m_style}">
                                    <div class="badge-cat">{row["category"]}</div>
                                    <div class="badge-date">{row["v_dt"].day}</div>
                                    <img src="{row["img_url"] if row["img_url"] else "https://via.placeholder.com/300x450?text=No+Image"}">
                                </div>
                            ''', unsafe_allow_html=True)
                            if st.button(row['title'][:10], key=f"all_{row['id']}", use_container_width=True):
                                # 상세 보기 다이얼로그 호출 (생략된 세부 함수는 이전 버전과 동일)
                                pass

# --- [카테고리별 탭] ---
for i, c_name in enumerate(cat_list):
    with tabs[i+1]:
        c_df = df[df['category'] == c_name]
        if c_df.empty:
            st.info(f"{c_name} 카테고리에 기록이 없습니다.")
        else:
            cols = st.columns(6)
            for idx, row in enumerate(c_df.to_dict('records')):
                with cols[idx % 6]:
                    m_style = "music-tab-style" if c_name == "MUSIC" else ""
                    st.markdown(f'<div class="cal-img-box {m_style}"><div class="badge-date">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                    if st.button(row['title'][:10], key=f"cat_{c_name}_{row['id']}", use_container_width=True):
                        pass

# --- [탭: WRITE - 기사 스크랩 기능 추가] ---
if st.session_state.is_logged_in:
    with tabs[-1]:
        write_cat = st.radio("CATEGORY", cat_list, horizontal=True)
        
        # 스크랩 영역
        with st.container(border=True):
            if write_cat == "ARTICLES":
                article_url = st.text_input("🔗 기사 URL 입력")
                if st.button("📰 기사 정보 가져오기"):
                    res = scrape_article(article_url)
                    if res:
                        st.session_state.api_data = {'title': res['title'], 'img': res['img'], 'venue': res['venue'], 'summary': res['summary'], 'creator': '뉴스/칼럼'}
                        st.rerun()
            else:
                sq = st.text_input(f"🔍 {write_cat} 검색어 입력")
                if st.button("✨ 데이터 스크랩"):
                    # 기존 TMDB, Kakao, KOPIS 스크랩 로직 수행
                    pass

        # 입력 폼 (고정된 캔버스 레이아웃)
        st.divider()
        data = st.session_state.get('api_data', {})
        c1, c2 = st.columns([0.4, 0.6])
        with c1:
            i_img = st.text_input("🖼️ 이미지 URL", value=data.get('img',''))
            if i_img: st.image(i_img, use_container_width=True)
            i_t = st.text_input("제목", value=data.get('title',''))
            i_c = st.text_input("창작자/매체", value=data.get('creator',''))
            i_v = st.text_input("장소/출처", value=data.get('venue',''))
        with c2:
            i_s = st.text_area("작품소개/원문링크", value=data.get('summary',''))
            i_b = st.text_input("한 줄 요약")
            i_h = st.text_area("인상 깊은 구절")
            i_n = st.text_area("🌈 PRISM (나의 생각)")
            i_vd = st.date_input("감상일", value=date.today())
            
            if st.button("💾 아카이브 기록 저장", use_container_width=True, type="primary"):
                conn = get_connection()
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", 
                             (write_cat, i_t, i_c, "", i_v, i_s, i_b, i_h, i_n, i_img, str(date.today()), str(i_vd)))
                conn.commit()
                st.cache_data.clear(); st.session_state.api_data = {}; st.success("저장 완료!"); time.sleep(0.5); st.rerun()
