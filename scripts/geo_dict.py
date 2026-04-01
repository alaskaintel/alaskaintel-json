"""
geo_dict.py
Provides a static geocoding lookup table for major Alaska cities, towns, and landmarks.
Also provides an Anchorage street-grid geocoder for APD incident address parsing.
Returns [latitude, longitude] for mapping signals and incidents to the globe.
"""

ALASKA_GEO_DICT = {
    "anchorage": [61.2181, -149.9003],
    "fairbanks": [64.8378, -147.7164],
    "juneau": [58.3019, -134.4197],
    "wasilla": [61.5809, -149.4401],
    "sitka": [57.0531, -135.3300],
    "ketchikan": [55.3422, -131.6461],
    "kenai": [60.5544, -151.2583],
    "kodiak": [57.7900, -152.4072],
    "bethel": [60.7922, -161.7558],
    "palmer": [61.5997, -149.1128],
    "homer": [59.6425, -151.5483],
    "unalaska": [53.8741, -166.5340],
    "dutch harbor": [53.8906, -166.5292],
    "barrow": [71.2906, -156.7887],
    "utqiagvik": [71.2906, -156.7887],
    "soldotna": [60.4878, -151.0583],
    "valdez": [61.1308, -146.3483],
    "nome": [64.5011, -165.4064],
    "kotzebue": [66.8983, -162.5958],
    "petersburg": [56.8125, -132.9556],
    "seward": [60.1042, -149.4422],
    "wrangell": [56.4708, -132.3767],
    "dillingham": [59.0397, -158.4575],
    "cordova": [60.5428, -145.7575],
    "haines": [59.2358, -135.4450],
    "skagway": [59.4583, -135.3139],
    "delta junction": [64.0378, -145.7317],
    "delta": [64.0378, -145.7317],
    "glennallen": [62.1103, -145.5500],
    "tok": [63.3367, -142.9856],
    "north pole": [64.7511, -147.3494],
    "nenana": [64.5619, -149.0983],
    "mcgrath": [62.9564, -155.5958],
    "king salmon": [58.6883, -156.6492],
    "sand point": [55.3392, -160.4969],
    "cold bay": [55.2003, -162.7147],
    "yakutat": [59.5469, -139.7272],
    "girdwood": [60.9576, -149.1558],
    "turnagain": [60.9500, -149.2000],
    "houston": [61.6311, -149.8169],
    "sutton": [61.7103, -148.8872],
    "big lake": [61.5342, -149.9511],
    "aniak": [61.5817, -159.5331],
    "craig": [55.4769, -133.1483],
    "emmonak": [62.7761, -164.5375],
    "galena": [64.7336, -156.9205],
    "klawock": [55.5528, -133.0906],
    "st. marys": [62.0522, -163.1678],
    "st marys": [62.0522, -163.1678],
    "northslope": [71.2906, -156.7887],
    "anch": [61.2181, -149.9003]
}

# ── Anchorage street-grid geocoder ───────────────────────────────────────────
# Covers major corridors and named intersections so APD alerts (which include
# block-level addresses like "500 block of E 5th Ave") get real coordinates
# instead of piling on the generic Anchorage centroid.
#
# Coordinates are centerline midpoints of each named road segment or landmark.

ANCHORAGE_STREETS = {
    # === EAST-WEST CORRIDORS ===
    "international airport rd":    [61.1757, -149.9914],
    "airport rd":                  [61.1757, -149.9914],
    "dimond blvd":                 [61.1394, -149.8800],
    "dimond":                      [61.1394, -149.8800],
    "tudor rd":                    [61.1872, -149.8275],
    "tudor":                       [61.1872, -149.8275],
    "northern lights blvd":        [61.1981, -149.8900],
    "northern lights":             [61.1981, -149.8900],
    "benson blvd":                 [61.2019, -149.8800],
    "benson":                      [61.2019, -149.8800],
    "5th avenue":                  [61.2163, -149.8900],
    "5th ave":                     [61.2163, -149.8900],
    "6th avenue":                  [61.2153, -149.8850],
    "6th ave":                     [61.2153, -149.8850],
    "9th avenue":                  [61.2117, -149.8850],
    "9th ave":                     [61.2117, -149.8850],
    "15th avenue":                 [61.2066, -149.8850],
    "15th ave":                    [61.2066, -149.8850],
    "20th avenue":                 [61.2020, -149.8850],
    "20th ave":                    [61.2020, -149.8850],
    "36th avenue":                 [61.1869, -149.8850],
    "36th ave":                    [61.1869, -149.8850],
    "debarr rd":                   [61.2083, -149.7914],
    "debarr":                      [61.2083, -149.7914],
    "muldoon rd":                  [61.2072, -149.7481],
    "muldoon":                     [61.2072, -149.7481],
    "abbot rd":                    [61.1450, -149.8400],
    "huffman rd":                  [61.1544, -149.8400],
    "huffman":                     [61.1544, -149.8400],
    "o'malley rd":                 [61.1611, -149.8400],
    "o'malley":                    [61.1611, -149.8400],
    "omalley rd":                  [61.1611, -149.8400],
    "rabbit creek rd":             [61.1306, -149.8100],
    "dowling rd":                  [61.1761, -149.8400],
    "dowling":                     [61.1761, -149.8400],
    "klatt rd":                    [61.1483, -149.8400],
    "sand lake rd":                [61.1700, -149.9500],
    "jewel lake rd":               [61.1700, -149.9800],
    "jewel lake":                  [61.1700, -149.9800],
    "w 36th ave":                  [61.1869, -149.9100],
    "fireweed ln":                 [61.2044, -149.8800],
    "fireweed":                    [61.2044, -149.8800],
    "old seward hwy":              [61.1761, -149.8550],
    "new seward hwy":              [61.1761, -149.8550],
    "seward hwy":                  [61.1761, -149.8550],

    # === NORTH-SOUTH CORRIDORS ===
    "minnesota dr":                [61.1900, -149.9480],
    "minnesota":                   [61.1900, -149.9480],
    "c street":                    [61.2050, -149.8878],
    "c st":                        [61.2050, -149.8878],
    "a street":                    [61.2100, -149.8828],
    "a st":                        [61.2100, -149.8828],
    "e street":                    [61.2050, -149.8828],
    "gambell st":                  [61.2060, -149.8692],
    "gambell":                     [61.2060, -149.8692],
    "ingra st":                    [61.2060, -149.8658],
    "ingra":                       [61.2060, -149.8658],
    "lake otis pkwy":              [61.1950, -149.8292],
    "lake otis":                   [61.1950, -149.8292],
    "boniface pkwy":               [61.2050, -149.7783],
    "boniface":                    [61.2050, -149.7783],
    "bragaw st":                   [61.2050, -149.7958],
    "bragaw":                      [61.2050, -149.7958],
    "piper st":                    [61.2050, -149.8200],
    "mountain view dr":            [61.2200, -149.8100],
    "mountain view":               [61.2200, -149.8100],
    "barrett st":                  [61.2200, -149.8050],
    "wisconsin st":                [61.2200, -149.8028],
    "eastern ave":                 [61.2200, -149.8083],
    "e northern lights blvd":      [61.1981, -149.8600],

    # === NEIGHBORHOODS / LANDMARKS ===
    "midtown":                     [61.1967, -149.8872],
    "downtown anchorage":          [61.2181, -149.9003],
    "downtown":                    [61.2181, -149.9003],
    "spenard":                     [61.2019, -149.9183],
    "fairview":                    [61.2139, -149.8542],
    "mountain view":               [61.2228, -149.8125],
    "university area":             [61.1908, -149.8042],
    "university":                  [61.1908, -149.8042],
    "uaa":                         [61.1908, -149.8042],
    "south anchorage":             [61.1500, -149.8400],
    "east anchorage":              [61.2050, -149.7700],
    "rogers park":                 [61.1900, -149.8700],
    "sand lake":                   [61.1700, -149.9600],
    "jewel lake":                  [61.1711, -149.9944],
    "campbell lake":               [61.1567, -149.8600],
    "bayshore":                    [61.1750, -150.0100],
    "oceanview":                   [61.1556, -149.9600],
    "taku campbell":               [61.1650, -149.8300],
    "airport heights":             [61.2083, -149.8200],
    "russian jack":                [61.2119, -149.8008],
    "bartlett":                    [61.2186, -149.7561],
    "nunaka valley":               [61.2208, -149.7753],
    "chugiak":                     [61.3883, -149.4869],
    "eagle river":                 [61.3217, -149.5681],
    "e/r":                         [61.3217, -149.5681],
    "birchwood":                   [61.4072, -149.4628],
    "eklutna":                     [61.4628, -149.3611],
    "ship creek":                  [61.2253, -149.8853],
    "port of anchorage":           [61.2331, -149.8931],

    # === MAJOR RETAIL/HIGH-CALL NODES ===
    "benson blvd and minnesota":   [61.2019, -149.9500],
    "tudor and lake otis":         [61.1872, -149.8292],
    "dimond center":               [61.1406, -149.8503],
    "tikahtnu":                    [61.2308, -149.7722],
    "north muldoon":               [61.2208, -149.7481],
    "elmendorf":                   [61.2506, -149.8011],
    "jber":                        [61.2506, -149.8011],
    "fort richardson":             [61.2722, -149.7108],
}

# Anchorage generic centroid — used as fallback detection
ANCHORAGE_CENTROID = [61.2181, -149.9003]


from typing import List, Optional
import re


def geocode_anchorage_address(text: str) -> Optional[List[float]]:
    """
    Attempt to geocode an Anchorage-specific address or block reference from text.
    Returns [lat, lng] if a known street/neighborhood is found, else None.
    This is used as a secondary pass for APD signals that would otherwise fall
    back to the generic Anchorage centroid.
    """
    if not text:
        return None

    lower = text.lower()

    # Sort by length desc to match "northern lights blvd" before "northern lights"
    sorted_keys = sorted(ANCHORAGE_STREETS.keys(), key=len, reverse=True)

    for key in sorted_keys:
        if re.search(r'\b' + re.escape(key) + r'\b', lower):
            coords = ANCHORAGE_STREETS[key]
            # Adjust lat slightly based on block number if present
            # e.g. "700 block of e 5th ave" → 700 means east of C St
            block_m = re.search(r'(\d{1,4})\s+block', lower)
            if block_m:
                block = int(block_m.group(1))
                # Anchorage grid: ~100 blocks per ~0.0011 deg lat / ~0.0016 deg lng
                # Offset is very rough — just enough to scatter pins in the right area
                lng_offset = (block / 100) * 0.0016
                return [coords[0], coords[1] - lng_offset]
            return list(coords)

    return None


def geocode_text(text: str) -> Optional[List[float]]:
    """
    Looks for the longest matching location name in the text
    and returns its [lat, lon], or None if not found.
    """
    if not text:
        return None

    lower_text = text.lower()

    # Sort by length descending to match "delta junction" before "delta"
    sorted_keys = sorted(ALASKA_GEO_DICT.keys(), key=len, reverse=True)

    import re as _re
    for key in sorted_keys:
        # Match as a distinct word to avoid matching "nome" in "phenomenon"
        if _re.search(r'\b' + _re.escape(key) + r'\b', lower_text):
            return ALASKA_GEO_DICT[key]

    return None
