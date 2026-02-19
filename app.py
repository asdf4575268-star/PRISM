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

# --- [2. 카카오 도서 검색 함수] ---
@st.cache_data(ttl=3600)
def search_books_kakao(query):
    if not query: return []
    
    # 발급받으신 REST API 키를 여기에 넣었습니다.
    KAKAO_API_KEY = "a356895a3aae4f0acf9f4ee884d90a6a" 
    
    url = "https://dapi.kakao.com/v3/search/book"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query, "size": 10}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            results = []
            for item in data.get("documents", []):
                results.append({
                    "label": f"📚 {item['title']} ({', '.join(item['authors'])})",
                    "title": item['title'],
                    "creator": ", ".join(item['authors']),
                    "date": item['datetime'][:10] if item['datetime'] else "",
                    "img": item['thumbnail'],
                    "desc": item['contents']
                })
            return results
        return []
    except:
        return []

# --- [3. 메인 UI 구성] ---
init_db()
st.set_page_config(page_title="PRISM Archive", layout="wide")

# CSS 설정 (활동명 90 / 날짜 30 / 숫자 60 bpm)
st.markdown("""
    <style>
    .title-text { 
        font-size: 70px !important; /* 90에서 70으로 살짝 조정 (너무 크면 가독성 저하) */
        font-family: 'serif'; 
        font-weight: 900;
        color: #1d1d1d;
        line-height: 1.0; 
        margin: 20px 0px 10px 0px;
        word-break: keep-all; /* 단어 단위로 줄바꿈 */
    }
    .date-text { 
        font-size: 30px !important; 
        color: #888; 
        font-weight: 300;
    }
    .number-text { 
        font-size: 60px !important; 
        font-weight: bold; 
        color: #ff4b4b;
    }
    .bpm-text {
        font-size: 24px;
        color: #333;
    }
    </style>
    """, unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🖋️ 기록하기", "📂 아카이브 불러오기"])

with tab1:
    col1, col2 = st.columns([0.6, 0.4])
    
    with col1:
        category = st.selectbox("카테고리", ["책"])
        search_query = st.text_input("🔍 국내 도서 제목/저자 검색 (엔터를 누르세요)")
        
        books = search_books_kakao(search_query)
        if search_query:
            if books:
                selected_book = st.selectbox("검색 결과 선택", books, format_func=lambda x: x['label'])
                if st.button("✨ 데이터 불러오기"):
                    st.session_state.api_data = selected_book
            else:
                st.info("검색 결과가 없습니다. 직접 정보를 입력해주세요.")

        data = st.session_state.get('api_data', {})
        st.divider()
        
        # 활동명 90px
        title_val = st.text_input("활동명 (제목)", value=data.get('title', ''))
        st.markdown(f'<p class="title-text">{title_val if title_val else "PRISM"}</p>', unsafe_allow_html=True)
        
        creator = st.text_input("창작자 (작가)", value=data.get('creator', ''))
        release_date = st.text_input("출판일", value=data.get('date', ''))
        impression = st.text_area("인상 깊은 부분 (수기)")
        note = st.text_area("감상 노트", value=data.get('desc', ''), height=150)

    with col2:
        # 날짜 30px
        st.markdown(f'<p class="date-text">{date.today()}</p>', unsafe_allow_html=True)
        
        # 만족도 60 bpm
        score = st.slider("만족도", 0, 100, 80)
        st.markdown(f'<span class="number-text">{score}</span> <span style="font-size:24px;">bpm</span>', unsafe_allow_html=True)
        
        st.divider()
        # 이미지 상시 확인 가능하도록 구성
        img_url = st.text_input("이미지 주소 (자동 입력됨)", value=data.get('img', ''))
        if img_url:
            st.image(img_url, use_container_width=True)
            
        if st.button("✅ 아카이브 저장"):
            conn = sqlite3.connect('prism_archive.db')
            c = conn.cursor()
            c.execute("INSERT INTO archive (title, category, creator, performer, release_date, impression, note, save_date, image_url, score) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (title_val, "책", creator, "-", release_date, impression, note, str(date.today()), img_url, score))
            conn.commit()
            st.success(f"'{title_val}' 저장 완료!")

with tab2:
    # 아카이브 리스트 및 삭제 로직
    st.header("나의 PRISM 데이터 아카이브")
    conn = sqlite3.connect('prism_archive.db')
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    
    if not df.empty:
        st.dataframe(df[['id', 'title', 'creator', 'save_date', 'score']], use_container_width=True)
        selected_title = st.selectbox("항목 선택", df['title'].tolist())
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

