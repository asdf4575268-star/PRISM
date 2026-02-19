import streamlit as st
import sqlite3
import pandas as pd
import requests
from datetime import date

# --- [1. 데이터베이스 설정] ---
def init_db():
    conn = sqlite3.connect('prism_archive.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS archive
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT, creator TEXT, release_date TEXT, 
                  impression TEXT, note TEXT, image_url TEXT, save_date TEXT)''')
    conn.commit()
    return conn

# --- [2. 카카오 도서 검색 함수] ---
def search_books_kakao(query):
    if not query: return []
    KAKAO_API_KEY = "a356895a3aae4f0acf9f4ee884d90a6a" 
    url = "https://dapi.kakao.com/v3/search/book"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query, "size": 10}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            return response.json().get("documents", [])
        return []
    except:
        return []

# --- [3. 메인 로직] ---
st.set_page_config(layout="wide")
init_db()

tab1, tab2 = st.tabs(["🖋️ 데이터 입력", "📂 보관함 확인"])

with tab1:
    # 검색부
    search_query = st.text_input("🔍 도서 검색", placeholder="제목/저자 입력 후 엔터")
    if search_query:
        books = search_books_kakao(search_query)
        if books:
            book_options = {f"📚 {b['title']} ({', '.join(b['authors'])})": b for b in books}
            selected_label = st.selectbox("결과 선택", list(book_options.keys()))
            if st.button("✨ 데이터 불러오기"):
                st.session_state.api_data = book_options[selected_label]
        else:
            st.info("검색 결과가 없습니다.")

    st.divider()

    # 입력 및 이미지 레이아웃
    data = st.session_state.get('api_data', {})
    
    # col1(기본 정보들), col2(이미지 크게)
    col1, col2 = st.columns([0.6, 0.4])

    with col1:
        # 연동된 텍스트 정보들
        title = st.text_input("활동명 (제목)", value=data.get('title', ''))
        creator = st.text_input("창작자 (작가)", value=", ".join(data.get('authors', [])) if 'authors' in data else "")
        release_date = st.text_input("날짜 (출판일)", value=data.get('datetime', '')[:10] if data.get('datetime') else "")
        
        # 수동 입력 정보들
        impression = st.text_area("인상 깊은 부분 (수동 입력)", height=100)
        note = st.text_area("감상 노트 (자동 연동)", value=data.get('contents', ''), height=250)

    with col2:
        st.write("### 연동 이미지")
        img_url = data.get('thumbnail', '')
        if img_url:
            # 고화질 변환 시도 (카카오 썸네일 사이즈 제한 해제)
            high_res_img = img_url.replace("fname=t1.daumcdn.net", "fname=t1.daumcdn.net").replace("width=120", "width=500")
            st.image(high_res_img, use_container_width=True)
        else:
            # 이미지 없을 때 가이드
            st.info("연동된 이미지가 없습니다.")
            manual_img = st.text_input("이미지 주소 직접 입력(URL)")
            if manual_img:
                st.image(manual_img, use_container_width=True)
                img_url = manual_img

        st.divider()
        if st.button("✅ 아카이브에 최종 저장", use_container_width=True):
            if title:
                conn = sqlite3.connect('prism_archive.db')
                c = conn.cursor()
                c.execute("""INSERT INTO archive 
                          (title, creator, release_date, impression, note, image_url, save_date) 
                          VALUES (?, ?, ?, ?, ?, ?, ?)""",
                          (title, creator, release_date, impression, note, img_url, str(date.today())))
                conn.commit()
                conn.close()
                st.success(f"'{title}' 저장 완료!")
                st.rerun()
            else:
                st.warning("제목을 입력해주세요.")

with tab2:
    # (보관함 확인 로직은 이전과 동일)
    st.subheader("저장된 기록 목록")
    conn = sqlite3.connect('prism_archive.db')
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    conn.close()

    if not df.empty:
        st.dataframe(df[['id', 'title', 'creator', 'save_date']], use_container_width=True)
        st.divider()
        selected_id = st.selectbox("상세히 볼 기록의 ID 선택", df['id'].tolist())
        detail = df[df['id'] == selected_id].iloc[0]
        
        det_col1, det_col2 = st.columns([0.6, 0.4])
        with det_col1:
            st.write(f"### {detail['title']}")
            st.write(f"**작가:** {detail['creator']} | **출판일:** {detail['release_date']}")
            st.info(f"**감상 노트:**\n\n{detail['note']}")
            st.warning(f"**인상 깊은 부분:**\n\n{detail['impression']}")
        with det_col2:
            if detail['image_url']:
                st.image(detail['image_url'], use_container_width=True)
            if st.button("🗑️ 이 기록 삭제", use_container_width=True):
                conn = sqlite3.connect('prism_archive.db')
                c = conn.cursor()
                c.execute("DELETE FROM archive WHERE id = ?", (int(selected_id),))
                conn.commit()
                conn.close()
                st.rerun()
