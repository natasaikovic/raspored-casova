"""Uski, eksplicitno odobreni izuzeci od opstih pravila rasporeda."""

SOLFEDJO_PETI_CAS = frozenset({
    ("Марија Цветковић", "41"),
    ("Соња Пана Виријевић", "42"),
    ("Јелена Михаиловић Красић", "43"),
})

# Potvrđeni izuzeci od nedeljnog ograničenja pauza. Za ove osobe pauze i dalje
# ulaze u cilj kvaliteta, ali njihov broj i trajanje nisu čvrsta ograničenja.
IZUZECI_OD_OGRANICENJA_PAUZA = frozenset({
    "Анастасиа Античевић",
    "Бранислава Порчић",
    "Ива Бојовић Петковић",
    "Ксенија Дукић",
    "Лидија Палчић",
    "Марија Вученовић",
    "Мирјана Анђелковић",
    "Нина Анђић",
    "Петар Ђорчевски",
    "Владимир Јовановић",
    "Ђорђе Михајловић",
    "Ђорђина Убовић",
})


def dozvoljen_peti_cas_solfedja(predmet: str, nastavnik: str, odeljenja) -> bool:
    """Samo tri odobrena casa Solfedja smeju u peti blok jutarnje smene."""
    return (
        predmet == "Солфеђо"
        and len(odeljenja) == 1
        and (nastavnik, odeljenja[0]) in SOLFEDJO_PETI_CAS
    )


def izuzet_od_ogranicenja_pauza(osoba: str) -> bool:
    """Da li osoba sme imati više pauza ili pauzu dužu od dva bloka."""

    return osoba in IZUZECI_OD_OGRANICENJA_PAUZA
