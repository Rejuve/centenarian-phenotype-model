"""
================================================================================
REJUVE LONGEVITY APP — Centenarian Data Pipeline
FILE: scraper_news.py
VERSION: 3.1
PURPOSE: Scrapes centenarian/longevity articles from 176 global news,
         lifestyle, and dedicated longevity outlets across 50+ countries.

PIPELINE CONTEXT:
  scraper_news.py      <- THIS FILE (news, lifestyle, longevity outlets)
  scraper_science.py   <- Science journalism outlets (separate)
  scraper_medical.py   <- Hospital/academic medical center news (separate)
  scraper_academic.py  <- PubMed, PMC, Cell, Nature papers (API-based)
  scraper_datasets.py  <- Structured downloadable datasets
  scraper_youtube.py   <- Validated YouTube transcripts
  merge_all.py         <- Combines all outputs into master dataset

  Scrapers are OFFLINE TOOLS run on your laptop. They produce CSV files
  which feed model training. The trained model (~50KB) ships with the app.
  Users never run scrapers.

HOW IT WORKS:
  1. Loads each source's tag/search page
  2. Harvests links as plain Python strings (no stale DOM references)
  3. Filters by ANCHOR TEXT — only visits links with longevity headlines
  4. Extracts structured data with clean column schema
  5. Saves INCREMENTALLY — crash-safe, every record written immediately
  6. RESUME on re-run — skips URLs already in CSV

OUTPUT (in data/raw/):
  news_articles.csv         — full dataset with article text
  news_articles_preview.csv — same without full_text (Excel-friendly)

COLUMN SCHEMA:
  Publication:  source_name, source_country, source_class, url, dates
  Subject:      subject_name, subject_age, subject_city, subject_country
  Traits:       trait_physical_activity, trait_diet, trait_social,
                trait_purpose_psychology, trait_sleep  (TRUE/FALSE)
  Biomarkers:   biomarker_inflammation, biomarker_glucose, biomarker_lipids,
                biomarker_igf1, biomarker_telomeres, biomarker_epigenetic,
                biomarker_microbiome, biomarker_hormones, biomarker_functional,
                biomarker_metabolomic  (TRUE/FALSE)
  Genetics:     gene_apoe, gene_foxo3, gene_cetp, gene_klotho,
                gene_other  (TRUE/FALSE)
  Statistics:   stat_odds_ratio, stat_hazard_ratio, stat_sample_size,
                stat_percentage, stat_p_value, stat_confidence_interval

DEPENDENCIES: pip install selenium webdriver-manager pandas
REQUIRES: Google Chrome installed
AUTHOR: Rejuve Longevity (open-source)
LICENSE: MIT
================================================================================
"""

import time, re, os, csv
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    StaleElementReferenceException, WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# ================================================================================
# CONFIGURATION
# ================================================================================

OUTPUT_DIR  = "data/raw"
OUTPUT_FILE = "news_articles.csv"
PAGE_LOAD_TIMEOUT       = 20
DELAY_BETWEEN_ARTICLES  = 2.5
DELAY_BETWEEN_SOURCES   = 5
MAX_SCROLLS             = 25
MIN_WORD_COUNT          = 150

# ================================================================================
# SOURCES — 176 outlets across 9 classes, 50+ countries
# ================================================================================

def _s(n, c, cl, u, f, scroll=True):
    """Compact source constructor."""
    return {"name":n, "country":c, "source_class":cl,
            "tag_url":u, "url_must_contain":f, "scroll":scroll}

SOURCES = [

    # ══════════════════════════════════════════════════════════════════════════
    # CLASS 1: DEDICATED LONGEVITY / AGING OUTLETS (15)
    # Every article is on-topic. Highest signal density per article.
    # ══════════════════════════════════════════════════════════════════════════

    _s("Longevity.Technology", "UK", "longevity_outlet",
       "https://longevity.technology/news/", "longevity.technology/"),
    _s("Lifespan.io", "USA", "longevity_outlet",
       "https://www.lifespan.io/news/", "lifespan.io/news/"),
    _s("Fight Aging!", "USA", "longevity_outlet",
       "https://www.fightaging.org/", "fightaging.org/"),
    _s("Life Extension Magazine", "USA", "longevity_outlet",
       "https://www.lifeextension.com/magazine", "lifeextension.com/magazine"),
    _s("Buck Institute News", "USA", "longevity_outlet",
       "https://www.buckinstitute.org/news/", "buckinstitute.org/"),
    _s("Lifespan Research Institute", "USA", "longevity_outlet",
       # Formerly SENS Research Foundation
       "https://www.lifespanresearchinstitute.org/news/",
       "lifespanresearchinstitute.org/"),
    _s("Methuselah Foundation", "USA", "longevity_outlet",
       "https://www.mfoundation.org/news", "mfoundation.org/"),
    _s("Longecity News", "USA", "longevity_outlet",
       "https://www.longecity.org/forum/page/index.html", "longecity.org/"),
    _s("AgingAnalytics", "UK", "longevity_outlet",
       "https://aginganalytics.com/news", "aginganalytics.com/"),
    _s("GeroScience News", "USA", "longevity_outlet",
       "https://link.springer.com/journal/11357", "springer.com/"),
    _s("Rejuvenation Research News", "USA", "longevity_outlet",
       "https://home.liebertpub.com/publications/rejuvenation-research/127",
       "liebertpub.com/"),
    _s("Aging Cell News", "UK", "longevity_outlet",
       # News section only — journal papers go in scraper_academic.py
       "https://onlinelibrary.wiley.com/journal/14749726", "wiley.com/"),
    _s("SuperAging.news", "USA", "longevity_outlet",
       "https://superaging.news/", "superaging.news/"),
    _s("Longevity Advice", "USA", "longevity_outlet",
       "https://longevityadvice.com/", "longevityadvice.com/"),
    _s("Blue Zones", "USA", "longevity_outlet",
       # Dan Buettner's Blue Zones — centenarian profiles + longevity lifestyle
       # articles (editorial /YYYY/MM/ posts; municipal "Project" PR excluded).
       "https://www.bluezones.com/news/", "bluezones.com/"),

    # ══════════════════════════════════════════════════════════════════════════
    # CLASS 2: MAINSTREAM NEWS — USA (23)
    # ══════════════════════════════════════════════════════════════════════════

    _s("TODAY.com", "USA", "mainstream_news",
       "https://www.today.com/health/live-to-100-longevity-tips-centenarians-advice",
       "today.com/health"),
    _s("CNN Health", "USA", "mainstream_news",
       "https://www.cnn.com/health/longevity", "cnn.com/"),
    _s("NBC News Health", "USA", "mainstream_news",
       "https://www.nbcnews.com/health/aging", "nbcnews.com/health"),
    _s("CBS News Health", "USA", "mainstream_news",
       "https://www.cbsnews.com/tag/centenarian/", "cbsnews.com/news"),
    _s("ABC News Health", "USA", "mainstream_news",
       "https://abcnews.go.com/Health", "abcnews.go.com/"),
    _s("Washington Post Health", "USA", "mainstream_news",
       "https://www.washingtonpost.com/wellness/longevity/",
       "washingtonpost.com/"),
    _s("New York Times Health", "USA", "mainstream_news",
       "https://www.nytimes.com/spotlight/longevity", "nytimes.com/"),
    _s("TIME Health", "USA", "mainstream_news",
       "https://time.com/tag/longevity/", "time.com/"),
    _s("AARP Longevity", "USA", "mainstream_news",
       "https://www.aarp.org/search/#q=centenarian&sortBy=PublishDate",
       "aarp.org/health"),
    _s("People Magazine", "USA", "mainstream_news",
       "https://people.com/tag/centenarians/", "people.com/"),
    _s("Business Insider Health", "USA", "mainstream_news",
       "https://www.businessinsider.com/s?q=centenarian+longevity",
       "businessinsider.com/"),
    _s("Fox News Health", "USA", "mainstream_news",
       "https://www.foxnews.com/tag/longevity", "foxnews.com/health"),
    _s("Bloomberg Health", "USA", "mainstream_news",
       "https://www.bloomberg.com/topics/longevity", "bloomberg.com/"),
    _s("Reuters Health", "International", "mainstream_news",
       "https://www.reuters.com/business/healthcare-pharmaceuticals/",
       "reuters.com/"),
    _s("AP News Health", "International", "mainstream_news",
       "https://apnews.com/hub/longevity", "apnews.com/article"),
    _s("USA Today Health", "USA", "mainstream_news",
       "https://www.usatoday.com/health/", "usatoday.com/story"),
    _s("Newsweek Health", "USA", "mainstream_news",
       "https://www.newsweek.com/health", "newsweek.com/"),
    _s("The Atlantic Health", "USA", "mainstream_news",
       "https://www.theatlantic.com/health/", "theatlantic.com/"),
    _s("Vox Health", "USA", "mainstream_news",
       "https://www.vox.com/health", "vox.com/"),
    _s("NPR Health", "USA", "mainstream_news",
       "https://www.npr.org/sections/health/", "npr.org/"),
    _s("STAT News", "USA", "mainstream_news",
       "https://www.statnews.com/tag/aging/", "statnews.com/"),
    _s("EurekAlert", "USA", "mainstream_news",
       "https://www.eurekalert.org/search?query=centenarian",
       "eurekalert.org/news-releases"),
    _s("MedPage Today", "USA", "mainstream_news",
       "https://www.medpagetoday.com/geriatrics", "medpagetoday.com/"),

    # ══════════════════════════════════════════════════════════════════════════
    # CLASS 3: MAINSTREAM NEWS — UK / IRELAND (13)
    # ══════════════════════════════════════════════════════════════════════════

    _s("BBC Future", "UK", "mainstream_news",
       "https://www.bbc.com/future/tags/longevity", "bbc.com/future/article"),
    _s("BBC Health", "UK", "mainstream_news",
       "https://www.bbc.com/news/health", "bbc.com/news/articles"),
    _s("The Guardian Health", "UK", "mainstream_news",
       "https://www.theguardian.com/society/longevity", "theguardian.com/"),
    _s("Daily Mail Health", "UK", "mainstream_news",
       "https://www.dailymail.co.uk/health/index.html",
       "dailymail.co.uk/health/article"),
    _s("The Telegraph Health", "UK", "mainstream_news",
       "https://www.telegraph.co.uk/health-fitness/longevity/",
       "telegraph.co.uk/"),
    _s("The Times Health", "UK", "mainstream_news",
       "https://www.thetimes.co.uk/topic/longevity", "thetimes.co.uk/article"),
    _s("The Independent Health", "UK", "mainstream_news",
       "https://www.independent.co.uk/topic/longevity", "independent.co.uk/"),
    _s("The Mirror Health", "UK", "mainstream_news",
       "https://www.mirror.co.uk/lifestyle/health/", "mirror.co.uk/"),
    _s("The Sun Health", "UK", "mainstream_news",
       "https://www.thesun.co.uk/health/", "thesun.co.uk/health/"),
    _s("Sky News Health", "UK", "mainstream_news",
       "https://news.sky.com/topic/health-6116", "news.sky.com/story"),
    _s("The Scotsman Health", "UK", "mainstream_news",
       "https://www.scotsman.com/health/", "scotsman.com/"),
    _s("Irish Times Health", "Ireland", "mainstream_news",
       "https://www.irishtimes.com/health/", "irishtimes.com/"),
    _s("Irish Independent Health", "Ireland", "mainstream_news",
       "https://www.independent.ie/life/health-wellbeing/", "independent.ie/"),

    # ══════════════════════════════════════════════════════════════════════════
    # CLASS 4: MAINSTREAM NEWS — EUROPE (30)
    # ══════════════════════════════════════════════════════════════════════════

    # Germany (3)
    _s("Der Spiegel Health", "Germany", "mainstream_news",
       "https://www.spiegel.de/thema/longevity/", "spiegel.de/"),
    _s("Die Welt Gesundheit", "Germany", "mainstream_news",
       "https://www.welt.de/gesundheit/", "welt.de/"),
    _s("Frankfurter Allgemeine", "Germany", "mainstream_news",
       "https://www.faz.net/aktuell/wissen/medizin-ernaehrung/", "faz.net/"),

    # France (2)
    _s("Le Monde Sante", "France", "mainstream_news",
       "https://www.lemonde.fr/sante/", "lemonde.fr/"),
    _s("Le Figaro Sante", "France", "mainstream_news",
       "https://sante.lefigaro.fr/", "lefigaro.fr/"),

    # Spain (2)
    _s("El Pais Salud", "Spain", "mainstream_news",
       "https://elpais.com/salud-y-bienestar/", "elpais.com/"),
    _s("El Mundo Salud", "Spain", "mainstream_news",
       "https://www.elmundo.es/salud.html", "elmundo.es/"),

    # Italy (3) — critical: Sardinia Blue Zone
    _s("La Repubblica Salute", "Italy", "mainstream_news",
       "https://www.repubblica.it/salute/", "repubblica.it/"),
    _s("Corriere della Sera Salute", "Italy", "mainstream_news",
       "https://www.corriere.it/salute/", "corriere.it/"),
    _s("La Stampa Salute", "Italy", "mainstream_news",
       "https://www.lastampa.it/salute/", "lastampa.it/"),

    # Netherlands (2) — Leiden Longevity Study population
    _s("NRC Gezondheid", "Netherlands", "mainstream_news",
       "https://www.nrc.nl/tag/veroudering/", "nrc.nl/"),
    _s("De Volkskrant Gezondheid", "Netherlands", "mainstream_news",
       "https://www.volkskrant.nl/gezondheid/", "volkskrant.nl/"),

    # Switzerland (1)
    _s("NZZ Gesundheit", "Switzerland", "mainstream_news",
       "https://www.nzz.ch/wissenschaft/medizin/", "nzz.ch/"),

    # Scandinavia (5) — Danish Twin Study, Swedish Centenarian Study
    _s("Dagens Nyheter Halsa", "Sweden", "mainstream_news",
       "https://www.dn.se/halsa/", "dn.se/"),
    _s("Aftenposten Helse", "Norway", "mainstream_news",
       "https://www.aftenposten.no/helse/", "aftenposten.no/"),
    _s("Politiken Sundhed", "Denmark", "mainstream_news",
       "https://politiken.dk/sundhed/", "politiken.dk/"),
    _s("Berlingske Sundhed", "Denmark", "mainstream_news",
       "https://www.berlingske.dk/sundhed/", "berlingske.dk/"),
    _s("Helsingin Sanomat Health", "Finland", "mainstream_news",
       "https://www.hs.fi/hyvinvointi/", "hs.fi/"),

    # Portugal (2)
    _s("Publico Saude", "Portugal", "mainstream_news",
       "https://www.publico.pt/saude/", "publico.pt/"),
    _s("Expresso Saude", "Portugal", "mainstream_news",
       "https://expresso.pt/saude/", "expresso.pt/"),

    # Greece (2) — Ikaria Blue Zone
    _s("Kathimerini Health", "Greece", "mainstream_news",
       "https://www.kathimerini.gr/life/health/", "kathimerini.gr/"),
    _s("To Vima Health", "Greece", "mainstream_news",
       "https://www.tovima.gr/category/science/health/", "tovima.gr/"),

    # Belgium (1)
    _s("De Standaard Gezondheid", "Belgium", "mainstream_news",
       "https://www.standaard.be/tag/gezondheid", "standaard.be/"),

    # Ireland broadcast (1) — different from print Irish Times
    _s("RTE Health", "Ireland", "mainstream_news",
       "https://www.rte.ie/lifestyle/health/", "rte.ie/"),

    # Poland (1)
    _s("Gazeta Wyborcza Health", "Poland", "mainstream_news",
       "https://wyborcza.pl/0,173236.html", "wyborcza.pl/"),

    # Czech Republic (2)
    _s("Lidove Noviny Health", "Czech Republic", "mainstream_news",
       "https://www.lidovky.cz/zdravi/", "lidovky.cz/"),
    _s("Denik N Health", "Czech Republic", "mainstream_news",
       "https://denikn.cz/tema/zdravi/", "denikn.cz/"),

    # Romania (1)
    _s("Adevarul Sanatate", "Romania", "mainstream_news",
       "https://adevarul.ro/sanatate/", "adevarul.ro/"),

    # Hungary (1)
    _s("Magyar Nemzet Egeszseg", "Hungary", "mainstream_news",
       "https://magyarnemzet.hu/tudomany/", "magyarnemzet.hu/"),

    # Turkey (1)
    _s("Daily Sabah Health", "Turkey", "mainstream_news",
       "https://www.dailysabah.com/health", "dailysabah.com/"),

    # ══════════════════════════════════════════════════════════════════════════
    # CLASS 5: BLUE ZONE SPECIFIC OUTLETS (8)
    # Low volume but HIGHEST model value — cover centenarian populations directly.
    # ══════════════════════════════════════════════════════════════════════════

    # Sardinia, Italy — highest male centenarian concentration globally
    _s("L'Unione Sarda", "Italy", "blue_zone_outlet",
       "https://www.unionesarda.it/", "unionesarda.it/"),
    _s("La Nuova Sardegna", "Italy", "blue_zone_outlet",
       "https://www.lanuovasardegna.it/", "lanuovasardegna.it/"),

    # Okinawa, Japan — world's longest-lived women
    _s("Okinawa Times", "Japan", "blue_zone_outlet",
       "https://www.okinawatimes.co.jp/", "okinawatimes.co.jp/"),
    _s("Ryukyu Shimpo", "Japan", "blue_zone_outlet",
       "https://ryukyushimpo.jp/", "ryukyushimpo.jp/"),

    # Nicoya Peninsula, Costa Rica — men 2x chance of reaching 90
    _s("La Nacion Costa Rica", "Costa Rica", "blue_zone_outlet",
       "https://www.nacion.com/ciencia/salud/", "nacion.com/"),
    _s("El Diario Extra Costa Rica", "Costa Rica", "blue_zone_outlet",
       "https://www.diarioextra.com/", "diarioextra.com/"),

    # Ikaria, Greece — where people "forget to die"
    _s("Ikaria Magazine", "Greece", "blue_zone_outlet",
       "https://www.ikariamag.gr/", "ikariamag.gr/"),

    # Loma Linda, California — 5th Blue Zone, Seventh-Day Adventist community
    _s("Loma Linda Sun", "USA", "blue_zone_outlet",
       "https://www.sbsun.com/location/loma-linda/", "sbsun.com/"),

    # ══════════════════════════════════════════════════════════════════════════
    # CLASS 6: MAINSTREAM NEWS — ASIA / PACIFIC (41)
    # ══════════════════════════════════════════════════════════════════════════

    # Japan (5) — world's highest centenarian rate
    _s("Japan Times Health", "Japan", "mainstream_news",
       "https://www.japantimes.co.jp/life/health-wellness/",
       "japantimes.co.jp/"),
    _s("Nikkei Asia Health", "Japan", "mainstream_news",
       "https://asia.nikkei.com/Life-Arts", "asia.nikkei.com/"),
    _s("Yomiuri Shimbun Health", "Japan", "mainstream_news",
       "https://www.yomiuri.co.jp/medical/", "yomiuri.co.jp/"),
    _s("Asahi Shimbun Health", "Japan", "mainstream_news",
       "https://www.asahi.com/ajw/category/health/", "asahi.com/"),
    _s("Mainichi Shimbun Health", "Japan", "mainstream_news",
       "https://mainichi.jp/english/health/", "mainichi.jp/"),

    # China (1) — China Daily is accessible English-language option
    _s("China Daily Health", "China", "mainstream_news",
       "https://www.chinadaily.com.cn/health", "chinadaily.com.cn/"),

    # Hong Kong (1)
    _s("South China Morning Post Health", "Hong Kong", "mainstream_news",
       "https://www.scmp.com/lifestyle/health-wellness", "scmp.com/"),

    # India (6)
    _s("Times of India Health", "India", "mainstream_news",
       "https://timesofindia.indiatimes.com/life-style/health-fitness",
       "timesofindia.indiatimes.com/"),
    _s("The Hindu Health", "India", "mainstream_news",
       "https://www.thehindu.com/sci-tech/health/", "thehindu.com/"),
    _s("Hindustan Times Health", "India", "mainstream_news",
       "https://www.hindustantimes.com/lifestyle/health",
       "hindustantimes.com/"),
    _s("NDTV Health", "India", "mainstream_news",
       "https://www.ndtv.com/health", "ndtv.com/health"),
    _s("India Today Health", "India", "mainstream_news",
       "https://www.indiatoday.in/health", "indiatoday.in/"),
    _s("The Indian Express Health", "India", "mainstream_news",
       "https://indianexpress.com/section/lifestyle/health/",
       "indianexpress.com/"),

    # South Korea (3) — Korean centenarian studies
    _s("Korea Herald Health", "South Korea", "mainstream_news",
       "https://www.koreaherald.com/section/health", "koreaherald.com/"),
    _s("Korea JoongAng Daily", "South Korea", "mainstream_news",
       "https://koreajoongangdaily.joins.com/section/culture",
       "koreajoongangdaily.joins.com/"),
    _s("Chosun Ilbo Health", "South Korea", "mainstream_news",
       "https://english.chosun.com/", "english.chosun.com/"),

    # Singapore (5) — longevity hub, positioning as Blue Zone 2.0
    _s("Straits Times Health", "Singapore", "mainstream_news",
       "https://www.straitstimes.com/tags/longevity", "straitstimes.com/"),
    _s("CNA Health", "Singapore", "mainstream_news",
       "https://www.channelnewsasia.com/wellness", "channelnewsasia.com/"),
    _s("Today Online Singapore Health", "Singapore", "mainstream_news",
       "https://www.todayonline.com/singapore", "todayonline.com/"),
    _s("Business Times Singapore Health", "Singapore", "mainstream_news",
       "https://www.businesstimes.com.sg/lifestyle", "businesstimes.com.sg/"),
    _s("Mothership.sg Health", "Singapore", "mainstream_news",
       "https://mothership.sg/tag/health/", "mothership.sg/"),

    # Australia (10) — Australian Centenarian Study
    _s("ABC Australia Health", "Australia", "mainstream_news",
       "https://www.abc.net.au/news/health", "abc.net.au/news"),
    _s("Sydney Morning Herald Health", "Australia", "mainstream_news",
       "https://www.smh.com.au/lifestyle/health-and-wellness", "smh.com.au/"),
    _s("The Age Health", "Australia", "mainstream_news",
       "https://www.theage.com.au/lifestyle/health-and-wellness",
       "theage.com.au/"),
    _s("Herald Sun Health", "Australia", "mainstream_news",
       "https://www.heraldsun.com.au/lifestyle/health", "heraldsun.com.au/"),
    _s("Brisbane Times Health", "Australia", "mainstream_news",
       "https://www.brisbanetimes.com.au/lifestyle/health-and-wellness",
       "brisbanetimes.com.au/"),
    _s("Daily Telegraph Sydney Health", "Australia", "mainstream_news",
       "https://www.dailytelegraph.com.au/lifestyle/health",
       "dailytelegraph.com.au/"),
    _s("The Australian Health", "Australia", "mainstream_news",
       "https://www.theaustralian.com.au/science/health",
       "theaustralian.com.au/"),
    _s("news.com.au Health", "Australia", "mainstream_news",
       "https://www.news.com.au/lifestyle/health", "news.com.au/"),
    _s("SBS Health", "Australia", "mainstream_news",
       "https://www.sbs.com.au/topics/science/humans/health", "sbs.com.au/"),
    _s("Perth Now Health", "Australia", "mainstream_news",
       "https://www.perthnow.com.au/lifestyle/health", "perthnow.com.au/"),

    # New Zealand (2)
    _s("New Zealand Herald Health", "New Zealand", "mainstream_news",
       "https://www.nzherald.co.nz/lifestyle/health/", "nzherald.co.nz/"),
    _s("Stuff.co.nz Health", "New Zealand", "mainstream_news",
       "https://www.stuff.co.nz/life-style/well-good/", "stuff.co.nz/"),

    # Southeast Asia (5)
    _s("Philippine Daily Inquirer Health", "Philippines", "mainstream_news",
       "https://newsinfo.inquirer.net/category/latest-stories", "inquirer.net/"),
    _s("Bangkok Post Health", "Thailand", "mainstream_news",
       "https://www.bangkokpost.com/life/social-and-lifestyle",
       "bangkokpost.com/"),
    _s("The Nation Thailand Health", "Thailand", "mainstream_news",
       "https://www.nationthailand.com/lifestyle", "nationthailand.com/"),
    _s("The Star Health", "Malaysia", "mainstream_news",
       "https://www.thestar.com.my/lifestyle/health", "thestar.com.my/"),
    _s("New Straits Times Health", "Malaysia", "mainstream_news",
       "https://www.nst.com.my/lifestyle/heal", "nst.com.my/"),
    _s("Jakarta Post Health", "Indonesia", "mainstream_news",
       "https://www.thejakartapost.com/life", "thejakartapost.com/"),
    _s("Vietnam News Health", "Vietnam", "mainstream_news",
       "https://vietnamnews.vn/society/", "vietnamnews.vn/"),

    # ══════════════════════════════════════════════════════════════════════════
    # CLASS 7: MAINSTREAM NEWS — LATIN AMERICA (11)
    # ══════════════════════════════════════════════════════════════════════════

    _s("Globo Saude", "Brazil", "mainstream_news",
       "https://g1.globo.com/saude/", "g1.globo.com/"),
    _s("Folha de Sao Paulo Saude", "Brazil", "mainstream_news",
       "https://www1.folha.uol.com.br/equilibrioesaude/", "folha.uol.com.br/"),
    _s("UOL Saude", "Brazil", "mainstream_news",
       "https://www.uol.com.br/vivabem/saude/", "uol.com.br/"),
    _s("Infobae Salud", "Argentina", "mainstream_news",
       "https://www.infobae.com/salud/", "infobae.com/"),
    _s("La Nacion Argentina Salud", "Argentina", "mainstream_news",
       "https://www.lanacion.com.ar/salud/", "lanacion.com.ar/"),
    _s("El Universal Salud", "Mexico", "mainstream_news",
       "https://www.eluniversal.com.mx/ciencia-y-salud/",
       "eluniversal.com.mx/"),
    _s("La Tercera Salud", "Chile", "mainstream_news",
       "https://www.latercera.com/que-pasa/salud/", "latercera.com/"),
    _s("El Tiempo Salud", "Colombia", "mainstream_news",
       "https://www.eltiempo.com/salud/", "eltiempo.com/"),
    _s("El Espectador Salud", "Colombia", "mainstream_news",
       "https://www.elespectador.com/salud/", "elespectador.com/"),
    _s("El Comercio Salud", "Peru", "mainstream_news",
       "https://elcomercio.pe/tecnologia/ciencias/", "elcomercio.pe/"),
    _s("La Razon Salud", "Bolivia", "mainstream_news",
       "https://www.la-razon.com/salud/", "la-razon.com/"),

    # ══════════════════════════════════════════════════════════════════════════
    # CLASS 8: MAINSTREAM NEWS — MIDDLE EAST / AFRICA (16)
    # ══════════════════════════════════════════════════════════════════════════

    # Israel (3) — Ashkenazi Jewish centenarian studies (FOXO3, CETP genes)
    _s("Haaretz Health", "Israel", "mainstream_news",
       "https://www.haaretz.com/life/", "haaretz.com/"),
    _s("Jerusalem Post Health", "Israel", "mainstream_news",
       "https://www.jpost.com/health-and-wellness", "jpost.com/"),
    _s("Times of Israel Health", "Israel", "mainstream_news",
       "https://www.timesofisrael.com/topic/health/", "timesofisrael.com/"),

    # Middle East (4)
    _s("Al Jazeera Health", "Qatar", "mainstream_news",
       "https://www.aljazeera.com/tag/health/", "aljazeera.com/"),
    _s("Arab News Health", "Saudi Arabia", "mainstream_news",
       "https://www.arabnews.com/health", "arabnews.com/"),
    _s("The National Health", "UAE", "mainstream_news",
       "https://www.thenationalnews.com/health/", "thenationalnews.com/"),
    _s("Gulf News Health", "UAE", "mainstream_news",
       "https://gulfnews.com/lifestyle/health-fitness", "gulfnews.com/"),

    # Turkey (1)
    _s("Hurriyet Daily News Health", "Turkey", "mainstream_news",
       "https://www.hurriyetdailynews.com/health", "hurriyetdailynews.com/"),

    # Pakistan (1)
    _s("Dawn Health", "Pakistan", "mainstream_news",
       "https://www.dawn.com/news/health", "dawn.com/news"),

    # Africa (7)
    _s("News24 Health", "South Africa", "mainstream_news",
       "https://www.news24.com/health24/", "news24.com/"),
    _s("IOL Health", "South Africa", "mainstream_news",
       "https://www.iol.co.za/lifestyle/health", "iol.co.za/"),
    _s("Mail & Guardian Health", "South Africa", "mainstream_news",
       "https://mg.co.za/tag/health/", "mg.co.za/"),
    _s("Daily Nation Health", "Kenya", "mainstream_news",
       "https://nation.africa/kenya/health/", "nation.africa/"),
    _s("The East African Health", "Kenya", "mainstream_news",
       # Regional: covers Kenya, Tanzania, Uganda, Rwanda
       "https://www.theeastafrican.co.ke/tea/science-health",
       "theeastafrican.co.ke/"),
    _s("Premium Times Health", "Nigeria", "mainstream_news",
       # Nigeria: largest population in Africa
       "https://www.premiumtimesng.com/health/", "premiumtimesng.com/"),
    _s("Punch Health", "Nigeria", "mainstream_news",
       "https://punchng.com/topics/health/", "punchng.com/"),

    # ══════════════════════════════════════════════════════════════════════════
    # CLASS 10: LIFESTYLE & GENERAL INTEREST MAGAZINES (20)
    # Where centenarian profiles get the most personal detail.
    # Cross-publication frequency is itself a model signal.
    # ══════════════════════════════════════════════════════════════════════════

    _s("Prevention Magazine", "USA", "lifestyle_magazine",
       "https://www.prevention.com/health/", "prevention.com/"),
    _s("Health Magazine", "USA", "lifestyle_magazine",
       "https://www.health.com/longevity", "health.com/"),
    _s("Men's Health", "USA", "lifestyle_magazine",
       "https://www.menshealth.com/health/", "menshealth.com/"),
    _s("Women's Health", "USA", "lifestyle_magazine",
       "https://www.womenshealthmag.com/health/", "womenshealthmag.com/"),
    _s("SELF Magazine", "USA", "lifestyle_magazine",
       "https://www.self.com/health/", "self.com/"),
    _s("Shape Magazine", "USA", "lifestyle_magazine",
       "https://www.shape.com/lifestyle/", "shape.com/"),
    _s("Good Housekeeping Health", "USA", "lifestyle_magazine",
       "https://www.goodhousekeeping.com/health/", "goodhousekeeping.com/"),
    _s("Reader's Digest Health", "USA", "lifestyle_magazine",
       "https://www.rd.com/health/", "rd.com/"),
    _s("Better Homes & Gardens Health", "USA", "lifestyle_magazine",
       "https://www.bhg.com/health-family/", "bhg.com/"),
    _s("Real Simple Health", "USA", "lifestyle_magazine",
       "https://www.realsimple.com/health", "realsimple.com/"),
    _s("Parade Magazine", "USA", "lifestyle_magazine",
       "https://parade.com/health", "parade.com/"),
    _s("Woman's World", "USA", "lifestyle_magazine",
       "https://www.womansworld.com/health", "womansworld.com/"),
    _s("Oprah Daily Health", "USA", "lifestyle_magazine",
       "https://www.oprahdaily.com/life/health/", "oprahdaily.com/"),
    _s("Closer Weekly", "USA", "lifestyle_magazine",
       "https://www.closerweekly.com/category/health/", "closerweekly.com/"),
    _s("First for Women", "USA", "lifestyle_magazine",
       "https://www.firstforwomen.com/health", "firstforwomen.com/"),
    _s("Saga Magazine", "UK", "lifestyle_magazine",
       "https://www.saga.co.uk/magazine/health-wellbeing", "saga.co.uk/"),
    _s("Woman's Weekly UK", "UK", "lifestyle_magazine",
       "https://www.womansweekly.com/health/", "womansweekly.com/"),
    _s("Yours Magazine", "UK", "lifestyle_magazine",
       "https://www.yours.co.uk/health/", "yours.co.uk/"),
    _s("Prima Magazine", "UK", "lifestyle_magazine",
       "https://www.prima.co.uk/diet-and-health/", "prima.co.uk/"),
    _s("New Idea Health", "Australia", "lifestyle_magazine",
       "https://www.newidea.com.au/health/", "newidea.com.au/"),
]


# ================================================================================
# ANCHOR TEXT KEYWORDS — filter BEFORE visiting any link
# If a link's visible headline text doesn't contain any of these, skip it.
# ================================================================================

ANCHOR_KEYWORDS = [
    "100-year", "100 year", "101", "102", "103", "104", "105",
    "106", "107", "108", "109", "110", "111", "112", "113", "114",
    "115", "116", "117", "118", "119", "120",
    "centenarian", "supercentenarian",
    "oldest", "lives to 100", "live to 100", "reach 100",
    "turned 100", "turns 100",
    "longevity", "long life", "lifespan", "healthspan",
    "live longer", "living longer", "secrets to",
    "tips for a long", "longevity tips", "longevity secrets",
    "longevity habits", "anti-aging", "anti-ageing",
    "life expectancy", "healthy aging", "healthy ageing",
    "exceptional longevity", "blue zone", "ikigai",
    "aging well", "ageing well",
]

# ================================================================================
# CONTENT KEYWORDS — article body must contain at least one
# ================================================================================

CONTENT_KEYWORDS = [
    "centenarian", "supercentenarian", "100 year", "100-year",
    "longevity", "live to 100", "lifespan", "healthspan",
    "blue zone", "ikigai", "exceptional longevity",
    "healthy aging", "healthy ageing", "life expectancy",
    "oldest living", "aging well", "ageing well", "long life",
    "live longer", "living longer",
]

# ================================================================================
# KEYWORD -> COLUMN MAPS
# Each keyword maps to a specific TRUE/FALSE column in the output CSV.
# Column names directly correspond to scoring model dimensions and app fields.
# ================================================================================

KW_PHYSICAL = [
    "exercise", "swim", "swimming", "walk", "walking", "gym", "workout",
    "yoga", "dance", "dancing", "active", "movement", "zumba", "cardio",
    "strength training", "weightlifting", "cycling", "gardening", "hiking",
    "tai chi", "sedentary", "run", "running", "jog", "jogging", "pilates",
    "martial art", "tennis", "golf", "physical activity",
]
KW_DIET = [
    "vegetable", "vegetables", "plant-based", "plant based", "mediterranean",
    "olive oil", "legume", "legumes", "fruit", "fruits", "diet", "nutrition",
    "calorie", "caloric", "alcohol", "smoking", "whole food", "whole foods",
    "processed food", "sugar", "red wine", "fasting", "protein", "fiber",
    "fibre", "antioxidant", "okinawa diet", "pescatarian", "vegetarian",
    "vegan", "fish", "nuts", "seeds", "grains", "dairy", "fermented",
    "probiotic", "omega-3", "omega 3",
]
KW_SOCIAL = [
    "social", "community", "family", "friend", "friends", "church", "faith",
    "religion", "religious", "volunteer", "volunteering", "moai", "belonging",
    "connection", "loneliness", "isolated", "isolation", "marriage", "married",
    "spouse", "grandchild", "grandchildren", "neighborhood", "tribe",
]
KW_PURPOSE = [
    "purpose", "ikigai", "positive", "optimis", "grateful", "gratitude",
    "stress", "meaning", "passion", "attitude", "mindset", "resilience",
    "conscientiou", "neuroticism", "extraversion", "happiness", "humor",
    "laughter", "anxiety", "depression", "mental health", "cognitive",
    "curiosity", "learning", "reading", "retired", "retirement", "working",
    "job", "career", "meaningful work",
]
KW_SLEEP = [
    "sleep", "rest", "nap", "siesta", "insomnia", "circadian",
    "melatonin", "sleep quality", "sleep duration", "hours of sleep",
]

KW_BIO_INFLAMMATION = [
    "inflammation", "inflammatory", "crp", "c-reactive", "il-6",
    "interleukin", "tnf", "cytokine", "anti-inflammatory", "nf-kb",
    "chronic inflammation", "inflammaging", "fibrinogen", "esr",
]
KW_BIO_GLUCOSE = [
    "glucose", "insulin", "hba1c", "a1c", "blood sugar", "diabetes",
    "metabolic syndrome", "insulin resistance", "homa-ir", "fasting glucose",
    "glycemic", "prediabetes",
]
KW_BIO_LIPIDS = [
    "cholesterol", "triglyceride", "hdl", "ldl", "lipid", "lipids",
    "apolipoprotein", "apob", "apoa1", "statin",
]
KW_BIO_IGF1 = [
    "igf-1", "igf1", "igf 1", "insulin-like growth factor",
    "growth hormone", "mtor",
]
KW_BIO_TELOMERES = [
    "telomere", "telomeres", "telomerase", "telomere length",
    "leukocyte telomere",
]
KW_BIO_EPIGENETIC = [
    "epigenetic", "methylation", "dna methylation", "biological age",
    "epigenetic clock", "horvath", "grimage", "phenoage", "dnam",
    "epigenetic age",
]
KW_BIO_MICROBIOME = [
    "microbiome", "gut bacteria", "gut microbiota", "probiotic",
    "gut health", "microbiota diversity",
]
KW_BIO_HORMONES = [
    "cortisol", "testosterone", "estrogen", "dhea", "thyroid",
    "hormone", "hormonal", "melatonin",
]
KW_BIO_FUNCTIONAL = [
    "grip strength", "gait speed", "vo2 max", "vo2max", "fev1",
    "lung function", "balance test", "functional capacity", "frailty",
    "sarcopenia", "muscle mass",
]
KW_BIO_METABOLOMIC = [
    "metabolomics", "metabolomic", "bile acid", "bile acids",
    "chenodeoxycholic", "lithocholic", "metabolite", "bilirubin",
]

KW_GENE_APOE = ["apoe", "apolipoprotein e", "apoe4", "apoe2"]
KW_GENE_FOXO3 = ["foxo3", "foxo3a", "forkhead box"]
KW_GENE_CETP = ["cetp", "cholesteryl ester transfer"]
KW_GENE_KLOTHO = ["klotho", "kl-vs"]
KW_GENE_OTHER = [
    "sirt1", "sirtuin", "ace gene", "mtor pathway", "ampk",
    "brca", "gwas", "genome-wide", "polymorphism", "snp",
    "genetic variant", "heritability", "hereditary",
]

# ================================================================================
# STATISTICAL EXTRACTION PATTERNS
# ================================================================================

STAT_PATTERNS = {
    "odds_ratio":          r'(?:OR|odds ratio)[^\d]*(\d+\.?\d*)',
    "hazard_ratio":        r'(?:HR|hazard ratio)[^\d]*(\d+\.?\d*)',
    "sample_size":         r'(?:n\s*=\s*|studied\s+|enrolled\s+)(\d[\d,]+)',
    "percentage":          r'(\d+\.?\d*)\s*(?:%|percent)',
    "p_value":             r'p\s*[<=]\s*(\d+\.?\d+)',
    "confidence_interval": r'(?:95%\s*CI|confidence interval)[^\d]*(\d+\.?\d*)[^\d]+(\d+\.?\d*)',
}

# ================================================================================
# BROWSER
# ================================================================================

def create_driver():
    opts = Options()
    opts.add_argument("--headless=new")  # comment out to watch browser
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-gpu")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36")
    opts.add_experimental_option(
        "excludeSwitches", ["enable-logging", "enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    svc = Service(ChromeDriverManager().install())
    drv = webdriver.Chrome(service=svc, options=opts)
    drv.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    drv.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
    return drv

# ================================================================================
# SCROLL
# ================================================================================

def scroll_page(driver, mx=MAX_SCROLLS):
    try:
        lh = driver.execute_script("return document.body.scrollHeight")
    except Exception:
        return  # page didn't load properly, skip scrolling
    done = 0
    while done < mx:
        try:
            driver.execute_script("window.scrollTo(0,document.body.scrollHeight);")
            time.sleep(2.5)
            nh = driver.execute_script("return document.body.scrollHeight")
            if nh == lh: break
            lh = nh; done += 1
        except Exception:
            break  # stop scrolling if anything goes wrong, don't crash
    print(f"    Scrolled {done}x | Height: {lh}px")

# ================================================================================
# LINK HARVESTING
# ================================================================================

def anchor_ok(text):
    t = text.lower()
    return any(kw in t for kw in ANCHOR_KEYWORDS)

def harvest_links(driver, source):
    skip = ["/tag/","/author/","/page/","/category/","/topic/","/section/",
            "mailto:","javascript:","#","twitter.com","facebook.com",
            "instagram.com","youtube.com","linkedin.com",".pdf",".rss",
            "/advertise","/subscribe","/newsletter","/login","/register",
            "/privacy","/terms","/about","/contact","/sitemap"]
    raw = []
    try:
        for el in driver.find_elements(By.TAG_NAME, "a"):
            try:
                raw.append({"href": el.get_attribute("href") or "", "text": el.text.strip()})
            except (StaleElementReferenceException, WebDriverException):
                continue
    except: return []
    seen, out = set(), []
    for lnk in raw:
        h, t = lnk["href"], lnk["text"]
        if not h or source["url_must_contain"] not in h: continue
        if any(p in h.lower() for p in skip): continue
        if len(h) < 50: continue
        if not anchor_ok(t): continue
        if h in seen: continue
        seen.add(h); out.append(h)
    return out

# ================================================================================
# EXTRACTION
# ================================================================================

def _has(tl, kws):
    return any(kw in tl for kw in kws)

def extract_subject(title, body):
    c = title + " " + body[:800]
    name = ""
    m = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+),?\s*(?:age\s*)?(\d{2,3})', c)
    if m and 85 <= int(m.group(2)) <= 130:
        name = m.group(1)
    else:
        m = re.search(r'(\d{3})-?year-?old\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', c)
        if m and 85 <= int(m.group(1)) <= 130:
            name = m.group(2)
    age = ""
    am = re.findall(r'\b(1[0-2][0-9])\b', title)
    if am: age = am[0]
    elif name:
        ni = c.find(name)
        if ni >= 0:
            nb = c[max(0,ni-50):ni+100]
            am2 = re.findall(r'\b(1[0-2][0-9])\b', nb)
            if am2: age = am2[0]
    city = country = ""
    lm = re.search(
        r'(?:of|from|in|lives? in|based in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
        r'(?:,\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?))?', c)
    if lm:
        city = lm.group(1) or ""
        country = lm.group(2) or ""
    return {"subject_name":name, "subject_age":age,
            "subject_city":city, "subject_country":country}

def extract_ages(text):
    raw = re.findall(r'\b(1[0-2][0-9]|[89][0-9])\b', text)
    u = sorted(set(int(a) for a in raw if 85 <= int(a) <= 130))
    return ",".join(str(a) for a in u) if u else ""

def extract_stats(text):
    st = {}
    for nm, pat in STAT_PATTERNS.items():
        ms = re.findall(pat, text, re.IGNORECASE)
        if ms:
            fl = [str(m) if isinstance(m,str) else "|".join(m) for m in ms]
            st[nm] = "; ".join(fl[:5])
    return st

def extract_columns(body):
    tl = body.lower()
    return {
        "trait_physical_activity":  _has(tl, KW_PHYSICAL),
        "trait_diet":              _has(tl, KW_DIET),
        "trait_social":            _has(tl, KW_SOCIAL),
        "trait_purpose_psychology": _has(tl, KW_PURPOSE),
        "trait_sleep":             _has(tl, KW_SLEEP),
        "biomarker_inflammation":  _has(tl, KW_BIO_INFLAMMATION),
        "biomarker_glucose":       _has(tl, KW_BIO_GLUCOSE),
        "biomarker_lipids":        _has(tl, KW_BIO_LIPIDS),
        "biomarker_igf1":          _has(tl, KW_BIO_IGF1),
        "biomarker_telomeres":     _has(tl, KW_BIO_TELOMERES),
        "biomarker_epigenetic":    _has(tl, KW_BIO_EPIGENETIC),
        "biomarker_microbiome":    _has(tl, KW_BIO_MICROBIOME),
        "biomarker_hormones":      _has(tl, KW_BIO_HORMONES),
        "biomarker_functional":    _has(tl, KW_BIO_FUNCTIONAL),
        "biomarker_metabolomic":   _has(tl, KW_BIO_METABOLOMIC),
        "gene_apoe":               _has(tl, KW_GENE_APOE),
        "gene_foxo3":              _has(tl, KW_GENE_FOXO3),
        "gene_cetp":               _has(tl, KW_GENE_CETP),
        "gene_klotho":             _has(tl, KW_GENE_KLOTHO),
        "gene_other":              _has(tl, KW_GENE_OTHER),
    }

def content_ok(text):
    tl = text.lower()
    return any(kw in tl for kw in CONTENT_KEYWORDS)

# ================================================================================
# ARTICLE SCRAPER
# ================================================================================

def scrape_article(driver, url, source):
    try:
        driver.get(url)
        time.sleep(1.5)
        title = ""
        for tag in ["h1","h2"]:
            els = driver.find_elements(By.TAG_NAME, tag)
            if els:
                try:
                    t = els[0].text.strip()
                    if t: title = t; break
                except (StaleElementReferenceException, WebDriverException):
                    continue
        parts = []
        try:
            for p in driver.find_elements(By.TAG_NAME, "p"):
                try:
                    t = p.text.strip()
                    if t: parts.append(t)
                except (StaleElementReferenceException, WebDriverException):
                    continue
        except: pass
        body = " ".join(parts)
        if len(body.split()) < MIN_WORD_COUNT: return None
        if not content_ok(title + " " + body): return None
        date_str = ""
        for sel in ["time[datetime]","[class*='date']","[class*='Date']",
                     "[class*='timestamp']","[class*='published']","time"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                date_str = el.get_attribute("datetime") or el.text.strip()
                if date_str: break
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        full = title + " " + body
        ages = extract_ages(full)
        stats = extract_stats(body)
        cols = extract_columns(body)
        subj = extract_subject(title, body)
        max_age = str(max(int(a) for a in ages.split(","))) if ages else ""
        rec = {
            "source_name":    source["name"],
            "source_country": source["country"],
            "source_class":   source["source_class"],
            "url":            url,
            "scraped_date":   datetime.now().strftime("%Y-%m-%d"),
            "publish_date":   date_str,
            "title":          title,
            "word_count":     len(body.split()),
            "full_text":      body,
            "subject_name":   subj["subject_name"],
            "subject_age":    subj["subject_age"],
            "subject_city":   subj["subject_city"],
            "subject_country":subj["subject_country"],
            "ages_mentioned": ages,
            "max_age":        max_age,
            "stat_odds_ratio":         stats.get("odds_ratio",""),
            "stat_hazard_ratio":       stats.get("hazard_ratio",""),
            "stat_sample_size":        stats.get("sample_size",""),
            "stat_percentage":         stats.get("percentage",""),
            "stat_p_value":            stats.get("p_value",""),
            "stat_confidence_interval":stats.get("confidence_interval",""),
            "has_age":   bool(ages),
            "has_stats": bool(stats),
            "is_centenarian_profile": any(
                kw in full.lower() for kw in
                ["centenarian","100-year-old","100 year old",
                 "supercentenarian","lives to 100"]),
        }
        rec.update(cols)
        return rec
    except TimeoutException: return None
    except (ConnectionResetError, ConnectionAbortedError): return None
    except WebDriverException: return None
    except Exception: return None

# ================================================================================
# RESUME + SAVE
# ================================================================================

def load_done(path):
    if not os.path.exists(path): return set()
    try: return set(pd.read_csv(path, usecols=["url"])["url"].dropna().tolist())
    except: return set()

def save_rec(rec, path, hdr):
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rec.keys())
        if hdr: w.writeheader()
        w.writerow(rec)

# ================================================================================
# MAIN
# ================================================================================

def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    done = load_done(out)
    hdr = len(done) == 0

    print("="*70)
    print("  REJUVE LONGEVITY — News Scraper v3.1")
    print(f"  Sources:   {len(SOURCES)}")
    print(f"  Output:    {out}")
    print(f"  Resuming:  {len(done)} URLs already collected")
    print("="*70)

    driver = create_driver()
    ss = 0

    try:
        for si, src in enumerate(SOURCES):
            print(f"\n{'─'*70}")
            print(f"[{si+1}/{len(SOURCES)}] {src['name']} | {src['country']} | {src['source_class']}")
            print(f"{'─'*70}")
            try:
                driver.get(src["tag_url"])
                time.sleep(3)
            except (TimeoutException, WebDriverException) as e:
                print(f"  ✗ Could not load — skipping ({type(e).__name__})")
                continue
            if src.get("scroll"):
                time.sleep(2)
                scroll_page(driver)
            links = harvest_links(driver, src)
            print(f"  → {len(links)} qualifying links")
            if not links: continue
            sv = 0
            for i, url in enumerate(links):
                if url in done: continue
                print(f"  [{i+1}/{len(links)}] ", end="", flush=True)
                rec = scrape_article(driver, url, src)
                if rec:
                    save_rec(rec, out, hdr); hdr = False
                    done.add(url); sv += 1; ss += 1
                    age = f"age={rec['subject_age']}" if rec['subject_age'] else (
                          f"max={rec['max_age']}" if rec['max_age'] else "no age")
                    nm = rec['subject_name'] or ""
                    st = " 📊" if rec['has_stats'] else ""
                    ct = " 👤" if rec['is_centenarian_profile'] else ""
                    print(f"✓ {rec['title'][:40]}... [{nm} {age}{st}{ct}]")
                else:
                    print("✗")
                time.sleep(DELAY_BETWEEN_ARTICLES)
            print(f"\n  ✓ {sv} new articles")
            time.sleep(DELAY_BETWEEN_SOURCES)
    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted — progress saved")
    finally:
        driver.quit()
        print("\n→ Browser closed")

    print(f"\n{'='*70}")
    print(f"  DONE | Session: {ss} new articles")
    print(f"{'='*70}")

    if os.path.exists(out):
        df = pd.read_csv(out)
        print(f"\n  TOTAL: {len(df)} articles")
        print(f"  Centenarian profiles:  {df['is_centenarian_profile'].sum()}")
        print(f"  With age mentions:     {df['has_age'].sum()}")
        print(f"  With stats:            {df['has_stats'].sum()}")
        tc = [c for c in df.columns if c.startswith("trait_")]
        bc = [c for c in df.columns if c.startswith("biomarker_")]
        gc = [c for c in df.columns if c.startswith("gene_")]
        print(f"\n  TRAIT COVERAGE:")
        for c in tc: print(f"    {c:<30} {df[c].sum():>5}")
        print(f"\n  BIOMARKER COVERAGE:")
        for c in bc: print(f"    {c:<30} {df[c].sum():>5}")
        print(f"\n  GENE COVERAGE:")
        for c in gc: print(f"    {c:<30} {df[c].sum():>5}")
        print(f"\n  BY SOURCE CLASS:")
        for cl,ct in df["source_class"].value_counts().items():
            print(f"    {cl:<30} {ct}")
        print(f"\n  BY COUNTRY (top 15):")
        for co,ct in df["source_country"].value_counts().head(15).items():
            print(f"    {co:<20} {ct}")
        prev = out.replace(".csv","_preview.csv")
        df[[c for c in df.columns if c!="full_text"]].to_csv(
            prev, index=False, encoding="utf-8")
        print(f"\n  FILES:\n    {out}\n    {prev}")

if __name__ == "__main__":
    run()
