import streamlit as st
import sqlite3
import pandas as pd
from ytmusicapi import YTMusic
import requests
from datetime import date

# --- [1. 데이터베이스 초기화] ---
def init_db():
    conn = sqlite3.connect('prism_archive.db')
    c = conn.cursor()
    # PRISM 통합 테이블 생성
    c.execute('''CREATE TABLE IF NOT EXISTS archive
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT, category TEXT, creator TEXT, performer TEXT, 
                  release_date TEXT, impression TEXT, note TEXT, 
                  save_date TEXT, image_url TEXT, score INTEGER)''')
    conn.commit()
    return conn

# --- [2. API 검색 함수들] ---
def search_data(query, category):
    if not query: return None
    
    if category == "음악":
        try:
            yt = YTMusic()
            res = yt.search(query, filter="songs")
            if res:
                item = res[0]
                return {
                    "title": item['title'], "creator": item['artists'][0]['name'],
                    "performer": item['artists'][0]['name'], "date": item.get('year', ''),
                    "img": item['thumbnails'][-1]['url'], "desc": f"Album: {item['album']['name'] if 'album' in item else 'Single'}"
                }
        except: return None

    elif category == "책":
        res = requests.get(f"https://www.googleapis.com/books/v1/volumes?q={query}").json()
        if "items" in res:
            item = res["items"][0]["volumeInfo"]
            return {
                "title": item.get("title"), "creator": ", ".join(item.get("authors", [])),
                "performer": "-", "date": item.get("publishedDate"),
                "img": item.get("imageLinks", {}).get("thumbnail"), "desc": item.get("description", "")
            }
    # 영화/무대극 등 타 카테고리 확장 가능
    return None

# --- [3. UI 레이아웃 및 로직] ---
init_db()
st.set_page_config(page_title="PRISM Archive", layout="wide")

# CSS 적용 (90/30/60 규칙 유지)
st.markdown("""
    <style>
    .title-text { font-size: 90px; font-family: 'serif'; margin-bottom: -10px; }
    .date-text { font-size: 30px; color: #888; }
    .number-text { font-size: 60px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🖋️ 기록하기", "📂 아카이브 불러오기"])

with tab1:
    col1, col2 = st.columns([0.6, 0.4])
    with col1:
        category = st.selectbox("카테고리", ["책", "음악", "영화", "TV/OTT 시리즈", "무대극"])
        search_query = st.text_input("🔍 제목으로 검색")
        
        # 버튼 클릭 시에만 API 호출 (비용 및 속도 최적화)
        if st.button("데이터 검색 및 연동"):
            st.session_state.api_data = search_data(search_query, category)
        
        data = st.session_state.get('api_data', None)
        
        title = st.text_input("활동명", value=data['title'] if data else "")
        st.markdown(f'<p class="title-text">{title if title else "PRISM"}</p>', unsafe_allow_html=True)
        
        creator = st.text_input("창작자", value=data['creator'] if data else "")
        performer = st.text_input("실연자", value=data['performer'] if data else "")
        release_date = st.text_input("날짜 정보", value=data['date'] if data else "")
        impression = st.text_area("인상 깊은 부분")
        note = st.text_area("감상 노트", value=data['desc'] if data else "")

    with col2:
        st.markdown(f'<p class="date-text">{date.today()}</p>', unsafe_allow_html=True)
        score = st.slider("만족도", 0, 100, 80)
        st.markdown(f'<span class="number-text">{score}</span> bpm', unsafe_allow_html=True)
        
        if data and data['img']:
            st.image(data['img'], width=300)
            
        if st.button("✅ 아카이브에 저장"):
            conn = sqlite3.connect('prism_archive.db')
            c = conn.cursor()
            c.execute("INSERT INTO archive (title, category, creator, performer, release_date, impression, note, save_date, image_url, score) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (title, category, creator, performer, release_date, impression, note, str(date.today()), data['img'] if data else "", score))
            conn.commit()
            st.success("데이터베이스에 성공적으로 저장되었습니다!")

with tab2:
    st.header("나의 PRISM 데이터 아카이브")
    conn = sqlite3.connect('prism_archive.db')
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    
    if not df.empty:
        # 아카이브 리스트 출력
        st.dataframe(df[['category', 'title', 'creator', 'save_date', 'score']], use_container_width=True)
        
        # 특정 항목 상세 보기
        selected_title = st.selectbox("상세 정보를 확인할 항목 선택", df['title'].tolist())
        detail = df[df['title'] == selected_title].iloc[0]
        st.write(f"### {detail['title']} ({detail['category']})")
        st.write(f"**창작자:** {detail['creator']} | **실연자:** {detail['performer']}")
        st.info(detail['note'])
    else:
        st.write("아직 저장된 아카이브가 없습니다.")