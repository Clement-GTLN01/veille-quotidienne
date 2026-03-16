import os
import requests
import feedparser
from datetime import date
from bs4 import BeautifulSoup

# Clés API
GROQ_KEY = os.environ["GROQ_KEY"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID = os.environ["NOTION_PAGE_ID"]

# Flux RSS par thème
SOURCES = {
    "📈 Bourse & Finance": [
        "https://www.lesechos.fr/rss/rss_finance.xml",
        "https://www.lefigaro.fr/rss/figaro_economie.xml",
        "https://www.latribune.fr/rss/all.xml",
        "https://bfmbusiness.bfmtv.com/rss/info/flux-rss/flux-toutes-les-actualites/",
        "https://www.zonebourse.com/rss/actualite.xml",
    ],
    "🌍 Actualité générale": [
        "https://www.lemonde.fr/rss/une.xml",
        "https://www.lefigaro.fr/rss/figaro_actualites.xml",
        "https://www.franceinfo.fr/rss",
        "https://www.liberation.fr/arc/outboundfeeds/rss/",
        "https://www.20minutes.fr/feeds/rss/actu.xml",
    ],
    "🤖 IA & Tech": [
        "https://www.01net.com/feed/",
        "https://www.lebigdata.fr/feed",
        "https://www.usine-digitale.fr/rss/all.xml",
        "https://siecledigital.fr/feed/",
        "https://www.bfmtv.com/rss/tech/",
    ],
}

def recuperer_articles_rss(flux_urls, nb_par_source=2):
    articles = []
    for url in flux_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:nb_par_source]:
                titre = entry.get("title", "Sans titre")
                resume = entry.get("summary", "")
                lien = entry.get("link", "")
                articles.append({
                    "titre": titre,
                    "resume": resume,
                    "lien": lien,
                    "contenu": None
                })
        except Exception as e:
            print(f"Erreur RSS {url} : {e}")
    return articles

def recuperer_contenu_article(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code != 200:
            return None
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        contenu = ""
        for balise in ["article", "main"]:
            element = soup.find(balise)
            if element:
                contenu = element.get_text(separator=" ", strip=True)
                break
        if not contenu:
            contenu = soup.get_text(separator=" ", strip=True)
        return contenu[:1500] if len(contenu) > 200 else None
    except Exception as e:
        print(f"Impossible de recuperer {url} : {e}")
        return None

def enrichir_articles(articles):
    for article in articles:
        print(f"  Contenu : {article['titre'][:50]}...")
        contenu = recuperer_contenu_article(article["lien"])
        article["contenu"] = contenu
    return articles

def formater_pour_groq(articles):
    texte = ""
    for a in articles:
        texte += f"\n---\nTitre : {a['titre']}\n"
        if a["contenu"]:
            texte += f"Contenu : {a['contenu']}\n"
        else:
            texte += f"Resume : {a['resume']}\nLien : {a['lien']}\n"
    return texte

def resumer_avec_groq(label, articles):
    texte = formater_pour_groq(articles)
    prompt = (
        "Tu es un assistant de veille professionnelle pour un professionnel francophone.\n"
        f"Voici des articles recents sur le theme : {label}\n\n"
        f"{texte}\n\n"
        "Fais un resume structure en 5 points cles. Pour chaque point :\n"
        "- Une phrase de titre en gras\n"
        "- 2-3 phrases d'explication concrete sur l'impact business ou utilisateur\n"
        "- Cite la source avec son lien entre parentheses\n\n"
        "Sois factuel, precis, sans jargon technique. Pas de generalites."
    )
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}]
    }
    res = requests.post(url, headers=headers, json=body)
    data = res.json()
    if "choices" not in data:
        raise Exception(f"Erreur Groq : {data}")
    return data["choices"][0]["message"]["content"]

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
    res = requests.patch(url, headers=headers, json={"children": blocks})
    print(f"Notion status : {res.status_code}")
    print(f"Notion reponse : {res.text}")
    print("Veille envoyee dans Notion !")

# Programme principal
contenu = []
for label, flux_urls in SOURCES.items():
    print(f"\nRecuperation : {label}")
    articles = recuperer_articles_rss(flux_urls)
    print(f"  {len(articles)} articles recuperes")
    articles = enrichir_articles(articles)
    print(f"  Resume en cours...")
    resume = resumer_avec_groq(label, articles)
    contenu.append((resume, label))

envoyer_vers_notion(contenu)
