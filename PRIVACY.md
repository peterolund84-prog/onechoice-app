# Integritetspolicy — OneChoice

Senast uppdaterad: 2026-07-19

OneChoice (“vi”) är personuppgiftsansvarig för behandlingen av dina personuppgifter i appen. Kontakta oss via den e-postadress som anges i appens distributionskanal om du har frågor om denna policy.

## Vad vi behandlar

| Uppgift | Syfte | Lagring |
|---------|--------|---------|
| E-post + konto-id | Inloggning, konto | Tills du raderar kontot |
| Frågor & beslut | Ge dig ett beslut, historik | Tills du raderar; fritext i `routed_queries` nollas efter **90 dagar** |
| Preferenser (accept/reject) | Bättre förslag | Tills du raderar |
| Profil (kost, plats, storlekar) | Anpassa beslut | Tills du raderar |
| Kylskåpsfoton | Identifiera varor för ett beslut | Tillfälligt i session; för inloggade kan foton lagras privat max **24 timmar**, sedan raderas automatiskt |
| Delningslänkar | Visa ett beslut utan inloggning | Tills du raderar kontot (ägda länkar) |

**Hög risk / känsliga frågor** (hälsa, juridik, ekonomi m.m.) loggas **utan innehåll** — endast att en sådan förfrågan skett.

## AI-leverantör (tredjelandsöverföring)

När du ställer en fritextfråga eller fotograferar kylen skickas **frågetexten** respektive **bilden** till vår AI-leverantör **xAI (Grok)** för behandling. Det är nödvändigt för tjänstens funktion.

- Vi skickar **aldrig** ditt `user_id`, e-post eller andra direkta identifierare i AI-anropet.
- Vi skickar bara frågan / bilden och anonymiserad kontext (t.ex. kostpreferenser, tid, generella inställningar).
- Leverantören är personuppgiftsbiträde. Kontrollera aktuella API-villkor hos xAI (inkl. att API-data inte används för modellträning — verifiera vid varje större villkorsändring).
- Överföring till USA sker med lämpliga skyddsåtgärder enligt gällande regelverk (t.ex. standardavtalsklausuler / leverantörens DPA).

## Var data lagras

Kontodata och historik lagras hos **Supabase** (Postgres + Auth + Storage). **Skapa projektet i en EU-region** (t.ex. Frankfurt `eu-central-1` eller Stockholm). Supabase erbjuder DPA som personuppgiftsbiträde.

## Dina rättigheter

- **Tillgång & portabilitet (art. 15/20):** under Profil → **Ladda ner min data** (JSON).
- **Radering (art. 17):** under Profil → **Radera mitt konto**. Det tar bort autentiseringskontot och all kopplad data (beslut, preferenser, loggar, foton, dina delningslänkar) — inte “avaktivering”.
- **Invändning / begränsning:** kontakta oss.
- Klagomål kan lämnas till Integritetsskyddsmyndigheten (IMY).

## Samtycke

Vid registrering måste du godkänna denna policy. Du kan återkalla samtycke genom att radera kontot; då upphör lärandet på dina preferenser.

## Säkerhet

- Row Level Security (RLS) i databasen — användare ska bara nå egen data.
- Privata storage-buckets för foton med RLS.
- Gästläge: data sparas lokalt i enheten och synkas inte till molnet.

## Ändringar

Vi kan uppdatera policyn. Väsentliga ändringar meddelas i appen eller via e-post när det är rimligt.
