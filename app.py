import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date
from PIL import Image
import io

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="My Prism Archive")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; }
    
    div[data-testid="stImage"] > img {
        border-radius: 12px;
        transition: transform 0.3s ease;
        cursor: pointer;
    }
    div[data-testid="stImage"] > img:hover { transform: scale(1.05); }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_v10.db'
KAKAO_KEY = "a356895a3aae4f0acf9f4ee884d90a6a"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')

# --- [2. OCR 기능 (사이드바 배치)] ---
with st.sidebar:
    st.header("📸 OCR 문자 인식")
    uploaded_file = st.file_uploader("이미지를 업로드하면 글자를 추출합니다", type=["jpg", "png", "jpeg"])
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="업로드된 이미지", use_container_width=True)
        if st.button("글자 추출하기"):
            url = "https://dapi.kakao.com/v2/vision/text/ocr"
            headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG')
            res = requests.post(url, headers=headers, files={"image": img_byte_arr.getvalue()})
            result = res.json().get("result", [])
            full_text = " ".join([r['words'][0] for r in result])
            st.text_area("추출 결과 (복사해서 사용하세요)", value=full_text, height=150)

# --- [3. API 연동 함수] ---

# 영화 연동 (카카오 통합 검색 대안)
def search_movie_contents(query):
    headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
    # 웹 검색과 이미지 검색을 조합하여 포스터와 정보를 가져옵니다.
    web_res = requests.get("https://dapi.kakao.com/v2/search/web", headers=headers, params={"query": f"영화 {query} 정보"}).json().get("documents", [])
    img_res = requests.get("https://dapi.kakao.com/v2/search/image", headers=headers, params={"query": f"영화 {query} 포스터"}).json().get("documents", [])
    return web_res, img_res

# --- [4. 상세 보기 팝업] ---
@st.dialog("📖 상세 기록 보기", width="large")
def show_details(item):
    col_img, col_txt = st.columns([0.4, 0.6])
    with col_img:
        if item['img_url']: st.image(item['img_url'], use_container_width=True)
    with col_txt:
        st.subheader(item['title'])
        st.write(f"**정보:** {item['creator']} | **날짜:** {item['rel_date']}")
        st.divider()
        st.info(f"**📖 요약**\n\n{item['summary']}")
        st.warning(f"**✨ 하이라이트**\n\n{item['highlights']}")
        st.write(f"**💬 감상**\n\n{item['note']}")
        if st.button("🗑️ 삭제하기"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

init_db()

# --- [메인 로직] ---
tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 보관함"])

with tab1:
    category = st.radio("📂 카테고리", ["도서", "음악", "영화"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색", placeholder="제목을 입력하세요")
    
    if search_query and category == "영화":
        web_docs, img_docs = search_movie_contents(search_query)
        if img_docs:
            col_preview = st.columns(5)
            for i, img_doc in enumerate(img_docs[:5]):
                with col_preview[i]:
                    st.image(img_doc['image_url'], use_container_width=True)
                    if st.button(f"선택 {i+1}"):
                        st.session_state.api_data = {
                            'title': search_query,
                            'creator': "영화 감독/배우",
                            'date': str(date.today()),
                            'img': img_doc['image_url'],
                            'note': web_docs[0]['contents'].replace('<b>','').replace('</b>','') if web_docs else ""
                        }
                        st.rerun()

    data = st.session_state.get('api_data', {})
    st.divider()
    col_l, col_r = st.columns([0.4, 0.6])
    
    with col_l:
        # 직접 이미지 업로드 기능 추가 (연동 실패 대비)
        uploaded_poster = st.file_uploader("이미지 직접 업로드", type=["jpg", "png"])
        if uploaded_poster:
            # 여기서는 간단히 로직 생략, 필요시 추가
            pass
        
        display_img = data.get('img', '')
        if display_img: st.image(display_img, use_container_width=False)
        
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자", value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', ''))

    with col_r:
        summary = st.text_area("📖 요약", value=data.get('note', ''), height=80)
        highlights = st.text_area("✨ 하이라이트", height=120)
        note = st.text_area("💬 감상", height=120)
        
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 최종 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, highlights, note, data.get('img', ''), str(date.today())))
            st.success("저장되었습니다!")
            st.rerun()

with tab2:
    f_book, f_music, f_movie = st.tabs(["📚 도서", "🎸 음악", "🎬 영화"])
    def display_gallery(cat):
        with sqlite3.connect(DB_NAME) as conn:
            df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{cat}' ORDER BY id DESC", conn)
        if df.empty: return st.info("기록이 없습니다.")
        cols = st.columns(4)
        for idx, row in df.iterrows():
            with cols[idx % 4]:
                if row['img_url']: st.image(row['img_url'], use_container_width=True)
                if st.button(row['title'], key=f"btn_{cat}_{row['id']}", use_container_width=True):
                    show_details(row)
    with f_book: display_gallery("도서")
    with f_music: display_gallery("음악")
    with f_movie: display_gallery("영화")
