import re

PHONE_RE = re.compile(
    r'(?:\+?7|8)\d{9,11}'
    r'|(?:\+?7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}'
    r'|(?:\+?7|8)[\s\-()]*\d{5}[\s\-()]*\d[\s\-()]*\d{2}[\s\-()]*\d{2}'
    r'|(?:\+?7|8)?[\s\-()]*\d{4}[\s\-()]*\d{2}[\s\-()]*\d{2}[\s\-()]*\d{2}'
    r'|\d{2,3}[\s\-()]*\d{2}[\s\-()]*\d{2}[\s\-()]*\d{2}'
)

POSITION_KEYWORDS = [
    "приемная", "приёмная", "секретарь", "отд.закупок", "отдел закупок",
    "гл.агроном", "главный агроном", "агроном", "бухгалтер", "директор",
    "ген.директор", "генеральный директор", "зам.директора", "коммерческий",
    "менеджер", "лпр", "уполномоченный", "заместитель", "заведующий",
]


def parse_phones(raw: str) -> list[dict]:
    if not raw or str(raw).strip().lower() in ("nan", "—", "-", ""):
        return []

    raw = str(raw).strip()
    parts = re.split(r"[;\n]+", raw)
    results = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        phones = PHONE_RE.findall(part)

        remaining = part
        found_phone = None
        if phones:
            found_phone = phones[0].strip()
            remaining = part.replace(found_phone, "").strip(" ,;-")

        name = None
        position = None
        note = None

        name_match = re.search(
            r"([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)",
            remaining,
        )
        if name_match:
            name = name_match.group(1).strip()
            remaining = remaining.replace(name, "").strip(" ,;-")

        for kw in POSITION_KEYWORDS:
            if kw in remaining.lower():
                position = kw
                remaining = re.sub(re.escape(kw), "", remaining, flags=re.IGNORECASE).strip(" ,;-")
                break

        remaining = remaining.strip(" ,;-")
        if remaining:
            note = remaining

        if found_phone or name:
            results.append({
                "phone": found_phone or "",
                "name": name,
                "position": position,
                "note": note,
            })

    return results


if __name__ == "__main__":
    test_cases = [
        ("7 (811) 523-23-36", "7 (811) 523-23-36"),
        ("+7 (81146) 2-13-37", "+7 (81146) 2-13-37"),
        ("892100200475 директор Евгения Александровна", "892100200475"),
        ("7 474 234-59-62; 7 474 715-22-84", "7 474 234-59-62"),
        ("+79210020047", "+79210020047"),
    ]
    for raw, expected_phone in test_cases:
        result = parse_phones(raw)
        phone = result[0]["phone"] if result else ""
        status = "OK" if expected_phone in phone else "FAIL"
        print(f"{status}: '{raw}' -> '{phone}' (expected '{expected_phone}')")
