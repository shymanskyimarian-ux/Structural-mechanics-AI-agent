"""
База знань агента (RAG).

Замість того, щоб при кожному запиті запихати в контекст LLM ПОВНИЙ вміст
УСІХ файлів simulators/templates/*.html (що швидко переповнює контекст
маленьких локальних моделей), ми ведемо легкий індекс `index.json` з
описом + ключовими словами кожного шаблону і підмішуємо в промпт лише
2-3 найбільш релевантні приклади щодо поточного завдання користувача.

Це ж місце відповідає за "самонавчання": коли агент створює новий
симулятор для невідомої йому схеми, новий .html-файл і його опис
дописуються в index.json — і з наступного запиту агент вже "знає"
про нього.
"""

import json
import os
import re
from datetime import datetime
from typing import Optional

TEMPLATES_DIR = os.path.join("simulators", "templates")
INDEX_PATH = os.path.join(TEMPLATES_DIR, "index.json")

KNOWN_TYPES = ("beam", "truss", "arch", "frame")

# невелика "інженерна тезаурус"-мапа для якіснішого пошуку релевантності
SYNONYMS = {
    "beam": ["балка", "балку", "балки", "балці", "гербера", "прогін", "прогони"],
    "truss": ["ферма", "ферму", "ферми", "фермі", "стрижень", "стрижні", "шпренгель"],
    "arch": ["арка", "арку", "арки", "арці", "розпір", "тришарнірна"],
    "frame": ["рама", "раму", "рами", "рамі", "стійка", "ригель", "затяжка"],
}


def ensure_storage():
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    if not os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump({"templates": []}, f, ensure_ascii=False, indent=2)


def load_index() -> dict:
    ensure_storage()
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"templates": []}


def save_index(idx: dict):
    ensure_storage()
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


def list_templates() -> list:
    return load_index().get("templates", [])


def guess_type(query: str) -> Optional[str]:
    """Евристично визначає тип конструкції (beam/truss/arch/frame) із тексту запиту."""
    q = query.lower()
    best, best_score = None, 0
    for t, words in SYNONYMS.items():
        score = sum(1 for w in words if w in q)
        if score > best_score:
            best, best_score = t, score
    return best


def _relevance_score(query: str, entry: dict) -> int:
    q = query.lower()
    score = 0
    for kw in entry.get("keywords", []):
        if kw.lower() in q:
            score += 2
    etype = entry.get("type", "")
    if etype and any(w in q for w in SYNONYMS.get(etype, [])):
        score += 3
    for word in re.findall(r"[а-щьюяіїєa-z]{4,}", entry.get("title", "").lower()):
        if word in q:
            score += 1
    return score


def get_relevant_templates(query: str, k: int = 2, max_chars: int = 2500):
    """
    Повертає (text_for_prompt, matched_entries) — компактний текстовий блок
    із витягом коду 1-2 найрелевантніших шаблонів для підмішування в
    системний промпт, замість повного дампу всієї бібліотеки.
    """
    entries = list_templates()
    if not entries:
        return "(Базі знань поки порожня — це буде перший симулятор.)", []

    scored = sorted(entries, key=lambda e: _relevance_score(query, e), reverse=True)
    top = [e for e in scored if _relevance_score(query, e) > 0][:k]
    if not top:
        # нічого явно не збіглось — все одно даємо приклад стилю коду
        top = entries[:1]

    chunks = []
    for e in top:
        path = os.path.join(TEMPLATES_DIR, e["file"])
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        chunks.append(
            f"--- Приклад шаблону: {e['file']} "
            f"(тип: {e.get('type')}, «{e.get('title', '')}») ---\n"
            f"{content[:max_chars]}\n...[СКОРОЧЕНО ДЛЯ ЕКОНОМІЇ КОНТЕКСТУ]\n"
        )
    return "\n".join(chunks), top


def suggest_metadata(user_prompt: str, doc_type: str) -> dict:
    """Легка (без звернення до LLM) евристика для авто-заповнення форми навчання."""
    words = re.findall(r"[а-щьюяіїєА-ЩЬЮЯІЇЄ]{4,}", user_prompt)
    keywords = list(dict.fromkeys(w.lower() for w in words))[:8]
    title = user_prompt.strip().split(".")[0][:80] or f"Нова схема ({doc_type})"
    safe_base = re.sub(r"[^a-z0-9_]+", "_", title.lower()).strip("_") or f"custom_{doc_type}"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"{safe_base}_{ts}.html"
    return {"title": title, "keywords": keywords, "file_name": file_name}


def add_template(file_name: str, title: str, doc_type: str, keywords: list, html_content: str):
    """Зберігає новий симулятор у бібліотеку (самонавчання агента)."""
    ensure_storage()
    if not file_name.endswith(".html"):
        file_name += ".html"
    path = os.path.join(TEMPLATES_DIR, file_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)

    idx = load_index()
    idx["templates"] = [e for e in idx.get("templates", []) if e["file"] != file_name]
    idx["templates"].append({
        "file": file_name,
        "report": f"report_{doc_type}.docx",
        "type": doc_type,
        "title": title,
        "keywords": keywords,
        "canvas_id": "mainCanvas",
        "diagram_tab_button": "btnDiagM",
        "builtin": False,
        "learned_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_index(idx)
    return path
