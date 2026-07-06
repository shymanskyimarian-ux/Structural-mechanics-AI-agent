"""
Structural Mechanics AI Agent
=============================
Автономний ШІ-агент інженера-конструктора: розв'язує задачі будівельної
механіки (статично визначені балки, ферми, арки, рами), генерує
інтерактивні HTML/JS-симулятори, самонавчається (зберігає нові схеми
у власну базу знань) і формує стандартизований .docx-звіт із
розрахунковими схемами та епюрами. Працює повністю локально на Ollama —
без звернень до будь-якого зовнішнього хмарного API.
"""

import io
import json
import re

import ollama
import streamlit as st
import streamlit.components.v1 as components
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
from streamlit_javascript import st_javascript

from agent import knowledge_base as kb
from agent import report_export
from agent.capture_js import build_capture_script
from agent.prompts import build_system_prompt
from agent.verification import build_correction_message, check_equilibrium

# --------------------------------------------------------------------------
# Захист від запуску `python app.py` замість `streamlit run app.py`
# --------------------------------------------------------------------------
if get_script_run_ctx(suppress_warning=True) is None:
    if __name__ == "__main__":
        print("Помилка: запускайте цей застосунок через Streamlit, а не python.\n"
              "Використайте:\n    streamlit run app.py")
        raise SystemExit(1)

st.set_page_config(page_title="AI Structural Engineer", page_icon="🏗️", layout="wide")

DEFAULT_MODEL = "qwen2.5-coder:7b"
FALLBACK_MODELS = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder:14b",
    "qwen2.5-coder:1.5b",
    "deepseek-coder-v2:16b",
    "llama3.1:8b",
]
MAX_SELF_CORRECTIONS = 2


def extract_html(text: str) -> str:
    match = re.search(r"```html\s*\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_json(text: str) -> dict:
    match = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        # інколи модель лишає висячу кому чи коментар — пробуємо м'яко почистити
        cleaned = re.sub(r",\s*([}\]])", r"\1", match.group(1))
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}


def get_available_ollama_models() -> list:
    try:
        resp = ollama.list()
        names = [m.get("model") or m.get("name") for m in resp.get("models", [])]
        return [n for n in names if n] or FALLBACK_MODELS
    except Exception:
        return FALLBACK_MODELS


# --------------------------------------------------------------------------
# Стан сесії
# --------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # історія для Ollama (без системного — додається динамічно)
    st.session_state.display_messages = []
    st.session_state.latest_html = ""
    st.session_state.latest_json = {}
    st.session_state.latest_type = "beam"
    st.session_state.captured_images = {}
    st.session_state.last_user_prompt = ""

# --------------------------------------------------------------------------
# Бічна панель
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Модель Ollama")
    available_models = get_available_ollama_models()
    model_name = st.selectbox(
        "Модель генерації", options=available_models,
        index=0 if DEFAULT_MODEL not in available_models else available_models.index(DEFAULT_MODEL),
        help="Більші моделі (7b/14b) дають набагато точніші розрахунки, ніж 1.5b.",
    )

    st.markdown("---")
    st.header("🧠 База знань агента")
    templates = kb.list_templates()
    if templates:
        for t in templates:
            tag = "вбудований" if t.get("builtin") else "вивчений"
            st.caption(f"**{t['title']}** _( {tag}, {t['file']} )_")
    else:
        st.caption("Поки порожньо.")

    st.markdown("---")
    st.subheader("🎓 Самонавчання: зберегти поточний симулятор")
    if st.session_state.latest_html:
        suggested = kb.suggest_metadata(st.session_state.last_user_prompt, st.session_state.latest_type)
        new_title = st.text_input("Назва схеми", value=suggested["title"])
        new_keywords = st.text_input(
            "Ключові слова (через кому)", value=", ".join(suggested["keywords"])
        )
        new_file = st.text_input("Ім'я файлу", value=suggested["file_name"])
        if st.button("💾 Запам'ятати у базі знань"):
            kw_list = [w.strip() for w in new_keywords.split(",") if w.strip()]
            kb.add_template(
                file_name=new_file,
                title=new_title,
                doc_type=st.session_state.latest_type,
                keywords=kw_list,
                html_content=st.session_state.latest_html,
            )
            st.success(f"Симулятор «{new_title}» додано до бази знань як {new_file}.")
    else:
        st.caption("Спершу згенеруйте симулятор у чаті.")

    st.markdown("---")
    st.subheader("📄 Експорт у Word")
    st.caption(
        "1) Натисніть «Зняти зображення з симулятора» (захопить схему й епюру "
        "прямо з інтерактивного canvas). 2) Натисніть «Згенерувати .docx»."
    )
    if st.button("📸 Зняти зображення з симулятора"):
        if not st.session_state.latest_html:
            st.error("Немає активного симулятора.")
        else:
            entry = next(
                (t for t in templates if t.get("type") == st.session_state.latest_type),
                None,
            )
            btn_id = entry.get("diagram_tab_button") if entry else "btnDiagM"
            script = build_capture_script(btn_id)
            result = st_javascript(script)
            if isinstance(result, str) and result:
                try:
                    parsed = json.loads(result)
                    if parsed.get("error"):
                        st.warning(
                            "Не вдалося знайти canvas симулятора автоматично "
                            "(можливо, сторінка ще не відрендерилась — спробуйте ще раз)."
                        )
                    else:
                        st.session_state.captured_images = parsed.get("images", {})
                        st.success("Зображення схеми/епюри знято ✅")
                except json.JSONDecodeError:
                    st.warning("Не вдалося розпізнати відповідь браузера, спробуйте ще раз.")
            else:
                st.info("Очікую відповідь браузера… якщо нічого не з'явилось, натисніть кнопку ще раз.")

    if st.button("📥 Згенерувати .docx звіт"):
        if not st.session_state.latest_json:
            st.error("Немає розрахункових даних для звіту. Спочатку розв'яжіть задачу в чаті.")
        else:
            doc_type = st.session_state.latest_json.get("type", st.session_state.latest_type)
            try:
                stream = report_export.build_docx(
                    doc_type=doc_type,
                    context=st.session_state.latest_json,
                    images=st.session_state.captured_images,
                )
                st.download_button(
                    "⬇️ Завантажити Звіт.docx",
                    data=stream,
                    file_name=f"Звіт_{doc_type}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            except FileNotFoundError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Помилка формування Word-звіту: {e}")

# --------------------------------------------------------------------------
# Головний екран
# --------------------------------------------------------------------------
st.title("🏗️ Structural Mechanics AI Agent")
st.caption(
    "Локальний ШІ-агент інженера-конструктора на Ollama — без хмарних API. "
    "Розв'язує балки, ферми, арки та рами; самонавчається новим схемам."
)

if st.session_state.latest_html:
    components.html(st.session_state.latest_html, height=700, scrolling=True)
    st.markdown("---")

for msg in st.session_state.display_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Опишіть інженерне завдання (напр.: 'розрахувати триполкову раму...')"):
    st.session_state.last_user_prompt = prompt
    st.session_state.captured_images = {}

    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.display_messages.append({"role": "user", "content": prompt})

    doc_type_guess = kb.guess_type(prompt) or st.session_state.latest_type
    rag_context, matched = kb.get_relevant_templates(prompt, k=2)
    system_prompt = build_system_prompt(rag_context)

    convo = [{"role": "system", "content": system_prompt}]
    convo.extend(st.session_state.messages)
    convo.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        ai_text = ""
        html_code = ""
        json_data = {}
        attempt = 0

        with st.spinner("Проєктую, розраховую, генерую симулятор..."):
            try:
                response = ollama.chat(
                    model=model_name, messages=convo,
                    options={"num_predict": 6000, "temperature": 0.1},
                )
                ai_text = response["message"]["content"]
                html_code = extract_html(ai_text)
                json_data = extract_json(ai_text)
            except Exception as e:
                st.error(f"Помилка сервера Ollama: {e}. Перевірте, що `ollama serve` запущено.")

        # ---------------- Самокорекція (self-correction loop) ----------------
        doc_type = json_data.get("type", doc_type_guess) if json_data else doc_type_guess
        while json_data and attempt < MAX_SELF_CORRECTIONS:
            problems = check_equilibrium(doc_type, json_data)
            if not problems:
                break
            attempt += 1
            st.warning(
                f"🔁 Агент виявив похибку рівноваги і самостійно перераховує "
                f"(спроба {attempt}/{MAX_SELF_CORRECTIONS})…"
            )
            convo.append({"role": "assistant", "content": ai_text})
            convo.append({"role": "user", "content": build_correction_message(problems)})
            with st.spinner("Перераховую та виправляю помилку..."):
                try:
                    response = ollama.chat(
                        model=model_name, messages=convo,
                        options={"num_predict": 6000, "temperature": 0.1},
                    )
                    ai_text = response["message"]["content"]
                    new_html = extract_html(ai_text)
                    new_json = extract_json(ai_text)
                    if new_html:
                        html_code = new_html
                    if new_json:
                        json_data = new_json
                        doc_type = json_data.get("type", doc_type)
                except Exception as e:
                    st.error(f"Помилка під час самокорекції: {e}")
                    break

        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.messages.append({"role": "assistant", "content": ai_text})

        if json_data:
            st.session_state.latest_json = json_data
            st.session_state.latest_type = doc_type

        if html_code and "<html" in html_code.lower():
            st.session_state.latest_html = html_code
            note = "✅ Симулятор згенеровано та розраховано. Див. інтерактивне вікно вище."
            if attempt:
                note += f" (з {attempt} самокорекцією/ями рівноваги)"
            st.success(note)
            st.session_state.display_messages.append({"role": "assistant", "content": note})
            st.rerun()
        else:
            st.markdown(ai_text)
            st.session_state.display_messages.append({"role": "assistant", "content": ai_text})
