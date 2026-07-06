"""
Захоплення зображень схем/епюр із інтерактивного симулятора.

Симулятор рендериться через `st.components.v1.html`, тобто фізично
живе у власному <iframe> всередині сторінки Streamlit. Ми виконуємо
JS не всередині цього iframe, а в контексті ГОЛОВНОЇ сторінки
(через пакет streamlit-javascript), звідки видно всі iframe як
DOM-елементи `window.parent.document`, і — оскільки вони того ж
походження (same-origin, без sandbox) — маємо доступ до їх
contentDocument. Звідти забираємо canvas.toDataURL('image/png').

Це узгоджено з "контрактом" у prompts.py: головний canvas має
id="mainCanvas" (нові симулятори) або один із відомих легасі-id
(archCanvas/frameCanvas/beamCanvas/trussCanvas — вбудовані шаблони).
"""

from typing import Optional

KNOWN_MAIN_IDS = ["mainCanvas", "archCanvas", "frameCanvas", "beamCanvas", "trussCanvas"]


def build_capture_script(diagram_button_id: Optional[str]) -> str:
    known_ids_js = ", ".join(f"'{i}'" for i in KNOWN_MAIN_IDS)
    btn_js = f"'{diagram_button_id}'" if diagram_button_id else "null"
    return f"""
(function() {{
    function findSimulator() {{
        const knownIds = [{known_ids_js}];
        const iframes = window.parent.document.querySelectorAll('iframe');
        for (const f of iframes) {{
            try {{
                const d = f.contentDocument || (f.contentWindow && f.contentWindow.document);
                if (!d) continue;
                for (const id of knownIds) {{
                    const c = d.getElementById(id);
                    if (c && c.tagName === 'CANVAS') return {{ doc: d, canvas: c }};
                }}
            }} catch (e) {{ /* крос-origin iframe — пропускаємо */ }}
        }}
        return null;
    }}

    const found = findSimulator();
    if (!found) {{
        return JSON.stringify({{ error: 'simulator_not_found' }});
    }}

    const d = found.doc;
    const mainCanvas = found.canvas;
    const images = {{}};

    try {{ images.scheme_image = mainCanvas.toDataURL('image/png'); }} catch (e) {{}}

    const diagBtnId = {btn_js};
    if (diagBtnId) {{
        const btn = d.getElementById(diagBtnId);
        if (btn) {{
            try {{ btn.click(); }} catch (e) {{}}
            try {{ images.diagram_image = mainCanvas.toDataURL('image/png'); }} catch (e) {{}}
        }}
    }}
    if (!images.diagram_image) {{
        images.diagram_image = images.scheme_image || null;
    }}

    const infCanvas = d.getElementById('influenceCanvas');
    if (infCanvas) {{
        try {{ images.influence_lines_image = infCanvas.toDataURL('image/png'); }} catch (e) {{}}
    }}
    const unitCanvas = d.getElementById('unitLoadCanvas');
    if (unitCanvas) {{
        try {{ images.unit_load_diagram_image = unitCanvas.toDataURL('image/png'); }} catch (e) {{}}
    }}

    return JSON.stringify({{ images: images }});
}})()
"""
