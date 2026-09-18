"""The 43 electoral circumscriptions (fixed by law: 41 counties in
alphabetical order + Bucharest (42) + Diaspora (43)). Codes are the
standard county abbreviations; B for Bucharest, DIA for Diaspora."""

CIRCUMSCRIPTII = [
    {"nr": 1, "cod": "AB", "nume": "Alba"},
    {"nr": 2, "cod": "AR", "nume": "Arad"},
    {"nr": 3, "cod": "AG", "nume": "Argeș"},
    {"nr": 4, "cod": "BC", "nume": "Bacău"},
    {"nr": 5, "cod": "BH", "nume": "Bihor"},
    {"nr": 6, "cod": "BN", "nume": "Bistrița-Năsăud"},
    {"nr": 7, "cod": "BT", "nume": "Botoșani"},
    {"nr": 8, "cod": "BV", "nume": "Brașov"},
    {"nr": 9, "cod": "BR", "nume": "Brăila"},
    {"nr": 10, "cod": "BZ", "nume": "Buzău"},
    {"nr": 11, "cod": "CS", "nume": "Caraș-Severin"},
    {"nr": 12, "cod": "CL", "nume": "Călărași"},
    {"nr": 13, "cod": "CJ", "nume": "Cluj"},
    {"nr": 14, "cod": "CT", "nume": "Constanța"},
    {"nr": 15, "cod": "CV", "nume": "Covasna"},
    {"nr": 16, "cod": "DB", "nume": "Dâmbovița"},
    {"nr": 17, "cod": "DJ", "nume": "Dolj"},
    {"nr": 18, "cod": "GL", "nume": "Galați"},
    {"nr": 19, "cod": "GR", "nume": "Giurgiu"},
    {"nr": 20, "cod": "GJ", "nume": "Gorj"},
    {"nr": 21, "cod": "HR", "nume": "Harghita"},
    {"nr": 22, "cod": "HD", "nume": "Hunedoara"},
    {"nr": 23, "cod": "IL", "nume": "Ialomița"},
    {"nr": 24, "cod": "IS", "nume": "Iași"},
    {"nr": 25, "cod": "IF", "nume": "Ilfov"},
    {"nr": 26, "cod": "MM", "nume": "Maramureș"},
    {"nr": 27, "cod": "MH", "nume": "Mehedinți"},
    {"nr": 28, "cod": "MS", "nume": "Mureș"},
    {"nr": 29, "cod": "NT", "nume": "Neamț"},
    {"nr": 30, "cod": "OT", "nume": "Olt"},
    {"nr": 31, "cod": "PH", "nume": "Prahova"},
    {"nr": 32, "cod": "SM", "nume": "Satu Mare"},
    {"nr": 33, "cod": "SJ", "nume": "Sălaj"},
    {"nr": 34, "cod": "SB", "nume": "Sibiu"},
    {"nr": 35, "cod": "SV", "nume": "Suceava"},
    {"nr": 36, "cod": "TR", "nume": "Teleorman"},
    {"nr": 37, "cod": "TM", "nume": "Timiș"},
    {"nr": 38, "cod": "TL", "nume": "Tulcea"},
    {"nr": 39, "cod": "VS", "nume": "Vaslui"},
    {"nr": 40, "cod": "VL", "nume": "Vâlcea"},
    {"nr": 41, "cod": "VN", "nume": "Vrancea"},
    {"nr": 42, "cod": "B", "nume": "București"},
    {"nr": 43, "cod": "DIA", "nume": "Diaspora"},
]

_BY_NR = {c["nr"]: c for c in CIRCUMSCRIPTII}


def cod_pentru_nr(nr: int) -> str:
    return _BY_NR[nr]["cod"]
