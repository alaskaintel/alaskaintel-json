#!/usr/bin/env python3
"""
Alaska Intel Feed Aggregator
Fetches and aggregates 100+ RSS feeds for alaskaintel.com
"""

import feedparser
import json
import os
import re
import sys
import hashlib
import threading
from datetime import datetime, timedelta, timezone
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from tenacity import retry, stop_after_attempt, wait_exponential
import html
import glob
import shutil
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timezone, timedelta
from typing import List, Dict
import ssl
from geo_dict import geocode_text, geocode_anchorage_address, ANCHORAGE_CENTROID

ssl._create_default_https_context = ssl._create_unverified_context

# Archive settings
ARCHIVE_DIR = os.path.join("data", "archive")
ARCHIVE_RETENTION_DAYS = 365

# HTTP configuration
# Use a modern Chrome user‑agent to reduce blocks from strict servers
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

# Feed status tracking: external list of feeds currently on hold or marked stale
FEED_STATUS_FILE = os.path.join("data", "feed_status.json")

# FAIR USE snippet limits were increased upstream; keep the larger value.
FAIR_USE_MAX_CHARS = 1000
FAIR_USE_MAX_RATIO = 0.10
FAIR_USE_MAX_RATIO = 0.10

REGION_KEYWORDS = {
    "Mat-Su": ["mat-su", "matanuska", "susitna", "wasilla", "palmer"],
    "Southcentral": ["anchorage", "kenai", "soldotna", "homer", "cordova", "whittier", "girdwood", "turnagain"],
    "Southeast": ["juneau", "sitka", "ketchikan", "petersburg", "wrangell", "skagway", "haines"],
    "Interior": ["fairbanks", "delta", "tok", "north pole"],
    "Western Alaska": ["bethel", "nome", "dillingham", "kuskokwim", "yukon"],
    "North Slope": ["utqiagvik", "barrow", "north slope", "kotzebue"],
    "Gulf Coast": ["kodiak", "valdez", "seward", "prince william sound"],
}

# Complete list of 184 RSS feeds for Alaska intelligence
FEEDS = [
    # === STATEWIDE & GENERAL NEWS (1-9) ===
    {"name": "Alaska Public Media", "url": "https://alaskapublic.org/news.rss", "category": "News"},
    {"name": "KTOO Juneau", "url": "https://ktoo.org/feed", "category": "News"},
    {"name": "Must Read Alaska", "url": "https://mustreadalaska.com/feed/", "category": "Politics"},
    {"name": "Alaska Native News", "url": "https://alaska-native-news.com/feed", "category": "Native"},
    {"name": "Alaska Watchman", "url": "https://alaskawatchman.com/feed/", "category": "News"},
    {"name": "Alaska Beacon", "url": "https://alaskabeacon.com/feed/", "category": "News"},
    {"name": "Dermot Cole", "url": "https://www.dermotcole.com/reportingfromalaska?format=rss", "category": "Politics"},
    {"name": "Alaska Landmine", "url": "https://alaskalandmine.com/feed/", "category": "Politics"},
    
    # === REGIONAL & COMMUNITY NEWS (10-22) ===
    {"name": "Juneau Empire", "url": "https://juneauempire.com/feed", "category": "Regional"},
    {"name": "Nome Nugget", "url": "https://nomenugget.net/rss.xml", "category": "Regional"},
    {"name": "Homer News", "url": "https://homernews.com/feed/", "category": "Regional"},
    {"name": "The Cordova Times", "url": "https://thecordovatimes.com/feed", "category": "Regional"},
    {"name": "Petersburg Pilot", "url": "https://petersburgpilot.com/rss", "category": "Regional"},
    {"name": "Anchorage Daily News", "url": "https://www.adn.com/arc/outboundfeeds/rss/?outputType=xml", "category": "News"},
    {"name": "Fairbanks News-Miner", "url": "https://newsminer.com/search/?f=rss", "category": "Regional"},
    {"name": "Kodiak Daily Mirror", "url": "https://kodiakdailymirror.com/search/?f=rss&t=article&c=news&l=50&s=start_time&sd=desc", "category": "Regional"},
    {"name": "Mat-Su Frontiersman", "url": "https://www.frontiersman.com/search/?f=rss&t=article&c=news&l=50&s=start_time&sd=desc", "category": "Regional"},
    # {"name": "Sitka Sentinel", "url": "https://www.sitkasentinel.com/search/?f=rss&t=article&c=news&l=50&s=start_time&sd=desc", "category": "Regional"}, # 403 Forbidden
    {"name": "Chilkat Valley News", "url": "https://chilkatvalleynews.com/feed", "category": "Regional"},
    # === INDUSTRY & ECONOMY (23-31) ===
    {"name": "Alaska Business Magazine", "url": "https://akbizmag.com/feed", "category": "Business"},
    # {"name": "Resource Development Council", "url": "https://akrdc.org/rss", "category": "Industry"}, # 404 Not Found
    {"name": "Petroleum News", "url": "https://www.petroleumnews.com/rss/rssfeed.xml", "category": "Energy"},
    # "Alaska Economic Report" removed — no standalone RSS; covered by Alaska Public Media feed above
    
    # === GOVERNMENT & CIVIC (32-37) ===
    {"name": "BLM Alaska", "url": "https://blm.gov/press-release/alaska/rss", "category": "Government"},
    # === CITY & BOROUGH GOVERNMENT — VERIFIED LIVE RSS (discovered 2026-03-23) ===
    {"name": "Anchorage Police Dept", "url": "https://www.anchoragepolice.com/news?format=rss", "category": "Safety"},
    {"name": "Juneau CBJ", "url": "https://juneau.org/feed", "category": "Government"},
    {"name": "North Slope Borough", "url": "https://www.north-slope.org/news/feed", "category": "Government"},
    {"name": "Alaska Governor's Office", "url": "https://gov.alaska.gov/feed", "category": "Government"},
    {"name": "AK Dept of Natural Resources", "url": "https://dnr.alaska.gov/rss.xml", "category": "Environment"},
    {"name": "Wrangell City", "url": "https://www.wrangell.com/rss.xml", "category": "Government"},
    {"name": "Petersburg City", "url": "https://www.petersburgak.gov/rss.xml", "category": "Government"},
    {"name": "Dillingham City", "url": "https://www.dillinghamak.us/news/rss", "category": "Government"},
    {"name": "Cordova City", "url": "https://www.cityofcordova.net/feed", "category": "Government"},
    {"name": "Unalaska City", "url": "https://www.ci.unalaska.ak.us/rss.xml", "category": "Government"},
    
    # === EMERGENCY, WEATHER & ENVIRONMENT (38-45) ===
    {"name": "NWS Alaska CAP Alerts", "url": "https://api.weather.gov/alerts/active.atom?area=AK", "category": "Emergency"},
    {"name": "Tsunami Warning Center", "url": "https://tsunami.gov/events/xml/PAAQAtom.xml", "category": "Emergency"},
    # === NWS FORECAST OFFICES — ALASKA (correct office site codes) ===
    {"name": "NWS Anchorage", "url": "https://www.weather.gov/rss_page.php?site_name=afc", "category": "Weather"},
    {"name": "NWS Fairbanks", "url": "https://www.weather.gov/rss_page.php?site_name=afg", "category": "Weather"},
    {"name": "NWS Juneau", "url": "https://www.weather.gov/rss_page.php?site_name=ajk", "category": "Weather"},
    # === NICHE & INDEPENDENT (46-50) ===
    {"name": "Northern Journal", "url": "https://northernjournal.substack.com/feed", "category": "News"},
    # "Alaska Outdoor Journal" removed — ADFG RSS endpoints return 404
    # "ADN Alaska Journal" removed — no dedicated RSS for this section (use main ADN feed above)
    {"name": "Kenai Fly Fish", "url": "https://kenaiflyfish.com/feed", "category": "Recreation"},
    
    # === NATIVE CORPORATIONS & TRIBAL (51-58) ===
    {"name": "Sealaska Corporation", "url": "https://sealaska.com/feed", "category": "Native"},
    {"name": "Calista Corporation", "url": "https://www.calistacorp.com/feed/", "category": "Native"},
    {"name": "Doyon Limited", "url": "https://doyon.com/wp-json/wp/v2/posts?per_page=100", "category": "Native"},  # WP API: live 2026-03-27 (feed/ empty)
    {"name": "Chugach Alaska Corp", "url": "https://www.chugach.com/feed", "category": "Native"},
    {"name": "Sitnasuak Native Corp", "url": "https://snc.org/feed", "category": "Native"},
    {"name": "Alaska Federation of Natives", "url": "https://nativefederation.org/feed/", "category": "Native"},
    # === SPECIALIZED FISHERIES (59-66) ===
    # Pacific Maritime & Marine Exchange return HTTP 200 but zero items — checked 2026-03-27; keep for future recovery
    # {"name": "Pacific Maritime Magazine", "url": "https://pacmar.com/feed/", "category": "Maritime"},
    # {"name": "Marine Exchange of Alaska", "url": "https://mxak.org/feed/", "category": "Maritime"},
    
    # === FEDERAL AGENCIES (67-73) ===
    {"name": "NPS Denali", "url": "https://www.nps.gov/feeds/getNewsRSS.htm?parkCode=dena", "category": "Parks"},
    {"name": "NPS Glacier Bay", "url": "https://www.nps.gov/feeds/getNewsRSS.htm?parkCode=glba", "category": "Parks"},
    {"name": "NPS Kenai Fjords", "url": "https://www.nps.gov/feeds/getNewsRSS.htm?parkCode=kefj", "category": "Parks"},
    # USDA Alaska Statistics → see USDA NASS Reports below (same URL, keeping filtered version)
    
    # === ENERGY, MINING & INFRASTRUCTURE (74-79) ===
    {"name": "Mining.com Alaska", "url": "https://mining.com/feed", "category": "Mining"},
    {"name": "Northern Miner Alaska", "url": "https://www.northernminer.com/feed/", "category": "Mining"},
    {"name": "Alaska Power Association", "url": "https://alaskapower.org/feed", "category": "Energy"},
    {"name": "Oil & Gas IQ", "url": "https://oilandgasiq.com/rss/news", "category": "Energy"},
    {"name": "Renewable Energy Alaska", "url": "https://alaskarenewableenergy.org/feed", "category": "Energy"},
    
    # === RESEARCH & SCIENCE (80-86) ===
    # {"name": "UAF News", "url": "https://uaf.edu/news/archives/news-archives-2002-2010/images/08/slideshows/4-H_christian/edits/1220578665286.xml", "category": "Science"}, # Replaced by Tier-11 Headless Extractor
    {"name": "Alaska Ocean Observing", "url": "https://aoos.org/feed", "category": "Science"},
    {"name": "AK Conservation Science", "url": "https://accs.uaa.alaska.edu/feed", "category": "Environment"},
    {"name": "Mongabay Alaska", "url": "https://news.mongabay.com/feed", "category": "Environment"},
    {"name": "The Arctic Institute", "url": "https://thearcticinstitute.org/feed", "category": "Research"},
    {"name": "IARC UAF", "url": "https://uaf-iarc.org/feed/", "category": "Science"},
    
    # === HYPER-LOCAL COMMUNITY (87-95) ===
    # Kodiak Mirror → duplicate of Kodiak Daily Mirror above; removed
    {"name": "Skagway News", "url": "https://skagwaynews.com/feed.atom", "category": "Regional"},
    {"name": "Wrangell Sentinel", "url": "https://wrangellsentinel.com/browse.rss", "category": "Regional"},
    {"name": "KMXT Kodiak", "url": "https://kmxt.org/news/feed", "category": "Radio"},
    {"name": "KCAW Sitka", "url": "https://kcaw.org/feed", "category": "Radio"},
    {"name": "KHNS Haines/Skagway", "url": "https://khns.org/feed", "category": "Radio"},
    # === CIVIC & SAFETY FAST SIGNALS (96-100) ===
    # ===================================================================
    # EXPANSION BATCH (101-150) - Added from DATA_SOURCES_CATALOG.md
    # Note: Some may not have RSS - will need validation
    # ===================================================================
    
    # === ENVIRONMENTAL & CONSERVATION (101-110) ===
    {"name": "Alaska Conservation Foundation", "url": "https://alaskaconservation.org/feed", "category": "Environment"},
    {"name": "Sierra Club Alaska", "url": "https://sierraclub.org/rss.xml", "category": "Environment"},
    {"name": "Trustees for Alaska", "url": "https://trustees.org/feed", "category": "Environment"},
    {"name": "World Wildlife Fund Arctic", "url": "https://arcticwwf.org/feed", "category": "Environment"},
    {"name": "Alaska Wildlife Alliance", "url": "https://www.akwildlife.org/news?format=rss", "category": "Wildlife"},
    {"name": "Defenders of Wildlife Alaska", "url": "https://defenders.org/rss.xml", "category": "Wildlife"},
    {"name": "Center for Biological Diversity", "url": "https://app.newsloth.com/biologicaldiversity-org/UlFXUFdU.rss", "category": "Wildlife"},
    
    # === INDIGENOUS & TRIBAL (111-120) ===
    {"name": "Aleut Community of St. Paul", "url": "https://accsp.com/feed", "category": "Native"},
    {"name": "Tanana Chiefs Conference", "url": "https://tananachiefs.org/feed/", "category": "Native"},
    {"name": "Bristol Bay Native Corporation", "url": "https://www.bbnc.net/wp-json/wp/v2/posts?per_page=100", "category": "Native"},  # WP API: live 2026-03-27
    {"name": "Cook Inlet Region Inc", "url": "https://ciri.com/feed", "category": "Native"},
    {"name": "NANA Regional Corporation", "url": "https://nana.com/feed/atom", "category": "Native"},
    {"name": "Kawerak Inc", "url": "https://kawerak.org/feed", "category": "Native"},
    {"name": "Ahtna Inc", "url": "https://ahtna-inc.com/feed/atom", "category": "Native"},
    {"name": "Koniag Inc", "url": "https://koniag.com/feed", "category": "Native"},
    
    # === TRANSPORTATION & MARITIME (121-127) ===
    # "KBBI Homer Radio" removed — consistent 75s+ timeout (confirmed in exec summary)
    {"name": "USACE Alaska District", "url": "https://www.poa.usace.army.mil/DesktopModules/ArticleCS/RSS.aspx?ContentType=1&Site=1&max=25", "category": "Government"},
    # === EMERGENCY & FIRE (128-132) ===
    {"name": "Alaska Interagency Fire", "url": "https://akfireinfo.com/feed", "category": "Emergency"},
    # NWS Tsunami Center → duplicate of Tsunami Warning Center above; removed
    # === EDUCATION & RESEARCH (133-140) ===
    # {"name": "University of Alaska System", "url": "https://ou-webserver02.alaska.edu/rss/rss-custom-sample.xml", "category": "Education"}, # Replaced by Tier-11 Headless Extractor
    {"name": "North Pacific Research", "url": "https://nprb.org/feed/", "category": "Research"},
    {"name": "Institute of the North", "url": "https://institutenorth.org/feed", "category": "Research"},
    {"name": "Alaska Climate Center", "url": "https://akclimate.org/feed", "category": "Climate"},
    {"name": "Scenarios Network AK", "url": "https://snap.uaf.edu/?feed=rss2", "category": "Climate"},
    
    # === HEALTH & SOCIAL (141-145) ===
    {"name": "Alaska Mental Health Trust", "url": "https://alaskamentalhealthtrust.org/feed", "category": "Health"},
    {"name": "United Way of Anchorage", "url": "https://liveunitedanc.org/rss.xml", "category": "Social"},
    
    # === BUSINESS & DEVELOPMENT (146-150) ===
    {"name": "Anchorage Economic Dev", "url": "https://aedcweb.com/wp-json/wp/v2/posts?per_page=100", "category": "Economy"},  # WP API: live 2026-03-27 (/feed empty)
    {"name": "Alaska Small Business Dev", "url": "https://aksbdc.org/feed/", "category": "Business"},
    {"name": "Alaska Policy Forum", "url": "https://alaskapolicyforum.org/feed/", "category": "Politics"},
    {"name": "Northern Economics", "url": "https://northerneconomics.com/feed/atom", "category": "Economy"},
    
    # ===================================================================
    # NEXT-50 CATALOG SOURCES (151-197) — RSS-VERIFIED
    # ===================================================================

    # === TV & COMMERCIAL NEWS ===
    {"name": "News Talk KFQD 750", "url": "https://kfqd.com/feed", "category": "News"},
    {"name": "Peninsula Clarion", "url": "https://www.peninsulaclarion.com/feed", "category": "Regional"},
    {"name": "Kenaitze Indian Tribe", "url": "https://www.kenaitze.org/feed/atom", "category": "Native"},
    {"name": "Senior Voice Alaska", "url": "https://seniorvoicealaska.com/rss", "category": "Health"},
    {"name": "Alaska Magazine", "url": "https://www.alaskamagazine.com/feed", "category": "News"},
    # {"name": "Daily Sitka Sentinel", "url": "https://www.sitkasentinel.com/search/?f=rss&t=article&c=news&l=50&s=start_time&sd=desc", "category": "Regional"}, # 403 Forbidden
    {"name": "Ketchikan Daily News", "url": "https://ketchikandailynews.com/search/?f=rss&t=article&c=news&l=50&s=start_time&sd=desc", "category": "Regional"},
    # === PUBLIC RADIO — VERIFIED FEEDS ===
    {"name": "KRBD Ketchikan", "url": "https://www.krbd.org/feed", "category": "Radio"},
    {"name": "KDLG Dillingham", "url": "https://www.kdlg.org/news.rss", "category": "Radio"},
    {"name": "KNBA Anchorage", "url": "https://www.knba.org/news.rss", "category": "Radio"},
    {"name": "KSTK Wrangell", "url": "https://www.kstk.org/feed", "category": "Radio"},
    {"name": "KFSK Petersburg", "url": "https://www.kfsk.org/feed", "category": "Radio"},

    # === MUNI OF ANCHORAGE — SPECIFIC RSS ENDPOINTS ===
    # === FISHERY MANAGEMENT ===
    {"name": "North Pacific Fishery Mgmt Council", "url": "https://www.npfmc.org/feed/atom/", "category": "Fisheries"},  # trailing slash required — confirmed live 2026-03-27
    # === RCA & REGULATORY (VERIFIED) ===
    # === FEDERAL / COAST GUARD / AVIATION ===
    # === ALASKA STATE LEGISLATURE ===
    {"name": "Alaska Senate Majority", "url": "https://alaskasenate.org/feed/", "category": "Government"},
    # === SPECIALIZED REGIONAL (VERIFIED LIVE) ===
    {"name": "Homer Electric Association", "url": "https://www.homerelectric.com/feed", "category": "Infrastructure"},
    {"name": "Golden Valley Electric", "url": "https://www.gvea.com/news-releases_category/news/feed/", "category": "Infrastructure"},
    {"name": "Alaska Village Electric Coop", "url": "https://avec.org/feed", "category": "Infrastructure"},
    # === ENVIRONMENT & LAND ===
    {"name": "Cook Inletkeeper", "url": "https://inletkeeper.org/feed", "category": "Environment"},

    # === CORRECTIONS & JUSTICE ===
    # === HEALTH & EMERGENCY ===
    # ===================================================================
    # ALL 12 ANCSA REGIONAL NATIVE CORPORATIONS
    # ===================================================================

    # === SOUTHEAST ===
    # Sealaska Corporation → canonical entry above; removed duplicate
    {"name": "Sealaska Heritage Institute", "url": "https://www.sealaskaheritage.org/wp-json/wp/v2/posts?per_page=100", "category": "Native"},  # WP API: live 2026-03-27

    # === SOUTHCENTRAL ===
    {"name": "Cook Inlet Region Inc (CIRI)", "url": "https://www.ciri.com/feed", "category": "Native"},
    # Chugach Alaska Corporation → same URL as Chugach Alaska Corp above; removed duplicate
    # Ahtna Inc → canonical entry above; removed duplicate

    # === INTERIOR ===
    {"name": "Doyon Limited (dup)", "url": "https://doyon.com/wp-json/wp/v2/posts?per_page=100", "category": "Native"},  # WP API: live, dedup handled by hash

    # === NORTHWEST/ARCTIC ===
    # NANA Regional Corporation → canonical entry above; removed duplicate
    {"name": "Bering Straits Native Corp", "url": "https://www.beringstraits.com/feed", "category": "Native"},
    {"name": "Arctic Slope Regional Corp (ASRC)", "url": "https://www.asrc.com/feed", "category": "Native"},

    # === WESTERN/SOUTHWEST ===
    # Calista Corporation → canonical entry above; removed duplicate
    {"name": "Bristol Bay Native Corp (BBNC)", "url": "https://www.bbnc.net/wp-json/wp/v2/posts?per_page=100", "category": "Native"},  # WP API: live 2026-03-27

    # === SOUTHWEST/ALEUTIAN ===
    {"name": "The Aleut Corporation", "url": "https://www.aleutcorp.com/feed", "category": "Native"},
    {"name": "Koniag Inc", "url": "https://www.koniag.com/feed", "category": "Native"},

    # === ANCSA REGIONAL ASSOCIATION ===
    {"name": "ANCSA Regional Association", "url": "https://www.ancsaregional.com/feed", "category": "Native"},
    # ===================================================================
    # TRIBAL CONSORTIA & HEALTH CORPORATIONS
    # ===================================================================

    # === TRIBAL HEALTH NETWORKS ===
    {"name": "Southcentral Foundation (SCF)", "url": "https://www.southcentralfoundation.com/feed", "category": "Health"},
    {"name": "Yukon-Kuskokwim Health Corp (YKHC)", "url": "https://www.ykhc.org/feed", "category": "Health"},
    {"name": "Chugachmiut", "url": "https://www.chugachmiut.org/feed", "category": "Health"},
    {"name": "Copper River Native Assoc", "url": "https://www.crnative.org/feed", "category": "Health"},
    {"name": "Interior Regional Health Services", "url": "https://www.irhs.org/feed", "category": "Health"},
    # === TRIBAL POLITICAL ORGANIZATIONS ===
    {"name": "Central Council Tlingit Haida", "url": "https://www.ccthita.org/feed", "category": "Native"},
    {"name": "Assoc of Village Council Presidents (AVCP)", "url": "https://www.avcp.org/wp-json/wp/v2/posts?per_page=100", "category": "Native"},  # WP API: live 2026-03-27
    # Kenaitze Indian Tribe → canonical entry above (NEXT-50 section); removed duplicate
    {"name": "Sitka Tribe of Alaska", "url": "https://www.sitkatribe.org/feed", "category": "Native"},
    {"name": "Metlakatla Indian Community", "url": "https://www.metlakatla.com/feed", "category": "Native"},

    # === ALASKA NATIVE ADVOCACY & POLICY ===
    {"name": "Alaska Federation of Natives", "url": "https://www.nativefederation.org/feed/", "category": "Native"},
    {"name": "Kawerak Inc (Bering Strait)", "url": "https://www.kawerak.org/feed", "category": "Native"},
    {"name": "Rural Alaska Community Action (RurAL CAP)", "url": "https://www.ruralcap.com/feed", "category": "Native"},

    # === MUSIC & MEDIA ===
    {"name": "Indigefi", "url": "https://www.indigefi.org/feed/", "category": "Music & Media"},
    {"name": "The Alaska Music Podcast", "url": "https://feed.podbean.com/kurtriemann/feed.xml", "category": "Music & Media"},
    {"name": "Alaska Signal (Music)", "url": "https://alaskasignal.com/category/music/feed/", "category": "Music & Media"},
    # === NATIVE MEDIA & NEWS ===
    # Alaska Native News → canonical entry at top of FEEDS; removed duplicate
    # KNBA Native Radio Anchorage → same URL as KNBA Anchorage above; removed duplicate
    {"name": "Native News Online", "url": "https://www.nativenews.net/feed/", "category": "Native"},
    {"name": "KNOM Nome Indigenous Radio", "url": "https://www.knom.org/feed", "category": "Native"},
    {"name": "Indian Country Today Alaska", "url": "https://ictnews.org/tag/alaska/feed", "category": "Native"},
    {"name": "Native Voice One", "url": "https://www.nv1.org/feed", "category": "Native"},

    # === EDUCATION & CULTURAL ===
    # ===================================================================
    # GIRDWOOD & CHUGACH (HYPER-LOCAL)
    # ===================================================================

    # === AVALANCHE & SAFETY ===
    # Chugach National Forest Avalanche Info Center — covers Turnagain Pass,
    # Girdwood, Summit Lake, Seward/Lost Lake. Daily forecasts in winter season.
    {"name": "CNFAIC Avalanche Center", "url": "https://www.cnfaic.org/feed/", "category": "Emergency"},

    # === GIRDWOOD BOARD OF SUPERVISORS (MOA) ===
    # GBOS has no standalone RSS. Its agendas, minutes, and public notices are
    # published via muni.org — targeted by the "Muni Public Notices" entry above.
    # No additional entry needed; GBOS signals surface via MOA public notices feed.

    # === NEW NATIONAL/GLOBAL FEEDS (FILTERED FOR ALASKA) ===
    {"name": "Mining.com Global", "url": "https://www.mining.com/feed/", "category": "Mining", "filter_keyword": "alaska"},
    {"name": "USDA NASS News", "url": "https://www.nass.usda.gov/rss/news.xml", "category": "Agriculture", "filter_keyword": "alaska"},
    {"name": "USDA NASS Reports", "url": "https://www.nass.usda.gov/rss/reports.xml", "category": "Agriculture", "filter_keyword": "alaska"},

    # === ALASKA HIDDEN WARNING SIGNALS (DEEP CUTS) ===
    {"name": "Valdez Avalanche", "url": "https://www.alaskasnow.org/valdez/feed/", "category": "Emergency"},

    # ===================================================================
    # MANIFEST EXPANSION — VERIFIED LIVE (2026-03-27)
    # All URLs confirmed via 3-stage testing:
    #   Stage 1: Direct probe | Stage 2: Alternate URL sweep | Stage 3: HTML autodiscovery
    # ===================================================================
    {"name": "Alaska Wilderness League",    "url": "https://www.alaskawild.org/feed/",               "category": "Environment"},
    {"name": "KUAC Fairbanks",              "url": "https://kuac.org/feed",                        "category": "Radio"},
    {"name": "Copper River Native Assoc",   "url": "https://www.crnative.org/feed/",                  "category": "Native"},
    {"name": "Eklutna Inc",                 "url": "https://www.eklutna-nsn.gov/feed/",               "category": "Native"},
    {"name": "Aleut Community of St. Paul", "url": "https://www.aleut.com/news/feed/",                "category": "Native"},
    {"name": "Hatcher Pass Avalanche Ctr",  "url": "https://www.hpavalanche.org/feed/",               "category": "Emergency"},
    {"name": "Delta Wind",                  "url": "https://www.deltawindonline.com/search/?f=rss&t=article&l=50&s=start_time&sd=desc", "category": "Regional"},
    {"name": "Federal Court Alaska",        "url": "https://www.akd.uscourts.gov/rss.xml",            "category": "Government"},
    {"name": "DOT Alaska Aviation Safety",  "url": "https://dot.alaska.gov/aviation",                 "category": "Safety"},
    {"name": "KUCB Unalaska",               "url": "https://www.kucb.org/term/local-news/rss",          "category": "Radio"},  # Fixed 2026-03-27: index.rss is empty shell; /term/local-news/rss is LIVE
    {"name": "Alaska SeaLife Center Blog",  "url": "https://www.alaskasealife.org/science_blog_rss",  "category": "Science"},
    {"name": "KBBI Homer",                  "url": "https://www.kbbi.org/term/local-news/rss",          "category": "Radio"},  # Fixed 2026-03-27: index.rss is empty shell; /term/local-news/rss is LIVE
    {"name": "KYUK Bethel",                  "url": "https://www.kyuk.org/term/local-news/rss",          "category": "Radio"},  # Added 2026-03-27: index.rss empty shell; /term/local-news/rss LIVE
    {"name": "NWS Alaska Alerts (CAP)",     "url": "https://api.weather.gov/alerts/active.atom?area=AK", "category": "Emergency"},
    {"name": "Alaska DNR Statewide",        "url": "https://dnr.alaska.gov/rss.xml",                  "category": "Government"},

    {"name": "USGS AK Earthquakes",         "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.atom",  "category": "Emergency", "filter_keyword": "alaska"},  # LIVE 2026-03-27

    # ===================================================================
    # SYNTHETIC RSS — alaskaintel-rss-proxy Cloudflare Worker
    # Sources with no native RSS feed. Scraped & served as RSS 2.0 by
    # our own CF Worker at: alaskaintel-rss-proxy.workers.dev
    # TODO: Update base URL to custom domain after wrangler deploy
    # ===================================================================
    # Worker repo: ALASKAINTEL_AG-v101/alaskaintel-rss-proxy/
    # Deploy: cd alaskaintel-rss-proxy && wrangler deploy
    # ===================================================================

    # NOTE: Replace WORKER_BASE with your deployed worker hostname.
    # After deploy, update with: sed -i 's|WORKER_BASE|https://rss.alaskaintel.com|g' scripts/fetch_intel.py
    # ─────────────────────────────────────────────────────────────────

    {"name": "Muni Anchorage Mayor Press",    "url": "https://alaskaintel-rss-proxy.workers.dev/rss/muni-press",    "category": "Government"},
    {"name": "Muni Anchorage Public Notices", "url": "https://alaskaintel-rss-proxy.workers.dev/rss/muni-notices",  "category": "Government"},
    {"name": "AOGCC Oil Gas Commission",      "url": "https://alaskaintel-rss-proxy.workers.dev/rss/aogcc",         "category": "Energy"},
    {"name": "RCA Issued Orders",             "url": "https://alaskaintel-rss-proxy.workers.dev/rss/rca-orders",    "category": "Government"},
    {"name": "RCA Press Releases",            "url": "https://alaskaintel-rss-proxy.workers.dev/rss/rca-releases",  "category": "Government"},
    {"name": "Alaska DEC Spill Reports",      "url": "https://alaskaintel-rss-proxy.workers.dev/rss/dec-spills",    "category": "Environment"},
    {"name": "Alaska DEC Air Quality",        "url": "https://alaskaintel-rss-proxy.workers.dev/rss/dec-air",       "category": "Environment"},
    {"name": "Alaska DOT Aviation Safety",    "url": "https://alaskaintel-rss-proxy.workers.dev/rss/dot-aviation",  "category": "Safety"},
    {"name": "Alaska Marine Highway News",    "url": "https://alaskaintel-rss-proxy.workers.dev/rss/dot-amhs",      "category": "Government"},
    {"name": "Alaska Dept of Labor News",     "url": "https://alaskaintel-rss-proxy.workers.dev/rss/labor",         "category": "Economy"},
    {"name": "NOAA Fisheries Alaska",         "url": "https://alaskaintel-rss-proxy.workers.dev/rss/noaa-fisheries","category": "Fisheries"},
    {"name": "USACE Alaska District",         "url": "https://alaskaintel-rss-proxy.workers.dev/rss/usace",         "category": "Government"},
    {"name": "National Fire Center (NIFC)",   "url": "https://alaskaintel-rss-proxy.workers.dev/rss/nifc",          "category": "Emergency"},
    {"name": "Alaska Legislature News",       "url": "https://alaskaintel-rss-proxy.workers.dev/rss/legislature",   "category": "Government"},
    {"name": "Alaska Dept of Health News",    "url": "https://alaskaintel-rss-proxy.workers.dev/rss/healthdept",    "category": "Health"},
    {"name": "Alaska State Troopers (AST)",   "url": "https://alaskaintel-rss-proxy.workers.dev/rss/ast",           "category": "Safety"},

    # ===================================================================
    # MUNICIPAL PUBLIC SAFETY — NO NATIVE RSS (verified 2026-03-27)
    # Homer, Whittier, Seward, Kenai, MatSu, Fairbanks, Kodiak, Valdez,
    # Nome, Bethel all return 403/404 on all feed paths.
    # Routed through alaskaintel-rss-proxy CF Worker for synthetic ingestion.
    # TODO: Implement each route in alaskaintel-rss-proxy/src/index.ts
    # ===================================================================
    {"name": "Homer City PD/Fire Notices",    "url": "https://alaskaintel-rss-proxy.workers.dev/rss/homer-pd",       "category": "Safety"},
    {"name": "Seward City PD/Safety",         "url": "https://alaskaintel-rss-proxy.workers.dev/rss/seward-pd",      "category": "Safety"},
    {"name": "Whittier City Safety",          "url": "https://alaskaintel-rss-proxy.workers.dev/rss/whittier-pd",    "category": "Safety"},
    {"name": "Kenai City PD Notices",         "url": "https://alaskaintel-rss-proxy.workers.dev/rss/kenai-pd",       "category": "Safety"},
    {"name": "Kenai Peninsula Borough",       "url": "https://alaskaintel-rss-proxy.workers.dev/rss/kpb",            "category": "Government"},
    {"name": "MatSu Borough Emergency",       "url": "https://alaskaintel-rss-proxy.workers.dev/rss/matsu-safety",   "category": "Safety"},
    {"name": "Fairbanks PD / FNSB Safety",   "url": "https://alaskaintel-rss-proxy.workers.dev/rss/fairbanks-pd",   "category": "Safety"},
    {"name": "Kodiak City/Borough Safety",    "url": "https://alaskaintel-rss-proxy.workers.dev/rss/kodiak-pd",      "category": "Safety"},
    {"name": "Valdez City Safety",            "url": "https://alaskaintel-rss-proxy.workers.dev/rss/valdez-pd",      "category": "Safety"},
    {"name": "Nome City Safety",              "url": "https://alaskaintel-rss-proxy.workers.dev/rss/nome-pd",        "category": "Safety"},
    {"name": "Bethel City Safety",            "url": "https://alaskaintel-rss-proxy.workers.dev/rss/bethel-pd",      "category": "Safety"},
    {"name": "Anchorage Fire Dept",           "url": "https://alaskaintel-rss-proxy.workers.dev/rss/afd",            "category": "Safety"},
    {"name": "Sitka CBJ Safety",              "url": "https://alaskaintel-rss-proxy.workers.dev/rss/sitka-pd",       "category": "Safety"},
    {"name": "AK Emergency Management",       "url": "https://alaskaintel-rss-proxy.workers.dev/rss/hsem",           "category": "Emergency"},
    {"name": "AK State Fire Marshal",         "url": "https://alaskaintel-rss-proxy.workers.dev/rss/fire-marshal",   "category": "Safety"},
]


def generate_hash(title: str, link: str) -> str:
    """Generate a unique hash for deduplication."""
    unique_string = f"{title}|{link}"
    return hashlib.md5(unique_string.encode()).hexdigest()


def resolve_article_url(raw_title: str, raw_link: str) -> str:
    """Resolve tracker links to real article URLs when possible."""
    if "post_type=od_url_metrics" in raw_link and raw_title.startswith("http"):
        return raw_title.strip()
    return raw_link.strip()


def is_bad_rss_item(title: str, link: str, summary: str) -> bool:
    """Drop known bad feed items (tracker, payments, image uploads, embed payloads)."""
    link_l = link.lower()
    title_l = title.lower().strip()
    summary_l = (summary or "").lower()

    if not title_l and not summary_l:
        return True

    # WordPress/payment noise.
    if "post_type=give_payment" in link_l:
        return True

    # Image upload artifacts, not news articles.
    if "wp-content/uploads" in title_l and title_l.startswith("http"):
        return True
    if re.search(r"\.(jpg|jpeg|png|gif|webp)$", title_l):
        return True

    # Pure numeric titles are usually non-article metadata posts.
    if title.strip().isdigit() and len(summary.strip()) < 80:
        return True

    # Embedded widget/json payloads are malformed for reader UX.
    if re.search(r"\{\s*\"?url\"?\s*:", summary_l) or "islcp" in summary_l or "viewport" in summary_l:
        return True

    return False


def clean_text(raw: str) -> str:
    """Convert HTML-rich RSS text into plain normalized text."""
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_fair_use_snippet(text: str) -> str:
    """Create a fair-use-safe snippet: 10% of source text, but with a readable floor."""
    cleaned = clean_text(text)
    if not cleaned:
        return "Open article for full details at source."

    # Calculation logic:
    # 1. Start with 10% of the source text length
    ratio_limit = int(len(cleaned) * FAIR_USE_MAX_RATIO)
    
    # 2. Apply a "Smart Floor" (min 300 chars) to ensure it's readable,
    # but don't exceed the actual text length if it's shorter than 300.
    floor = min(300, len(cleaned))
    limit = max(floor, ratio_limit)
    
    # 3. Cap at the absolute MAX allowed
    limit = min(limit, FAIR_USE_MAX_CHARS)
    
    snippet = cleaned[:limit].rstrip()
    if len(cleaned) > limit:
        snippet += "..."
    return snippet


def infer_region(text: str) -> str:
    """Infer Alaska region from title/summary text when possible."""
    lower_text = text.lower()
    for region, keywords in REGION_KEYWORDS.items():
        if any(keyword in lower_text for keyword in keywords):
            return region
    return "Statewide"


def build_data_tag(category: str, title: str, summary: str) -> str:
    """Attach a lightweight transformative data tag for legal/UX context."""
    region = infer_region(f"{title} {summary}")
    return f"[Region: {region}] [Category: {category}]"


def fetch_feeds() -> List[Dict]:
    """Fetch all RSS feeds and return new aggregated data."""
    import argparse
    parser = argparse.ArgumentParser(description="Fetch AlaskaIntel RSS feeds.")
    parser.add_argument("--category", type=str, help="Comma-separated list of categories to fetch (e.g. Native,Safety)")
    parser.add_argument("--priority", type=str, help="Comma-separated list of priorities to fetch (e.g. high,medium,low)")
    # Since fetch_feeds is called by main(), we parse args from sys.argv
    args, unknown = parser.parse_known_args()
    
    target_categories = [c.strip().lower() for c in args.category.split(",")] if args.category else []
    target_priorities = [p.strip().lower() for p in args.priority.split(",")] if args.priority else []

    intel_data = []
    seen_hashes = set()
    
    # Load optional feed status (hold/stale) -- operator-maintained JSON
    hold = set()
    stale = set()
    try:
        if os.path.exists(FEED_STATUS_FILE):
            with open(FEED_STATUS_FILE, "r") as f:
                status = json.load(f)
                hold = set(status.get("hold", []))
                stale = set(status.get("stale", []))
    except Exception as e:
        print(f"Warning: could not read {FEED_STATUS_FILE}: {e}")

    # Determine default priority based on category if not explicitly set in the dict
    def get_feed_priority(feed_cat: str) -> str:
        cat = feed_cat.lower()
        if cat in ["safety", "emergency", "news", "weather", "maritime", "radio", "politics"]:
            return "high"
        if cat in ["native", "regional", "health", "fisheries"]:
            return "medium"
        return "low"

    # Filter out feeds on hold/stale, and optionally by category/priority
    feeds_to_fetch = []
    for f in FEEDS:
        if f["name"] in hold or f["name"] in stale:
            continue
            
        f_cat = f.get("category", "")
        f_pri = f.get("priority") or get_feed_priority(f_cat)
        
        # Apply strict filters if provided via CLI
        if target_categories and f_cat.lower() not in target_categories:
            continue
        if target_priorities and f_pri.lower() not in target_priorities:
            continue
            
        # Guarantee priority is set for logging/intervals later
        f["_computed_priority"] = f_pri.lower()
        feeds_to_fetch.append(f)

    print(f"Fetching {len(feeds_to_fetch)} feeds "
          f"(Category={args.category or 'ALL'}, Priority={args.priority or 'ALL'}, "
          f"hold={len(hold)}, stale={len(stale)})...")
          
    # Load feed scores and health to determine priority and next check
    scores_data = {}
    source_health = {}
    feed_last_seen = {}
    try:
        if os.path.exists('data/feed_scores.json'):
            with open('data/feed_scores.json', 'r') as f:
                scores_data = json.load(f)
        if os.path.exists('data/source_health.json'):
            with open('data/source_health.json', 'r') as f:
                source_health = json.load(f)
        if os.path.exists('data/feed_last_seen.json'):
            with open('data/feed_last_seen.json', 'r') as f:
                feed_last_seen = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load data files: {e}")
    
    now = datetime.now(timezone.utc)
    
    # Load existing data to avoid duplicates
    if os.path.exists('data/latest_intel.json'):
        try:
            with open('data/latest_intel.json', 'r') as f:
                existing_data = json.load(f)
                for item in existing_data:
                    if 'hash' in item:
                        seen_hashes.add(item['hash'])
        except Exception as e:
            print(f"Warning: Could not load existing data: {e}")
    
    lock = threading.Lock()

    def process_feed(i, feed):
        score_info = scores_data.get(feed['name'], {})
        next_check_str = score_info.get('next_check_due')
        priority = feed.get("_computed_priority", "medium")
        
        # Determine check interval (aligned with GitHub Actions Cron)
        intervals = {'high': 30, 'medium': 60, 'low': 360, 'zero-signal': 10080}
        interval_mins = intervals.get(priority, 30)
        
        # === SMART PRIORITY DECAY (1-100 Level) ===
        scan_priority = 100
        last_seen_str = feed_last_seen.get(feed['name'])
        if last_seen_str:
            try:
                last_seen_dt = datetime.fromisoformat(last_seen_str.replace('Z', '+00:00'))
                if last_seen_dt.tzinfo is None:
                    last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
                days_since = (now - last_seen_dt).days
                
                if days_since < 2:
                    scan_priority = 100
                elif days_since < 7:
                    scan_priority = 75
                    interval_mins = max(interval_mins, 120)  # At least 2 hours
                elif days_since < 30:
                    scan_priority = 50
                    interval_mins = max(interval_mins, 360)  # At least 6 hours
                else:
                    scan_priority = 25
                    interval_mins = max(interval_mins, 1440) # At least 24 hours
            except Exception:
                pass
        else:
            scan_priority = 10
            interval_mins = 2880 # 48 hours for never-seen
        
        if next_check_str:
            try:
                next_check = datetime.fromisoformat(next_check_str.replace('Z', '+00:00'))
                if next_check.tzinfo is None:
                    next_check = next_check.replace(tzinfo=timezone.utc)
                    
                if now < next_check:
                    print(f"[{i}/{len(feeds_to_fetch)}] Skipping: {feed['name']} (Due: {next_check.strftime('%H:%M')} UTC - {priority})")
                    return
            except Exception:
                pass
                
        print(f"[{i}/{len(feeds_to_fetch)}] Fetching: {feed['name']} ({priority} | Priority Score: {scan_priority}/100)...")
        
        # Grab previous etag and modified headers from score_info to save bandwidth
        old_etag = score_info.get('etag')
        old_modified = score_info.get('modified')
        
        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
        def fetch_feed_with_retry():
            headers = {'User-Agent': CHROME_UA}
            if old_etag: headers['If-None-Match'] = old_etag
            if old_modified: headers['If-Modified-Since'] = old_modified
            
            resp = requests.get(feed['url'], headers=headers, timeout=15, verify=False)
            
            class MockParsed:
                status: int = 304
                entries: list = []
                bozo: bool = False
                
            if resp.status_code == 304:
                return MockParsed()
                
            resp.raise_for_status()
            p = feedparser.parse(resp.content)
            
            # Reattach metadata for parser logic
            p.status = resp.status_code
            p.etag = resp.headers.get('ETag') or resp.headers.get('etag')
            p.modified = resp.headers.get('Last-Modified') or resp.headers.get('last-modified')
            
            return p

        try:
            # request using conditional headers and smart retries
            parsed = fetch_feed_with_retry()
            
            if hasattr(parsed, 'status') and parsed.status == 304:
                # 304 Not Modified means no changes since last fetch! Save CPU.
                print(f"  ⚡ 304 Not Modified for {feed['name']} (skipped parsing)")
                with lock:
                    score_info['next_check_due'] = (now + timedelta(minutes=interval_mins)).isoformat()
                    scores_data[feed['name']] = score_info
                    source_health[feed['name']] = {"last_checked": now.isoformat(), "status": "304 Cached", "entries": 0, "category": feed['category']}
                return
                
            if not parsed.entries:
                print(f"  ⚠️  No entries found for {feed['name']}")
                with lock:
                    stale.add(feed['name'])
                    source_health[feed['name']] = {"last_checked": now.isoformat(), "status": "Empty Feed", "entries": 0, "category": feed['category']}
                return
            
            local_items = []
            
            # Process all entries from each feed
            for entry in parsed.entries:
                raw_title = entry.get("title", "").strip()
                raw_link = entry.get("link", "").strip()
                raw_summary = entry.get("summary", "")

                if not raw_title or not raw_link:
                    continue

                # Resolve article URL and scrub junk posts before dedupe.
                link = resolve_article_url(raw_title, raw_link)
                title = raw_title
                if is_bad_rss_item(title, link, raw_summary):
                    continue

                # NWS Alert Smart Filtering: remove "noise" that most people just read over
                if "NWS" in feed['name'] or "Weather" in feed['name']:
                    combined_nws = (title + " " + raw_summary).lower()
                    if "special weather statement" in combined_nws or "minor" in combined_nws or "small craft advisory" in combined_nws or "dense fog" in combined_nws:
                        continue
                
                # Standardized filter content
                combined_text_for_filter = (title + " " + raw_summary).lower()

                # Basic keyword filter
                filter_kw = feed.get("filter_keyword")
                if filter_kw:
                    # Skip if the target keyword is not found anywhere in the title or summary
                    if filter_kw.lower() not in combined_text_for_filter:
                        continue
                
                # Generate hash for deduplication
                item_hash = generate_hash(title, link)
                
                with lock:
                    # Skip if we've already seen this item
                    if item_hash in seen_hashes:
                        continue
                    seen_hashes.add(item_hash)
                
                # Extract image from RSS feed (multiple possible locations)
                image_url = None
                
                # Try media:thumbnail (common in WordPress feeds)
                if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                    image_url = entry.media_thumbnail[0].get('url') if isinstance(entry.media_thumbnail, list) else entry.media_thumbnail.get('url')
                
                # Try media:content
                if not image_url and hasattr(entry, 'media_content') and entry.media_content:
                    media = entry.media_content[0] if isinstance(entry.media_content, list) else entry.media_content
                    if media.get('medium') == 'image' or media.get('type', '').startswith('image/'):
                        image_url = media.get('url')
                
                # Try enclosures (common for images/podcasts)
                if not image_url and hasattr(entry, 'enclosures') and entry.enclosures:
                    for enclosure in entry.enclosures:
                        if enclosure.get('type', '').startswith('image/'):
                            image_url = enclosure.get('href') or enclosure.get('url')
                            break
                
                # Try content/description for og:image or img tags
                if not image_url:
                    content = entry.get('content', [{}])[0].get('value', '') if entry.get('content') else entry.get('description', '')
                    if content:
                        # Look for og:image
                        og_match = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\'\']+)', content)
                        if og_match:
                            image_url = og_match.group(1)
                        # Look for first img tag
                        elif not image_url:
                            img_match = re.search(r'<img[^>]+src=["\']([^"\'\']+)', content)
                            if img_match:
                                image_url = img_match.group(1)
                
                # === HAWAII VOLCANO / EARTHQUAKE FILTER ===
                # USGS and other federal feeds often leak Hawaiian data into the ALASKA feeds
                if "hawaii" in combined_text_for_filter or "hvo " in combined_text_for_filter or "kilauea" in combined_text_for_filter or "mauna" in combined_text_for_filter:
                    continue

                published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                published_iso = None
                
                if published_struct:
                    published_iso = datetime(*published_struct[:6], tzinfo=timezone.utc).isoformat()
                else:
                    # Attempt regex extraction of timestamp from summary if missing (Common in USGS / Earthquake feeds)
                    # e.g., "Mar 10, 2026 22:17" or "2026-03-10 22:17:00"
                    date_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\s+\d{2}:\d{2}', raw_summary)
                    if date_match:
                        try:
                            parsed_date = datetime.strptime(date_match.group(0), "%b %d, %Y %H:%M")
                            published_iso = parsed_date.replace(tzinfo=timezone.utc).isoformat()
                        except Exception:
                            pass
                    
                    # === SECONDARY DOMAIN DATE EXTRACTION ===
                    # Attempt to extract precise historical dates routed inside the external URL path.
                    # Ex: /releases/3-30-22 Bing's Landing... -> 2022-03-30
                    if not published_iso:
                        url_date_match = re.search(r'(?:/| |^)(\d{1,2})[-._/](\d{1,2})[-._/](\d{2,4})\b', entry.get('link', '') + ' ' + title)
                        if url_date_match:
                            try:
                                m, d, y = url_date_match.groups()
                                if len(y) == 2:
                                    # Normalize YY to YYYY
                                    y = "20" + y
                                parsed_date = datetime(int(y), int(m), int(d))
                                published_iso = parsed_date.replace(tzinfo=timezone.utc).isoformat()
                            except Exception:
                                pass

                    if not published_iso:
                        # For AST/DPS sources, scrape_ast.py owns the timestamps — skip
                        if feed['name'] in ('Alaska State Troopers', 'Alaska DPS'):
                            continue
                        
                        # Apply an extreme 24-hour safeguard before dumping a live generic timestamp 
                        published_iso = datetime.now(timezone.utc).isoformat()
                # Prefer full content over summary for better 10% snippets
                full_content = ""
                if entry.get('content'):
                    full_content = entry.get('content')[0].get('value', '')
                elif entry.get('description'):
                    full_content = entry.get('description', '')
                
                snippet_base = full_content or raw_summary

                summary_text = build_fair_use_snippet(snippet_base)
                category = feed['category']
                impact = score_signal({"title": title, "summary": summary_text}, category)
                region = infer_region_typed(title, summary_text)
                sector = infer_sector(category)
                urgency = infer_urgency(impact)
                entities = resolve_entities(title, summary_text)

                item = {
                    "hash": item_hash,
                    "source": feed['name'],
                    "category": category,
                    "title": title,
                    "link": link,
                    "published": entry.get("published", ""),
                    "summary": summary_text,
                    "dataTag": build_data_tag(category, title, snippet_base),
                    "sourceAttribution": f"Source: {feed['name']}",
                    "imageUrl": image_url,
                    "timestamp": published_iso,
                    # === SIGNAL ENGINE FIELDS ===
                    "impactScore":  impact,
                    "region":       region,
                    "sector":       sector,
                    "urgency":      urgency,
                    "entitySlugs": entities,
                }
                
                # Geocode signal to exact Lat/Lon when possible
                coords = geocode_text(f"{title} {summary_text}")

                # Secondary pass for APD: if we only got the generic Anchorage centroid,
                # try the Anchorage street-grid geocoder for block-level accuracy.
                if feed['name'] == 'Anchorage Police Dept' and (
                    coords is None or coords == ANCHORAGE_CENTROID
                ):
                    apd_coords = geocode_anchorage_address(f"{title} {summary_text}")
                    if apd_coords:
                        coords = apd_coords

                if coords:
                    item['lat'] = coords[0]
                    item['lng'] = coords[1]

                local_items.append(item)
            
            with lock:
                intel_data.extend(local_items)
                # After fetch, update next_check_due
                score_info['next_check_due'] = (now + timedelta(minutes=interval_mins)).isoformat()
                
                # Save caching headers for next run
                if hasattr(parsed, 'etag') and parsed.etag:
                    score_info['etag'] = parsed.etag
                if hasattr(parsed, 'modified') and parsed.modified:
                    score_info['modified'] = parsed.modified
                    
                scores_data[feed['name']] = score_info
                
                entries_fetched = len(parsed.entries)
                
                # Check for dormant feeds (last seen > 30 days ago)
                now_iso = now.isoformat()
                if len(local_items) > 0:
                    feed_last_seen[feed['name']] = now_iso
                
                status_str = "OK"
                last_seen_str = feed_last_seen.get(feed['name'])
                if last_seen_str:
                    try:
                        last_seen_dt = datetime.fromisoformat(last_seen_str.replace('Z', '+00:00'))
                        if (now - last_seen_dt).days > 365:
                            status_str = "DORMANT"
                    except Exception:
                        pass
                else:
                    status_str = "DORMANT" # No valid signals ever seen

                source_health[feed['name']] = {"last_checked": now_iso, "status": status_str, "entries": entries_fetched, "category": feed['category']}
                
            print(f"  ✓ Retrieved {entries_fetched} entries for {feed['name']}")
            
        except Exception as e:
            with lock:
                # ===== AUTO-RETIREMENT: Failure Streak Tracking =====
                streak = score_info.get("fail_streak", 0) + 1
                score_info["fail_streak"] = streak

                if streak >= 20:
                    # RETIRED: auto-add to stale list — stops being fetched
                    stale.add(feed["name"])
                    backoff = 10080  # 1 week — check again next full-harvest cycle
                    status_tag = f"RETIRED (streak {streak}) — {str(e)[:40]}"
                    print(f"  💀 AUTO-RETIRED {feed['name']} after {streak} consecutive failures")
                elif streak >= 5:
                    backoff = 120  # 2-hour backoff — probation
                    status_tag = f"PROBATION (streak {streak}) — {str(e)[:40]}"
                    print(f"  ⚠️  PROBATION {feed['name']} (streak {streak}): {str(e)}")
                else:
                    backoff = 60   # Standard 1-hour backoff
                    status_tag = f"Error: {str(e)[:50]}"
                    print(f"  ✗ Error fetching {feed['name']}: {str(e)}")

                score_info["next_check_due"] = (now + timedelta(minutes=backoff)).isoformat()
                scores_data[feed["name"]] = score_info
                source_health[feed["name"]] = {
                    "last_checked": now.isoformat(),
                    "status": status_tag,
                    "entries": 0,
                    "category": feed["category"],
                    "fail_streak": streak,
                }


    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(process_feed, i, feed) for i, feed in enumerate(feeds_to_fetch, 1)]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Worker thread exception: {e}")
    
    # Persist any changes to feed status (holds left intact, new stales added)
    try:
        os.makedirs(os.path.dirname(FEED_STATUS_FILE), exist_ok=True)
        with open(FEED_STATUS_FILE, "w") as f:
            json.dump({"hold": sorted(list(hold)), "stale": sorted(list(stale))}, f, indent=2)
    except Exception as e:
        print(f"Warning: could not write feed status file: {e}")
        
    # Save updated next_check_due
    try:
        os.makedirs('data', exist_ok=True)
        with open('data/feed_scores.json', 'w') as f:
            json.dump(scores_data, f, indent=2)
    except Exception as e:
        print(f"Warning: could not write feed scores file: {e}")
        
    # Save source health rollcall
    try:
        with open('data/source_health.json', 'w') as f:
            json.dump(source_health, f, indent=2)
    except Exception as e:
        print(f"Warning: could not write source health log: {e}")

    # Save feed_last_seen
    try:
        with open('data/feed_last_seen.json', 'w') as f:
            json.dump(feed_last_seen, f, indent=2)
    except Exception as e:
        print(f"Warning: could not write feed_last_seen log: {e}")

    return intel_data


# ===================================================================
# SIGNAL ENGINE — SCORING, TAGGING & LINKING
# ===================================================================

CATEGORY_TO_SECTOR = {
    "Health": "health",
    "Fisheries": "fisheries",
    "Energy": "energy",
    "Mining": "energy",
    "Emergency": "safety",
    "Safety": "safety",
    "Government": "governance",
    "Legal": "governance",
    "Politics": "governance",
    "Native": "native-affairs",
    "Environment": "environment",
    "Wildlife": "environment",
    "Climate": "environment",
    "Transportation": "transportation",
    "Maritime": "transportation",
    "Research": "research",
    "Science": "research",
    "Economy": "economy",
    "Business": "economy",
    "Labor": "economy",
    "Fisheries": "fisheries",
    "Agriculture": "subsistence",
    "Recreation": "subsistence",
    "Education": "research",
    "Social": "governance",
    "Industry": "energy",
    "Parks": "environment",
    "Forest": "environment",
    "Radio": "governance",
    "Regional": "governance",
    "News": "governance",
}

ENTITY_KEYWORDS: Dict[str, List[str]] = {
    "ykhc":     ["ykhc", "yukon-kuskokwim health"],
    "avcp":     ["avcp", "association of village council"],
    "ciri":     ["ciri", "cook inlet region"],
    "anthc":    ["anthc", "alaska native tribal health"],
    "searhc":   ["searhc", "southeast alaska regional health"],
    "asrc":     ["asrc", "arctic slope regional"],
    "doyon":    ["doyon"],
    "sealaska": ["sealaska"],
    "bbnc":     ["bbnc", "bristol bay native"],
    "calista":  ["calista"],
    "adfg":     ["adf&g", "fish and game", "adfg"],
    "nws":      ["national weather service", "nws anchorage", "nws fairbanks", "nws juneau"],
    "blm":      ["bureau of land management", "blm alaska"],
    "tanana":   ["tanana chiefs"],
    "maniilaq": ["maniilaq"],
    "norton":   ["norton sound health"],
    "kana":     ["kodiak area native", "kana"],
    "bbahc":    ["bristol bay area health", "bbahc"],
    "nana":     ["nana regional", "nana corporation"],
}


def score_signal(item: Dict, category: str) -> int:
    """Compute an impact score (1–100) for a signal based on category and keywords."""
    score = 30  # baseline
    title_l = item.get("title", "").lower()
    summary_l = item.get("summary", "").lower()
    text = f"{title_l} {summary_l}"

    # === VADER SENTIMENT & THREAT ANALYSIS ===
    try:
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        sia = SentimentIntensityAnalyzer()
        sentiment = sia.polarity_scores(text)
        if sentiment['neg'] > 0.15:
            score += 25
        elif sentiment['neg'] > 0.05:
            score += 10
        if sentiment['pos'] > 0.2 and category not in ("Economy", "Business"):
            score -= 10
    except Exception:
        pass

    # === EMERGENCY / SAFETY ===
    if category in ("Emergency", "Safety"):
        score += 40
    if any(w in text for w in ["tsunami", "earthquake", "eruption", "wildfire", "evacuation", "amber alert"]):
        score += 35
    if any(w in text for w in ["advisory", "warning", "alert", "closure", "emergency order", "declaration"]):
        score += 25

    # === HEALTH ===
    if category == "Health":
        score += 20
    if any(w in text for w in ["outbreak", "health advisory", "disease", "vaccination", "epidemic"]):
        score += 20

    # === FISHERIES ===
    if category == "Fisheries":
        score += 18
    if any(w in text for w in ["emergency order", "escapement", "run strength", "opener", "fishery closure"]):
        score += 20

    # === GOVERNANCE / POLICY ===
    if category in ("Government", "Legal", "Politics"):
        score += 10
    if any(w in text for w in ["executive order", "legislation", "passed", "signed", "budget", "lawsuit", "ruling"]):
        score += 15

    # === NATIVE / TRIBAL ===
    if category == "Native":
        score += 8
    if any(w in text for w in ["ancsa", "subsistence", "tribal sovereignty", "land rights", "tribal compact"]):
        score += 12

    # === ENERGY ===
    if category in ("Energy", "Mining"):
        score += 10
    if any(w in text for w in ["spill", "pipeline", "permit", "project approval", "drilling"]):
        score += 15

    # === SCIENCE / RESEARCH ===
    if category in ("Science", "Research"):
        score += 5

    # === BACKGROUND / LOW SIGNAL ===
    if category in ("Recreation", "Social", "Agriculture"):
        score -= 10

    return max(10, min(100, score))


def infer_sector(category: str) -> str:
    """Map RSS category to a Sector type."""
    return CATEGORY_TO_SECTOR.get(category, "governance")


def infer_urgency(impact_score: int) -> str:
    """Map impact score to urgency level."""
    if impact_score >= 80:
        return "now"
    if impact_score >= 50:
        return "soon"
    return "background"


def infer_region_typed(title: str, summary: str) -> str:
    """Infer region using the canonical Region type values."""
    text = f"{title} {summary}".lower()
    region_map = {
        "Yukon-Kuskokwim": ["bethel", "kuskokwim", "yukon", "yk delta", "ykhc", "avcp", "calista", "kwethluk", "aniak"],
        "North Slope":     ["utqiagvik", "barrow", "north slope", "kotzebue", "prudhoe", "asrc", "arctic slope"],
        "Cook Inlet":      ["anchorage", "kenai", "soldotna", "homer", "cook inlet", "ciri"],
        "Southeast":       ["juneau", "sitka", "ketchikan", "petersburg", "wrangell", "skagway", "haines", "sealaska", "ccthita", "searhc"],
        "Interior":        ["fairbanks", "delta", "tok", "north pole", "doyon", "tanana chiefs"],
        "Mat-Su":          ["mat-su", "matanuska", "susitna", "wasilla", "palmer"],
        "Southwest":       ["dillingham", "bristol bay", "bbnc", "bbahc", "king salmon"],
        "Gulf Coast":      ["kodiak", "valdez", "seward", "cordova", "prince william sound", "kana"],
        "Southcentral":    ["muldoon", "eagle river", "girdwood", "whittier", "anthc", "southcentral foundation"],
    }
    for region, keywords in region_map.items():
        if any(kw in text for kw in keywords):
            return region
    return "Statewide"


def resolve_entities(title: str, summary: str) -> List[str]:
    """Return list of entity slugs mentioned in the signal."""
    text = f"{title} {summary}".lower()
    return [slug for slug, kws in ENTITY_KEYWORDS.items() if any(kw in text for kw in kws)]


def build_related_signals(intel_data: List[Dict]) -> List[Dict]:
    """Post-processing pass: link signals using TF-IDF text similarity, region + sector, and entities."""
    
    # Pre-compute TF-IDF Matrix for all intelligence items
    similarity_matrix = None
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        
        texts = [f"{item.get('title', '')} {item.get('summary', '')}" for item in intel_data]
        if len(texts) > 0:
            vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
            tfidf_matrix = vectorizer.fit_transform(texts)
            similarity_matrix = cosine_similarity(tfidf_matrix)
    except Exception as e:
        print(f"Warning: TF-IDF failed, falling back to basic matching: {e}")

    for i, item in enumerate(intel_data):
        related = []
        item_ts_str = item.get("timestamp", "")
        item_region = item.get("region", "")
        item_sector = item.get("sector", "")
        item_entities = set(item.get("entitySlugs", []))
        try:
            item_ts = datetime.fromisoformat(item_ts_str.replace("Z", "+00:00"))
        except Exception:
            item_ts = None

        for j, other in enumerate(intel_data):
            if i == j:
                continue
            if other.get("hash") == item.get("hash"):
                continue
                
            # --- TF-IDF Story Clustering ---
            if similarity_matrix is not None:
                sim_score = similarity_matrix[i][j]
                if sim_score > 0.35:  # Strong textual corroboration
                    # Boost urgency dynamically due to corroborated megathread
                    item['impactScore'] = min(100, item.get('impactScore', 30) + 10)
                    related.append(other["hash"])
                    continue

            # Time proximity check
            if item_ts:
                try:
                    other_ts = datetime.fromisoformat(other.get("timestamp", "").replace("Z", "+00:00"))
                    dt_diff = abs((item_ts - other_ts).total_seconds())
                except Exception:
                    dt_diff = float("inf")
            else:
                dt_diff = float("inf")

            # Same region + sector, within 48 hours
            same_region = item_region and item_region == other.get("region")
            same_sector = item_sector and item_sector == other.get("sector")
            if same_region and same_sector and dt_diff < 172800:
                related.append(other["hash"])
                continue

            # Shared entity
            other_entities = set(other.get("entitySlugs", []))
            if item_entities & other_entities:
                related.append(other["hash"])

        # De-dup, limit to top 5
        item["relatedSignalIds"] = list(dict.fromkeys(related))[:5]

    return intel_data


def build_pulse_indices(intel_data: List[Dict]) -> Dict:
    """Compute 3 composite Signal Pulse Indices from recent signals."""
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)

    def avg_score(sectors: List[str]) -> int:
        scores = [
            item.get("impactScore", 30)
            for item in intel_data
            if item.get("sector") in sectors
            and _ts_within(item.get("timestamp", ""), cutoff_7d)
        ]
        return int(sum(scores) / len(scores)) if scores else 0

    def _ts_within(ts_str: str, cutoff: datetime) -> bool:
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return ts >= cutoff
        except Exception:
            return False

    def trend_label(score: int) -> str:
        if score >= 70: return "elevated"
        if score >= 45: return "normal"
        return "low"

    health_score = avg_score(["health", "safety"])
    subsistence_score = avg_score(["fisheries", "subsistence"])
    economic_score = avg_score(["economy", "energy"])

    return {
        "updated": now.isoformat(),
        "alaskaHealthIndex":        {"score": health_score,      "label": trend_label(health_score)},
        "subsistencePressureIndex": {"score": subsistence_score, "label": trend_label(subsistence_score)},
        "economicActivityIndex":    {"score": economic_score,    "label": trend_label(economic_score)},
    }


def save_data(new_data: List[Dict]):
    """Save aggregated data to JSON file, merging with existing history."""
    os.makedirs('data', exist_ok=True)
    existing_data: List[Dict] = []
    
    if os.path.exists('data/latest_intel.json'):
        try:
            with open('data/latest_intel.json', 'r') as f:
                existing_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load existing intel history: {e}")

    # Merge and deduplicate by hash
    merged_by_hash: Dict[str, Dict] = {}
    for item in existing_data + new_data:
        item_hash = item.get('hash')
        if item_hash:
            merged_by_hash[item_hash] = item

    # Hygiene pass: purge legacy junk and normalize links for all history.
    cleaned_data: List[Dict] = []
    for item in merged_by_hash.values():
        title = item.get('title', '')
        link = resolve_article_url(title, item.get('link', ''))
        summary = item.get('summary', '')
        source = item.get('source', 'Unknown')
        category = item.get('category', 'Unknown')

        if not link.startswith('http'):
            continue

        if is_bad_rss_item(title, link, summary):
            continue

        item['link'] = link
        item['summary'] = build_fair_use_snippet(summary)
        item['dataTag'] = item.get('dataTag') or build_data_tag(
            category,
            title,
            summary,
        )
        item['sourceAttribution'] = item.get('sourceAttribution') or f"Source: {source}"
        cleaned_data.append(item)

    data = cleaned_data

    # === SIGNAL ENGINE: cross-link related signals ===
    print("🔗 Building related signal links...")
    data = build_related_signals(data)
    
    # === SIGNAL ENGINE: incident deduplication (Feature 2) ===
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from group_intel import group_signals
        print("🌍 Deduplicating overlapping signals (Incident Clustering)...")
        data = group_signals(data)
    except Exception as e:
        print(f"Warning: Signal deduplication failed: {e}")
    
    # Build historical archives grouped by YYYY/MM to prevent infinite JSON scaling
    monthly_archives = {}
    
    for item in data:
        dt = item.get('timestamp')
        if not dt: continue
        # Extract YYYY/MM
        match = re.search(r'^(\d{4})-(\d{2})', dt)
        if match:
            year, month = match.groups()
            key = f"{year}/{month}"
            if key not in monthly_archives:
                monthly_archives[key] = []
            monthly_archives[key].append(item)
            
    # Save the paginated archives into the public/ directory for React to fetch
    os.makedirs('public/archive', exist_ok=True)
    manifest = []
    
    for key, items in monthly_archives.items():
        year, month = key.split('/')
        os.makedirs(f'public/archive/{year}', exist_ok=True)
        archive_path = f'public/archive/{year}/{month}.json'
        
        # Load existing archive to prevent data loss over months
        existing_archive = []
        if os.path.exists(archive_path):
            try:
                with open(archive_path, 'r') as af:
                    existing_archive = json.load(af)
            except Exception:
                pass
                
        # Merge and deduplicate
        archive_dict = {x.get('hash') or x.get('id'): x for x in existing_archive if (x.get('hash') or x.get('id'))}
        for x in items:
            key = x.get('hash') or x.get('id')
            if key:
                archive_dict[key] = x
            
        merged_items = sorted(list(archive_dict.values()), key=lambda x: x.get('timestamp', ''), reverse=True)
        
        with open(archive_path, 'w') as af:
            json.dump(merged_items, af, indent=2)
            
        manifest.append(key)
        
    with open('public/archive/manifest.json', 'w') as mf:
        json.dump(sorted(list(set(manifest)), reverse=True), mf, indent=2)
        
        
    # Strictly Cap latest_intel.json to a 365-Day rolling window for blazing fast UI loads
    now = datetime.now()
    if now.tzinfo is None:
        now = now.astimezone()
    cutoff_30d = now - timedelta(days=60)
    
    recent_signals = []
    for item in data:
        dt_str = item.get('timestamp')
        if dt_str:
            try:
                ts = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                if ts >= cutoff_30d:
                    recent_signals.append(item)
            except Exception:
                pass
                
    recent_signals.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    with open('data/latest_intel.json', 'w') as f:
        json.dump(recent_signals, f, indent=2)

    # === SIGNAL ENGINE: write pulse indices ===
    try:
        os.makedirs('public', exist_ok=True)
        pulse = build_pulse_indices(recent_signals)
        with open('public/pulse_indices.json', 'w') as pf:
            json.dump(pulse, pf, indent=2)
        print(f"📡 Pulse indices written (Health:{pulse['alaskaHealthIndex']['score']} "
              f"Subsistence:{pulse['subsistencePressureIndex']['score']} "
              f"Economic:{pulse['economicActivityIndex']['score']})")
    except Exception as e:
        print(f"Warning: could not write pulse indices: {e}")

    # Also create a summary file
    summary = {
        "last_updated": datetime.now().isoformat(),
        "newest_signal": data[0].get('timestamp', datetime.now().isoformat()) if data else datetime.now().isoformat(),
        "total_items": len(data),
        "categories": {},
        "sources": {}
    }
    
    for item in data:
        category = item.get('category', 'Unknown')
        source = item.get('source', 'Unknown')
        
        summary['categories'][category] = summary['categories'].get(category, 0) + 1
        summary['sources'][source] = summary['sources'].get(source, 0) + 1
    
    with open('data/intel_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)


def archive_daily_snapshot():
    """Save one snapshot per calendar day and prune archives older than ARCHIVE_RETENTION_DAYS."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_path = os.path.join(ARCHIVE_DIR, f"{today_str}.json")
    latest_path = os.path.join("data", "latest_intel.json")

    # Only write today's archive once (first run of the day)
    if not os.path.exists(archive_path) and os.path.exists(latest_path):
        shutil.copy2(latest_path, archive_path)
        print(f"✓ Daily archive saved: {archive_path}")
    else:
        print(f"  Archive for {today_str} already exists, skipping")

    # Prune old archives
    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_RETENTION_DAYS)
    pruned = 0
    for path in glob.glob(os.path.join(ARCHIVE_DIR, "*.json")):
        filename = os.path.basename(path)
        try:
            file_date = datetime.strptime(filename.replace(".json", ""), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if file_date < cutoff:
                os.remove(path)
                pruned += 1
        except ValueError:
            continue
    if pruned:
        print(f"✓ Pruned {pruned} archive(s) older than {ARCHIVE_RETENTION_DAYS} days")


def generate_news_sitemap(data: List[Dict]):
    """Generate a Google News compatible XML sitemap from the latest data."""
    now = datetime.now(timezone.utc)
    two_days_ago = now - timedelta(days=2)
    
    # Filter for items from last 2 days
    news_items = []
    for item in data:
        try:
            # Reformat timestamp if needed, but fetch_intel stores ISO
            ts_str = item.get('timestamp', '')
            if not ts_str: continue
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            if ts > two_days_ago:
                news_items.append(item)
        except Exception as e:
            continue
            
    # Limit to 1000 items as per Google specs
    news_items = news_items[:1000]
    
    # Register namespace for clean prefixing
    ET.register_namespace('news', 'http://www.google.com/schemas/sitemap-news/0.9')
    
    # XML Construction
    root = ET.Element("urlset")
    root.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")
    # ET.register_namespace will handle xmlns:news automatically
    
    for item in news_items:
        url_el = ET.SubElement(root, "url")
        loc = ET.SubElement(url_el, "loc")
        loc.text = item.get('link', '')
        
        news_el = ET.SubElement(url_el, "{http://www.google.com/schemas/sitemap-news/0.9}news")
        
        pub_el = ET.SubElement(news_el, "{http://www.google.com/schemas/sitemap-news/0.9}publication")
        name_el = ET.SubElement(pub_el, "{http://www.google.com/schemas/sitemap-news/0.9}name")
        name_el.text = item.get('source', 'Alaska Intel')
        lang_el = ET.SubElement(pub_el, "{http://www.google.com/schemas/sitemap-news/0.9}language")
        lang_el.text = "en"
        
        date_el = ET.SubElement(news_el, "{http://www.google.com/schemas/sitemap-news/0.9}publication_date")
        date_el.text = item.get('timestamp', '')
        
        title_el = ET.SubElement(news_el, "{http://www.google.com/schemas/sitemap-news/0.9}title")
        title_el.text = item.get('title', '')

    # Write to public/sitemap-news.xml
    xml_str = ET.tostring(root, encoding='utf-8', method='xml')
    reparsed = minidom.parseString(xml_str)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    
    os.makedirs('public', exist_ok=True)
    with open('public/sitemap-news.xml', 'w') as f:
        f.write(pretty_xml)
    print(f"✓ News Sitemap generated: public/sitemap-news.xml ({len(news_items)} items)")


def main():
    """Main execution function."""
    print("=" * 60)
    print("Alaska Intel Aggregator")
    print("=" * 60)
    
    new_intel = fetch_feeds()
    
    print("\n" + "=" * 60)
    print(f"Successfully scraped {len(new_intel)} new intel items")
    print("=" * 60)
    
    save_data(new_intel)
    
    # Inject recent AST Trooper dispatch logs into the main feed
    # This makes "Alaska State Troopers" appear as a filterable source on the homepage
    ast_path = 'data/ast_logs.json'
    if os.path.exists(ast_path):
        try:
            with open(ast_path, 'r') as af:
                ast_logs = json.load(af)
            with open('data/latest_intel.json', 'r') as f:
                current_feed = json.load(f)
            
            now = datetime.now()
            cutoff = now - timedelta(days=3650)
            existing_hashes = {item.get('hash') for item in current_feed}
            
            injected = 0
            updated_ts = 0
            # Build a lookup of existing feed items by hash for fast update
            feed_by_hash = {item.get('hash'): item for item in current_feed if item.get('hash')}
            for item in ast_logs:
                ts_str = item.get('timestamp', '')
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).replace(tzinfo=None)
                    if ts < cutoff:
                        continue
                except Exception:
                    continue
                h = item.get('hash')
                if not h:
                    continue
                # Ensure all required SignalCard fields are present
                item.setdefault('sourceUrl', 'https://dailydispatch.dps.alaska.gov')
                item.setdefault('articleUrl', item.get('link', 'https://dailydispatch.dps.alaska.gov'))
                item.setdefault('topic', item.get('incident_type', 'Law Enforcement'))
                item.setdefault('section', 'Safety')
                item.setdefault('sourceLean', 'neutral')
                item.setdefault('category', 'Safety')
                if h in feed_by_hash:
                    # Always overwrite the timestamp with the DPS-sourced posted_ts
                    # so AST items never display the crawl time ("Just now").
                    existing = feed_by_hash[h]
                    if existing.get('timestamp') != item.get('timestamp'):
                        existing['timestamp'] = item['timestamp']
                        existing['posted'] = item.get('posted', existing.get('posted', ''))
                        updated_ts += 1
                else:
                    current_feed.append(item)
                    feed_by_hash[h] = item
                    existing_hashes.add(h)
                    injected += 1
            
            if injected > 0 or updated_ts > 0:
                current_feed.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                with open('data/latest_intel.json', 'w') as f:
                    json.dump(current_feed, f, indent=2)
                print(f"✓ Injected {injected} new + updated {updated_ts} AST timestamps in main feed")
        except Exception as e:
            print(f"Warning: Could not merge AST logs: {e}")

    # === NEW: Inject custom scrapers (Global Map Layers) ===
    global_layers = [
        ('data/usace_notices.json', 'USACE Alaska District'),
        ('data/dec_spills.json', 'Alaska DEC Spills'),
        ('data/afs_fires.json', 'AFS Fires'), 
        ('data/ua_grants.json', 'UA Grants'), 
        ('data/muni_notices.json', 'Anchorage Municipality'),
        ('data/511ak.json', 'Alaska 511 Traffic'),
        ('data/earthquakes.json', 'USGS Earthquakes'),
        ('data/wildfires.json', 'Active Wildfires'),
        ('data/weather.json', 'NWS Weather Alerts'),
        ('data/aviation.json', 'Aviation Incidents'),
        ('data/fisheries.json', 'Alaska Fisheries'),
        ('data/asd_news.json', 'Anchorage School District'),
        ('data/ua_news.json', 'University of Alaska System'),
        ('data/k12_districts.json', 'Alaska K-12 Districts')
    ]
    
    for scraper_file, name in global_layers:
        try:
            if os.path.exists(scraper_file):
                with open(scraper_file, 'r') as sf:
                    scraper_data = json.load(sf)
                
                items_to_inject = []
                
                # Flatten the data based on known schemas
                if isinstance(scraper_data, list):
                    items_to_inject = scraper_data
                elif isinstance(scraper_data, dict):
                    if "features" in scraper_data and isinstance(scraper_data["features"], list):
                        items_to_inject.extend(scraper_data["features"])
                    if "earthquakes" in scraper_data:
                        items_to_inject.extend(scraper_data["earthquakes"])
                    if "wildfires" in scraper_data:
                        items_to_inject.extend(scraper_data["wildfires"])
                    if "items" in scraper_data and isinstance(scraper_data["items"], list):
                        items_to_inject.extend(scraper_data["items"])
                    if "alerts" in scraper_data and "items" in scraper_data["alerts"]:
                        items_to_inject.extend(scraper_data["alerts"]["items"])
                    if "tfrs" in scraper_data and "items" in scraper_data["tfrs"]:
                        items_to_inject.extend(scraper_data["tfrs"]["items"])
                    if "airports" in scraper_data and "stations" in scraper_data["airports"]:
                        # Only inject delayed airports into the text radar
                        for st in scraper_data["airports"]["stations"]:
                            if st.get("status") == "delayed":
                                items_to_inject.append(st)

                with open('data/latest_intel.json', 'r') as f:
                    current_feed = json.load(f)
                
                existing_hashes = {item.get('hash') for item in current_feed if item.get('hash')}
                existing_ids = {item.get('id') for item in current_feed if item.get('id')}
                injected = 0
                
                for item in items_to_inject:
                    h = item.get('hash') or item.get('id')
                    
                    if h and (h not in existing_hashes) and (h not in existing_ids):
                        # Ensure baseline signal properties exist
                        if "timestamp" not in item:
                            item["timestamp"] = item.get("published") or item.get("time") or item.get("effective") or datetime.utcnow().isoformat() + "Z"
                        if "title" not in item:
                            if "place" in item and "magnitude" in item:
                                item["title"] = f"Magnitude {item['magnitude']} Earthquake - {item['place']}"
                            elif "headline" in item:
                                item["title"] = item["headline"]
                            elif "name" in item:
                                item["title"] = item["name"]
                            elif "notam_id" in item:
                                item["title"] = f"Aviation TFR: {item.get('description', '')}"
                            else:
                                item["title"] = "System Signal Update"
                        
                        if "url" not in item:
                            item["url"] = item.get("link") or item.get("articleUrl") or item.get("source_url") or "#"
                            
                        if "source" not in item:
                            item["source"] = name

                        current_feed.append(item)
                        existing_hashes.add(h)
                        existing_ids.add(h)
                        injected += 1
                
                if injected > 0:
                    current_feed.sort(key=lambda x: str(x.get('timestamp', x.get('published', ''))), reverse=True)
                    with open('data/latest_intel.json', 'w') as f:
                        json.dump(current_feed, f, indent=2)
                print(f"✓ Injected {injected} new items from {name}")
        except Exception as e:
            print(f"Warning: Could not merge {name}: {e}")
    
    # Load all merged data for sitemap generation
    with open('data/latest_intel.json', 'r') as f:
        all_data = json.load(f)

    # === NEW: Inject Alaska Legislature (HTML Scraper) ===
    leg_path = 'data/legislature.json'
    if os.path.exists(leg_path):
        try:
            with open(leg_path, 'r') as sf:
                leg_wrapper = json.load(sf)
                leg_data = leg_wrapper.get("items", [])
                
            existing_hashes = {item.get('hash') for item in all_data if item.get('hash')}
            injected = 0
            
            for item in leg_data:
                # Generate reliable SHA-256 hash mathematically tied to title & link
                unique_str = f"{item.get('title', '')}{item.get('link', '')}{item.get('published', '')}"
                h = hashlib.sha256(unique_str.encode('utf-8')).hexdigest()
                item['hash'] = h
                
                if h not in existing_hashes:
                    # Provide default properties to prevent crashing the React Wall UI
                    item['source'] = "Alaska Legislature Updates"
                    item['sourceUrl'] = "https://www.akleg.gov/"
                    item['topic'] = "Legislative Actions"
                    item['section'] = "Government"
                    item['sourceLean'] = "neutral"
                    if "timestamp" not in item and "published" in item:
                        item["timestamp"] = item["published"]
                        
                    all_data.append(item)
                    existing_hashes.add(h)
                    injected += 1
                    
            if injected > 0:
                all_data.sort(key=lambda x: x.get('timestamp', x.get('published', '')), reverse=True)
                with open('data/latest_intel.json', 'w') as f:
                    json.dump(all_data, f, indent=2)
            print(f"✓ Injected {injected} native items from Alaska Legislature JSON")
        except Exception as e:
            print(f"Warning: Could not merge Legislature data: {e}")
        
    # === NEW: Upload to Cloudflare D1 ===
    try:
        import urllib.request
        print("\n☁️ Syncing real-time signals to Cloudflare D1...")
        url = "https://alaskaintel-api.kbdesignphoto.workers.dev/ingest"
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "AlaskaIntel-Pipeline/1.0")
        
        ingest_secret = os.environ.get("INGEST_SECRET")
        if ingest_secret:
            req.add_header("Authorization", f"Bearer {ingest_secret}")
        
        # Uploading top 250 signals is sufficient because D1 handles upserts
        json_data = json.dumps(all_data[:250]).encode("utf-8") 
        with urllib.request.urlopen(req, data=json_data) as response:
            res = json.loads(response.read().decode("utf-8"))
            print(f"✓ Synced to D1 Database (Inserted: {res.get('inserted')})")
    except Exception as e:
        print(f"Warning: Cloudflare D1 sync failed: {e}")

    generate_news_sitemap(all_data)
    
    # Setup cross-repository paths for shared automation scripts
    # Priority: 1. scripts/ dir itself (CI: only alaskaintel-data/ is checked out)
    #            2. www.alaskaintel.com/scripts/ (local monorepo)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)  # archive_r2.py, generate_sitemap.py live here in CI
    frontend_scripts = os.path.abspath(os.path.join(script_dir, '../../www.alaskaintel.com/scripts'))
    if os.path.exists(frontend_scripts):
        sys.path.insert(0, frontend_scripts)
        
    # Per-feed sitemaps + sitemap index
    try:
        from generate_sitemap import generate_feed_sitemaps, generate_sitemap_index
        feed_slugs = generate_feed_sitemaps(all_data)
        generate_sitemap_index(feed_slugs)
    except Exception as e:
        print(f"Warning: Could not generate feed sitemaps: {e}")
    
    # R2 archive pipeline — permanent link fingerprinting
    try:
        from archive_r2 import archive_new_articles
        archive_new_articles(all_data)
    except Exception as e:
        print(f"Warning: R2 archive pipeline failed: {e}")
    
    archive_daily_snapshot()
    
    print(f"\n✓ Data saved to data/latest_intel.json")
    print(f"✓ Summary saved to data/intel_summary.json")


if __name__ == "__main__":
    main()
