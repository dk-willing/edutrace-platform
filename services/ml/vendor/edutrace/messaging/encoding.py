"""SMS segmentation and the Ghanaian-orthography trap.

Ghana's major languages do not fit GSM-7.  Twi/Akan needs ``ɛ`` and ``ɔ``, Ewe
needs ``ɖ ƒ ŋ ʋ``, Dagbani needs ``ɣ ŋ ʒ``.  A single such character forces the
**entire message** into UCS-2, which cuts the segment size from 160 characters
to 70 (67 when concatenated).  A 150-character alert that costs one segment in
English costs three in Twi -- a 3x cost multiplier on the highest-volume thing
the product does, and it renders unreliably on the feature phones most likely
to be at the receiving end.

So: transliterate to ASCII for SMS, and reserve true orthography for voice and
for the web UI, where it costs nothing and reads properly.  ``plan()`` makes the
cost of getting this wrong visible before a single message is sent.
"""

from __future__ import annotations

from dataclasses import dataclass

GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
#: Characters that fit GSM-7 but occupy two septets via the escape table.
GSM7_EXTENDED = "^{}\\[~]|€"

GSM7_SINGLE_LIMIT = 160
GSM7_CONCAT_LIMIT = 153
UCS2_SINGLE_LIMIT = 70
UCS2_CONCAT_LIMIT = 67

#: ASCII fallbacks for the non-GSM-7 letters used in Ghanaian orthographies.
TRANSLITERATIONS = {
    "ɛ": "e", "Ɛ": "E",
    "ɔ": "o", "Ɔ": "O",
    "ɖ": "d", "Ɖ": "D",
    "ƒ": "f", "Ƒ": "F",
    "ŋ": "ng", "Ŋ": "Ng",
    "ʋ": "v", "Ʋ": "V",
    "ɣ": "gh", "Ɣ": "Gh",
    "ʒ": "zh", "Ʒ": "Zh",
    "ɩ": "i", "Ɩ": "I",
    "ʊ": "u", "Ʊ": "U",
    "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...",
}


def transliterate(text: str) -> str:
    """Map Ghanaian orthography to GSM-7-safe ASCII."""
    return "".join(TRANSLITERATIONS.get(ch, ch) for ch in text)


def is_gsm7(text: str) -> bool:
    return all(ch in GSM7_BASIC or ch in GSM7_EXTENDED for ch in text)


def septet_length(text: str) -> int:
    return sum(2 if ch in GSM7_EXTENDED else 1 for ch in text)


@dataclass(frozen=True, slots=True)
class Segmentation:
    encoding: str          # "GSM-7" or "UCS-2"
    units: int             # septets or UTF-16 code units
    segments: int
    per_segment: int
    offending: tuple[str, ...] = ()

    @property
    def wasteful(self) -> bool:
        return self.encoding == "UCS-2"


def plan(text: str) -> Segmentation:
    if is_gsm7(text):
        n = septet_length(text)
        limit = GSM7_SINGLE_LIMIT if n <= GSM7_SINGLE_LIMIT else GSM7_CONCAT_LIMIT
        return Segmentation(
            "GSM-7", n, max(1, -(-n // limit)), limit
        )

    # UTF-16 code units: characters outside the BMP count as two.
    n = sum(2 if ord(ch) > 0xFFFF else 1 for ch in text)
    limit = UCS2_SINGLE_LIMIT if n <= UCS2_SINGLE_LIMIT else UCS2_CONCAT_LIMIT
    offending = tuple(
        sorted({ch for ch in text if ch not in GSM7_BASIC and ch not in GSM7_EXTENDED})
    )
    return Segmentation("UCS-2", n, max(1, -(-n // limit)), limit, offending)


def prepare(text: str, force_ascii: bool = True) -> tuple[str, Segmentation]:
    """Return the wire text and its segmentation.

    With ``force_ascii`` (the default) the text is transliterated first, which
    is almost always the right call for SMS: it turns a 3-segment UCS-2 message
    into a 1-segment GSM-7 one and renders on every handset.
    """
    wire = transliterate(text) if force_ascii else text
    return wire, plan(wire)


__all__ = [
    "Segmentation",
    "TRANSLITERATIONS",
    "transliterate",
    "is_gsm7",
    "septet_length",
    "plan",
    "prepare",
]
