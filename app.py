import streamlit as st
import sqlite3
import datetime
import pandas as pd
import re
from contextlib import contextmanager

# 🚨 Streamlit 화면 설정은 무조건 최상단에 위치해야 합니다.
st.set_page_config(page_title="공무원 판례 대시보드", page_icon="⚖️", layout="wide")

# --- 🔒 비밀번호 잠금 시스템 ---
def check_password():
    # 클라우드에 설정할 비밀번호를 가져옵니다. (클라우드 설정 전 로컬 테스트용 기본 비밀번호: '7777')
    CORRECT_PASSWORD = st.secrets.get("password", "7777")
    
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 나만의 7급 판례 대시보드")
        st.markdown("안전한 접속을 위해 비밀번호를 입력해주세요.")
        
        pwd_input = st.text_input("비밀번호", type="password")
        
        if st.button("접속하기", type="primary"):
            if pwd_input == CORRECT_PASSWORD:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ 비밀번호가 틀렸습니다.")
        return False
    return True

# 비밀번호를 맞추기 전까지는 아래의 앱 코드가 실행되지 않고 멈춥니다.
if not check_password():
    st.stop()


# ==========================================
# 아래부터는 기존 판례 대시보드 전체 코드입니다.
# ==========================================

# --- 데이터베이스 설정 및 🚀 무한 로딩(Deadlock) 방지 시스템 ---
DB_FILE = "law_precedents.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30, check_same_thread=False, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL;") 
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        yield conn
    finally:
        conn.close() 

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS categories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        main_cat TEXT,
                        mid_cat TEXT,
                        sub_cat TEXT,
                        UNIQUE(main_cat, mid_cat, sub_cat)
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS precedents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        main_cat TEXT,
                        mid_cat TEXT,
                        sub_cat TEXT,
                        p_number TEXT,
                        p_title TEXT,
                        p_content TEXT,
                        p_tags TEXT,
                        reg_date TEXT
                    )''')
        
        new_columns = ["p_desc", "p_grade", "p_location", "p_related", "p_result", "read_count", "p_exams"]
        for col in new_columns:
            try:
                if col == "read_count":
                    c.execute(f"ALTER TABLE precedents ADD COLUMN {col} INTEGER DEFAULT 0")
                else:
                    c.execute(f"ALTER TABLE precedents ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass

def load_categories():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT main_cat, mid_cat, sub_cat FROM categories")
        rows = c.fetchall()
    categories = {"헌법": {}, "행정법": {}}
    for main, mid, sub in rows:
        if mid:
            if mid not in categories[main]:
                categories[main][mid] = []
            if sub and sub not in categories[main][mid]:
                categories[main][mid].append(sub)
    return categories

def add_category(main_cat, mid_cat, sub_cat=""):
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute("INSERT INTO categories (main_cat, mid_cat, sub_cat) VALUES (?, ?, ?)", 
                      (main_cat, mid_cat, sub_cat))
            return True
        except sqlite3.IntegrityError:
            return False

def sort_exams_desc(exam_text):
    if not exam_text:
        return ""
    lines = [line.strip() for line in exam_text.split('\n') if line.strip()]
    
    def get_year(s):
        match = re.search(r'\d{4}', s)
        return int(match.group()) if match else 0
        
    sorted_lines = sorted(lines, key=get_year, reverse=True)
    return "\n".join(sorted_lines)

init_db()
categories = load_categories()

# --- 커스텀 CSS ---
st.markdown("""
    <style>
    /* 기본 메트릭 컨테이너 스타일 */
    div[data-testid="metric-container"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    div[data-testid="stTextInput"] > div > div > input {
        border-radius: 20px;
    }
    
    /* 얇은 줄 구분선 스타일 */
    hr.thin-line {
        border: 0;
        border-top: 1px solid #e0e0e0;
        margin: 5px 0 5px 0;
    }
    
    /* 일반 버튼(페이지네이션 등) 높이 조정 */
    .stButton > button {
        height: 40px;
    }

    /* 🚀 홈 화면 네비게이션 버튼을 메트릭(Metric) 카드처럼 꾸미는 CSS 매직 */
    div[data-testid="element-container"]:has(.metric-btn-marker) {
        display: none; 
    }
    div[data-testid="element-container"]:has(.metric-btn-marker) + div[data-testid="element-container"] button {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 15px 15px 5px 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        height: 104px; 
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: flex-start;
        text-align: left;
        transition: all 0.2s ease;
    }
    div[data-testid="element-container"]:has(.metric-btn-marker) + div[data-testid="element-container"] button:hover {
        border-color: #ff4b4b; 
        box-shadow: 2px 2px 8px rgba(0,0,0,0.1);
    }
    div[data-testid="element-container"]:has(.metric-btn-marker) + div[data-testid="element-container"] button p {
        margin: 0;
        color: #555;
    }
    </style>
""", unsafe_allow_html=True)

# 📌 페이지 이동을 위한 안전한 콜백 함수
def change_menu(target_menu):
    st.session_state['menu_choice'] = target_menu

if 'menu_choice' not in st.session_state:
    st.session_state['menu_choice'] = "📊 홈 (대시보드)"

# --- 사이드바 네비게이션 ---
with st.sidebar:
    st.title("⚙️ Dashboard")
    menu_options = [
        "📊 홈 (대시보드)", 
        "🏛️ 헌법 판례집", 
        "⚖️ 행정법 판례집", 
        "🎲 헌법 랜덤 복습", 
        "🎲 행정법 랜덤 복습", 
        "📁 카테고리 관리", 
        "✍️ 판례 등록"
    ]
    menu = st.radio("메뉴", menu_options, key="menu_choice", label_visibility="collapsed")
    st.write("---")
    st.caption("✔️ 비밀번호 보안 기능 적용됨")

def get_stats():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM precedents")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM precedents WHERE p_grade='S' OR p_grade='A+'")
        high_grade = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM precedents WHERE main_cat='헌법'")
        const_total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM precedents WHERE main_cat='행정법'")
        admin_total = c.fetchone()[0]
    return total, high_grade, const_total, admin_total

# --- 1. 홈 (대시보드) ---
if menu == "📊 홈 (대시보드)":
    st.title("Hello, 예비 7급 공무원님 👋")
    st.markdown("목표 달성을 위한 판례 회독을 시작해 보세요. 응원합니다!")
    st.write("")
    
    total, high_grade, const_total, admin_total = get_stats()
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("총 등록 판례", f"{total} 개", "열공 중!")
    with col2:
        st.metric("S 및 A+ 판례 (핵심)", f"{high_grade} 개", "우선 복습 권장")
    
    with col3:
        st.markdown('<div class="metric-btn-marker"></div>', unsafe_allow_html=True)
        st.button(f"🏛️ 헌법 판례  \n### {const_total} 개", on_click=change_menu, args=("🏛️ 헌법 판례집",), use_container_width=True)
    with col4:
        st.markdown('<div class="metric-btn-marker"></div>', unsafe_allow_html=True)
        st.button(f"⚖️ 행정법 판례  \n### {admin_total} 개", on_click=change_menu, args=("⚖️ 행정법 판례집",), use_container_width=True)
    
    st.write("---")
    
    s_col1, s_col2 = st.columns([3, 1])
    with s_col1:
        search_query = st.text_input("🔍 Search", placeholder="판례 번호, 제목, 태그, 기출 내역 등 통합 검색", label_visibility="collapsed")
    
    st.write("")
    
    with get_db() as conn:
        if search_query:
            like_query = f"%{search_query}%"
            df_all = pd.read_sql_query('''
                SELECT main_cat AS 대분류, mid_cat AS 목차, sub_cat AS 소분류, 
                       p_number AS 판례번호, p_title AS 제목, p_result AS 판결결과, p_grade AS 중요도, 
                       read_count AS 회독수, p_location AS 교재위치, p_exams AS 출제내역, p_tags AS 태그 
                FROM precedents 
                WHERE p_number LIKE ? OR p_tags LIKE ? OR p_title LIKE ? OR p_desc LIKE ? OR p_location LIKE ? OR p_related LIKE ? OR p_exams LIKE ?
                ORDER BY id DESC
            ''', conn, params=(like_query, like_query, like_query, like_query, like_query, like_query, like_query))
        else:
            df_all = pd.read_sql_query('''
                SELECT main_cat AS 대분류, mid_cat AS 목차, sub_cat AS 소분류, 
                       p_number AS 판례번호, p_title AS 제목, p_result AS 판결결과, p_grade AS 중요도, 
                       read_count AS 회독수, p_location AS 교재위치, p_exams AS 출제내역, p_tags AS 태그 
                FROM precedents 
                ORDER BY id DESC LIMIT 20
            ''', conn)

    if not df_all.empty:
        df_all = df_all.fillna("") 
        st.dataframe(df_all, use_container_width=True, hide_index=True)
        if not search_query:
            st.caption("최근 등록된 판례 최대 20개를 보여줍니다.")
    else:
        st.info("등록된 판례가 없습니다.")

# --- 2. 과목별 판례집 ---
elif menu in ["🏛️ 헌법 판례집", "⚖️ 행정법 판례집"]:
    subject = "헌법" if menu == "🏛️ 헌법 판례집" else "행정법"
    st.title(menu)
    st.markdown(f"등록된 {subject} 판례를 검색하거나 필터링하여 모아볼 수 있습니다.")
    st.write("---")
    
    subject_search = st.text_input("🔍 판례 검색", placeholder="판례 번호, 제목, 태그, 기출 내역, 내용 등 검색", key=f"search_{subject}")
    
    col_mid, col_sub, col_grade = st.columns(3)
    mid_options = ["전체"] + list(categories[subject].keys())
    
    with col_mid:
        sel_mid = st.selectbox("📂 목차 선택", mid_options)
    
    with col_sub:
        sel_sub = "전체"
        if sel_mid != "전체":
            sub_options = ["전체"] + categories[subject].get(sel_mid, [])
            sel_sub = st.selectbox("📑 소분류 선택", sub_options)
        else:
            st.selectbox("📑 소분류 선택", ["목차를 먼저 선택하세요"], disabled=True)
            
    with col_grade:
        sel_grade = st.selectbox("⭐ 중요도 선택", ["전체", "S", "A+", "A", "B+", "B", "C+", "C"])
            
    st.write("") 

    st.markdown("<hr class='thin-line'>", unsafe_allow_html=True)
    c_sort1, c_sort2 = st.columns([3, 7])
    
    with c_sort1:
        sort_order = st.radio("정렬 기준", ["중요도순", "최신순"], horizontal=True, label_visibility="collapsed")

    with get_db() as conn:
        conn.row_factory = sqlite3.Row  
        c = conn.cursor()
        
        query = "SELECT * FROM precedents WHERE main_cat = ?"
        params = [subject]
        
        if subject_search:
            like_query = f"%{subject_search}%"
            query += " AND (p_number LIKE ? OR p_tags LIKE ? OR p_title LIKE ? OR p_desc LIKE ? OR p_exams LIKE ?)"
            params.extend([like_query, like_query, like_query, like_query, like_query])

        if sel_mid != "전체":
            query += " AND mid_cat = ?"
            params.append(sel_mid)
        if sel_sub != "전체":
            query += " AND sub_cat = ?"
            params.append(sel_sub)
        if sel_grade != "전체":
            query += " AND p_grade = ?"
            params.append(sel_grade)
            
        if sort_order == "중요도순":
            query += ''' ORDER BY CASE p_grade 
                            WHEN 'S' THEN 1 
                            WHEN 'A+' THEN 2 
                            WHEN 'A' THEN 3 
                            WHEN 'B+' THEN 4 
                            WHEN 'B' THEN 5 
                            WHEN 'C+' THEN 6 
                            WHEN 'C' THEN 7 
                            ELSE 8 END, id DESC'''
        elif sort_order == "최신순":
            query += " ORDER BY id DESC"
                        
        c.execute(query, params)
        rows = c.fetchall()

    total_items = len(rows)

    with c_sort2:
        st.markdown(f"<div style='padding-top: 10px; color: #777; font-size: 14px;'>검색된 판례: 총 <b>{total_items}</b>개</div>", unsafe_allow_html=True)
        
    st.markdown("<hr class='thin-line'>", unsafe_allow_html=True)

    if total_items == 0:
        st.info("해당 조건에 맞는 판례가 없습니다.")
    else:
        page_key = f'current_page_{subject}'
        if page_key not in st.session_state:
            st.session_state[page_key] = 1

        items_per_page = 10
        total_pages = (total_items - 1) // items_per_page + 1

        if st.session_state[page_key] > total_pages:
            st.session_state[page_key] = total_pages

        current_page = st.session_state[page_key]

        start_idx = (current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        paged_rows = rows[start_idx:end_idx]

        for row in paged_rows:
            p = dict(row)
            grade_mark = f"⭐ {p.get('p_grade', 'C')}" if p.get('p_grade') else ""
            result_mark = f"[{p.get('p_result')}] " if subject == '헌법' and p.get('p_result') else ""
            
            rc = p.get('read_count') or 0
            
            if rc >= 10:
                fire_badge = "👑[마스터] "
            elif rc >= 3:
                fire_badge = "🔥 "
            else:
                fire_badge = ""
                
            read_badge = f" [🔄 {rc}회독]" if rc > 0 else ""
            
            with st.expander(f"{fire_badge}{grade_mark} {result_mark}{p.get('p_number', '')} {p.get('p_title', '')}{read_badge}"):
                tab_view, tab_edit = st.tabs(["👁️ 열람", "✏️ 수정 및 삭제"])
                
                with tab_view:
                    st.markdown(f"**카테고리:** {p['main_cat']} > {p['mid_cat']} > {p['sub_cat']}")
                    if p.get('p_location'):
                        st.markdown(f"**📖 교재 수록 위치:** {p['p_location']}")
                    if p.get('p_related'):
                        st.markdown(f"**🔗 연관 판례 및 조문:** {p['p_related']}")
                    if p.get('p_tags'):
                        st.markdown(f"**🏷️ 태그:** `{p['p_tags']}`")
                    
                    st.write("---")
                    st.write("**💡 판례 설명 (해설)**")
                    st.info(p.get('p_desc', '설명이 없습니다.'))
                    
                    st.write("**📄 판례 요지 (원문)**")
                    st.write(p.get('p_content', '내용이 없습니다.'))
                    
                    if p.get('p_exams'):
                        st.write("---")
                        st.write("**🏆 시험 출제 내역**")
                        for exam in p['p_exams'].split('\n'):
                            if exam.strip():
                                st.markdown(f"- {exam}")
                
                with tab_edit:
                    st.caption("카테고리를 바꾸거나 내용을 변경한 뒤 [수정 저장] 버튼을 누르세요.")
                    
                    c_cat1, c_cat2, c_cat3 = st.columns(3)
                    with c_cat1:
                        e_main = st.selectbox("대분류", ["헌법", "행정법"], index=0 if p['main_cat'] == "헌법" else 1, key=f"e_main_{p['id']}")
                    
                    mid_opts = list(categories[e_main].keys()) if e_main in categories else []
                    current_mid = p['mid_cat'] if p['mid_cat'] in mid_opts else (mid_opts[0] if mid_opts else "목차 없음")
                    mid_idx = mid_opts.index(current_mid) if current_mid in mid_opts else 0
                    
                    with c_cat2:
                        e_mid = st.selectbox("목차", mid_opts if mid_opts else ["목차 없음"], index=mid_idx, key=f"e_mid_{p['id']}")
                        
                    sub_opts = categories[e_main].get(e_mid, []) if e_mid != "목차 없음" else []
                    current_sub = p['sub_cat'] if p['sub_cat'] in sub_opts else (sub_opts[0] if sub_opts else "소분류 없음")
                    sub_idx = sub_opts.index(current_sub) if current_sub in sub_opts else 0
                    
                    with c_cat3:
                        e_sub = st.selectbox("소분류", sub_opts if sub_opts else ["소분류 없음"], index=sub_idx, key=f"e_sub_{p['id']}")

                    with st.form(f"edit_form_{p['id']}"):
                        c1, c2 = st.columns(2)
                        grade_opts = ["S", "A+", "A", "B+", "B", "C+", "C"]
                        current_grade = p.get('p_grade', 'C')
                        grade_idx = grade_opts.index(current_grade) if current_grade in grade_opts else 6
                        
                        with c1:
                            e_grade = st.selectbox("⭐ 중요도", grade_opts, index=grade_idx)
                            e_number = st.text_input("📌 판례 번호", p.get('p_number', ''))
                            e_loc = st.text_input("📖 교재 수록 위치", p.get('p_location', ''))
                            if e_main == '헌법':
                                result_opts = ["합헌", "위헌", "헌법불합치", "기각", "인용", "각하", "한정위헌", "기타"]
                                current_result = p.get('p_result') if p.get('p_result') in result_opts else "기타"
                                res_idx = result_opts.index(current_result) if current_result in result_opts else 7
                                e_result = st.selectbox("⚖️ 판결 결과", result_opts, index=res_idx)
                            else:
                                e_result = ""
                                
                        with c2:
                            e_title = st.text_input("📝 판례 제목", p.get('p_title', ''))
                            e_tags = st.text_input("🏷️ 태그", p.get('p_tags', ''))
                            e_rel = st.text_input("🔗 연관 판례 및 조문", p.get('p_related', ''))
                        
                        e_desc = st.text_area("💡 판례 설명", p.get('p_desc', ''), height=100)
                        e_content = st.text_area("📄 판례 요지", p.get('p_content', ''), height=150)
                        e_exams = st.text_area("🏆 시험 출제 내역 (엔터로 여러 개 구분)", p.get('p_exams', ''), height=100)
                        
                        if st.form_submit_button("수정 저장", use_container_width=True):
                            sorted_e_exams = sort_exams_desc(e_exams)
                            with get_db() as up_conn:
                                uc = up_conn.cursor()
                                uc.execute('''UPDATE precedents 
                                              SET main_cat=?, mid_cat=?, sub_cat=?, p_grade=?, p_number=?, p_title=?, p_tags=?, 
                                                  p_location=?, p_related=?, p_desc=?, p_content=?, p_result=?, p_exams=?
                                              WHERE id=?''',
                                           (e_main, e_mid, e_sub, e_grade, e_number, e_title, e_tags, e_loc, e_rel, e_desc, e_content, e_result, sorted_e_exams, p['id']))
                            st.success("✅ 수정이 완료되었습니다!")
                            st.rerun()

                    st.write("---")
                    with st.expander("🚨 판례 삭제 (주의)"):
                        st.caption("삭제한 판례는 복구할 수 없습니다.")
                        if st.button("🗑️ 이 판례 삭제하기", key=f"del_btn_{p['id']}", use_container_width=True, type="primary"):
                            with get_db() as del_conn:
                                dc = del_conn.cursor()
                                dc.execute("DELETE FROM precedents WHERE id=?", (p['id'],))
                            st.success("🗑️ 판례가 삭제되었습니다.")
                            st.rerun()

        st.write("")
        st.write("")
        
        chunk_size = 10
        current_chunk = (current_page - 1) // chunk_size
        start_page = current_chunk * chunk_size + 1
        end_page = min(start_page + chunk_size - 1, total_pages)

        btn_labels = []
        btn_pages = []

        if start_page > 1:
            btn_labels.append("처음")
            btn_pages.append(1)
            btn_labels.append("◀")
            btn_pages.append(start_page - 1)

        for p in range(start_page, end_page + 1):
            btn_labels.append(str(p))
            btn_pages.append(p)

        if end_page < total_pages:
            next_end = min(end_page + chunk_size, total_pages)
            btn_labels.append(f"{end_page+1}~{next_end} ▶")
            btn_pages.append(end_page + 1)
            btn_labels.append("끝")
            btn_pages.append(total_pages)

        cols = st.columns(len(btn_labels))
        
        for i, label in enumerate(btn_labels):
            with cols[i]:
                is_current = (btn_pages[i] == current_page and label == str(btn_pages[i]))
                if st.button(label, key=f"page_btn_{subject}_{label}_{btn_pages[i]}", type="primary" if is_current else "secondary", use_container_width=True):
                    st.session_state[page_key] = btn_pages[i]
                    st.rerun()

# --- 3. 랜덤 복습 기능 (Active Recall) ---
elif menu in ["🎲 헌법 랜덤 복습", "🎲 행정법 랜덤 복습"]:
    subject = "헌법" if "헌법" in menu else "행정법"
    st.title(f"🎲 {subject} 랜덤 복습")
    st.markdown(f"등록된 **{subject} 판례** 중 하나를 무작위로 불러옵니다. 제목과 태그를 보고 핵심 내용을 먼저 떠올려 보세요!")
    st.write("---")
    
    if st.button("🔄 새로운 판례 불러오기", use_container_width=True):
        with get_db() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM precedents WHERE main_cat = ? ORDER BY RANDOM() LIMIT 1", (subject,))
            row = c.fetchone()
            
            if row:
                st.session_state[f'random_p_{subject}'] = dict(row)
                st.session_state[f'read_done_{subject}'] = False
            else:
                st.session_state[f'random_p_{subject}'] = None
                st.warning(f"등록된 {subject} 판례가 없습니다. 판례를 먼저 등록해주세요.")

    p = st.session_state.get(f'random_p_{subject}')
    
    if p:
        st.write("")
        st.write("")
        grade_mark = f"⭐ {p.get('p_grade', 'C')}" if p.get('p_grade') else ""
        rc = p.get('read_count') or 0
        
        if rc >= 10:
            fire_badge = "👑[마스터] "
        elif rc >= 3:
            fire_badge = "🔥 "
        else:
            fire_badge = ""
            
        read_badge = f" [현재 {rc}회독]"
        
        st.subheader(f"{fire_badge}{grade_mark} {p.get('p_number', '')} {p.get('p_title', '')} {read_badge}")
        st.markdown(f"**카테고리:** {p['main_cat']} > {p['mid_cat']} > {p['sub_cat']}")
        
        if p.get('p_tags'):
            st.markdown(f"**🏷️ 태그:** `{p['p_tags']}`")
        if p.get('p_related'):
            st.markdown(f"**🔗 연관 판례 및 조문:** {p['p_related']}")
        
        st.write("")
        
        with st.expander("💡 판결 결과 및 내용 확인하기 (클릭)"):
            if subject == '헌법' and p.get('p_result'):
                st.markdown(f"### ⚖️ 판결 결과: [{p.get('p_result')}]")
                st.write("---")
                
            st.write("**💡 판례 설명 (해설)**")
            st.info(p.get('p_desc', '설명이 없습니다.'))
            
            st.write("**📄 판례 요지 (원문)**")
            st.write(p.get('p_content', '내용이 없습니다.'))
            
            if p.get('p_exams'):
                st.write("---")
                st.write("**🏆 시험 출제 내역**")
                for exam in p['p_exams'].split('\n'):
                    if exam.strip():
                        st.markdown(f"- {exam}")
                        
            if p.get('p_location'):
                st.write("")
                st.caption(f"📖 참고 교재: {p['p_location']}")
                
        st.write("")
        
        if st.session_state.get(f'read_done_{subject}'):
            new_rc = p.get('read_count', 0)
            if new_rc >= 10:
                st.success(f"👑 **대단합니다! {new_rc}회독 마스터 달성!** 이 판례는 이제 완벽하게 내 것이 되었습니다.")
                st.balloons()
            else:
                st.success(f"🎉 **{new_rc}번째 회독 완료!** 머릿속에 확실히 각인되었습니다.")
            st.info("아래의 '다음 판례' 버튼을 눌러 학습을 이어가세요.")
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("✔️ 회독 완료", use_container_width=True, disabled=st.session_state.get(f'read_done_{subject}', False)):
                with get_db() as conn:
                    c = conn.cursor()
                    c.execute("UPDATE precedents SET read_count = COALESCE(read_count, 0) + 1 WHERE id = ?", (p['id'],))
                    
                    c.execute("SELECT read_count FROM precedents WHERE id = ?", (p['id'],))
                    new_count = c.fetchone()[0]
                    
                st.session_state[f'random_p_{subject}']['read_count'] = new_count
                st.session_state[f'read_done_{subject}'] = True
                st.rerun() 
                
        with col_btn2:
            if st.button("⏭️ 다음 판례", use_container_width=True, type="primary"):
                with get_db() as conn:
                    conn.row_factory = sqlite3.Row
                    c = conn.cursor()
                    c.execute("SELECT * FROM precedents WHERE main_cat = ? ORDER BY RANDOM() LIMIT 1", (subject,))
                    row = c.fetchone()
                    if row:
                        st.session_state[f'random_p_{subject}'] = dict(row)
                        st.session_state[f'read_done_{subject}'] = False
                    else:
                        st.session_state[f'random_p_{subject}'] = None
                st.rerun()

# --- 4. 카테고리 관리 ---
elif menu == "📁 카테고리 관리":
    st.title("📁 Categories")
    st.write("목차와 세부 소분류를 추가하거나 삭제할 수 있습니다.")
    
    st.subheader("➕ 카테고리 추가")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**1단계: 목차 추가**")
        main_cat_add = st.selectbox("대분류 선택", ["헌법", "행정법"], key="add_main")
        new_mid = st.text_input("새로운 목차 이름")
        if st.button("목차 추가", use_container_width=True):
            if new_mid and add_category(main_cat_add, new_mid):
                st.success("추가됨!")
                st.rerun()
                
    with col2:
        st.markdown("**2단계: 소분류 추가**")
        mid_options_add = list(categories[main_cat_add].keys())
        if mid_options_add:
            selected_mid_add = st.selectbox("목차 선택", mid_options_add, key="add_mid")
            new_sub = st.text_input("새로운 소분류 이름")
            if st.button("소분류 추가", use_container_width=True):
                if new_sub and add_category(main_cat_add, selected_mid_add, new_sub):
                    st.success("추가됨!")
                    st.rerun()

    st.write("---")
    
    st.subheader("🗑️ 카테고리 삭제")
    st.caption("더 이상 사용하지 않는 목차나 소분류를 지울 수 있습니다. (※ 연결된 판례는 삭제되지 않습니다.)")
    
    main_cat_del = st.selectbox("대분류 선택", ["헌법", "행정법"], key="del_main")
    
    col3, col4 = st.columns(2)
    mid_options_del = list(categories[main_cat_del].keys())
    
    with col3:
        st.markdown("**목차 전체 삭제**")
        if mid_options_del:
            selected_mid_del = st.selectbox("삭제할 목차 선택", mid_options_del, key="del_mid_target")
            if st.button("목차 삭제 (하위 포함)", use_container_width=True, type="primary"):
                with get_db() as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM categories WHERE main_cat=? AND mid_cat=?", (main_cat_del, selected_mid_del))
                st.success(f"'{selected_mid_del}' 목차가 삭제되었습니다.")
                st.rerun()
        else:
            st.info("삭제할 목차가 없습니다.")
            
    with col4:
        st.markdown("**특정 소분류만 삭제**")
        if mid_options_del:
            selected_mid_for_sub = st.selectbox("목차 먼저 선택", mid_options_del, key="del_mid_for_sub")
            sub_options_del = categories[main_cat_del].get(selected_mid_for_sub, [])
            sub_options_del = [s for s in sub_options_del if s] 
            
            if sub_options_del:
                selected_sub_del = st.selectbox("삭제할 소분류 선택", sub_options_del, key="del_sub_target")
                if st.button("소분류 삭제", use_container_width=True, type="primary"):
                    with get_db() as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM categories WHERE main_cat=? AND mid_cat=? AND sub_cat=?", (main_cat_del, selected_mid_for_sub, selected_sub_del))
                    st.success(f"'{selected_sub_del}' 소분류가 삭제되었습니다.")
                    st.rerun()
            else:
                st.info("해당 목차에 삭제할 소분류가 없습니다.")

# --- 5. 판례 등록 ---
elif menu == "✍️ 판례 등록":
    st.title("✍️ Add Precedent")
    st.write("기출 내역 등 판례 상세 정보를 꼼꼼하게 기록하세요.")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        reg_main = st.selectbox("대분류", ["헌법", "행정법"])
    
    mid_options = list(categories[reg_main].keys())
    with col2:
        reg_mid = st.selectbox("목차", mid_options if mid_options else ["목차 없음"])
        
    sub_options = categories[reg_main].get(reg_mid, []) if reg_mid != "목차 없음" else []
    with col3:
        reg_sub = st.selectbox("소분류", sub_options if sub_options else ["소분류 없음"])
        
    if reg_mid == "목차 없음" or reg_sub == "소분류 없음":
        st.warning("카테고리 관리 메뉴에서 목차와 소분류를 먼저 생성해주세요.")
    else:
        with st.form("precedent_form", clear_on_submit=True):
            
            c_grade, c_result = st.columns(2)
            with c_grade:
                p_grade = st.selectbox("⭐ 중요도 (S가 가장 중요함)", ["S", "A+", "A", "B+", "B", "C+", "C"], index=2)
            with c_result:
                if reg_main == "헌법":
                    p_result = st.selectbox("⚖️ 판결 결과", ["합헌", "위헌", "헌법불합치", "기각", "인용", "각하", "한정위헌", "기타"])
                else:
                    p_result = ""
            
            p_number = st.text_input("📌 판례 번호", placeholder="예: 2018헌마736")
            p_title = st.text_input("📝 판례 제목", placeholder="예: 공무원 시험 응시연령 상한 사건")
            
            col_loc, col_rel = st.columns(2)
            with col_loc:
                p_location = st.text_input("📖 교재 수록 위치", placeholder="예: 2024 기본서 1권 152p")
            with col_rel:
                p_related = st.text_input("🔗 연관 판례 및 조문", placeholder="예: 행정기본법 제2조, 2019헌바11")
                
            p_content = st.text_area("📄 판례 요지 및 내용 (원문)", height=150)
            p_desc = st.text_area("💡 판례 설명 (나만의 쉬운 해설)", height=100, placeholder="이 판례의 핵심 논점이나 암기 팁을 적어보세요.")
            p_tags = st.text_input("🏷️ 태그 (쉼표로 구분)", placeholder="예: 공무원, 평등권")
            
            p_exams = st.text_area("🏆 시험 출제 내역 (기출 이력)", height=100, 
                                   placeholder="예:\n2024 국가직 7급 15번\n2023 지방직 7급 12번\n(엔터키로 구분해서 여러 개 입력하시면 자동으로 연도순 정렬됩니다.)")
            
            submit_btn = st.form_submit_button("저장", use_container_width=True)
            
            if submit_btn:
                if p_number and p_title:
                    sorted_exams = sort_exams_desc(p_exams) 
                    
                    with get_db() as conn:
                        c = conn.cursor()
                        reg_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                        cleaned_tags = ", ".join([tag.strip() for tag in p_tags.split(",") if tag.strip()])
                        
                        c.execute('''INSERT INTO precedents 
                                     (main_cat, mid_cat, sub_cat, p_number, p_title, p_content, 
                                      p_tags, p_desc, p_grade, p_location, p_related, p_result, p_exams, reg_date) 
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                  (reg_main, reg_mid, reg_sub, p_number, p_title, p_content, 
                                   cleaned_tags, p_desc, p_grade, p_location, p_related, p_result, sorted_exams, reg_date))
                    st.success(f"✅ [{p_grade}등급] 판례 저장 완료!")
                else:
                    st.error("판례 번호와 제목을 입력하세요.")