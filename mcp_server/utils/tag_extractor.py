import re


TAG_REGEX = re.compile(
    r"\b(?:UTI|ACI|RED|LFS|LFI|CPD|LTQ)(?:_[A-Z0-9_]+)\b"
    r"|\b(?:SIN|CDT)[A-Z0-9_]+\b",
    re.IGNORECASE,
)


def extract_tags_from_text(text: str | None) -> list[str]:
    if not text:
        return []

    found_tags = TAG_REGEX.findall(text)

    tags_unicas: list[str] = []
    vistos = set()

    for tag in found_tags:
        clean_tag = tag.upper()

        if clean_tag not in vistos:
            tags_unicas.append(clean_tag)
            vistos.add(clean_tag)

    return tags_unicas


def merge_unique_tags(*tag_lists: list[str]) -> list[str]:
    resultado: list[str] = []
    vistos = set()

    for tag_list in tag_lists:
        for tag in tag_list or []:
            clean_tag = str(tag).upper().strip()

            if clean_tag and clean_tag not in vistos:
                resultado.append(clean_tag)
                vistos.add(clean_tag)

    return resultado