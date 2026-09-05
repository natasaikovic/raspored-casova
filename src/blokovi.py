"""Tačni predmetni ključevi i dijagnostika obaveznih dvočasa (2026/27)."""
from .model import Ulaz

OBAVEZNI_DVOCASI = frozenset({
    "Традиционално певање", "Солфеђо", "Етномузикологија", "Историја игре",
    "Биологија", "Социологија", "Психологија", "Филозофија",
})
INFORMATIKA = "Рачунарство и информатика"
SRPSKI = "Српски језик и књижевност"

def sukobi_fonda(ulaz: Ulaz) -> list[str]:
    greske = []
    for z in ulaz.zahtevi:
        if z.predmet in OBAVEZNI_DVOCASI and z.fond % 2:
            greske.append(
                f"{z.datoteka or 'улаз'}, ред {z.red}: „{z.predmet}“, "
                f"{', '.join(z.odeljenja)}, недељни фонд {z.fond}; "
                "обавезни су искључиво двочаси, а фонд је непаран"
            )
    return greske
