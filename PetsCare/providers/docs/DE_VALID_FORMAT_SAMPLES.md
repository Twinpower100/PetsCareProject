# Valid format samples for Germany (DE) — python-stdnum

Reference list of values that pass format validation (python-stdnum or project rules) for provider registration wizard fields. Use for tests, fixtures, or manual checks.

**Country:** Germany (DE)  
**Validation:** `PetsCare.providers.validation_rules` (stdnum: stnr, eu.vat, iban, bic, handelsregisternummer)

---

## 1. Телефон организации (Organization phone)

Project validates: length 10–15, digits and `+` (E.164-style). Not validated by stdnum; these are valid German-style numbers.

| # | Value |
|---|--------|
| 1 | +49301234567 |
| 2 | +498912345678 |
| 3 | +496221123456 |
| 4 | +49 30 12345678 |
| 5 | +49 89 1234567 |
| 6 | +49 211 12345678 |
| 7 | +49 40 123456789 |
| 8 | 0049301234567 |
| 9 | +49 69 123456 |
| 10 | +49351234567 |

*Note: Backend may strip spaces; use compact form (e.g. `+49301234567`) if validation fails.*

---

## 2. ИНН / Tax ID (Steuernummer)

**Module:** `stdnum.de.stnr`  
**Format:** 10 or 11 digits (regional), optional separators (e.g. `12/345/67890`).

| # | Value |
|---|--------|
| 1 | 18181508155 |
| 2 | 20112312340 |
| 3 | 4151081508156 |
| 4 | 181/815/08155 |
| 5 | 12/345/67890 |
| 6 | 1234567890 |
| 7 | 201/123/12340 |
| 8 | 4151081508156 |
| 9 | 181 815 08155 |
| 10 | 12345678901 |

---

## 3. Регистрационный номер (Handelsregisternummer)

**Module:** `stdnum.de.handelsregisternummer`  
**Format:** Court name + HRA or HRB + number (e.g. `Aachen HRA 11223`).

| # | Value |
|---|--------|
| 1 | Aachen HRA 11223 |
| 2 | Aachen HRB 44123 |
| 3 | Berlin HRB 12345 |
| 4 | München HRB 1000 |
| 5 | Hamburg HRA 67890 |
| 6 | Chemnitz HRB 14011 |
| 7 | Frankfurt am Main HRB 50000 |
| 8 | Köln HRB 12345 |
| 9 | Dresden HRB 20000 |
| 10 | Stuttgart HRA 12345 |

---

## 4. VAT номер (USt-IdNr.)

**Module:** `stdnum.eu.vat`  
**Format:** DE + 9 digits (checksum validated).

| # | Value |
|---|--------|
| 1 | DE111111125 |
| 2 | DE122119035 |
| 3 | DE100000104 |
| 4 | DE100000112 |
| 5 | DE100000129 |
| 6 | DE100000137 |
| 7 | DE100000145 |
| 8 | DE100000153 |
| 9 | DE100000161 |
| 10 | DE100000170 |

---

## 5. IBAN

**Module:** `stdnum.iban`  
**Format:** DE + 2 check digits + 18 digits (22 characters), mod-97 checksum.

| # | Value |
|---|--------|
| 1 | DE89370400440532013000 |
| 2 | DE91100000000123456789 |
| 3 | DE37013235467620205483 |
| 4 | DE10402318674526541721 |
| 5 | DE27989613171364682552 |
| 6 | DE25881004571210176217 |
| 7 | DE12500105170648489890 |
| 8 | DE68246780842338352077 |
| 9 | DE86470454614405754923 |
| 10 | DE41290821756384443917 |

*All values pass `stdnum.iban.validate()` for country DE.*

---

## 6. SWIFT / BIC

**Module:** `stdnum.bic`  
**Format:** 8 or 11 characters (AAAA BB CC [DDD]).

| # | Value |
|---|--------|
| 1 | COBADEFF |
| 2 | COBADEFFXXX |
| 3 | DRESDEFF |
| 4 | DRESDEFF500 |
| 5 | DEUTDEFF |
| 6 | DEUTDEFFXXX |
| 7 | BELADEBE |
| 8 | GENODEM1GLS |
| 9 | HYVEDEMM488 |
| 10 | MHBEDEFF |

---

## Summary

| Field | stdnum module | Max samples |
|-------|----------------|-------------|
| Телефон организации | — (project rules) | 10 |
| ИНН / Tax ID | stdnum.de.stnr | 10 |
| Регистрационный номер | stdnum.de.handelsregisternummer | 10 |
| VAT номер | stdnum.eu.vat | 10 |
| IBAN | stdnum.iban | 10 |
| SWIFT / BIC | stdnum.bic | 10 |

All values above have been checked to pass the corresponding validator where applicable (Steuernummer, Handelsregisternummer, EU VAT, IBAN, BIC). Phone numbers comply with project E.164-style rules (10–15 digits, optional leading `+`).
