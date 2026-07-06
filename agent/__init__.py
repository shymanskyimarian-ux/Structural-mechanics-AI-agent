# Пакет "agent" містить логіку ШІ-агента:
#   knowledge_base.py  — база знань / RAG над бібліотекою симуляторів
#   schemas.py         — точні JSON-схеми під кожен тип Word-звіту
#   prompts.py         — побудова системного промпту для Ollama
#   verification.py    — самоперевірка рівноваги (self-correction)
#   report_export.py   — рендеринг .docx з docxtpl + вставка зображень епюр
#   capture_js.py      — JS-скрипт для захоплення canvas-зображень із симулятора
