"""
Самоперевірка (self-correction).

Після кожної відповіді LLM ми не просто довіряємо числам — ми чисто
Python-логікою перевіряємо, що контрольні суми рівноваги (ΣFy, ΣFx, ΣM),
які модель сама зобов'язана порахувати і повернути в JSON, дійсно
близькі до нуля. Якщо ні — це майже завжди ознака арифметичної помилки
LLM, і агент автоматично формує "зауваження" та просить модель
перерахувати ще раз (до MAX_SELF_CORRECTIONS спроб), перш ніж показати
результат користувачу.
"""

from .schemas import CHECK_FIELDS

TOLERANCE = 0.5  # кН або кН·м — допустима похибка округлення


def _to_float(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def check_equilibrium(doc_type: str, data: dict) -> list:
    """Повертає список рядків-проблем (порожній список = усе гаразд)."""
    problems = []
    for key in CHECK_FIELDS.get(doc_type, []):
        val = _to_float(data.get(key))
        if val is None:
            problems.append(f"Поле «{key}» відсутнє в JSON або не є числом.")
        elif abs(val) > TOLERANCE:
            problems.append(
                f"Перевірка рівноваги «{key}» = {val}, що не близько до нуля "
                f"(допуск ±{TOLERANCE}). Ймовірна арифметична помилка."
            )

    if doc_type == "beam":
        for span in data.get("spans") or []:
            val = _to_float(span.get("check_Y"))
            if val is not None and abs(val) > TOLERANCE:
                name = span.get("name", "?")
                problems.append(f"Прогін «{name}»: ΣFy = {val}, очікується ≈0.")

    return problems


def build_correction_message(problems: list) -> str:
    bullet_list = "\n".join(f"- {p}" for p in problems)
    return (
        "САМОПЕРЕВІРКА ВИЯВИЛА ПОМИЛКУ РІВНОВАГИ У ТВОЇЙ ПОПЕРЕДНІЙ ВІДПОВІДІ:\n"
        f"{bullet_list}\n\n"
        "Перерахуй задачу заново, знайди й виправ арифметичну помилку. "
        "Поверни ПОВНИЙ виправлений код у ```html ... ``` та ПОВНИЙ виправлений "
        "JSON у ```json ... ``` за тією ж схемою полів, що й раніше."
    )
