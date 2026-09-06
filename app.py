\import streamlit as st
import datetime
import pandas as pd
import re
import json
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

# 🚨 Streamlit 화면 설정 (최상단 고정)
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

# 📌 지문 데이터 (passages) 
@st.cache_data(ttl=60)
def load_passages_df():
    try:
        ws = get_worksheet("passages")
        records = ws.get_all_records()
    except WorksheetNotFound:
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

def add_category(main_cat, mid_cat, sub_cat=""):
    ws = get_worksheet("categories")
    records = ws.get_all_records()
    new_id = 1 if not records else max([int(r.get("id", 0)) for r in records]) + 1
    for r in records:
        if r.get("main_cat") == main_cat and r.get("mid_cat") == mid_cat and r.get("sub_cat") == sub_cat:
            return False
    ws.append_row([new_id, main_cat, mid_cat, sub_cat])
    load_categories.clear()
    return True

def delete_category(main_cat, mid_cat, sub_cat=None):
    ws = get_worksheet("categories")
    records = ws.get_all_records()
    if not records: return
    df = pd.DataFrame(records)
    if sub_cat is None:
        df = df[~((df['main_cat'] == main_cat) & (df['mid_cat'] == mid_cat))]
    else:
        df = df[~((df['main_cat'] == main_cat) & (df['mid_cat'] == mid_cat) & (df['sub_cat'] == sub_cat))]
    ws.clear()
    out_df = df.fillna("").astype(str)
    data = [out_df.columns.values.tolist()] + out_df.values.tolist()
    ws.update(values=data, range_name="A1")
    load_categories.clear()

# --- 유틸리티 ---
def sort_exams_desc(exam_text):
    if not exam_text: return ""
    lines = [line.strip() for line in str(exam_text).split('\n') if line.strip()]
    def get_year(s):
        match = re.search(r'\d{4}', s)
        return int(match.group()) if match else 0
    return "\n".join(sorted(lines, key=get_year, reverse=True))

def change_menu(target_menu):
    st.session_state['menu_choice'] = target_menu

categories = load_categories()
df_all_precedents = load_precedents_df()

# --- 커스텀 CSS (불필요한 버튼 해킹 코드 완전 삭제) ---
st.markdown("""
    <style>
    div[data-testid="metric-container"] { background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 15px; border-radius: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
    hr.thin-line { border: 0; border-top: 1px solid #e0e0e0; margin: 5px 0 5px 0; }
    .stButton > button { height: 40px; }
    </style>
""", unsafe_allow_html=True)


# --- 사이드바 네비게이션 ---
if 'menu_choice' not in st.session_state:
    st.session_state['menu_choice'] = "📊 홈 (대시보드)"

with st.sidebar:
    st.title("⚖️ 공판집")
    
    menu_options = [
        "📊 홈 (대시보드)", 
        "🏛️ 헌법 판례집", 
        "⚖️ 행정법 판례집", 
        "🎲 헌법 랜덤 복습", 
        "🎲 행정법 랜덤 복습", 
        "📝 헌법 지문 복습", 
        "📝 행정법 지문 복습", 
        "✅ O/X 문제풀기",
        "📁 카테고리 관리", 
        "✍️ 판례 등록", 
        "✍️ 지문 등록"
    ]
    
    menu = st.radio("메뉴", menu_options, key="menu_choice", label_visibility="collapsed")
    st.write("---")
    st.caption("☁️ 공판집 클라우드 연동됨")


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
    with col1: 
        st.metric("총 등록 판례", f"{total} 개", "열공 중!")
    with col2: 
        st.metric("S 및 A+ 판례 (핵심)", f"{high_grade} 개", "우선 복습 권장")
    
    # 📌 깔끔한 기본 숫자(Metric) 형태 복구 및 개별 이동 버튼 적용
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


# --- 2. 과목별 판례집 ---
elif menu in ["🏛️ 헌법 판례집", "⚖️ 행정법 판례집"]:
    subject = "헌법" if menu == "🏛️ 헌법 판례집" else "행정법"
    st.title(menu)
    st.write("---")
    
    search_key = f'search_{subject}'
    subject_search = st.text_input("🔍 판례 검색", placeholder="판례 번호, 제목 등 검색", key=search_key)
    
    col_mid, col_sub, col_grade = st.columns(3)
    mid_options = ["전체"] + list(categories.get(subject, {}).keys())
    with col_mid: sel_mid = st.selectbox("📂 목차 선택", mid_options)
    with col_sub:
        sel_sub = st.selectbox("📑 소분류 선택", ["전체"] + categories.get(subject, {}).get(sel_mid, [])) if sel_mid != "전체" else st.selectbox("📑 소분류 선택", ["전체"], disabled=True)
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
                    if p.get('p_location'): st.markdown(f"**📖 교재 수록 위치:** {p['p_location']}")
                    if p.get('p_related'): st.markdown(f"**🔗 연관 판례 및 조문:** {p['p_related']}")
                    if p.get('p_tags'): st.markdown(f"**🏷️ 태그:** `{p['p_tags']}`")
                    
                    st.write("---")
                    st.write("**💡 판례 설명 (해설)**")
                    st.info(p.get('p_desc', '설명이 없습니다.'))
                    st.write("**📄 판례 요지 (원문)**")
                    st.write(p.get('p_content', '내용이 없습니다.'))
                    if p.get('p_exams'):
                        st.write("---")
                        st.write("**🏆 시험 출제 내역**")
                        for exam in str(p['p_exams']).split('\n'):
                            if exam.strip(): st.markdown(f"- {exam}")
                    
                with tab_edit:
                    st.caption("내용 수정 시 1~3초가 소요됩니다.")
                    with st.form(f"edit_form_{p['id']}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            e_grade = st.selectbox("⭐ 중요도", ["S", "A+", "A", "B+", "B", "C+", "C"], index=["S", "A+", "A", "B+", "B", "C+", "C"].index(p.get('p_grade', 'C')))
                            e_number = st.text_input("📌 판례 번호", str(p.get('p_number', '')))
                        with c2:
                            e_title = st.text_input("📝 판례 제목", str(p.get('p_title', '')))
                            e_rel = st.text_input("🔗 연관 판례 및 조문", str(p.get('p_related', '')))
                        
                        e_desc = st.text_area("💡 판례 설명", str(p.get('p_desc', '')), height=100)
                        e_content = st.text_area("📄 판례 요지", str(p.get('p_content', '')), height=150)
                        
                        if st.form_submit_button("수정 저장", use_container_width=True):
                            df_update = load_precedents_df()
                            idx = df_update[df_update['id'].astype(str) == str(p['id'])].index
                            if not idx.empty:
                                df_update.loc[idx[0], "p_grade"] = e_grade
                                df_update.loc[idx[0], "p_number"] = e_number
                                df_update.loc[idx[0], "p_title"] = e_title
                                df_update.loc[idx[0], "p_related"] = e_rel
                                df_update.loc[idx[0], "p_desc"] = e_desc
                                df_update.loc[idx[0], "p_content"] = e_content
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
                            
        cols = st.columns(total_pages)
        for i in range(total_pages):
            with cols[i]:
                if st.button(str(i+1), key=f"page_{subject}_{i}", type="primary" if st.session_state[page_key]==i+1 else "secondary"):
                    st.session_state[page_key] = i+1
                    st.rerun()


# --- 3. 랜덤 복습 기능 (판례) ---
elif menu in ["🎲 헌법 랜덤 복습", "🎲 행정법 랜덤 복습"]:
    subject = "헌법" if "헌법" in menu else "행정법"
    st.title(f"🎲 {subject} 랜덤 복습")
    st.markdown(f"등록된 **{subject} 판례** 중 하나를 무작위로 불러옵니다. 핵심 내용을 먼저 떠올려 보세요!")
    st.write("---")
    
    if st.button("🔄 새로운 판례 불러오기", use_container_width=True):
        df = load_precedents_df()
        if not df.empty:
            df_subj = df[df['main_cat'] == subject]
            if not df_subj.empty:
                st.session_state[f'random_p_{subject}'] = df_subj.sample(1).iloc[0].to_dict()
                st.session_state[f'read_done_{subject}'] = False
            else:
                st.session_state[f'random_p_{subject}'] = None
                st.warning(f"등록된 {subject} 판례가 없습니다.")
        else:
            st.warning("등록된 판례가 없습니다.")

    p = st.session_state.get(f'random_p_{subject}')
    if p:
        st.write("")
        grade_mark = f"⭐ {p.get('p_grade', 'C')}" if p.get('p_grade') else ""
        rc = int(p.get('read_count', 0))
        read_badge = f" [현재 {rc}회독]"
        
        st.subheader(f"{grade_mark} {p.get('p_number', '')} {p.get('p_title', '')} {read_badge}")
        st.markdown(f"**카테고리:** {p['main_cat']} > {p['mid_cat']} > {p['sub_cat']}")
        if p.get('p_tags'): st.markdown(f"**🏷️ 태그:** `{p['p_tags']}`")
        if p.get('p_related'): st.markdown(f"**🔗 연관 조문:** {p['p_related']}")
        
        st.write("")
        with st.expander("💡 판결 결과 및 내용 확인하기 (클릭)"):
            if subject == '헌법' and p.get('p_result'): st.markdown(f"### ⚖️ 판결 결과: [{p.get('p_result')}]")
            st.info(p.get('p_desc', '설명이 없습니다.'))
            st.write(p.get('p_content', '내용이 없습니다.'))
            if p.get('p_exams'):
                for exam in str(p['p_exams']).split('\n'):
                    if exam.strip(): st.markdown(f"- {exam}")
                
        st.write("")
        if st.session_state.get(f'read_done_{subject}'):
            st.success(f"🎉 **{int(p.get('read_count', 0)) + 1}번째 회독 완료!**")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("✔️ 회독 완료", use_container_width=True, disabled=st.session_state.get(f'read_done_{subject}', False)):
                df_update = load_precedents_df()
                idx = df_update[df_update['id'].astype(str) == str(p['id'])].index
                if not idx.empty:
                    current_rc = int(df_update.loc[idx[0], "read_count"])
                    df_update.loc[idx[0], "read_count"] = current_rc + 1
                    save_precedents_df(df_update)
                    st.session_state[f'random_p_{subject}']['read_count'] = current_rc + 1
                    st.session_state[f'read_done_{subject}'] = True
                    st.rerun() 
        with col_btn2:
            if st.button("⏭️ 다음 판례", use_container_width=True, type="primary"):
                df_subj = load_precedents_df()[load_precedents_df()['main_cat'] == subject]
                if not df_subj.empty:
                    st.session_state[f'random_p_{subject}'] = df_subj.sample(1).iloc[0].to_dict()
                    st.session_state[f'read_done_{subject}'] = False
                st.rerun()


# --- 4. 지문 복습 ---
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
                    
                    with st.expander("✏️ 지문 삭제"):
                        if st.button("🗑️ 지문 삭제", key=f"del_pas_{p['id']}", type="primary"):
                            df_delete = load_passages_df()
                            df_delete = df_delete[df_delete['id'].astype(str) != str(p['id'])]
                            save_passages_df(df_delete)
                            st.success("삭제되었습니다.")
                            st.rerun()
    else:
        st.info("지문 데이터(passages) 시트가 비어있거나 생성되지 않았습니다.")


# --- 5. ✅ O/X 문제풀기 ---
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
            
            if p.get('related_p_number'):
                rel_num = str(p['related_p_number']).strip()
                st.markdown(f"**🔗 관련 판례:** {rel_num}")


# --- 6. 카테고리 관리 ---
elif menu == "📁 카테고리 관리":
    st.title("📁 Categories")
    st.write("목차와 세부 소분류를 추가하거나 삭제할 수 있습니다. (구글 시트 연동으로 1~3초 소요)")
    
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
        mid_options_add = list(categories.get(main_cat_add, {}).keys())
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
    mid_options_del = list(categories.get(main_cat_del, {}).keys())
    
    with col3:
        st.markdown("**목차 전체 삭제**")
        if mid_options_del:
            selected_mid_del = st.selectbox("삭제할 목차 선택", mid_options_del, key="del_mid_target")
            if st.button("목차 삭제 (하위 포함)", use_container_width=True, type="primary"):
                delete_category(main_cat_del, selected_mid_del)
                st.success(f"'{selected_mid_del}' 목차가 삭제되었습니다.")
                st.rerun()
        else:
            st.info("삭제할 목차가 없습니다.")
            
    with col4:
        st.markdown("**특정 소분류만 삭제**")
        if mid_options_del:
            selected_mid_for_sub = st.selectbox("목차 먼저 선택", mid_options_del, key="del_mid_for_sub")
            sub_options_del = categories.get(main_cat_del, {}).get(selected_mid_for_sub, [])
            sub_options_del = [s for s in sub_options_del if s] 
            
            if sub_options_del:
                selected_sub_del = st.selectbox("삭제할 소분류 선택", sub_options_del, key="del_sub_target")
                if st.button("소분류 삭제", use_container_width=True, type="primary"):
                    delete_category(main_cat_del, selected_mid_for_sub, selected_sub_del)
                    st.success(f"'{selected_sub_del}' 소분류가 삭제되었습니다.")
                    st.rerun()
            else:
                st.info("해당 목차에 삭제할 소분류가 없습니다.")


# --- 7. 판례 등록 ---
elif menu == "✍️ 판례 등록":
    st.title("✍️ Add Precedent")
    st.write("기출 내역 등 판례 상세 정보를 꼼꼼하게 기록하세요. (저장 시 1~3초 소요)")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        reg_main = st.selectbox("대분류", ["헌법", "행정법"])
    
    mid_options = list(categories.get(reg_main, {}).keys())
    with col2:
        reg_mid = st.selectbox("목차", mid_options if mid_options else ["목차 없음"])
        
    sub_options = categories.get(reg_main, {}).get(reg_mid, []) if reg_mid != "목차 없음" else []
    with col3:
        reg_sub = st.selectbox("소분류", sub_options if sub_options else ["소분류 없음"])
        
    if reg_mid == "목차 없음" or reg_sub == "소분류 없음":
        st.warning("카테고리 관리 메뉴에서 목차와 소분류를 먼저 생성해주세요.")
    else:
        with st.form("precedent_form", clear_on_submit=True):
            c_grade, c_result = st.columns(2)
            with c_grade:
                p_grade = st.selectbox("⭐ 중요도", ["S", "A+", "A", "B+", "B", "C+", "C"], index=2)
            with c_result:
                p_result = st.selectbox("⚖️ 판결 결과", ["합헌", "위헌", "헌법불합치", "기각", "인용", "각하", "한정위헌", "기타"]) if reg_main == "헌법" else ""
            
            p_number = st.text_input("📌 판례 번호", placeholder="예: 2018헌마736")
            p_title = st.text_input("📝 판례 제목", placeholder="예: 공무원 시험 응시연령 상한 사건")
            
            col_loc, col_rel = st.columns(2)
            with col_loc:
                p_location = st.text_input("📖 교재 수록 위치", placeholder="예: 2024 기본서 1권 152p")
            with col_rel:
                p_related = st.text_input("🔗 연관 판례 및 조문", placeholder="예: 행정기본법 제2조, 2019헌바11")
                
            p_content = st.text_area("📄 판례 요지 및 내용 (원문)", height=150)
            p_desc = st.text_area("💡 판례 설명 (나만의 쉬운 해설)", height=100)
            p_tags = st.text_input("🏷️ 태그 (쉼표로 구분)", placeholder="예: 공무원, 평등권")
            p_exams = st.text_area("🏆 시험 출제 내역 (엔터키로 구분)", height=100)
            
            if st.form_submit_button("저장", use_container_width=True):
                if p_number and p_title:
                    sorted_exams = sort_exams_desc(p_exams) 
                    reg_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    cleaned_tags = ", ".join([tag.strip() for tag in p_tags.split(",") if tag.strip()])
                    
                    df = load_precedents_df()
                    new_id = int(df['id'].max()) + 1 if not df.empty else 1
                    
                    new_row = pd.DataFrame([{
                        "id": new_id, "main_cat": reg_main, "mid_cat": reg_mid, "sub_cat": reg_sub, 
                        "p_number": p_number, "p_title": p_title, "p_content": p_content, 
                        "p_tags": cleaned_tags, "reg_date": reg_date, "p_desc": p_desc, 
                        "p_grade": p_grade, "p_location": p_location, "p_related": p_related, 
                        "p_result": p_result, "read_count": 0, "p_exams": sorted_exams
                    }])
                    df = pd.concat([df, new_row], ignore_index=True)
                    save_precedents_df(df)
                    st.success(f"✅ [{p_grade}등급] 판례 저장 완료! (구글 시트에 반영됨)")
                else:
                    st.error("판례 번호와 제목을 입력하세요.")


# --- 8. 지문 등록 ---
elif menu == "✍️ 지문 등록":
    st.title("✍️ Add Passage")
    st.markdown("실제 출제된 기출문제 지문을 등록하여 O/X 퀴즈에 활용하세요.")
    
    with st.form("passage_form", clear_on_submit=True):
        pas_main = st.selectbox("과목", ["헌법", "행정법"])
        pas_text = st.text_area("📝 지문 내용 (실제 출제 문장)")
        
        col1, col2 = st.columns(2)
        with col1:
            pas_source = st.text_input("📚 지문 출처 (예: 23년 국가직 7급)")
        with col2:
            pas_related = st.text_input("🔗 관련 판례 번호")
            
        pas_is_true = st.radio("✅ 참/거짓 정답 (O/X)", ["O", "X"], horizontal=True)
        pas_desc = st.text_area("💡 지문 해설 (오답인 이유 등)")
        
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
                st.success("✅ 기출 지문이 구글 시트에 안전하게 저장되었습니다!")
            else:
                st.error("지문 내용을 입력해주세요.")
