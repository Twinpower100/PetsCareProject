"""
Подсказки и плейсхолдеры для шага 2 мастера регистрации провайдера.

Зависят от страны (выбрана на шаге 1) и от языка интерфейса.
Используются в API GET /api/v1/provider-registration/step2-hints/
"""

# Плейсхолдер телефона по коду страны (ISO 3166-1 alpha-2)
STEP2_PHONE_BY_COUNTRY = {
    'DE': '+49 30 12345678',
    'AT': '+43 1 12345678',
    'CH': '+41 44 123 45 67',
    'FR': '+33 1 12 34 56 78',
    'IT': '+39 06 12345678',
    'ES': '+34 91 123 45 67',
    'PL': '+48 22 123 45 67',
    'NL': '+31 20 123 4567',
    'BE': '+32 2 123 45 67',
    'RU': '+7 495 123-45-67',
    'UA': '+380 44 123-45-67',
    'ME': '+382 20 123 456',
    'RS': '+381 11 123 4567',
    'HR': '+385 1 1234 567',
    'SI': '+386 1 123 45 67',
    'BG': '+359 2 123 4567',
    'RO': '+40 21 123 4567',
    'HU': '+36 1 123 4567',
    'CZ': '+420 2 1234 5678',
    'SK': '+421 2 1234 5678',
    'EE': '+372 612 3456',
    'LV': '+371 67 123 456',
    'LT': '+370 5 123 4567',
    'FI': '+358 9 123 4567',
    'SE': '+46 8 123 456 78',
    'NO': '+47 22 12 34 56',
    'DK': '+45 12 34 56 78',
    'IE': '+353 1 123 4567',
    'GB': '+44 20 7123 4567',
    'PT': '+351 21 123 4567',
    'GR': '+30 21 1234 5678',
}

# Примеры организационно-правовых форм по стране
STEP2_ORG_EXAMPLES_BY_COUNTRY = {
    'DE': 'GmbH, UG, AG, e.K., GbR, OHG, KG, PartG, e.V.',
    'AT': 'GmbH, AG',
    'CH': 'GmbH, AG',
    'FR': 'SARL, SA, SAS',
    'IT': 'S.r.l., S.p.A.',
    'ES': 'S.L., S.A.',
    'PL': 'sp. z o.o., S.A.',
    'NL': 'B.V., N.V.',
    'BE': 'BV, NV',
    'RU': 'ООО, ИП, АО, ПАО, ЗАО, ОАО, НКО, ПК, ГУП, МУП',
    'UA': 'ФОП, ТОВ, ПАТ, ПРАТ, ПП, ТДВ',
    'ME': 'Doo, AD, JP, Preduzetnik, OD, KD',
    'RS': 'Doo, AD',
    'HR': 'Doo, d.o.o.',
    'SI': 'd.o.o.',
    'BG': 'ЕООД, ООД, АД',
    'RO': 'S.R.L., S.A.',
    'HU': 'Kft., Rt.',
    'CZ': 's.r.o., a.s.',
    'SK': 's.r.o., a.s.',
    'EE': 'OÜ, AS',
    'LV': 'SIA, AS',
    'LT': 'UAB, AB',
    'FI': 'Oy, Ab',
    'SE': 'AB',
    'NO': 'AS',
    'DK': 'ApS, A/S',
    'IE': 'Ltd, DAC',
    'GB': 'Ltd, PLC',
    'PT': 'Lda., S.A.',
    'GR': 'ΕΠΕ, ΑΕ',
}

# Шаблон подсказки для названия организации: «Примеры организационно-правовых форм: {examples}»
ORG_NAME_HINT_TEMPLATE = {
    'de': 'Beispiele für Rechtsformen: {examples}',
    'en': 'Examples of legal forms: {examples}',
    'ru': 'Примеры организационно-правовых форм: {examples}',
    'me': 'Primjeri pravnih oblika: {examples}',
}

# Поясняющий текст про опциональность документов (задача #13)
DOCUMENTS_HINT = {
    'de': (
        'Optional können Sie Lizenzen oder Zertifikate hochladen. '
        'Wir zeigen Verbrauchern bei Ihrer Einrichtung den Hinweis „Dokumente vorhanden“ '
        'und auf Wunsch die Dokumente selbst. '
        'Der Upload ist nicht erforderlich und hat keinen Einfluss auf die Registrierung.'
    ),
    'en': (
        'You may optionally upload licences or certificates. '
        'We will show consumers a "Documents available" badge on your organisation\'s profile '
        'and, on request, display the documents. '
        'Upload is not required and does not affect registration.'
    ),
    'ru': (
        'По желанию можно загрузить лицензии или сертификаты. '
        'Мы будем показывать потребителям отметку «Есть документы» в карточке вашей организации, '
        'а по запросу — сами документы. '
        'Загрузка не обязательна и не влияет на регистрацию.'
    ),
    'me': (
        'Po želji možete otpremiti licence ili sertifikate. '
        'Potrošačima ćemo prikazivati oznaku „Dokumenti dostupni“ u kartici vaše organizacije, '
        'a na zahtjev — same dokumente. '
        'Otpremanje nije obavezno i ne utiče na registraciju.'
    ),
}

# Плейсхолдер для поля адреса (задача #12, Google Places)
ADDRESS_PLACEHOLDER = {
    'de': 'Adresse eingeben oder auswählen',
    'en': 'Enter or select address',
    'ru': 'Введите или выберите адрес',
    'me': 'Unesite ili odaberite adresu',
}

# === Шаг 3: реквизиты — плейсхолдеры и подсказки по странам и языку ===
# Подсказка: (placeholder, hint) или (placeholder, { 'en': '...', 'ru': '...', 'de': '...', 'me': '...' })

STEP3_TAX_ID = {
    'RU': ('1234567890', {
        'en': '10 digits (legal entity) or 12 (sole proprietor)',
        'ru': '10 цифр (юрлица) или 12 (ИП)',
        'de': '10 Ziffern (Juristische Person) oder 12 (Einzelunternehmer)',
        'me': '10 cifara (pravno lice) ili 12 (samostalni preduzetnik)',
    }),
    'UA': ('12345678', {
        'en': '8 digits (ЄDRPOU) or 10 (sole proprietor tax ID)',
        'ru': '8 цифр (ЄДРПОУ) или 10 (ИНН ФОП)',
        'de': '8 Ziffern (ЄDRPOU) oder 10 (Steuer-ID Einzelunternehmer)',
        'me': '8 cifara (ЄDRPOU) ili 10 (PIB preduzetnika)',
    }),
    'ME': ('12345678', {
        'en': '8 digits',
        'ru': '8 цифр',
        'de': '8 Ziffern',
        'me': '8 cifara',
    }),
    'DE': ('12345678901', {
        'en': 'Tax number (Steuernummer): 10–11 digits (not VAT ID)',
        'ru': 'ИНН (Steuernummer): 10–11 цифр (не USt-IdNr.)',
        'de': 'Steuernummer: 10–11 Ziffern (nicht USt-IdNr.)',
        'me': 'Porezni broj: 10–11 cifara (ne PDV ID)',
    }),
    'AT': ('123456789', {
        'en': 'Tax number/UID: 8–10 digits (not ATU VAT ID)',
        'ru': 'ИНН/UID: 8–10 цифр (не ATU…)',
        'de': 'Steuernummer/UID: 8–10 Ziffern (nicht ATU…)',
        'me': 'Porezni broj/UID: 8–10 cifara (ne ATU…)',
    }),
    'FR': ('123 456 789', {
        'en': 'SIREN (9 digits) or SIRET (14 digits), not VAT number',
        'ru': 'SIREN (9 цифр) или SIRET (14 цифр), не номер TVA',
        'de': 'SIREN (9 Ziffern) oder SIRET (14 Ziffern), nicht USt-Nr.',
        'me': 'SIREN (9 cifara) ili SIRET (14 cifara), ne PDV broj',
    }),
    'PL': ('123-456-78-90', {
        'en': 'NIP: 10 digits (VAT = PL + NIP)',
        'ru': 'NIP: 10 цифр (VAT = PL + NIP)',
        'de': 'NIP: 10 Ziffern (USt = PL + NIP)',
        'me': 'NIP: 10 cifara (VAT = PL + NIP)',
    }),
}
STEP3_TAX_ID_DEFAULT = ('123456789', {
    'en': 'Digits, format depends on country',
    'ru': 'Цифры, формат зависит от страны',
    'de': 'Ziffern, Format abhängig vom Land',
    'me': 'Cifre, format zavisi od države',
})

# Рег. номер: (placeholder, hint_dict по языку)
STEP3_REGISTRATION_NUMBER = {
    'RU': ('ОГРН 1234567890123', {
        'en': '13 or 15 digits (OGRN/OGRNIP)',
        'ru': '13 или 15 цифр (ОГРН/ОГРНИП)',
        'de': '13 oder 15 Ziffern (OGRN/OGRNIP)',
        'me': '13 ili 15 cifara (OGRN/OGRNIP)',
    }),
    'UA': ('ЄДРПОУ 12345678', {
        'en': '8 digits (ЄDRPOU) or 10 (sole proprietor)',
        'ru': '8 цифр (ЄДРПОУ) или 10 (ИП)',
        'de': '8 Ziffern (ЄDRPOU) oder 10 (Einzelunternehmer)',
        'me': '8 cifara (ЄDRPOU) ili 10 (preduzetnik)',
    }),
    'ME': ('5-0123456', {
        'en': 'Registration number in registry (MAR)',
        'ru': 'Рег. № в реестре (МАР)',
        'de': 'Registernummer (MAR)',
        'me': 'Registracioni broj u registru (MAR)',
    }),
    # Handelsregisternummer: court name + HRA or HRB + number (stdnum.de.handelsregisternummer)
    'DE': ('München HRB 1000', {
        'en': 'Court name + HRA or HRB + number (e.g. München HRB 1000)',
        'ru': 'Название суда + HRA или HRB + номер (напр. München HRB 1000)',
        'de': 'Gerichtsname + HRA oder HRB + Nummer (z. B. München HRB 1000)',
        'me': 'Naziv suda + HRA ili HRB + broj (npr. München HRB 1000)',
    }),
    'AT': ('FN 123456a', {
        'en': 'FN + number (Firmenbuch)',
        'ru': 'FN + номер (Firmenbuch)',
        'de': 'FN + Nummer (Firmenbuch)',
        'me': 'FN + broj (Firmenbuch)',
    }),
    'PL': ('KRS 0000123456', {
        'en': 'KRS, 10 digits',
        'ru': 'KRS, 10 цифр',
        'de': 'KRS, 10 Ziffern',
        'me': 'KRS, 10 cifara',
    }),
    'FR': ('RCS Paris B 123 456 789', {
        'en': 'RCS + city + number',
        'ru': 'RCS + город + номер',
        'de': 'RCS + Stadt + Nummer',
        'me': 'RCS + grad + broj',
    }),
    'IT': ('REA 123456', {
        'en': 'REA + number',
        'ru': 'REA + номер',
        'de': 'REA + Nummer',
        'me': 'REA + broj',
    }),
    'ES': ('B-12345678', {
        'en': 'Registration number in provincial registry',
        'ru': 'Рег. № в реестре провинции',
        'de': 'Registernummer der Provinz',
        'me': 'Registracioni broj u pokrajinskom registru',
    }),
    'NL': ('12345678', {
        'en': 'KvK number, 8 digits',
        'ru': 'KvK‑номер, 8 цифр',
        'de': 'KvK‑nummer, 8 Ziffern',
        'me': 'KvK broj, 8 cifara',
    }),
    'CH': ('CHE-123.456.789', {
        'en': 'UID, 9 digits with dots',
        'ru': 'UID, 9 цифр с точками',
        'de': 'UID, 9 Ziffern mit Punkten',
        'me': 'UID, 9 cifara sa tačkama',
    }),
    'GB': ('12345678', {
        'en': 'Companies House number',
        'ru': 'Номер Companies House',
        'de': 'Companies House Nummer',
        'me': 'Broj Companies House',
    }),
}
STEP3_REGISTRATION_NUMBER_DEFAULT = ('123456', '')
STEP3_REGISTRATION_NUMBER_HINT = {
    'de': 'Buchstaben, Ziffern, Bindestriche (3–50 Zeichen)',
    'en': 'Letters, digits, hyphens (3–50 characters)',
    'ru': 'Буквы, цифры, дефисы (3–50 символов)',
    'me': 'Slova, brojevi, crtice (3–50 znakova)',
}

STEP3_VAT_NUMBER = {
    'DE': ('DE123456789', {
        'en': 'VAT ID: DE + 9 digits (separate from tax number)',
        'ru': 'НДС номер: DE + 9 цифр (отдельно от Steuernummer)',
        'de': 'USt-IdNr.: DE + 9 Ziffern (getrennt von Steuernummer)',
        'me': 'PDV ID: DE + 9 cifara (odvojeno od poreznog broja)',
    }),
    'AT': ('ATU12345678', {
        'en': 'VAT ID: ATU + 8 digits (separate from tax number/UID)',
        'ru': 'НДС номер: ATU + 8 цифр (отдельно от Steuernummer/UID)',
        'de': 'USt-IdNr.: ATU + 8 Ziffern (getrennt von Steuernummer/UID)',
        'me': 'PDV ID: ATU + 8 cifara (odvojeno od poreznog broja)',
    }),
    'FR': ('FR12345678901', {
        'en': 'VAT: FR + 11 digits (separate from SIREN/SIRET)',
        'ru': 'НДС: FR + 11 цифр (отдельно от SIREN/SIRET)',
        'de': 'USt-IdNr.: FR + 11 Ziffern (getrennt von SIREN/SIRET)',
        'me': 'PDV: FR + 11 cifara (odvojeno od SIREN/SIRET)',
    }),
    'IT': ('IT12345678901', {
        'en': 'Partita IVA: IT + 11 digits',
        'ru': 'Partita IVA: IT + 11 цифр',
        'de': 'Partita IVA: IT + 11 Ziffern',
        'me': 'Partita IVA: IT + 11 cifara',
    }),
    'ES': ('ES12345678901', {
        'en': 'CIF/VAT: ES + 11 characters',
        'ru': 'CIF/VAT: ES + 11 символов',
        'de': 'CIF/USt: ES + 11 Zeichen',
        'me': 'CIF/PDV: ES + 11 znakova',
    }),
    'PL': ('PL1234567890', {
        'en': 'VAT: PL + 10 digits (PL + NIP, for VAT payers only)',
        'ru': 'VAT: PL + 10 цифр (PL + NIP, только для плательщиков НДС)',
        'de': 'USt: PL + 10 Ziffern (PL + NIP, nur für USt-Pflichtige)',
        'me': 'PDV: PL + 10 cifara (samo za platce PDV-a)',
    }),
    'NL': ('NL123456789B01', {
        'en': 'NL: 9 digits + 2 chars + B + 2 digits',
        'ru': 'NL: 9 цифр + 2 символа + B + 2 цифры',
        'de': 'NL: 9 Ziffern + 2 Zeichen + B + 2 Ziffern',
        'me': 'NL: 9 cifara + 2 znaka + B + 2 cifre',
    }),
}
STEP3_VAT_NUMBER_DEFAULT = ('XX123456789', {
    'en': 'Country code + digits (EU VAT ID, not tax ID)',
    'ru': 'Код страны + цифры (EU VAT ID, не Tax ID)',
    'de': 'Ländercode + Ziffern (EU-USt-IdNr., nicht Steuernummer)',
    'me': 'Kod države + cifre (EU PDV ID, ne porezni broj)',
})

STEP3_KPP = ('770701001', {
    'en': '9 digits (Russian LLC only)',
    'ru': '9 цифр (только для РФ ООО)',
    'de': '9 Ziffern (nur für russische GmbH)',
    'me': '9 cifara (samo za ruske DOO)',
})

STEP3_IBAN = {
    'DE': ('DE89 3704 0044 0532 0130 00', {
        'en': 'DE, 22 characters',
        'ru': 'DE, 22 символа',
        'de': 'DE, 22 Zeichen',
        'me': 'DE, 22 znaka',
    }),
    'AT': ('AT61 1904 3002 3457 3201', {
        'en': 'AT, 20 characters',
        'ru': 'AT, 20 символов',
        'de': 'AT, 20 Zeichen',
        'me': 'AT, 20 znakova',
    }),
    'FR': ('FR14 2004 1010 0505 0001 3M02 606', {
        'en': 'FR, 27 characters',
        'ru': 'FR, 27 символов',
        'de': 'FR, 27 Zeichen',
        'me': 'FR, 27 znakova',
    }),
    'UA': ('UA21 322313 0000 0262 0123 4567 89', {
        'en': 'UA, up to 29 characters',
        'ru': 'UA, до 29 символов',
        'de': 'UA, bis zu 29 Zeichen',
        'me': 'UA, do 29 znakova',
    }),
    'ME': ('ME25 1234 5678 9012 3456 78', {
        'en': 'ME, 22 characters',
        'ru': 'ME, 22 символа',
        'de': 'ME, 22 Zeichen',
        'me': 'ME, 22 znaka',
    }),
    'PL': ('PL61 1090 1014 0000 0712 1981 2874', {
        'en': 'PL, 28 characters',
        'ru': 'PL, 28 символов',
        'de': 'PL, 28 Zeichen',
        'me': 'PL, 28 znakova',
    }),
}
STEP3_IBAN_DEFAULT = ('XX00 0000 0000 0000 0000 0', {
    'en': '2 letters + 2 digits + up to 30 characters',
    'ru': '2 буквы + 2 цифры + до 30 символов',
    'de': '2 Buchstaben + 2 Ziffern + bis zu 30 Zeichen',
    'me': '2 slova + 2 cifre + do 30 znakova',
})

STEP3_SWIFT_BIC = ('DEUTDEFF', {
    'en': '8 or 11 characters (4+2+2+[3])',
    'ru': '8 или 11 символов (4+2+2+[3])',
    'de': '8 oder 11 Zeichen (4+2+2+[3])',
    'me': '8 ili 11 znakova (4+2+2+[3])',
})
STEP3_SWIFT_BIC_HINT = {
    'de': '8 oder 11 Zeichen (z.B. DEUTDEFF oder DEUTDEFF500)',
    'en': '8 or 11 characters (e.g. DEUTDEFF or DEUTDEFF500)',
    'ru': '8 или 11 символов (напр. DEUTDEFF)',
    'me': '8 ili 11 znakova (npr. DEUTDEFF)',
}

STEP3_DIRECTOR_PLACEHOLDER = {
    'de': 'Max Mustermann',
    'en': 'John Smith',
    'ru': 'Иванов Иван Иванович',
    'me': 'Marko Marković',
}

SUPPORTED_LANGS = ('de', 'en', 'ru', 'me')
DEFAULT_LANG = 'en'


def _normalize_lang(lang: str) -> str:
    if not lang or not isinstance(lang, str):
        return DEFAULT_LANG
    lang = lang.strip().lower()[:2]
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def _resolve_hint(hint_value, lang: str) -> str:
    """Возвращает строку подсказки: если hint_value — dict по языкам, выбирает по lang."""
    if isinstance(hint_value, dict):
        return hint_value.get(lang, hint_value.get(DEFAULT_LANG, ''))
    return hint_value or ''


def get_step2_hints(country: str, lang: str) -> dict:
    """
    Возвращает подсказки для полей шага 2 в зависимости от страны и языка.

    :param country: Код страны (ISO 3166-1 alpha-2), выбранной на шаге 1.
    :param lang: Код языка (de, en, ru, me). По умолчанию en.
    :return: dict с ключами phonePlaceholder, orgNameHint, documentsHint, addressPlaceholder.
    """
    country = (country or '').upper()[:2]
    lang = _normalize_lang(lang)

    phone = STEP2_PHONE_BY_COUNTRY.get(country, '+000 0 000 00 00')
    examples = STEP2_ORG_EXAMPLES_BY_COUNTRY.get(country, '—')
    org_template = ORG_NAME_HINT_TEMPLATE.get(lang, ORG_NAME_HINT_TEMPLATE[DEFAULT_LANG])
    org_hint = org_template.format(examples=examples)

    return {
        'phonePlaceholder': phone,
        'orgNameHint': org_hint,
        'documentsHint': DOCUMENTS_HINT.get(lang, DOCUMENTS_HINT[DEFAULT_LANG]),
        'addressPlaceholder': ADDRESS_PLACEHOLDER.get(lang, ADDRESS_PLACEHOLDER[DEFAULT_LANG]),
    }


def get_step3_hints(country: str, lang: str) -> dict:
    """
    Подсказки и плейсхолдеры для полей шага 3 (реквизиты) по стране и языку.
    Все подсказки возвращаются на выбранном языке (lang).
    GET /api/v1/provider-registration/step3-hints/?country=DE&lang=de
    """
    country = (country or '').upper()[:2]
    lang = _normalize_lang(lang)

    t = STEP3_TAX_ID.get(country, STEP3_TAX_ID_DEFAULT)
    tax_ph = t[0] if isinstance(t, tuple) else t
    tax_hint = _resolve_hint(t[1], lang) if isinstance(t, tuple) else ''

    v = STEP3_VAT_NUMBER.get(country, STEP3_VAT_NUMBER_DEFAULT)
    vat_ph = v[0] if isinstance(v, tuple) else v
    vat_hint = _resolve_hint(v[1], lang) if isinstance(v, tuple) else ''

    kpp_ph, kpp_hint_raw = STEP3_KPP
    kpp_hint = _resolve_hint(kpp_hint_raw, lang)

    ib = STEP3_IBAN.get(country, STEP3_IBAN_DEFAULT)
    iban_ph = ib[0] if isinstance(ib, tuple) else ib
    iban_hint = _resolve_hint(ib[1], lang) if isinstance(ib, tuple) else ''

    sw_ph, sw_hint_raw = STEP3_SWIFT_BIC
    sw_hint = _resolve_hint(sw_hint_raw, lang)

    reg_data = STEP3_REGISTRATION_NUMBER.get(country, STEP3_REGISTRATION_NUMBER_DEFAULT)
    reg_ph = reg_data[0] if isinstance(reg_data, tuple) else reg_data
    reg_hint_val = reg_data[1] if isinstance(reg_data, tuple) and len(reg_data) > 1 else ''
    reg_hint = _resolve_hint(reg_hint_val, lang) if reg_hint_val else (
        STEP3_REGISTRATION_NUMBER_HINT.get(lang, STEP3_REGISTRATION_NUMBER_HINT[DEFAULT_LANG])
    )

    director_ph = STEP3_DIRECTOR_PLACEHOLDER.get(lang, STEP3_DIRECTOR_PLACEHOLDER[DEFAULT_LANG])

    return {
        'taxIdPlaceholder': tax_ph,
        'taxIdHint': tax_hint,
        'registrationNumberPlaceholder': reg_ph,
        'registrationNumberHint': reg_hint,
        'vatNumberPlaceholder': vat_ph,
        'vatNumberHint': vat_hint,
        'kppPlaceholder': kpp_ph,
        'kppHint': kpp_hint,
        'ibanPlaceholder': iban_ph,
        'ibanHint': iban_hint,
        'swiftBicPlaceholder': sw_ph,
        'swiftBicHint': sw_hint,
        'directorNamePlaceholder': director_ph,
    }
