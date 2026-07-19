# OneChoice

Generell AI-beslutshjälpare inspirerad av koreanska appar (Kakao / Naver).

## Starta

```bash
cd C:\Users\DELL\Projekt\onechoice
pip install -r requirements.txt
python -m streamlit run app.py
```

Eller dubbelklicka `desktop_shortcut.bat`.

## Hemligheter

`.streamlit/secrets.toml`:

```toml
GROK_API_KEY = "xai-..."
STRIPE_SECRET_KEY = "sk_test_..."
```

Utan nycklar: demo-läge med kategori-anpassade förslag.

## Logik

1. Detektera ämne (mat, kläder, resor, karriär, kväll, generellt)
2. Grok med chain-of-thought → 3 förslag
3. Matchande bilder + länkar (Se recept/Mer info, Beställ nu)

## Design

- Bakgrund `#f8f9fa`
- Primär `#5A8BFF`
- Beige `#F5F0E6`
- Mobil-först, mycket luft, soft shadow
