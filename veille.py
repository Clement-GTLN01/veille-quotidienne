import os
import requests
import feedparser
from datetime import date, datetime, timezone, timedelta
from bs4 import BeautifulSoup

# Clés API
GROQ_KEY = os.environ["GROQ_KEY"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID = os.environ["NOTION_PAGE_ID"]

# Flux RSS par thème
SOURCES = {
    "📈 Bourse & Finance": [
        "https://www.lesechos.fr/rss/rss_finance.xml",
        "https://www.latribune.fr/rss/all.xml",
        "https://www.zonebourse.com/rss/actualite.xml",
    ],
    "🌍 Actualité générale": [
        "https://www.lemonde.fr/rss/une.xml",
        "https://www.franceinfo.fr/rss",
        "https://www.lefigaro.fr/rss/figaro_actualites.xml",
    ],
    "🤖 IA & Tech": [
        "https://www.technologyreview.com/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "https://siecledigital.fr/feed/",
    ],
}

LIMITE_HEURES = 12

def est_recent(entry):
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            publie = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            limite = datetime.now(timezone.utc) - timedelta(hours=LIMITE_HEURES)
            return publie >= limite
    except Exception:
        pass
    return True  # Si pas de date, on garde l'article

def recuperer_articles_rss(flux_urls, nb_par_source=1):
    articles = []
    for url in flux_urls:
        try:
            feed = feedparser.parse(url)
            nb_ajoutes = 0
            for entry in feed.entries:
                if nb_ajoutes >= nb_par_source:
                    break
                if not est_recent(entry):
                    print(f"  Article trop ancien ignore : {entry.get('title', '')[:40]}...")
                    continue
                titre = entry.get("title", "Sans titre")
                resume = entry.get("summary", "")
                lien = entry.get("link", "")
                articles.append({
                    "titre": titre,
                    "resume": resume,
                    "lien": lien,
                    "contenu": None
                })
                nb_ajoutes += 1
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
        return contenu[:2000] if len(contenu) > 200 else None
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
    if not articles:
        return "Aucun article recent trouve dans les dernières 12h pour ce theme."
    texte = formater_pour_groq(articles)
    prompt = (
        "Tu es un assistant de veille professionnelle senior pour un cadre francophone.\n"
        f"Voici {len(articles)} articles recents sur le theme : {label}\n\n"
        f"{texte}\n\n"
        "Pour chacun des articles, redige un paragraphe de 3-4 phrases qui :\n"
        "- Commence par le titre exact de l'article en gras\n"
        "- Explique les faits precis (chiffres, noms, dates si disponibles)\n"
        "- Indique l'impact concret pour un professionnel\n"
        "- Termine par le lien source entre parentheses\n\n"
        "IMPORTANT : reste factuel et precis. Pas de generalites. "
        "Si l'article est en anglais, reponds en francais."
    )
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500
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
        morceaux = [texte[i:i+1900] for i in range(0, len(texte), 1900)]
        for morceau in morceaux:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": morceau}}]
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
    if res.status_code != 200:
        print(f"Notion reponse : {res.text}")
    else:
        print("Veille envoyee dans Notion !")

# Programme principal
contenu = []
for label, flux_urls in SOURCES.items():
    print(f"\nRecuperation : {label}")
    articles = recuperer_articles_rss(flux_urls)
    print(f"  {len(articles)} articles recents trouves")
    if articles:
        articles = enrichir_articles(articles)
    print(f"  Resume en cours...")
    resume = resumer_avec_groq(label, articles)
    contenu.append((resume, label))

envoyer_vers_notion(contenu)
