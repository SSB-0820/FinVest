LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
}


def normalize_language(value):
    value = (value or "en").strip()
    if value in LANGUAGES:
        return value
    if value.startswith("hi"):
        return "hi"
    if value.startswith("mr"):
        return "mr"
    return "en"
