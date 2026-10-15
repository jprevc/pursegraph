"""IBAN validation for the parsers."""

# IBAN lengths of the SEPA countries, so that a wrapped IBAN's first part never passes as a whole one.
IBAN_LENGTHS = {
    "AD": 24,
    "AT": 20,
    "BE": 16,
    "BG": 22,
    "CH": 21,
    "CY": 28,
    "CZ": 24,
    "DE": 22,
    "DK": 18,
    "EE": 20,
    "ES": 24,
    "FI": 18,
    "FR": 27,
    "GB": 22,
    "GI": 23,
    "GR": 27,
    "HR": 21,
    "HU": 28,
    "IE": 22,
    "IS": 26,
    "IT": 27,
    "LI": 21,
    "LT": 20,
    "LU": 20,
    "LV": 21,
    "MC": 27,
    "MT": 31,
    "NL": 18,
    "NO": 15,
    "PL": 28,
    "PT": 25,
    "RO": 24,
    "SE": 24,
    "SI": 19,
    "SK": 24,
    "SM": 27,
    "VA": 22,
}


def tidy_iban(text: str) -> str:
    """An IBAN as typed, without spaces and in capitals, like the parsers' IBANs."""
    return "".join(text.split()).upper()


def valid_iban(iban: str) -> bool:
    """The country's IBAN length, when known, and the ISO 13616 mod-97 check."""
    if len(iban) != IBAN_LENGTHS.get(iban[:2], len(iban)):
        return False
    digits = "".join(str(int(char, 36)) for char in iban[4:] + iban[:4])
    return int(digits) % 97 == 1
