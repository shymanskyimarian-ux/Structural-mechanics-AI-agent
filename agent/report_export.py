"""
Формування стандартизованого .docx-звіту.

Числові/текстові поля йдуть у Word-шаблон напряму з JSON, який
повернула модель (та який пройшов самоперевірку у verification.py).
Поля-зображення (*_image) підмінюються на InlineImage, зібрані з
PNG-знімків canvas симулятора (agent/capture_js.py). Якщо якогось
знімку немає (наприклад, легасі-шаблон не має окремого canvas для
ліній впливу) — поле просто лишається порожнім, docx не ламається.
"""

import base64
import io
import os

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage

from .schemas import IMAGE_FIELDS, SCHEMAS

TEMPLATES_DIR = os.path.join("simulators", "templates")


def _decode_image(data_url: str):
    if not data_url:
        return None
    try:
        b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
        return base64.b64decode(b64)
    except Exception:
        return None


def build_docx(doc_type: str, context: dict, images: dict) -> io.BytesIO:
    schema = SCHEMAS.get(doc_type)
    if not schema:
        raise ValueError(f"Невідомий тип звіту: {doc_type}")

    doc_path = os.path.join(TEMPLATES_DIR, schema["doc"])
    if not os.path.exists(doc_path):
        raise FileNotFoundError(f"Не знайдено шаблон Word: {doc_path}")

    doc = DocxTemplate(doc_path)
    ctx = dict(context)

    for field in IMAGE_FIELDS:
        raw = _decode_image((images or {}).get(field))
        if raw:
            try:
                ctx[field] = InlineImage(doc, io.BytesIO(raw), width=Mm(150))
                continue
            except Exception:
                pass
        ctx.setdefault(field, "")
        if not isinstance(ctx.get(field), InlineImage):
            ctx[field] = ""

    doc.render(ctx)
    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out
