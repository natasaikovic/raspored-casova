"""Uski, eksplicitno odobreni izuzeci od opstih pravila rasporeda."""

SOLFEDJO_PETI_CAS = frozenset({
    ("Марија Цветковић", "41"),
    ("Соња Пана Виријевић", "42"),
    ("Јелена Михаиловић Красић", "43"),
})


def dozvoljen_peti_cas_solfedja(predmet: str, nastavnik: str, odeljenja) -> bool:
    """Samo tri odobrena casa Solfedja smeju u peti blok jutarnje smene."""
    return (
        predmet == "Солфеђо"
        and len(odeljenja) == 1
        and (nastavnik, odeljenja[0]) in SOLFEDJO_PETI_CAS
    )
