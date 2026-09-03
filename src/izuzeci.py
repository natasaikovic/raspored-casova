"""Uski, eksplicitno odobreni izuzeci od opstih pravila rasporeda."""

SOLFEDJO_PETI_CAS = frozenset({
    ("Марија Цветковић", "41"),
    ("Соња Пана Виријевић", "42"),
    ("Јелена Михаиловић Красић", "43"),
})

# Samo ove dve osobe zadržavaju čvrsto ograničenje: najviše jedna pauza
# nedeljno, duga najviše dva bloka. Za sve ostale pauze ostaju deo cilja
# kvaliteta, ali njihov broj i trajanje nisu čvrsta ograničenja.
STROGO_OGRANICENE_PAUZE = frozenset({
    "Ивана Љујић",
    "Јелена Првуловић",
})


def dozvoljen_peti_cas_solfedja(predmet: str, nastavnik: str, odeljenja) -> bool:
    """Samo tri odobrena casa Solfedja smeju u peti blok jutarnje smene."""
    return (
        predmet == "Солфеђо"
        and len(odeljenja) == 1
        and (nastavnik, odeljenja[0]) in SOLFEDJO_PETI_CAS
    )


def dozvoljen_peti_cas(predmet: str, nastavnik: str, odeljenja) -> bool:
    """Da li konkretan cas sme u peti blok jutarnje smene."""

    return dozvoljen_peti_cas_solfedja(predmet, nastavnik, odeljenja) or (
        predmet == "Историјско балске игре"
        and nastavnik == "Теодора Мартиновски"
        and tuple(odeljenja) == ("41",)
    )


def izuzet_od_ogranicenja_pauza(osoba: str) -> bool:
    """Da li osoba sme imati više pauza ili pauzu dužu od dva bloka."""

    return osoba not in STROGO_OGRANICENE_PAUZE
