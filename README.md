# OneChoice

Generell AI-beslutshjälpare med minimalistisk premium koreansk estetik.

## Filer

```
onechoice/
├── app.py
├── requirements.txt
├── README.md
└── .streamlit/
    └── secrets.toml
```

## Starta

```bash
cd C:\Users\DELL\Projekt\onechoice
pip install -r requirements.txt
python -m streamlit run app.py
```

## Hemligheter

`.streamlit/secrets.toml`:

```toml
GROK_API_KEY = "xai-..."
STRIPE_SECRET_KEY = "sk_test_..."
```

Utan nycklar körs **demo-läge**.

## Funktioner

- SV / EN språkväxlare
- Ämnesdetektering (mat, kläder, resor, karriär, kväll …)
- 3 förslag med matchande bilder
- **Se recept** / **Mer info** + **Beställ nu**
- Historik + Pro (Stripe)
- Grok API med chain-of-thought

## Design

- Bakgrund `#f8f9fa`
- Primär `#5A8BFF`
- Beige `#F5F0E6`
- Mobil-först, runda hörn, soft shadow
