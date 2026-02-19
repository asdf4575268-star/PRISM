import streamlit as st
import sqlite3
import pandas as pd
import requests
import time
from datetime import date

# --- [1. 데이터베이스 초기화] ---
def init_db():
    conn = sqlite3.connect('prism_archive.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS archive
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT, category TEXT, creator TEXT, performer TEXT, 
                  release_date TEXT, impression TEXT, note TEXT, 
                  save_date TEXT, image_url TEXT, score INTEGER)''')
    conn.commit()
    return conn

# --- [2. 책 검색 함수 (캐싱 적용으로 429 에러 방지)] ---
@st.cache_data(ttl=3600)
def search_books_combined(query):
    if not query: return []
    results = []
    
    # 1. 아이튠즈 검색 (안정성용)
    try:
        itunes_url = f"https://itunes.apple.com/search?term={query.strip()}&entity=ebook&limit=5"
        it_res = requests.get(itunes_url, timeout=5).json()
        for item in it_res.get("results", []):
            results.append({
                "label": f"🍎 {item.get('trackName')} ({item.get('artistName')})",
                "title": item.get("trackName"),
                "creator": item.get("artistName"),
                "date": item.get("releaseDate")[:10] if item.get("releaseDate") else "",
                "img": item.get("artworkUrl100", "").replace("100x100bb", "600x600bb"),
                "desc": item.get("description", "").replace("<br />", "\n")
            })
    except: pass

    # 2. 구글 북스 검색 (데이터 보완용 - 에러 시 무시)
    try:
        google_url = f"https://www.googleapis.com/books/v1/volumes?q={query.strip()}&maxResults=5"
        g_res = requests.get(google_url, timeout=5).json()
        if "items" in g_res:
            for item in g_res["items"]:
                info = item.get("volumeInfo", {})
                results.append({
                    "label": f"🌐 {info.get('title')} ({', '.join(info.get('authors', ['미상']))})",
                    "title": info.get("title"),
                    "creator": ", ".join(info.get("authors", [])),
                    "date": info.get("publishedDate", ""),
                    "img": info.get("imageLinks", {}).get("thumbnail", ""),
                    "desc": info.get("description", "")
                })
    except: pass
    
    return results

# --- [3. UI 메인 설정] ---
init_db()
st.set_page_config(page_title="PRISM Archive", layout="wide")

# CSS 설정 (90/30/60 규칙)
st.markdown("""
    <style>
    .title-text { font-size: 90px !important; font-family: 'serif'; margin-bottom: -10px; line-height: 1.1; }
    .date-text { font-size: 30px !important; color: #888; }
    .number-text { font-size: 60px !important; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🖋️ 기록하기", "📂 아카이브 불러오기"])

with tab1:
    col1, col2 = st.columns([0.6, 0.4])
    with col1:
        category = st.selectbox("카테고리", ["책"])
        search_query = st.text_input("🔍 제목/작가 검색 (결과가 없으면 아래에 직접 타이핑하세요)")
        
        if search_query:
            books = search_books_combined(search_query)
            if books:
                selected_book = st.selectbox("검색 결과 선택", books, format_func=lambda x: x['label'])
                if st.button("이 데이터로 자동 채우기"):
                    st.session_state.api_data = selected_book
            else:
                st.info("검색 결과가 없습니다. 직접 정보를 입력해주세요.")

        data = st.session_state.get('api_data', {})
        st.divider()
        
        # [중요] 검색 결과가 있든 없든 사용자가 직접 수정 가능하도록 설정
        title_val = st.text_input("활동명", value=data.get('title', ''))
        st.markdown(f'<p class="title-text">{title_val if title_val else "PRISM"}</p>', unsafe_allow_html=True)
        
        creator = st.text_input("창작자 (작가)", value=data.get('creator', ''))
        release_date = st.text_input("출판일", value=data.get('date', ''))
        
        # 실연자 칸은 책에서도 수동 입력을 위해 열어둡니다 (공동 저자 등 활용)
        performer = st.text_input("추가 정보 (번역가 등)", value=data.get('performer', '-'))
        
        impression = st.text_area("인상 깊은 부분 (수기)")
        # 요약 정보가 너무 길면 직접 지우고 짧게 쓸 수 있도록 height 조절
        note = st.text_area("감상 노트", value=data.get('desc', ''), height=200)

    with col2:
        st.markdown(f'<p class="date-text">{date.today()}</p>', unsafe_allow_html=True)
        score = st.slider("만족도", 0, 100, 80)
        st.markdown(f'<span class="number-text">{score}</span> bpm', unsafe_allow_html=True)
        
        if data and data.get('img'):
            st.image(data['img'], width=300)
            
        if st.button("✅ 아카이브 저장"):
            conn = sqlite3.connect('prism_archive.db')
            c = conn.cursor()
            c.execute("INSERT INTO archive (title, category, creator, performer, release_date, impression, note, save_date, image_url, score) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (title_val, category, creator, "-", release_date, impression, note, str(date.today()), data['img'] if data else "", score))
            conn.commit()
            st.success("저장되었습니다!")

with tab2:
    # 아카이브 리스트 및 삭제 로직
    st.header("나의 PRISM 데이터 아카이브")
    conn = sqlite3.connect('prism_archive.db')
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    
    if not df.empty:
        st.dataframe(df[['id', 'category', 'title', 'save_date']], use_container_width=True)
        selected_title = st.selectbox("상세 보기 항목 선택", df['title'].tolist())
        detail = df[df['title'] == selected_title].iloc[0]
        
        if st.button("🗑️ 선택 항목 삭제"):
            c = conn.cursor()
            c.execute("DELETE FROM archive WHERE id = ?", (int(detail['id']),))
            conn.commit()
            st.rerun()
            
        st.write(f"### {detail['title']}")
        if detail['image_url']: st.image(detail['image_url'], width=200)
        st.info(detail['note'])
    else:
        st.write("아카이브가 비어있습니다.")




