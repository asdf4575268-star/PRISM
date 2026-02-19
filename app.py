import streamlit as st
import sqlite3
import pandas as pd
import requests
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

# --- [2. 책 검색 전용 함수] ---
def search_books(query):
    if not query: return []
    try:
        # Google Books API 호출 (결과 10개)
        url = f"https://www.googleapis.com/books/v1/volumes?q={query}&maxResults=10"
        res = requests.get(url, timeout=5).json()
        
        results = []
        if "items" in res:
            for item in res["items"]:
                info = item.get("volumeInfo", {})
                title = info.get("title", "제목 없음")
                authors = info.get("authors", ["작가 미상"])
                # 썸네일 이미지 처리 (없을 경우 빈 문자열)
                img_links = info.get("imageLinks", {})
                img_url = img_links.get("thumbnail") or img_links.get("smallThumbnail") or ""
                
                results.append({
                    "label": f"📚 {title} ({', '.join(authors)})",
                    "title": title,
                    "creator": ", ".join(authors),
                    "performer": "-", # 책은 실연자 없음
                    "date": info.get("publishedDate", "날짜 미상"),
                    "img": img_url,
                    "desc": info.get("description", "등록된 요약 정보가 없습니다.")
                })
        return results
    except Exception as e:
        st.error(f"연결 오류가 발생했습니다: {e}")
        return []

# --- [3. 메인 UI] ---
init_db()
st.set_page_config(page_title="PRISM Archive", layout="wide")

# CSS 설정 (요청하신 크기 반영)
st.markdown("""
    <style>
    .title-text { font-size: 90px; font-family: 'serif'; margin-bottom: -10px; line-height: 1.1; }
    .date-text { font-size: 30px; color: #888; }
    .number-text { font-size: 60px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🖋️ 기록하기", "📂 아카이브 불러오기"])

with tab1:
    col1, col2 = st.columns([0.6, 0.4])
    
    with col1:
        # 카테고리 고정 (일단 책부터 완벽하게)
        category = st.selectbox("카테고리", ["책"])
        search_query = st.text_input("🔍 책 제목이나 저자를 검색하세요")
        
        # 검색 결과 로직
        if search_query:
            books = search_books(search_query)
            if books:
                selected_book = st.selectbox(
                    "검색 결과 중 선택하세요", 
                    books, 
                    format_func=lambda x: x['label'],
                    key="book_selector"
                )
                if st.button("이 책의 정보 불러오기"):
                    st.session_state.api_data = selected_book
            else:
                st.info("검색 결과가 없습니다. 제목을 정확히 입력하셨나요?")

        # 입력 필드 (데이터가 있으면 자동 채움)
        data = st.session_state.get('api_data', None)
        
        st.divider()
        title_val = st.text_input("활동명", value=data['title'] if data else "")
        st.markdown(f'<p class="title-text">{title_val if title_val else "PRISM"}</p>', unsafe_allow_html=True)
        
        creator = st.text_input("창작자 (작가)", value=data['creator'] if data else "")
        performer = st.text_input("실연자", value="-", disabled=True)
        release_date = st.text_input("출판일", value=data['date'] if data else "")
        
        impression = st.text_area("인상 깊은 부분 (수기)")
        note = st.text_area("감상 노트 (요약)", value=data['desc'] if data else "", height=200)

    with col2:
        # 날짜(30px) 및 만족도(60px)
        st.markdown(f'<p class="date-text">{date.today().strftime("%Y-%m-%d")}</p>', unsafe_allow_html=True)
        
        score = st.slider("만족도 점수", 0, 100, 80)
        st.markdown(f'<span class="number-text">{score}</span> bpm', unsafe_allow_html=True)
        
        st.divider()
        # 이미지 상시 노출
        if data and data.get('img'):
            st.image(data['img'], width=300, caption="표지 미리보기")
        else:
            st.info("이미지가 없습니다.")
            
        if st.button("✅ 내 아카이브에 저장"):
            if not title_val:
                st.error("활동명을 입력해주세요.")
            else:
                conn = sqlite3.connect('prism_archive.db')
                c = conn.cursor()
                c.execute("""INSERT INTO archive 
                          (title, category, creator, performer, release_date, impression, note, save_date, image_url, score) 
                          VALUES (?,?,?,?,?,?,?,?,?,?)""",
                          (title_val, category, creator, performer, release_date, impression, note, str(date.today()), data['img'] if data else "", score))
                conn.commit()
                st.success(f"'{title_val}' 저장 완료!")

with tab2:
    # (아카이브 불러오기 및 삭제 로직 - 이전과 동일하게 유지)
    st.header("나의 PRISM 데이터 아카이브")
    conn = sqlite3.connect('prism_archive.db')
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    
    if not df.empty:
        st.dataframe(df[['id', 'category', 'title', 'creator', 'save_date', 'score']], use_container_width=True)
        st.divider()
        
        selected_title = st.selectbox("상세 정보를 확인할 항목 선택", df['title'].tolist())
        detail = df[df['title'] == selected_title].iloc[0]
        
        col_det1, col_det2 = st.columns([0.7, 0.3])
        with col_det1:
            st.write(f"### {detail['title']}")
            st.write(f"**작가:** {detail['creator']}")
            st.info(detail['note'])
        with col_det2:
            if detail['image_url']:
                st.image(detail['image_url'], use_container_width=True)
            if st.button("🗑️ 항목 삭제"):
                c = conn.cursor()
                c.execute("DELETE FROM archive WHERE id = ?", (int(detail['id']),))
                conn.commit()
                st.rerun()
    else:
        st.write("아카이브가 비어있습니다.")
