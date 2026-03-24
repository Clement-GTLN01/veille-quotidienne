import os
import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

# Clés API
GROQ_KEY = os.environ["GROQ_KEY"]
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

LIMITE_HEURES = 12

# Flux RSS surveillance annonces IA
SOURCES_ALERTES = [
    "https://openai.com/blog/rss",
    "https://www.anthropic.com/news/rss",
    "https://blog.google/technology/ai/rss",
    "https://blogs.microsoft.com/blog/feed",
]

def est_recent(entry):
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            publie = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            limite = datetime.now(timezone.utc) - timedelta(hours=LIMITE_HEURES)
            return publie >= limite
    except Exception as e:
        print(f"    Erreur date : {e}")
    return True

def recuperer_articles_rss(flux_urls, nb_par_source=2):
    articles = []
    for url in flux_urls:
        try:
            feed = feedparser.parse(url)
            print(f"  Feed {url} : {len(feed.entries)} entrees")
            nb_ajoutes = 0
            for entry in feed.entries:
                if nb_ajoutes >= nb_par_source:
                    break
                if not est_recent(entry):
                    print(f"    Trop ancien : {entry.get('title', '')[:40]}...")
                    continue
                articles.append({
                    "titre": entry.get("title", "Sans titre"),
                    "resume": entry.get("summary", ""),
                    "lien": entry.get("link", ""),
                    "contenu": None
                })
                nb_ajoutes += 1
        except Exception as e:
            print(f"  Erreur RSS {url} : {e}")
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
        print(f"  Impossible de recuperer {url} : {e}")
        return None

def enrichir_articles(articles):
    for article in articles:
        print(f"  Contenu : {article['titre'][:50]}...")
        article["contenu"] = recuperer_contenu_article(article["lien"])
    return articles

def resumer_avec_groq(articles):
    texte = ""
    for a in articles:
        texte += f"\n---\nTitre : {a['titre']}\n"
        if a["contenu"]:
            texte += f"Contenu : {a['contenu']}\n"
        else:
            texte += f"Resume : {a['resume']}\nLien : {a['lien']}\n"
    prompt = (
        "Tu es un assistant de veille IA pour un professionnel francophone.\n"
        f"Voici {len(articles)} annonces recentes de Google, Anthropic, Microsoft ou OpenAI.\n\n"
        f"{texte}\n\n"
        "Pour chaque annonce, redige un paragraphe de 3-4 phrases qui :\n"
        "- Commence par le nom de l'entreprise et le titre en gras\n"
        "- Explique les faits precis (chiffres, noms, dates)\n"
        "- Indique l'impact concret pour un professionnel\n"
        "- Termine par le lien source entre parentheses\n\n"
        "Sois factuel et precis. Si l'article est en anglais, reponds en francais."
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

def envoyer_email_alerte(articles, resume):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    sujet = f"🚨 Alerte IA — {len(articles)} nouvelle(s) annonce(s) ({now})"
    corps = "Nouvelles annonces détectées chez Google, Anthropic, Microsoft ou OpenAI :\n\n"
    for a in articles:
        corps += f"• {a['titre']}\n  {a['lien']}\n\n"
    corps += f"\n---\nRésumé :\n\n{resume}"
    msg = MIMEMultipart()
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS
    msg["Subject"] = sujet
    msg.attach(MIMEText(corps, "plain"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print("Email alerte envoye !")

# Programme principal
print("Verification annonces IA (dernières 12h)...")
articles = recuperer_articles_rss(SOURCES_ALERTES)
print(f"{len(articles)} annonces recentes trouvees")

if articles:
    articles = enrichir_articles(articles)
    resume = resumer_avec_groq(articles)
    envoyer_email_alerte(articles, resume)
else:
    print("Aucune nouvelle annonce — pas d'email envoye.")
