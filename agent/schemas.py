"""
Точні JSON-схеми під кожен тип звіту.

Кожна схема відповідає РІВНО плейсхолдерам {{ ... }} / {% for %} у
відповідному simulators/templates/report_<type>.docx. Це критично: якщо
LLM поверне JSON з іншими іменами полів — Word-звіт буде порожнім у
відповідних місцях. Тому схема повністю виписана в системний промпт
(prompts.py), а не залишена "на розсуд" моделі.

Поля з суфіксом *_image — це base64 PNG-знімки canvas із симулятора,
що підставляються в docx як InlineImage (report_export.py). LLM їх НЕ
генерує — воно лише лишає відповідний ключ у JSON порожнім рядком,
Python сам підставить туди зображення, зняте з інтерактивного симулятора.
"""

IMAGE_FIELDS = [
    "scheme_image",
    "diagram_image",
    "influence_lines_image",
    "unit_load_diagram_image",
]

CHECK_FIELDS = {
    "beam": ["check_Y", "check_M"],
    "truss": ["check_Y"],
    "arch": ["check_Y", "check_X"],
    "frame": ["check_X", "check_Y"],
}

SCHEMAS = {
    "beam": {
        "title": "Багатопрогінна шарнірна балка (балка Гербера)",
        "doc": "report_beam.docx",
        "fields": """{
  "type": "beam",
  "P": число, "q": число, "M": число, "l1": число, "l2": число, "l3": число,
  "variant": число_або_рядок,
  "unknowns_count": число, "equations_count": число, "determinacy_status": "рядок-висновок",
  "scheme_image": "",
  "spans": [
    {"name": "AB", "point1": "A", "reaction1_name": "RA", "reaction1_value": число,
     "point2": "B", "reaction2_name": "RB", "reaction2_value": число, "check_Y": число}
    /* один елемент на кожну просту балку поверхової схеми, від підвісних до головних */
  ],
  "diagram_image": "",
  "check_Y": число, "check_M": число,
  "influence_lines_image": "",
  "comparison": [
    {"name": "RA", "analytic": число, "influence": число, "error": число_у_відсотках}
  ]
}""",
    },
    "truss": {
        "title": "Шпренгельна ферма",
        "doc": "report_truss.docx",
        "fields": """{
  "type": "truss",
  "d": число, "h": число, "F_post": число, "P_timch": число, "panel_num": число,
  "scheme_image": "",
  "Va": число, "Vb": число, "check_Y": число,
  "cuts": [
    {"label": "I-I", "equation_name": "ΣM_вузол", "member": "2-4", "value": число, "state": "розтяг|стиск"}
  ],
  "nodes": [
    {"label": "K1", "member": "1-3", "value": число}
  ],
  "diagram_image": "",
  "members": [
    {"name": "0-1", "N": число, "status": "розтяг|стиск|0"}
  ]
}""",
    },
    "arch": {
        "title": "Тришарнірна арка",
        "doc": "report_arch.docx",
        "fields": """{
  "type": "arch",
  "L": число, "f_L": число, "f": число, "arch_axis_type": "парабола|коло|...",
  "scheme_label": "рядок", "alpha": число, "q": число, "P": число, "x_coef": число,
  "Va": число, "Vb": число, "check_Y": число,
  "Mc0": число, "H_val": число, "check_X": число,
  "xk": число, "yk": число, "tgphi_k": число, "sinphi_k": число, "cosphi_k": число,
  "Mk": число, "Qk": число, "Nk": число,
  "sections": [
    {"x": число, "y": число, "M": число, "Q": число, "N": число}
  ],
  "scheme_image": "", "diagram_image": "",
  "M_max": число, "Q_max": число, "N_max": число,
  "influence_lines_image": ""
}""",
    },
    "frame": {
        "title": "Статично визначена рама",
        "doc": "report_frame.docx",
        "fields": """{
  "type": "frame",
  "L": число, "h": число, "P": число, "M": число, "q": число, "Ip_Ist": число,
  "section_num": "рядок", "disp_direction": "рядок",
  "Vb": число, "Va": число, "Nzt": число, "Ha": число, "Hb": число,
  "check_X": число, "check_Y": число,
  "points": [
    {"name": "A", "M": число, "Q": число, "N": число}
  ],
  "scheme_image": "", "diagram_image": "",
  "M_max": число,
  "Va1": число, "Vb1": число, "Ha1": число,
  "delta": число, "delta_unit": "мм|рад|...",
  "unit_load_diagram_image": ""
}""",
    },
}


def schema_block_for_prompt() -> str:
    parts = []
    for t, s in SCHEMAS.items():
        parts.append(f"### Тип «{t}» — {s['title']} (шаблон {s['doc']})\n```json\n{s['fields']}\n```")
    return "\n\n".join(parts)
