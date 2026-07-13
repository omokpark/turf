"""화면별 챗봇 위젯 — 지금 화면 데이터(chat_context)만 근거로 답/재정리한다.

컨텍스트 스터핑 방식: 화면이 만든 데이터 마크다운을 system_instruction에 넣고, 사용자
질문만 대화로 주고받는다. 새 검색·API 호출 없음. 판단 원칙 가드레일은 SYSTEM_PROMPT에
못박는다(창업 판단·추천·예측 금지, 관측 사실만). provider = Google Gemini 무료 티어.

세션 대화 이력 키: st.session_state[f"chat_{screen_key}"] — [{"role","text"}] 리스트.
"""

from __future__ import annotations

import streamlit as st
from google import genai
from google.genai import errors, types

from core import config

MODEL = "gemini-2.5-flash"  # 무료 티어·빠름. Q&A/필터에 충분

SYSTEM_PROMPT = """너는 주류회사 영업사원용 도구 'Sales Radar'의 화면 도우미다.
아래 '===화면 데이터==='에 담긴, 사용자가 지금 보고 있는 데이터에만 근거해 한국어로 답한다.

규칙:
1. 오직 아래 화면 데이터만 근거로 삼는다. 새로 검색하거나 데이터를 지어내지 않는다.
   데이터에 없는 것을 물으면 "이 화면에 없는 정보입니다"라고 분명히 말한다.
   (예: 블로그 '글 원문'은 수집하지 않는다 — 관측 건수·시점만 배지에 있다.)
2. 상호·주소·숫자·배지 문구는 데이터에 있는 값을 그대로 인용한다. 반올림·창작 금지.
3. 창업 판단('여기 창업하면 잘된다/버틸까')·추천·예측 문구는 넣지 않는다.
   이 도구의 목적인 '방문 우선순위 랭킹'과 그 근거(배지) 설명은 해도 된다 —
   단, 점수의 근거를 항상 함께 투명하게 제시한다.
4. 사용자가 조건으로 재정리를 요청하면(예: '30평 이상만', '주점 업태만', '최근 신규만')
   화면 데이터에서 해당하는 업소만 추려 표나 목록으로 보여준다.
5. 간결하게. 목록·표가 도움되면 마크다운으로."""

_SUGGESTIONS = {
    "map": ["30평 이상만 추려줘", "최근 신규 개업만 보여줘", "호프·주점 업태만"],
    "ranking": ["상위 5곳 주소 알려줘", "블로그 언급이 많은 곳은?", "주점·호프 업태만 추려줘"],
    "outlook": ["지금 국면을 요약해줘", "순증 모멘텀이 뭐야?", "최근 폐업한 곳은?"],
}


@st.cache_resource(show_spinner=False)
def _client() -> genai.Client | None:
    """Gemini 클라이언트 — 키가 없으면 None(챗봇은 안내만 하고 크래시하지 않는다)."""
    try:
        return genai.Client(api_key=config.gemini_key())
    except RuntimeError:
        return None


def _stream(client: genai.Client, context_md: str, history: list[dict]):
    contents = [
        types.Content(
            role="user" if m["role"] == "user" else "model",
            parts=[types.Part.from_text(text=m["text"])],
        )
        for m in history
    ]
    cfg = types.GenerateContentConfig(
        system_instruction=f"{SYSTEM_PROMPT}\n\n===화면 데이터===\n{context_md}"
    )
    for chunk in client.models.generate_content_stream(model=MODEL, contents=contents, config=cfg):
        if chunk.text:
            yield chunk.text


def render_chat(screen_key: str, context_md: str, suggestions: list[str] | None = None) -> None:
    """화면 맨 아래 접이식 챗봇. context_md = 지금 화면 데이터(chat_context.*가 생성)."""
    suggestions = suggestions or _SUGGESTIONS.get(screen_key, [])
    with st.expander("💬 이 화면에 물어보기", expanded=False):
        client = _client()
        if client is None:
            st.info(
                "이 화면 데이터에 대해 질문하려면 `.env`에 `GEMINI_API_KEY`를 넣으세요 — "
                "aistudio.google.com에서 무료로 발급됩니다. (넣은 뒤 서버 재시작)"
            )
            return

        hist_key = f"chat_{screen_key}"
        history: list[dict] = st.session_state.setdefault(hist_key, [])

        if history and st.button("🧹 대화 지우기", key=f"clear_{screen_key}"):
            st.session_state[hist_key] = []
            st.rerun()

        for msg in history:
            with st.chat_message("user" if msg["role"] == "user" else "assistant"):
                st.markdown(msg["text"])

        pending = None
        if not history and suggestions:
            st.caption("예시 질문:")
            cols = st.columns(len(suggestions))
            for i, s in enumerate(suggestions):
                if cols[i].button(s, key=f"sug_{screen_key}_{i}", use_container_width=True):
                    pending = s

        prompt = pending or st.chat_input("이 화면 데이터에 대해 질문하세요", key=f"in_{screen_key}")
        if not prompt:
            return

        history.append({"role": "user", "text": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            try:
                reply = st.write_stream(_stream(client, context_md, history))
            except errors.ClientError as e:
                if getattr(e, "code", None) == 429:
                    st.warning("무료 사용량 한도에 도달했습니다. 잠시 후 다시 시도하세요.")
                else:
                    st.warning(f"요청을 처리하지 못했습니다: {getattr(e, 'message', e)}")
                return
            except errors.APIError as e:  # 5xx 등
                st.warning(f"Gemini 서버 오류로 응답하지 못했습니다: {getattr(e, 'message', e)}")
                return
            except Exception as e:  # noqa: BLE001 — 챗봇은 어떤 이유로도 앱을 죽이면 안 된다
                st.warning(f"응답 중 오류가 발생했습니다: {e}")
                return

        history.append({"role": "model", "text": reply})
