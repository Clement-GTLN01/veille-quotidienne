import os
import requests
from datetime import date

# Clés API récupérées depuis les secrets GitHub
NEWSAPI_KEY = os.environ["NEWSAPI_KEY"]
GEMINI_KEY = os.environ["GEMINI_KEY"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID = os.environ["NOTION_PAGE_ID"]

# Sujets de veille
SUJETS = [
    ("bourse finance marchés", "📈 Bourse & Finance"),
    ("actualité france monde", "🌍 Actualité générale"),
    ("intelligence artificielle IA annonce business", "🤖 IA & Tech"),
]

def recuperer_articles(sujet, nb=5):
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": sujet,
        "language": "fr",
        "sortBy": "publishedAt",
        "pageSize": nb,
        "apiKey": NEWSAPI_KEY,
    }
    res = requests.get(url, params=params)
    articles = res.json().get("articles", [])
    return [f"- {a['title']} ({a['source']['name']})" for a in articles]

def resumer_avec_gemini(sujet_label, articles):
    texte_articles = "\n".join(articles)
    prompt = f"""Tu es un assistant de veille professionnelle.
Voici des titres d'articles récents sur le thème : {sujet_label}
{texte_articles}
Fais un résumé structuré en 5 points clés, en français, orienté impact business et utilisateur.
Sois concis et direct. Pas de jargon technique."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    res = requests.post(url, json=body)
    data = res.json()
    if "candidates" not in data:
        raise Exception(f"Erreur Gemini : {data}")
    return data["candidates"][0]["content"]["parts"][0]["text"]

def envoyer_vers_notion(contenu):
    today = date.today().strftime("%d/%m/%Y")
    
    blocks = [
        {
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"type": "text", "text": {"content": f"Veille du {today}"}}]
            }
        }
    ]

    for texte, label in contenu:
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": label}}]
            }
        })
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": texte}}]
            }
        })

    url = f"https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    requests.patch(url, headers=headers, json={"children": blocks})
    print("✅ Veille envoyée dans Notion !")

# Programme principal
contenu = []
for sujet, label in SUJETS:
    print(f"Récupération : {label}")
    articles = recuperer_articles(sujet)
    print(f"Résumé en cours...")
    resume = resumer_avec_gemini(label, articles)
    contenu.append((resume, label))

envoyer_vers_notion(contenu)
