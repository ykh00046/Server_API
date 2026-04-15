"""
AI Section Component - Enhanced AI Analysis interface.

Features:
- Status indicator
- Smart insights cards
- Enhanced chat UI with Zero-State layout
- Excel download from AI tables
"""

import streamlit as st
import requests
from typing import Optional
from shared.config import API_BASE_URL, GEMINI_MODEL


def render_ai_status_indicator(is_online: bool = True) -> None:
    """
    Render AI status indicator.
    """
    status_color = "#00aa66" if is_online else "#cc4444"
    status_text = "온라인" if is_online else "오프라인"
    status_icon = "●" if is_online else "○"

    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 15px;">
        <span style="color: {status_color}; font-size: 1.2rem;">{status_icon}</span>
        <span style="color: {status_color}; font-weight: 600;">AI 엔진: {status_text}</span>
    </div>
    """, unsafe_allow_html=True)


def render_ai_header_with_animation() -> None:
    """Render AI section header with styling."""
    st.markdown(f"""
    <div style="padding: 5px 0;">
        <h1 style="
            font-size: 2.2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 0px;
        ">
            생산 데이터 분석 AI
        </h1>
        <p style="color: #888; font-size: 0.95rem;">
            Core Engine: {GEMINI_MODEL} | 2025-2026 통합 데이터
        </p>
    </div>
    """, unsafe_allow_html=True)


def render_ai_chat(api_url: str = f"{API_BASE_URL}/chat/") -> None:
    """
    Render professional AI chat interface with Zero-State Conversational UI.
    """
    # Initialize chat history (Empty for True Zero-State)
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # ==========================================
    # 1. Zero-State UI (대화 시작 전 중앙 화면)
    # ==========================================
    if len(st.session_state.messages) == 0:
        st.markdown("""
        <div style="text-align: center; margin-top: 60px; margin-bottom: 40px;">
            <div style="font-size: 3.5rem; margin-bottom: 15px;">👋</div>
            <h2 style="font-weight: 700; color: var(--text-color);">무엇을 분석해 드릴까요?</h2>
            <p style="color: #888; font-size: 1.1rem;">자연어로 질문하면, 수십만 건의 데이터를 즉시 분석해 표와 차트로 답변합니다.</p>
        </div>
        """, unsafe_allow_html=True)

        # Starter Prompt Cards (2x2 Grid)
        st.markdown("""
        <style>
            /* Reset button styling for cards */
            div[data-testid="column"] button {
                width: 100%;
                height: 100%;
                min-height: 120px;
                padding: 20px;
                text-align: left;
                background-color: var(--background-color);
                border: 1px solid rgba(102, 126, 234, 0.2);
                border-radius: 12px;
                transition: all 0.2s ease;
                white-space: pre-wrap;
            }
            div[data-testid="column"] button:hover {
                border-color: #667eea;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.1);
                transform: translateY(-2px);
            }
            div[data-testid="column"] button p {
                font-size: 1rem;
                color: var(--text-color);
                margin: 0;
            }
        </style>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        prompt_clicked = None
        
        with col1:
            if st.button("📊 이번 달 제품별 생산 현황\n\n최근 30일간 제품별 생산량, 배치 수, 점유율을 표로 정리해 줘."):
                prompt_clicked = "최근 30일간 제품별 생산량, 배치 수, 점유율(%)을 표로 정리하고 분석 코멘트도 달아줘."
            if st.button("🏆 생산량 TOP 10 리포트\n\n올해 상위 10개 제품의 생산량, 점유율, 전월 대비 증감을 분석해 줘."):
                prompt_clicked = "올해 상위 10개 제품의 생산량, 점유율(%), 전월 대비 증감률을 표로 보여주고 주요 트렌드를 분석해 줘."
                
        with col2:
            if st.button("⚖️ 전월 대비 증감 분석 리포트\n\n이번 달과 지난 달의 제품별 성과를 비교 분석해 줘."):
                prompt_clicked = "이번 달과 지난 달의 총 생산량, 배치 수를 비교하고, 주요 제품별 증감 현황도 표로 정리해 줘."
            if st.button("🔍 BW0021 종합 분석\n\nBW0021 제품의 월별 추이와 최근 이력을 함께 보여줘."):
                prompt_clicked = "BW0021 제품의 월별 생산 추이와 최근 10건 이력을 표로 보여주고, 평균 생산량과 추세를 분석해 줘."

        if prompt_clicked:
            st.session_state.messages.append({"role": "user", "content": prompt_clicked})
            st.rerun()

        # Fill remaining space so input stays at bottom
        st.markdown("<div style='height: 150px;'></div>", unsafe_allow_html=True)

    # ==========================================
    # 2. Active Chat UI (대화 진행 중)
    # ==========================================
    else:
        # Context Hint Badge
        st.markdown("""
        <div style="display: flex; justify-content: flex-end; margin-bottom: 10px;">
            <span style="background: rgba(102, 126, 234, 0.1); color: #667eea; padding: 6px 16px; border-radius: 20px; font-size: 0.85rem; font-weight: 500;">
                💡 팁: '표로 정리해줘'라고 질문하면 데이터를 엑셀로 다운로드할 수 있습니다.
            </span>
        </div>
        """, unsafe_allow_html=True)

        # Chat container
        chat_container = st.container(height=500)

        with chat_container:
            for i, message in enumerate(st.session_state.messages):
                avatar = "👤" if message["role"] == "user" else "🤖"
                with st.chat_message(message["role"], avatar=avatar):
                    content = message["content"]
                    st.markdown(content)
                    
                    # Excel Download Logic for AI Tables
                    if message["role"] == "assistant" and "|" in content and "\n|" in content:
                        try:
                            import pandas as pd
                            import io
                            
                            lines = content.split('\n')
                            table_lines = [line for line in lines if '|' in line and line.strip().startswith('|')]
                            
                            if len(table_lines) > 2:
                                table_text = '\n'.join(table_lines).replace('**', '')
                                df = pd.read_csv(io.StringIO(table_text.replace(' ', '')), sep='|').dropna(how='all', axis=1)
                                df = df[~df.iloc[:, 0].str.contains(r'^-+$', na=False)]
                                df.columns = [col.strip() for col in df.columns]
                                
                                if not df.empty:
                                    output = io.BytesIO()
                                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                        df.to_excel(writer, index=False, sheet_name='AI_Data')
                                    excel_data = output.getvalue()
                                    
                                    st.download_button(
                                        label="📊 이 데이터를 엑셀로 다운로드",
                                        data=excel_data,
                                        file_name=f"ai_analysis_{i}.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        key=f"dl_ai_table_{i}"
                                    )
                        except Exception:
                            pass

    # ==========================================
    # 3. Input & Processing (공통)
    # ==========================================
    prompt = st.chat_input("데이터에 대해 무엇이든 질문하세요 (예: 올해 1분기 총 생산량은?)")

    if prompt:
        # Avoid duplicate appending if triggered from button
        if len(st.session_state.messages) == 0 or st.session_state.messages[-1]["content"] != prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.rerun()

    # Process the last message if it's from the user
    if len(st.session_state.messages) > 0 and st.session_state.messages[-1]["role"] == "user":
        latest_prompt = st.session_state.messages[-1]["content"]
        
        with chat_container if 'chat_container' in locals() else st.container():
            with st.chat_message("assistant", avatar="🤖"):
                status_placeholder = st.empty()
                status_placeholder.markdown("""
                <div class="typing">
                    <span></span><span></span><span></span>
                </div>
                <style>
                    .typing { display: flex; gap: 4px; padding: 10px; }
                    .typing span { width: 8px; height: 8px; background: #667eea; border-radius: 50%; animation: bounce 1.4s infinite ease-in-out; }
                    .typing span:nth-child(1) { animation-delay: -0.32s; }
                    .typing span:nth-child(2) { animation-delay: -0.16s; }
                    @keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
                </style>
                """, unsafe_allow_html=True)
                
                try:
                    resp = requests.post(api_url, json={"query": latest_prompt}, timeout=60)
                    if resp.status_code == 200:
                        answer = resp.json().get("answer", "응답 없음")
                        st.session_state.messages.append({"role": "assistant", "content": answer})
                        st.rerun()
                    else:
                        status_placeholder.error(f"API 오류: {resp.status_code}")
                except requests.exceptions.ConnectionError:
                    status_placeholder.error("AI 서버에 연결할 수 없습니다. API가 실행 중인지 확인하세요.")
                except Exception as e:
                    status_placeholder.error(f"오류: {e}")

    # Clear chat button (Only in Active Chat UI)
    if len(st.session_state.messages) > 0:
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("새로운 대화 시작", icon="✨", help="대화 기록을 지우고 초기 화면으로 돌아갑니다."):
                st.session_state.messages = []
                st.rerun()


def render_ai_section(api_url: str = f"{API_BASE_URL}/chat/") -> None:
    """
    Render complete AI analysis section with premium CSS.
    """
    # Premium Enterprise CSS
    st.markdown("""
    <style>
        /* Message bubble enhancement */
        [data-testid="stChatMessage"] {
            border: 1px solid rgba(102, 126, 234, 0.15);
            border-radius: 16px;
            padding: 1rem;
            margin-bottom: 1rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            transition: all 0.3s ease;
        }
        
        [data-testid="stChatMessage"]:hover {
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.1);
            transform: translateY(-1px);
        }

        /* Distinct colors for roles */
        [data-testid="stChatMessage"][data-testid*="assistant"] {
            background-color: rgba(102, 126, 234, 0.03);
            border-left: 4px solid #667eea;
        }

        [data-testid="stChatMessage"][data-testid*="user"] {
            background-color: rgba(118, 75, 162, 0.03);
            border-right: 4px solid #764ba2;
        }

        /* Table styling inside chat */
        .stMarkdown table {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            font-size: 0.85rem;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }
        
        .stMarkdown th {
            background-color: #667eea !important;
            color: white !important;
            padding: 10px !important;
            text-align: left !important;
            font-weight: 600;
        }
        
        .stMarkdown td {
            padding: 8px 10px !important;
            border-bottom: 1px solid rgba(128,128,128,0.1) !important;
        }

        /* Download button */
        .stDownloadButton button {
            border-color: #667eea;
            color: #667eea;
            border-radius: 20px;
            padding: 2px 15px;
            font-size: 0.8rem;
        }
        .stDownloadButton button:hover {
            background-color: #667eea;
            color: white;
        }
    </style>
    """, unsafe_allow_html=True)

    # Header and Status
    col_h, col_s = st.columns([3, 1])
    with col_h:
        render_ai_header_with_animation()
    with col_s:
        st.write("") # Padding
        st.write("")
        render_ai_status_indicator(is_online=True)
    
    st.divider()
    render_ai_chat(api_url)
