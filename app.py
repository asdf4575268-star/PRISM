import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
import time
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from supabase import create_client, Client

# --- [1. 설정 및 UI 스타일링] ---
st.set_page_config(
    layout="wide", 
    page_title="PRISM ARCHIVE",
    page_icon="🌈",
    initial_sidebar_state="collapsed"
)

# API 및 DB 설정
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
DB_NAME = 'archive_prism_total_v5.db'
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 기존 UI 스타일 복구 및 고정 캔버스 설정
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
        
        /* 무지개 로고 스타일 */
        .logo-text { 
            font-size: 3rem; font-weight: 800; 
            background: linear-gradient(90deg, #FF0000, #FF7F00, #FFFF00, #00FF00, #0000FF, #4B0082, #8B00FF);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 1rem; letter-spacing: -2px;
        }
        
        /* 캔버스 고정 레이아웃 */
        .cal-img-box { 
            position: relative; width: 100%; aspect-ratio: 1/1.44; 
            overflow: hidden; border-radius: 4px; margin-top: 5px; 
            background: #1a1a1a; border: 1px solid #333;
        }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        
        /* MUSIC 카테고리 전용 원형/1:1 캔버스 */
        .music-tab-style { aspect-ratio: 1/1 !important; border-radius: 50% !important; border: 2px solid #444; }
        
        .badge-cat { position: absolute; top: 6px; left: 6px; background: rgba(0,0,0,0.8); color: #FFEB3B; padding: 2px 6px; border-radius: 3px; font-size: 9px; font-weight: bold; z-index: 5; }
        .badge-date { position: absolute; bottom: 6px; right: 6px; background: rgba(255,255,255,0.9); color: #000; padding: 1px 5px; border-radius: 3px; font-size: 10px; font-weight: bold; z-index: 5; }
        
        .stButton button { border-radius: 6px; }
    </style>
""", unsafe_allow_html=True)

# --- [2. 핵심 로직: DB 및 스크랩 엔진] ---
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

# API 스크랩 함수들 (Books, Music, Movies, Stage, Articles)
def search_kakao_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", [])

def search_tmdb(query, cat):
    tp = "movie" if cat == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{tp}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    return requests.get(url).json().get("results", [])

def scrape_article(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        title = soup.find('meta', property='og:title')['content'] if soup.find('meta', property='og:title') else soup.title.string
        img = soup.find('meta', property='og:image')['content'] if soup.find('meta', property='og:image') else ""
        site = soup.find('meta', property='og:site_name')['content'] if soup.find('meta', property='og:site_name') else "웹사이트"
        return {"title": title, "img": img, "venue": site, "summary": url}
    except: return None

# --- [3. 메인 UI 레이아웃] ---
st.markdown('<div class="logo-text">PRISM ARCHIVE</div>', unsafe_allow_html=True)

if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "api_data" not in st.session_state: st.session_state.api_data = {}

# 사이드바 관리자
with st.sidebar:
    if not st.session_state.is_logged_in:
        pw = st.text_input("Password", type="password")
        if pw == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.is_logged_in = True; st.rerun()
    else:
        st.success("Admin 모드")
        if st.button("Logout"): st.session_state.is_logged_in = False; st.rerun()

# 데이터 준비 및 카테고리 수량 계산
df = get_all_data()
cat_list = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "ARTICLES"]
counts = {c: len(df[df['category'] == c]) for c in cat_list}

# 탭 구성 (ALL + 각 카테고리 + WRITE)
tabs = st.tabs([f"📅 ALL ({len(df)})"] + [f"{c} ({counts[c]})" for c in cat_list] + (["🖋️ WRITE"] if st.session_state.is_logged_in else []))

# --- 탭 1: ALL (연도별/월별 목록창 유지) ---
with tabs[0]:
    if df.empty:
        st.info("아카이브가 비어있습니다.")
    else:
        df['v_dt'] = pd.to_datetime(df['view_date'])
        years = sorted(df['v_dt'].dt.year.unique(), reverse=True)
        for y in years:
            with st.expander(f"📂 {y}년 기록", expanded=True):
                y_df = df[df['v_dt'].dt.year == y]
                months = sorted(y_df['v_dt'].dt.month.unique(), reverse=True)
                for m in months:
                    st.markdown(f"**{m}월**")
                    m_df = y_df[y_df['v_dt'].dt.month == m]
                    cols = st.columns(6)
                    for idx, row in enumerate(m_df.to_dict('records')):
                        with cols[idx % 6]:
                            m_style = "music-tab-style" if row['category'] == "MUSIC" else ""
                            st.markdown(f'<div class="cal-img-box {m_style}"><div class="badge-cat">{row["category"]}</div><div class="badge-date">{row["v_dt"].day}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                            st.button(row['title'][:10], key=f"all_{row['id']}", use_container_width=True)

# --- 카테고리별 개별 탭 ---
for i, cn in enumerate(cat_list):
    with tabs[i+1]:
        c_df = df[df['category'] == cn]
        if c_df.empty: st.info("기록이 없습니다.")
        else:
            cols = st.columns(6)
            for idx, row in enumerate(c_df.to_dict('records')):
                with cols[idx % 6]:
                    m_style = "music-tab-style" if cn == "MUSIC" else ""
                    st.markdown(f'<div class="cal-img-box {m_style}"><div class="badge-date">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                    st.button(row['title'][:10], key=f"cat_{cn}_{row['id']}", use_container_width=True)

# --- [4. 스크랩 기능이 포함된 WRITE 탭] ---
if st.session_state.is_logged_in:
    with tabs[-1]:
        w_cat = st.radio("카테고리 선택", cat_list, horizontal=True)
        
        # [스크랩 엔진 UI]
        with st.container(border=True):
            st.markdown("### 🔍 데이터 스크랩")
            if w_cat == "ARTICLES":
                a_url = st.text_input("기사 URL 입력 (네이버 뉴스 등)")
                if st.button("📰 기사 스크랩", use_container_width=True):
                    res = scrape_article(a_url)
                    if res: 
                        st.session_state.api_data = {'title': res['title'], 'img': res['img'], 'venue': res['venue'], 'summary': res['summary'], 'creator': 'Article'}
                        st.rerun()
            else:
                sq = st.text_input(f"{w_cat} 검색어 입력")
                if st.button("✨ 데이터 검색 및 자동입력", use_container_width=True):
                    if w_cat == "BOOKS":
                        res = search_kakao_books(sq)
                        if res:
                            b = res[0] # 첫 번째 결과 자동 선택
                            st.session_state.api_data = {'title':b['title'], 'creator':", ".join(b['authors']), 'img':b['thumbnail'], 'venue':b['publisher'], 'summary':b['contents']}
                            st.rerun()
                    elif w_cat in ["MOVIES", "SERIES"]:
                        res = search_tmdb(sq, w_cat)
                        if res:
                            r = res[0]; tk = 'title' if w_cat == 'MOVIES' else 'name'
                            st.session_state.api_data = {'title':r[tk], 'img':f"https://image.tmdb.org/t/p/w500{r['poster_path']}", 'summary':r['overview']}
                            st.rerun()

        # [기록 입력 폼]
        st.divider()
        data = st.session_state.get('api_data', {})
        col1, col2 = st.columns([0.4, 0.6])
        with col1:
            f_img = st.text_input("🖼️ 이미지 URL", value=data.get('img',''))
            if f_img: st.image(f_img, use_container_width=True)
            f_title = st.text_input("제목", value=data.get('title',''))
            f_creator = st.text_input("창작자/작가", value=data.get('creator',''))
            f_venue = st.text_input("장소/출처", value=data.get('venue',''))
        with col2:
            f_sum = st.text_area("작품 소개/링크", value=data.get('summary',''), height=100)
            f_brief = st.text_input("한 줄 평")
            f_high = st.text_area("하이라이트", height=100)
            f_note = st.text_area("🌈 PRISM (생각)", height=150)
            f_vdate = st.date_input("감상일", value=date.today())
            
            if st.button("💾 아카이브 저장", type="primary", use_container_width=True):
                conn = get_connection()
                conn.execute("INSERT INTO archive (category, title, creator, venue, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (w_cat, f_title, f_creator, f_venue, f_sum, f_brief, f_high, f_note, f_img, str(date.today()), str(f_vdate)))
                conn.commit()
                # Supabase 동기화 (간략)
                try: supabase.table("archive").insert({"category":w_cat, "title":f_title, "creator":f_creator, "view_date":str(f_vdate), "img_url":f_img}).execute()
                except: pass
                st.cache_data.clear(); st.session_state.api_data = {}; st.success("저장되었습니다!"); time.sleep(0.5); st.rerun()
