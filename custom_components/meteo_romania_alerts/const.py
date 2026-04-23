DOMAIN = 'meteo_romania_alerts'
CONF_COUNTY = 'county'

# Romanian counties mapped to region keywords used in ANM weather warnings.
# Each entry: county name -> list of terms that, when found in a warning's text,
# indicate the warning is relevant for that county.
COUNTY_KEYWORDS: dict[str, list[str]] = {
    "Alba":              ["Alba", "Transilvania", "Transilvaniei", "Munții Apuseni", "Apuseni", "intracarpatice"],
    "Arad":              ["Arad", "Crișana", "Munții Apuseni", "Apuseni"],
    "Argeș":             ["Argeș", "Arges", "Muntenia", "Munteniei", "Carpații Meridionali"],
    "Bacău":             ["Bacău", "Bacau", "Moldova", "Moldovei", "Carpații Orientali"],
    "Bihor":             ["Bihor", "Crișana", "Munții Apuseni", "Apuseni"],
    "Bistrița-Năsăud":  ["Bistrița-Năsăud", "Bistrita-Nasaud", "Bistrița", "Transilvania", "Transilvaniei", "Carpații Orientali", "intracarpatice"],
    "Botoșani":          ["Botoșani", "Botosani", "Moldova", "Moldovei"],
    "Brașov":            ["Brașov", "Brasov", "Transilvania", "Transilvaniei", "Carpații de Curbură", "Curbură", "Carpații Orientali", "intracarpatice"],
    "Brăila":            ["Brăila", "Braila", "Muntenia", "Munteniei"],
    "București":         ["București", "Bucuresti", "Muntenia", "Munteniei", "Ilfov"],
    "Buzău":             ["Buzău", "Buzau", "Muntenia", "Munteniei", "Carpații de Curbură", "Curbură"],
    "Călărași":          ["Călărași", "Calarasi", "Muntenia", "Munteniei"],
    "Caraș-Severin":     ["Caraș-Severin", "Caras-Severin", "Banat", "Banatului", "Carpații Meridionali"],
    "Cluj":              ["Cluj", "Transilvania", "Transilvaniei", "Munții Apuseni", "Apuseni", "intracarpatice"],
    "Constanța":         ["Constanța", "Constanta", "Dobrogea", "Dobrogei", "litoral"],
    "Covasna":           ["Covasna", "Transilvania", "Transilvaniei", "Carpații de Curbură", "Curbură", "Carpații Orientali", "intracarpatice"],
    "Dâmbovița":         ["Dâmbovița", "Dambovita", "Muntenia", "Munteniei", "Carpații Meridionali"],
    "Dolj":              ["Dolj", "Oltenia", "Olteniei"],
    "Galați":            ["Galați", "Galati", "Moldova", "Moldovei"],
    "Giurgiu":           ["Giurgiu", "Muntenia", "Munteniei"],
    "Gorj":              ["Gorj", "Oltenia", "Olteniei", "Carpații Meridionali"],
    "Harghita":          ["Harghita", "Transilvania", "Transilvaniei", "Carpații Orientali", "intracarpatice"],
    "Hunedoara":         ["Hunedoara", "Transilvania", "Transilvaniei", "Carpații Meridionali", "Munții Apuseni", "Apuseni", "intracarpatice"],
    "Ialomița":          ["Ialomița", "Ialomita", "Muntenia", "Munteniei"],
    "Iași":              ["Iași", "Iasi", "Moldova", "Moldovei"],
    "Ilfov":             ["Ilfov", "Muntenia", "Munteniei", "București", "Bucuresti"],
    "Maramureș":         ["Maramureș", "Maramures", "Carpații Orientali"],
    "Mehedinți":         ["Mehedinți", "Mehedinti", "Oltenia", "Olteniei"],
    "Mureș":             ["Mureș", "Mures", "Transilvania", "Transilvaniei", "Carpații Orientali", "intracarpatice"],
    "Neamț":             ["Neamț", "Neamt", "Moldova", "Moldovei", "Carpații Orientali"],
    "Olt":               ["Olt", "Oltenia", "Olteniei"],
    "Prahova":           ["Prahova", "Muntenia", "Munteniei", "Carpații de Curbură", "Curbură", "Carpații Meridionali"],
    "Sălaj":             ["Sălaj", "Salaj", "Transilvania", "Transilvaniei"],
    "Satu Mare":         ["Satu Mare", "Maramureș", "Maramures"],
    "Sibiu":             ["Sibiu", "Transilvania", "Transilvaniei", "Carpații Meridionali", "intracarpatice"],
    "Suceava":           ["Suceava", "Moldova", "Moldovei", "Bucovina", "Carpații Orientali"],
    "Teleorman":         ["Teleorman", "Muntenia", "Munteniei"],
    "Timiș":             ["Timiș", "Timis", "Banat", "Banatului"],
    "Tulcea":            ["Tulcea", "Dobrogea", "Dobrogei", "Delta Dunării"],
    "Vâlcea":            ["Vâlcea", "Valcea", "Oltenia", "Olteniei", "Carpații Meridionali"],
    "Vaslui":            ["Vaslui", "Moldova", "Moldovei"],
    "Vrancea":           ["Vrancea", "Moldova", "Moldovei", "Carpații de Curbură", "Curbură", "Carpații Orientali"],
}

# Patterns that indicate a nationwide warning (always relevant).
NATIONWIDE_PATTERNS = [
    "toate regiunile",
    "toată țara",
    "toata tara",
    "întreg teritoriul",
    "întreaga țară",
    "întregul teritoriu",
]

# Map Romanian weather phenomena to concise English labels for local summary.
PHENOMENA_MAP = [
    (r"intensificări\s+(puternice\s+)?ale\s+vântului|vânt\s+puternic|vânt\b", "Strong wind"),
    (r"viscol", "Blizzard"),
    (r"ninsori|ninge|zăpadă|ninsoare", "Snow"),
    (r"precipitații\s+mixte", "Mixed precip."),
    (r"ploi\s+torențiale|precipitații\s+abundente", "Heavy rain"),
    (r"ploaie|ploi|precipitații", "Rain"),
    (r"furtuni|furtună|vijelii|vijelie", "Storms"),
    (r"descărcări\s+electrice", "Thunderstorms"),
    (r"grindină", "Hail"),
    (r"caniculă|val\s+de\s+căldură|temperaturi\s+ridicate|cald\b", "Extreme heat"),
    (r"ger\b|temperaturi\s+scăzute|rece\b|frig\b", "Cold"),
    (r"brumă|îngheț", "Frost"),
    (r"ceață", "Fog"),
    (r"polei", "Ice"),
]

MONTH_SHORT = {
    "ianuarie": "ian", "februarie": "feb", "martie": "mar",
    "aprilie": "apr", "mai": "mai", "iunie": "iun",
    "iulie": "iul", "august": "aug", "septembrie": "sep",
    "octombrie": "oct", "noiembrie": "nov", "decembrie": "dec",
}

MONTH_NUM = {
    "ianuarie": "1", "februarie": "2", "martie": "3",
    "aprilie": "4", "mai": "5", "iunie": "6",
    "iulie": "7", "august": "8", "septembrie": "9",
    "octombrie": "10", "noiembrie": "11", "decembrie": "12",
}

COLOR_EMOJI = {
    "GALBEN": "🟡",
    "PORTOCALIU": "🟠",
    "ROSU": "🔴",
    "NECUNOSCUT": "⚪",
}

COLOR_RGB = {
    "GALBEN":     {"r": 255, "g": 200, "b": 0},
    "PORTOCALIU": {"r": 255, "g": 120, "b": 0},
    "ROSU":       {"r": 255, "g": 0,   "b": 0},
    "NECUNOSCUT": {"r": 200, "g": 200, "b": 200},
}
