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
        # Supprimer les éléments inutiles
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        # Chercher le contenu principal
        contenu = ""
        for balise in ["article", "main", ".article-content", ".post-content"]:
            element = soup.find(balise)
            if element:
                contenu = element.get_text(separator=" ", strip=True)
                break
        if not contenu:
            contenu = soup.get_text(separator=" ", strip=True)
        # Limiter à 1500 caractères
        return contenu[:1500] if len(contenu) > 200 else None
    except Exception as e:
        print(f"Impossible de récupérer {url} : {e}")
        return None

def enrichir_articles(articles):
    for article in articles:
        print(f"  Récupération contenu : {article['titre'][:50]}...")
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
            texte += f"Résumé : {a['resume']}\n"
        texte += f"Source : {a['lien']}\n"
    return texte

def resumer_avec_groq(label, articles):
    texte = formater_pour_groq(articles)
    prompt = f"""Tu es un assistant de veille professionnelle pour un professionnel francophone.
Voici des articles récents sur le
