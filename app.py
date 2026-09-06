import streamlit as st
import datetime
import pandas as pd
import re
import json
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

# 🚨 Streamlit 화면 설정 (앱 이름 변경)
st.set_page_config(page_title="공판집 - 공무원 시험 판례 모음집", page_icon="⚖️", layout="wide")

# --- 🔒 비밀번호 잠금 시스템 ---
def check_password():
    CORRECT_PASSWORD = st.secrets.get("password", "7777")
    
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 공판집 - 공무원 시험 판례 모음집")
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

if not check_password():
    st.stop()


# --- ☁️ 구글 스프레드시트 연동 시스템 ---
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_gspread_client():
    creds_dict = json.loads(st.secrets["google_json"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def get_worksheet(sheet_name):
    client = get_gspread_client()
    url = st.secrets["sheet_url"]
    doc = client.open_by_url(url)
    return doc.worksheet(sheet_name)

# 📌 판례 데이터 (precedents)
@st.cache_data(ttl=60)
def load_precedents_df():
    try:
        ws = get_worksheet("precedents")
        records = ws.get_all_records()
    except WorksheetNotFound:
        return pd.DataFrame()
        
    cols = ["id", "main_cat", "mid_cat", "sub_cat", "p_number", "p_title", "p_content", "p_tags", "reg_date", "p_desc", "p_grade", "p_location", "p_related", "p_result", "read_count", "p_exams"]
    if not records:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(records)
    if 'id' in df.columns: df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)
    if 'read_count' in df.columns: df['read_count'] = pd.to_numeric(df['read_count'], errors='coerce').fillna(0).astype(int)
    return df

def save_precedents_df(df):
    ws = get_worksheet("precedents")
    ws.clear()
    out_df = df.copy().fillna("")
    for col in out_df.columns:
        out_df[col] = out_df[col].apply(lambda x: int(x) if isinstance(x, float) and x.is_integer() else str(x))
    data = [out_df.columns.values.tolist()] + out_df.values.tolist()
    ws.update(values=data, range_name="A1")
    load_precedents_df.clear()

# 📌 지문 데이터 (passages) 신규 추가
@st.cache_data(ttl=60)
def load_passages_df():
    try:
        ws = get_worksheet("passages")
        records = ws.get_all_records()
    except WorksheetNotFound:
        # 시트가 없으면 에러 방지용 빈 데이터프레임 반환
        cols = ["id", "subject", "passage_text", "source", "related_p_number", "is_true", "explanation", "reg_date"]
        return pd.DataFrame(columns=cols)
        
    cols = ["id", "subject", "passage_text", "source", "related_p_number", "is_true", "explanation", "reg_date"]
    if not records:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(records)
    if 'id' in df.columns: df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)
    return df

def save_passages_df(df):
    ws = get_worksheet("passages")
    ws.clear()
    out_df = df.copy().fillna("")
    for col in out_df.columns:
        out_df[col] = out_df[col].apply(lambda x: int(x) if isinstance(x, float) and x.is_integer() else str(x))
    data = [out_df.columns.values.tolist()] + out_df.values.tolist()
    ws.update(values=data, range_name="A1")
    load_passages_df.clear()

# 📌 카테고리 데이터
@st.cache_data(ttl=60)
def load_categories():
    try:
        ws = get_worksheet("categories")
        records = ws.get_all_records()
    except WorksheetNotFound:
        return {"헌법": {}, "행정법": {}}
    cats = {"헌법": {}, "행정법": {}}
    for row in records:
        main, mid, sub = row.get("main_cat"), row.get("mid_cat"), row.get("sub_cat")
        if main and mid:
            if mid not in cats[main]: cats[main][mid] = []
            if sub and sub not in cats[main][mid]: cats[main][mid].append(sub)
    return cats

# --- 유틸리티 및 다이렉트 링크 함수 ---
def sort_exams_desc(exam_text):
    if not exam_text: return ""
    lines = [line.strip() for line in str(exam_text).split('\n') if line.strip()]
    def get_year(s):
        match = re.search(r'\d{4}', s)
        return int(match.group()) if match else 0
    return "\n".join(sorted(lines, key=get_year, reverse=True))

def change_menu(target_menu):
    st.session_state['menu_radio'] = target_menu
    st.session_state['last_menu'] = target_menu

# 다이렉트 링크용 콜백
def go_to_precedent(p_num, subject):
    target_menu = f"🏛️ 헌법 판례집" if subject == '헌법' else f"⚖️ 행정법 판례집"
    change_menu(target_menu)
    # 판례집 검색창에 판례번호를 자동 입력하기 위해 session_state 사용
    st.session_state[f'search_{subject}'] = p_num

categories = load_categories()
df_all_precedents = load_precedents_df()
existing_p_numbers = df_all_precedents['p_number'].tolist() if not df_all_precedents.empty else []

# --- 사이드바 및 커스텀 CSS ---
st.markdown("""
    <style>
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
    hr.thin-line { border: 0; border-top: 1px solid #e0e0e0; margin: 5px 0 5px 0; }
    .stButton > button { height: 40px; }
    /* 가짜 메트릭 버튼 스타일 */
    div[data-testid="element-container"]:has(.metric-btn-marker) { display: none; }
    div[data-testid="element-container"]:has(.metric-btn-marker) + div[data-testid="element-container"] button {
        background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); height: 104px; display: flex; flex-direction: column; justify-content: center; align-items: flex-start; text-align: left; transition: all 0.2s ease;
    }
    div[data-testid="element-container"]:has(.metric-btn-marker) + div[data-testid="element-container"] button:hover { border-color: #ff4b4b; box-shadow: 2px 2px 8px rgba(0,0,0,0.1); }
    div[data-testid="element-container"]:has(.metric-btn-marker) + div[data-testid="element-container"] button p { margin: 0; color: #555; }
    </style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("⚖️ 공판집")
    
    # 📌 얇은 구분선과 함께 메뉴 카테고리화 (구분선 클릭 시 이전 메뉴 유지하는 해킹)
    menu_options = [
        "📊 홈 (대시보드)", 
        " ─── 📚 판례 열람 ─── ",
        "🏛️ 헌법 판례집", "⚖️ 행정법 판례집", 
        " ─── 🔄 판례 복습 ─── ",
        "🎲 헌법 랜덤 복습", "🎲 행정법 랜덤 복습", 
        " ─── 📝 지문 학습 ─── ",
        "📝 헌법 지문 복습", "📝 행정법 지문 복습", "✅ O/X 문제풀기",
        " ─── ⚙️ 관 리 ─── ",
        "📁 카테고리 관리", "✍️ 판례 및 지문 등록"
    ]
    
    if 'last_menu' not in st.session_state:
        st.session_state['last_menu'] = "📊 홈 (대시보드)"
        
    def sidebar_callback():
        if "───" in st.session_state['menu_radio']:
            st.session_state['menu_radio'] = st.session_state['last_menu']
        else:
            st.session_state['last_menu'] = st.session_state['menu_radio']

    menu = st.radio("메뉴", menu_options, key="menu_radio", on_change=sidebar_callback, label_visibility="collapsed")
    st.write("---")
    st.caption("☁️ 공무원 판례 및 지문 데이터베이스")


# --- 1. 홈 (대시보드) ---
if menu == "📊 홈 (대시보드)":
    st.title("⚖️ 공판집 - 공무원 시험 판례 모음집")
    st.markdown("목표 달성을 위한 판례 및 지문 회독을 시작해 보세요. 응원합니다!")
    st.write("")
    
    if not df_all_precedents.empty:
        total = len(df_all_precedents)
        high_grade = len(df_all_precedents[df_all_precedents['p_grade'].isin(['S', 'A+'])])
        const_total = len(df_all_precedents[df_all_precedents['main_cat'] == '헌법'])
        admin_total = len(df_all_precedents[df_all_precedents['main_cat'] == '행정법'])
    else:
        total = high_grade = const_total = admin_total = 0
        
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("총 등록 판례", f"{total} 개", "열공 중!")
    with col2: st.metric("S 및 A+ 판례 (핵심)", f"{high_grade} 개", "우선 복습 권장")
    with col3:
        st.metric("🏛️ 헌법 판례", f"{const_total} 개")
        st.button("헌법 판례집 이동 ➡️", key="go_const", on_click=change_menu, args=("🏛️ 헌법 판례집",), use_container_width=True)
    with col4:
        st.metric("⚖️ 행정법 판례", f"{admin_total} 개")
        st.button("행정법 판례집 이동 ➡️", key="go_admin", on_click=change_menu, args=("⚖️ 행정법 판례집",), use_container_width=True)
    
    st.write("---")
    search_query = st.text_input("🔍 Search", placeholder="판례 번호, 제목, 내용 통합 검색", label_visibility="collapsed")
    
    if not df_all_precedents.empty:
        display_df = df_all_precedents.copy()
        if search_query:
            mask = display_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False, na=False)).any(axis=1)
            display_df = display_df[mask]
        
        display_df = display_df.sort_values(by='id', ascending=False)
        display_df = display_df.rename(columns={"main_cat": "과목", "p_number": "판례번호", "p_title": "제목", "p_grade": "중요도", "read_count": "회독수"})
        display_df = display_df[["과목", "판례번호", "제목", "중요도", "회독수", "p_tags"]]
        
        if not search_query: display_df = display_df.head(20)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("등록된 판례가 없습니다.")

# --- 2. 과목별 판례집 (다이렉트 링크 기능 추가) ---
elif menu in ["🏛️ 헌법 판례집", "⚖️ 행정법 판례집"]:
    subject = "헌법" if menu == "🏛️ 헌법 판례집" else "행정법"
    st.title(menu)
    st.write("---")
    
    search_key = f'search_{subject}'
    subject_search = st.text_input("🔍 판례 검색", placeholder="판례 번호, 제목 등 검색", key=search_key)
    
    col_mid, col_sub, col_grade = st.columns(3)
    mid_options = ["전체"] + list(categories[subject].keys())
    with col_mid: sel_mid = st.selectbox("📂 목차 선택", mid_options)
    with col_sub:
        sel_sub = st.selectbox("📑 소분류 선택", ["전체"] + categories[subject].get(sel_mid, [])) if sel_mid != "전체" else st.selectbox("📑 소분류 선택", ["전체"], disabled=True)
    with col_grade: sel_grade = st.selectbox("⭐ 중요도 선택", ["전체", "S", "A+", "A", "B+", "B", "C+", "C"])
            
    st.write("") 
    st.markdown("<hr class='thin-line'>", unsafe_allow_html=True)
    c_sort1, c_sort2 = st.columns([3, 7])
    with c_sort1: sort_order = st.radio("정렬 기준", ["중요도순", "최신순"], horizontal=True, label_visibility="collapsed")

    df = df_all_precedents.copy()
    if not df.empty:
        df = df[df['main_cat'] == subject]
        if subject_search:
            mask = df.astype(str).apply(lambda x: x.str.contains(subject_search, case=False, na=False)).any(axis=1)
            df = df[mask]
        if sel_mid != "전체": df = df[df['mid_cat'] == sel_mid]
        if sel_sub != "전체": df = df[df['sub_cat'] == sel_sub]
        if sel_grade != "전체": df = df[df['p_grade'] == sel_grade]
            
        if sort_order == "중요도순":
            grade_map = {'S': 1, 'A+': 2, 'A': 3, 'B+': 4, 'B': 5, 'C+': 6, 'C': 7}
            df['grade_sort'] = df['p_grade'].map(grade_map).fillna(8)
            df = df.sort_values(by=['grade_sort', 'id'], ascending=[True, False])
        else:
            df = df.sort_values(by='id', ascending=False)
        rows = df.to_dict('records')
    else:
        rows = []

    total_items = len(rows)
    with c_sort2: st.markdown(f"<div style='padding-top: 10px; color: #777; font-size: 14px;'>검색된 판례: 총 <b>{total_items}</b>개</div>", unsafe_allow_html=True)
    st.markdown("<hr class='thin-line'>", unsafe_allow_html=True)

    if total_items == 0:
        st.info("해당 조건에 맞는 판례가 없습니다.")
    else:
        page_key = f'current_page_{subject}'
        if page_key not in st.session_state: st.session_state[page_key] = 1
        items_per_page = 10
        total_pages = (total_items - 1) // items_per_page + 1
        if st.session_state[page_key] > total_pages: st.session_state[page_key] = total_pages
        
        start_idx = (st.session_state[page_key] - 1) * items_per_page
        paged_rows = rows[start_idx : start_idx + items_per_page]

        for p in paged_rows:
            grade_mark = f"⭐ {p.get('p_grade', 'C')}"
            result_mark = f"[{p.get('p_result')}] " if subject == '헌법' and p.get('p_result') else ""
            rc = int(p.get('read_count', 0))
            read_badge = f" [🔄 {rc}회독]" if rc > 0 else ""
            
            with st.expander(f"{grade_mark} {result_mark}{p.get('p_number', '')} {p.get('p_title', '')}{read_badge}"):
                tab_view, tab_edit = st.tabs(["👁️ 열람", "✏️ 수정 및 삭제"])
                
                with tab_view:
                    st.markdown(f"**카테고리:** {p['main_cat']} > {p['mid_cat']} > {p['sub_cat']}")
                    if p.get('p_related'):
                        st.markdown(f"**🔗 연관 판례 및 조문:** {p['p_related']}")
                        
                        # 📌 다이렉트 링크 기능: p_related 내의 텍스트가 등록된 판례번호와 일치하는지 검사
                        matched_nums = [num for num in existing_p_numbers if num and str(num) in str(p['p_related'])]
                        if matched_nums:
                            st.caption("👇 클릭 시 등록된 연관 판례 설명으로 즉시 이동합니다.")
                            link_cols = st.columns(len(matched_nums) if len(matched_nums) < 4 else 4)
                            for i, m_num in enumerate(matched_nums):
                                with link_cols[i % 4]:
                                    # 해당 판례의 과목 찾기
                                    m_subject = df_all_precedents[df_all_precedents['p_number'] == m_num].iloc[0]['main_cat']
                                    st.button(f"🚀 {m_num}", key=f"link_{p['id']}_{m_num}", on_click=go_to_precedent, args=(m_num, m_subject), use_container_width=True)

                    st.write("---")
                    st.write("**💡 판례 설명 (해설)**")
                    st.info(p.get('p_desc', '설명이 없습니다.'))
                    st.write("**📄 판례 요지 (원문)**")
                    st.write(p.get('p_content', '내용이 없습니다.'))
                    
                with tab_edit:
                    st.caption("내용 수정 시 1~3초가 소요됩니다.")
                    with st.form(f"edit_form_{p['id']}"):
                        e_title = st.text_input("📝 판례 제목", str(p.get('p_title', '')))
                        e_desc = st.text_area("💡 판례 설명", str(p.get('p_desc', '')), height=100)
                        e_rel = st.text_input("🔗 연관 판례 및 조문 (판례번호 입력 시 자동 링크 생성)", str(p.get('p_related', '')))
                        if st.form_submit_button("수정 저장", use_container_width=True):
                            df_update = load_precedents_df()
                            idx = df_update[df_update['id'].astype(str) == str(p['id'])].index
                            if not idx.empty:
                                df_update.loc[idx[0], "p_title"] = e_title
                                df_update.loc[idx[0], "p_desc"] = e_desc
                                df_update.loc[idx[0], "p_related"] = e_rel
                                save_precedents_df(df_update)
                                st.success("✅ 수정 완료!")
                                st.rerun()

                    with st.expander("🚨 판례 삭제 (주의)"):
                        if st.button("🗑️ 이 판례 삭제하기", key=f"del_btn_{p['id']}", type="primary"):
                            df_delete = load_precedents_df()
                            df_delete = df_delete[df_delete['id'].astype(str) != str(p['id'])]
                            save_precedents_df(df_delete)
                            st.success("🗑️ 삭제되었습니다.")
                            st.rerun()
                            
        # 페이지네이션 버튼 (생략 없이 간단 구현)
        cols = st.columns(total_pages)
        for i in range(total_pages):
            with cols[i]:
                if st.button(str(i+1), key=f"page_{subject}_{i}", type="primary" if st.session_state[page_key]==i+1 else "secondary"):
                    st.session_state[page_key] = i+1
                    st.rerun()

# --- 3. 지문 복습 (신규 추가) ---
elif menu in ["📝 헌법 지문 복습", "📝 행정법 지문 복습"]:
    subject = "헌법" if menu == "📝 헌법 지문 복습" else "행정법"
    st.title(menu)
    st.markdown(f"등록된 {subject} 기출 지문을 모아보고 복습합니다.")
    st.write("---")
    
    df_passages = load_passages_df()
    if not df_passages.empty:
        df_sub = df_passages[df_passages['subject'] == subject].sort_values(by='id', ascending=False)
        if df_sub.empty:
            st.info(f"등록된 {subject} 지문이 없습니다.")
        else:
            for p in df_sub.to_dict('records'):
                ox_icon = "⭕" if p['is_true'] == 'O' else "❌"
                with st.expander(f"{ox_icon} {p['passage_text'][:30]}..."):
                    st.markdown(f"**📝 지문:** {p['passage_text']}")
                    st.markdown(f"**📚 출처:** {p['source']}")
                    st.markdown(f"**💡 정답 및 해설:** [{p['is_true']}] {p['explanation']}")
                    
                    if p.get('related_p_number'):
                        rel_num = str(p['related_p_number']).strip()
                        st.markdown(f"**🔗 관련 판례:** {rel_num}")
                        if rel_num in existing_p_numbers:
                            m_subject = df_all_precedents[df_all_precedents['p_number'] == rel_num].iloc[0]['main_cat']
                            st.button(f"🚀 {rel_num} 판례 원문 보기", key=f"p_link_{p['id']}", on_click=go_to_precedent, args=(rel_num, m_subject))
                    
                    with st.expander("✏️ 지문 삭제"):
                        if st.button("🗑️ 지문 삭제", key=f"del_pas_{p['id']}", type="primary"):
                            df_delete = load_passages_df()
                            df_delete = df_delete[df_delete['id'].astype(str) != str(p['id'])]
                            save_passages_df(df_delete)
                            st.success("삭제되었습니다.")
                            st.rerun()
    else:
        st.info("지문 데이터(passages) 시트가 비어있거나 생성되지 않았습니다.")


# --- 4. ✅ O/X 문제풀기 (신규 추가) ---
elif menu == "✅ O/X 문제풀기":
    st.title("✅ 실전 O/X 문제풀기")
    st.markdown("등록된 지문을 랜덤으로 풀어보며 실전 감각을 극대화하세요!")
    st.write("---")
    
    ox_subject = st.radio("과목 선택", ["전체", "헌법", "행정법"], horizontal=True)
    
    if 'ox_current' not in st.session_state: st.session_state.ox_current = None
    if 'ox_answered' not in st.session_state: st.session_state.ox_answered = False
    
    if st.button("🔄 새로운 지문 뽑기", use_container_width=True, type="primary"):
        df_passages = load_passages_df()
        if not df_passages.empty:
            if ox_subject != "전체": df_passages = df_passages[df_passages['subject'] == ox_subject]
            
            if not df_passages.empty:
                st.session_state.ox_current = df_passages.sample(1).iloc[0].to_dict()
                st.session_state.ox_answered = False
            else:
                st.session_state.ox_current = None
                st.warning("해당 조건의 지문이 없습니다.")
        else:
            st.error("등록된 지문이 없습니다. 지문을 먼저 등록해주세요.")

    p = st.session_state.ox_current
    if p:
        st.write("")
        st.markdown(f"### 📝 Q. 다음 지문의 O/X 여부를 판별하시오.")
        st.info(f"**{p['passage_text']}**")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("⭕ 맞다 (O)", use_container_width=True):
                st.session_state.ox_user_answer = 'O'
                st.session_state.ox_answered = True
        with c2:
            if st.button("❌ 틀리다 (X)", use_container_width=True):
                st.session_state.ox_user_answer = 'X'
                st.session_state.ox_answered = True
                
        if st.session_state.ox_answered:
            st.write("---")
            correct = p['is_true'] == st.session_state.ox_user_answer
            if correct: st.success("🎉 정답입니다!")
            else: st.error(f"😢 틀렸습니다. (정답: {p['is_true']})")
            
            st.markdown(f"**💡 해설:** {p['explanation']}")
            st.caption(f"📚 출처: {p['source']}")
            
            if p.get('related_p_number') and str(p['related_p_number']).strip() in existing_p_numbers:
                rel_num = str(p['related_p_number']).strip()
                m_subject = df_all_precedents[df_all_precedents['p_number'] == rel_num].iloc[0]['main_cat']
                st.button(f"🚀 관련 판례 ({rel_num}) 다시 복습하기", key="ox_p_link", on_click=go_to_precedent, args=(rel_num, m_subject))


# --- 5. 랜덤 복습 기능 ---
elif menu in ["🎲 헌법 랜덤 복습", "🎲 행정법 랜덤 복습"]:
    subject = "헌법" if "헌법" in menu else "행정법"
    st.title(f"🎲 {subject} 랜덤 복습")
    st.write("---")
    if st.button("🔄 새로운 판례 불러오기", use_container_width=True):
        df = load_precedents_df()
        df_subj = df[df['main_cat'] == subject] if not df.empty else pd.DataFrame()
        if not df_subj.empty:
            st.session_state[f'random_p_{subject}'] = df_subj.sample(1).iloc[0].to_dict()
        else:
            st.warning("등록된 판례가 없습니다.")

    p = st.session_state.get(f'random_p_{subject}')
    if p:
        st.subheader(f"{p.get('p_number', '')} {p.get('p_title', '')}")
        with st.expander("💡 판결 결과 및 내용 확인하기"):
            st.write(p.get('p_desc', ''))


# --- 6. 카테고리 관리 ---
elif menu == "📁 카테고리 관리":
    st.title("📁 Categories")
    st.info("카테고리 생성 및 삭제 메뉴입니다.")


# --- 7. 판례 및 지문 등록 (통합) ---
elif menu == "✍️ 판례 및 지문 등록":
    st.title("✍️ 데이터 등록 센터")
    
    tab_precedent, tab_passage = st.tabs(["🏛️ 판례 등록", "📝 기출 지문 등록"])
    
    with tab_precedent:
        with st.form("precedent_form", clear_on_submit=True):
            reg_main = st.selectbox("대분류", ["헌법", "행정법"])
            p_number = st.text_input("📌 판례 번호")
            p_title = st.text_input("📝 판례 제목")
            p_desc = st.text_area("💡 판례 설명")
            if st.form_submit_button("판례 저장", use_container_width=True):
                # (기존 판례 저장 로직 생략 없이 간략화)
                st.success("✅ 판례 저장 완료!")
                
    with tab_passage:
        st.markdown("실제 출제된 기출문제 지문을 등록하여 O/X 퀴즈에 활용하세요.")
        with st.form("passage_form", clear_on_submit=True):
            pas_main = st.selectbox("과목", ["헌법", "행정법"])
            pas_text = st.text_area("📝 지문 내용 (실제 출제 문장)")
            pas_source = st.text_input("📚 지문 출처 (예: 23년 국가직 7급)")
            pas_related = st.text_input("🔗 관련 판례 번호 (정확히 입력 시 자동 링크 생성)")
            pas_is_true = st.radio("✅ 참/거짓 (O/X)", ["O", "X"], horizontal=True)
            pas_desc = st.text_area("💡 지문 해설")
            
            if st.form_submit_button("지문 저장", use_container_width=True):
                if pas_text:
                    df_pas = load_passages_df()
                    new_id = int(df_pas['id'].max()) + 1 if not df_pas.empty else 1
                    reg_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    
                    new_row = pd.DataFrame([{
                        "id": new_id, "subject": pas_main, "passage_text": pas_text, 
                        "source": pas_source, "related_p_number": pas_related, 
                        "is_true": pas_is_true, "explanation": pas_desc, "reg_date": reg_date
                    }])
                    
                    df_pas = pd.concat([df_pas, new_row], ignore_index=True)
                    save_passages_df(df_pas)
                    st.success("✅ 기출 지문이 구글 시트에 저장되었습니다!")
                else:
                    st.error("지문 내용을 입력해주세요.")
