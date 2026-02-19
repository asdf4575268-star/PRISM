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
def search_books(query):
    if not query: return []
    try:
        # 구글 대신 iTunes API 사용 (차단이 거의 없음)
        # entity=ebook 설정을 통해 도서 정보를 가져옵니다.
        url = f"https://itunes.apple.com/search?term={query.strip()}&entity=ebook&limit=10"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            return []

        res = response.json()
        results = []
        
        if res.get("resultCount", 0) > 0:
            for item in res["results"]:
                # 이미지 고화질 변환 (100x100 -> 600x600)
                img_url = item.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
                
                results.append({
                    "label": f"📚 {item.get('trackName')} ({item.get('artistName')})",
                    "title": item.get("trackName", "제목 없음"),
                    "creator": item.get("artistName", "작가 미상"),
                    "performer": "-",
                    "date": item.get("releaseDate", "날짜 미상")[:10], # 날짜만 추출
                    "img": img_url,
                    "desc": item.get("description", "정보 없음").replace("<br />", "\n")
                })
        return results
    except Exception as e:
        st.error(f"연결 오류: {e}")
        return []

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
        search_query = st.text_input("🔍 책 제목 검색 (데미안 등을 입력하고 엔터)")
        
        if search_query:
            books = search_books(search_query)
            
            if books == "RATE_LIMIT":
                st.error("⚠️ 구글 서버 요청이 일시 제한되었습니다. 1분 뒤에 다시 시도해주세요.")
            elif books:
                selected_book = st.selectbox("정확한 항목을 선택하세요", books, format_func=lambda x: x['label'])
                if st.button("이 정보로 필드 채우기"):
                    st.session_state.api_data = selected_book
            else:
                st.info("검색 결과를 찾을 수 없습니다.")

        # 데이터 필드
        data = st.session_state.get('api_data', None)
        st.divider()
        
        title_val = st.text_input("활동명", value=data['title'] if data else "")       
        creator = st.text_input("창작자 (작가)", value=data['creator'] if data else "")
        release_date = st.text_input("출판일", value=data['date'] if data else "")
        impression = st.text_area("인상 깊은 부분 (수기)")
        note = st.text_area("감상 노트 (요약)", value=data['desc'] if data else "", height=200)

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


