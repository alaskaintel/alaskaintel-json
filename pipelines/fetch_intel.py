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
import html
import glob
import shutil
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

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
    {"name": "Must Read Alaska", "url": "https://mustreadalaska.com/feed", "category": "Politics"},
    {"name": "Alaska Native News", "url": "https://alaska-native-news.com/feed", "category": "Native"},
    {"name": "Alaska Watchman", "url": "https://alaskawatchman.com/feed", "category": "News"},
    {"name": "Alaska Beacon", "url": "https://alaskabeacon.com/feed", "category": "News"},
    {"name": "Dermot Cole", "url": "https://www.dermotcole.com/reportingfromalaska?format=rss", "category": "Politics"},
    {"name": "Alaska Landmine", "url": "https://alaskalandmine.com/feed", "category": "Politics"},
    
    # === REGIONAL & COMMUNITY NEWS (10-22) ===
    {"name": "Juneau Empire", "url": "https://juneauempire.com/feed", "category": "Regional"},
    {"name": "Nome Nugget", "url": "https://nomenugget.net/rss.xml", "category": "Regional"},
    {"name": "Homer News", "url": "https://homernews.com/feed", "category": "Regional"},
    {"name": "The Cordova Times", "url": "https://thecordovatimes.com/feed", "category": "Regional"},
    {"name": "Petersburg Pilot", "url": "https://petersburgpilot.com/rss", "category": "Regional"},
    {"name": "Anchorage Daily News", "url": "https://www.adn.com/arc/outboundfeeds/rss/", "category": "News"},
    {"name": "Fairbanks News-Miner", "url": "https://newsminer.com/search/?f=rss", "category": "Regional"},
    {"name": "Kodiak Daily Mirror", "url": "https://kodiakdailymirror.com/search/?f=rss", "category": "Regional"},
    {"name": "Mat-Su Frontiersman", "url": "https://frontiersman.com/search/?f=rss", "category": "Regional"},
    {"name": "Sitka Sentinel", "url": "https://sitkasentinel.com/rss", "category": "Regional"},
    {"name": "Chilkat Valley News", "url": "https://chilkatvalleynews.com/feed", "category": "Regional"},
    {"name": "Delta Wind", "url": "https://deltawind.com/feed", "category": "Regional"},
    {"name": "Arctic Sounder", "url": "https://thearcticsounder.com/feed", "category": "Regional"},
    
    # === INDUSTRY & ECONOMY (23-31) ===
    {"name": "ADF&G Commercial Fisheries", "url": "https://www.adfg.alaska.gov/index.cfm?adfg=rss.main", "category": "Fisheries"},
    {"name": "NOAA Fisheries Alaska", "url": "https://fisheries.noaa.gov/region/alaska/rss", "category": "Fisheries"},
    {"name": "Alaska Business Magazine", "url": "https://akbizmag.com/feed", "category": "Business"},
    {"name": "Alaska Journal of Commerce", "url": "https://www.adn.com/arc/outboundfeeds/rss/category/alaska-journal/?outputType=xml", "category": "Business"},
    {"name": "Resource Development Council", "url": "https://akrdc.org/rss", "category": "Industry"},
    {"name": "Fish Alaska Magazine", "url": "https://fishalaskamagazine.com/feed", "category": "Fisheries"},
    {"name": "Petroleum News", "url": "https://petroleumnews.com/rss", "category": "Energy"},
    {"name": "Alaska Economic Report", "url": "https://alaskapublic.org/news.rss", "category": "Economy"},
    
    # === GOVERNMENT & CIVIC (32-37) ===
    {"name": "Alaska DPS", "url": "https://dps.alaska.gov/RSS", "category": "Safety"},
    {"name": "BLM Alaska", "url": "https://blm.gov/press-release/alaska/rss", "category": "Government"},
    {"name": "Anchorage Municipality", "url": "http://www.muni.org/PublicNotice/_layouts/15/listfeed.aspx?List={416baa47-c958-4cbb-bd0b-7c29afddb8c3}", "category": "Government"},
    {"name": "USACE Alaska District", "url": "https://poa.usace.army.mil/Contact/RSS", "category": "Government"},
    # RETIRED: {"name": "Alaska Legislature", "url": "https://akleg.gov/basis/rss.asp", "category": "Government"},
    # RETIRED: {"name": "UAF Geophysical Institute", "url": "https://www.gi.alaska.edu/rss.xml", "category": "Science"},

    # === CITY & BOROUGH GOVERNMENT — VERIFIED LIVE RSS (discovered 2026-03-23) ===
    {"name": "Anchorage Police Dept", "url": "https://www.anchoragepolice.com/news?format=rss", "category": "Safety"},
    {"name": "Juneau CBJ", "url": "https://juneau.org/feed", "category": "Government"},
    {"name": "North Slope Borough", "url": "https://www.north-slope.org/news/feed", "category": "Government"},
    {"name": "Alaska Governor's Office", "url": "https://gov.alaska.gov/feed", "category": "Government"},
    {"name": "AK Dept of Natural Resources", "url": "https://dnr.alaska.gov/rss.xml", "category": "Environment"},
    {"name": "Wrangell City", "url": "https://www.wrangell.com/rss.xml", "category": "Government"},
    {"name": "Petersburg City", "url": "https://www.petersburgak.gov/rss.xml", "category": "Government"},
    {"name": "Dillingham City", "url": "https://www.dillinghamak.us/rss.xml", "category": "Government"},
    {"name": "Cordova City", "url": "https://www.cityofcordova.net/feed", "category": "Government"},
    {"name": "Unalaska City", "url": "https://www.ci.unalaska.ak.us/rss.xml", "category": "Government"},
    
    # === EMERGENCY, WEATHER & ENVIRONMENT (38-45) ===
    {"name": "USGS Earthquake Center", "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.atom", "category": "Emergency"},
    {"name": "NWS Anchorage", "url": "https://weather.gov/rss/afc", "category": "Weather"},
    {"name": "NWS Fairbanks", "url": "https://weather.gov/rss/afg", "category": "Weather"},
    {"name": "NWS Juneau", "url": "https://weather.gov/rss/ajp", "category": "Weather"},
    {"name": "Tsunami Warning Center", "url": "https://tsunami.gov/rss/tsunami.xml", "category": "Emergency"},
    {"name": "Alaska Volcano Observatory", "url": "https://avo.alaska.edu/rss.php", "category": "Emergency"},
    {"name": "Alaska 511 Road Conditions", "url": "https://511.alaska.gov/rss", "category": "Safety"},
    {"name": "National Fire Center", "url": "https://nifc.gov/rss", "category": "Emergency"},
    
    # === NICHE & INDEPENDENT (46-50) ===
    {"name": "Northern Journal", "url": "https://northernjournal.substack.com/feed", "category": "News"},
    {"name": "Outdoor Explorer", "url": "https://alaskapublic.org/news.rss", "category": "Recreation"},
    {"name": "ADN Archive", "url": "https://adn.com/tag/alaska-archive/feed", "category": "News"},
    {"name": "Kenai Fly Fish", "url": "https://kenaiflyfish.com/rss.xml", "category": "Recreation"},
    
    # === NATIVE CORPORATIONS & TRIBAL (51-58) ===
    {"name": "Sealaska Corporation", "url": "https://sealaska.com/news/feed", "category": "Native"},
    {"name": "Calista Corporation", "url": "https://calistacorp.com/feed", "category": "Native"},
    {"name": "Doyon Limited", "url": "https://doyon.com/feed", "category": "Native"},
    {"name": "Chugach Alaska Corp", "url": "https://www.chugach.com/feed", "category": "Native"},
    {"name": "Sitnasuak Native Corp", "url": "https://snc.org/feed", "category": "Native"},
    {"name": "Alaska Federation of Natives", "url": "https://nativefederation.org/feed", "category": "Native"},
    # RETIRED: {"name": "First Alaskans Institute", "url": "https://firstalaskans.org/feed", "category": "Native"},
    {"name": "Native American Law Blog", "url": "https://hklaw.com/en/insights/blogs/native-american-law-blog/feed", "category": "Native"},
    
    # === SPECIALIZED FISHERIES (59-66) ===
    {"name": "ADF&G Bristol Bay", "url": "https://www.adfg.alaska.gov/index.cfm?adfg=rss.main&area=bristolbay", "category": "Fisheries"},
    {"name": "ADF&G Cook Inlet", "url": "https://www.adfg.alaska.gov/index.cfm?adfg=rss.main&area=cookinlet", "category": "Fisheries"},
    {"name": "ADF&G Southeast", "url": "https://www.adfg.alaska.gov/index.cfm?adfg=rss.main&area=southeast", "category": "Fisheries"},
    {"name": "ADF&G Prince William Sound", "url": "https://www.adfg.alaska.gov/index.cfm?adfg=rss.main&area=pws", "category": "Fisheries"},
    {"name": "ADF&G Yukon", "url": "https://www.adfg.alaska.gov/index.cfm?adfg=rss.main&area=yukon", "category": "Fisheries"},
    {"name": "SeafoodNews Alaska", "url": "https://seafoodnews.com/RSS/Alaska", "category": "Fisheries"},
    {"name": "Pacific Maritime Magazine", "url": "https://pacmar.com/feed", "category": "Maritime"},
    {"name": "Marine Exchange of Alaska", "url": "https://mxak.org/feed", "category": "Maritime"},
    
    # === FEDERAL AGENCIES (67-73) ===
    {"name": "BLM Alaska Frontiers", "url": "https://blm.gov/media/alaska-frontiers-blog/feed", "category": "Government"},
    {"name": "NPS Denali", "url": "https://nps.gov/dena/learn/news/newsreleases.xml", "category": "Parks"},
    {"name": "NPS Glacier Bay", "url": "https://nps.gov/glba/learn/news/newsreleases.xml", "category": "Parks"},
    {"name": "NPS Kenai Fjords", "url": "https://nps.gov/kefj/learn/news/newsreleases.xml", "category": "Parks"},
    {"name": "USFS Chugach", "url": "https://fs.usda.gov/news/chugach/news-releases/feed", "category": "Forest"},
    {"name": "USFS Tongass", "url": "https://fs.usda.gov/news/tongass/news-releases/feed", "category": "Forest"},
    {"name": "USDA Alaska Statistics", "url": "https://www.nass.usda.gov/rss/reports.xml", "category": "Agriculture"},
    
    # === ENERGY, MINING & INFRASTRUCTURE (74-79) ===
    {"name": "RCA Issued Orders", "url": "https://rca.alaska.gov/RCAWeb/RSS/IssuedOrders", "category": "Energy"},
    {"name": "Mining.com Alaska", "url": "https://mining.com/feed", "category": "Mining"},
    {"name": "Northern Miner Alaska", "url": "https://northernminer.com/tag/alaska/feed", "category": "Mining"},
    {"name": "Alaska Power Association", "url": "https://alaskapower.org/feed", "category": "Energy"},
    {"name": "Oil & Gas IQ", "url": "https://oilandgasiq.com/rss/news", "category": "Energy"},
    {"name": "Renewable Energy Alaska", "url": "https://alaskarenewableenergy.org/feed", "category": "Energy"},
    
    # === RESEARCH & SCIENCE (80-86) ===
    {"name": "UAF News", "url": "https://uaf.edu/news/feed", "category": "Science"},
    {"name": "UAA Justice Center", "url": "https://uaa.alaska.edu/academics/college-of-health/departments/justice-center/news/feed", "category": "Research"},
    {"name": "Alaska Ocean Observing", "url": "https://aoos.org/feed", "category": "Science"},
    {"name": "AK Conservation Science", "url": "https://accs.uaa.alaska.edu/feed", "category": "Environment"},
    {"name": "Mongabay Alaska", "url": "https://news.mongabay.com/feed", "category": "Environment"},
    {"name": "The Arctic Institute", "url": "https://thearcticinstitute.org/feed", "category": "Research"},
    {"name": "IARC UAF", "url": "https://uaf-iarc.org/feed", "category": "Science"},
    
    # === HYPER-LOCAL COMMUNITY (87-95) ===
    {"name": "Kodiak Mirror", "url": "http://www.kodiakdailymirror.com/search/?f=rss&t=article&c=news&l=50&s=start_time&sd=desc", "category": "Regional"},
    {"name": "Seward Journal", "url": "https://sewardjournal.com/feed", "category": "Regional"},
    {"name": "Skagway News", "url": "https://skagwaynews.com/feed.atom", "category": "Regional"},
    {"name": "Wrangell Sentinel", "url": "https://wrangellsentinel.com/feed", "category": "Regional"},
    {"name": "KMXT Kodiak", "url": "https://www.kmxt.org/news.rss", "category": "Radio"},
    {"name": "KCAW Sitka", "url": "https://kcaw.org/feed", "category": "Radio"},
    {"name": "KBBI Homer", "url": "https://kbbi.org/feed", "category": "Radio"},
    {"name": "KHNS Haines/Skagway", "url": "https://khns.org/feed", "category": "Radio"},
    {"name": "KYUK Bethel", "url": "https://kyuk.org/feed", "category": "Radio"},
    
    # === CIVIC & SAFETY FAST SIGNALS (96-100) ===
    {"name": "Alaska State Troopers", "url": "https://dps.alaska.gov/RSS/AST", "category": "Safety"},
    {"name": "AK Medical Board", "url": "https://commerce.alaska.gov/web/cbpl/ProfessionalLicensing/StateMedicalBoard/RSS", "category": "Government"},
    {"name": "Federal Court Alaska", "url": "https://akd.uscourts.gov/rss-opinions.xml", "category": "Legal"},
    {"name": "AK Dept of Labor", "url": "https://labor.alaska.gov/news/feed", "category": "Labor"},
    {"name": "Alaska Homeless Info", "url": "https://alaskahomeless.org/feed", "category": "Social"},
    
    # ===================================================================
    # EXPANSION BATCH (101-150) - Added from DATA_SOURCES_CATALOG.md
    # Note: Some may not have RSS - will need validation
    # ===================================================================
    
    # === ENVIRONMENTAL & CONSERVATION (101-110) ===
    {"name": "Alaska Conservation Foundation", "url": "https://alaskaconservation.org/feed", "category": "Environment"},
    {"name": "Audubon Alaska", "url": "https://ak.audubon.org/feed", "category": "Environment"},
    {"name": "The Nature Conservancy Alaska", "url": "https://nature.org/en/about-us/where-we-work/united-states/alaska/feed", "category": "Environment"},
    {"name": "Alaska Wilderness League", "url": "https://alaskawildernessleague.org/feed", "category": "Environment"},
    {"name": "Sierra Club Alaska", "url": "https://sierraclub.org/rss.xml", "category": "Environment"},
    {"name": "Trustees for Alaska", "url": "https://trustees.org/feed", "category": "Environment"},
    {"name": "World Wildlife Fund Arctic", "url": "https://arcticwwf.org/feed", "category": "Environment"},
    {"name": "Alaska Wildlife Alliance", "url": "https://www.akwildlife.org/news?format=rss", "category": "Wildlife"},
    {"name": "Defenders of Wildlife Alaska", "url": "https://defenders.org/rss.xml", "category": "Wildlife"},
    {"name": "Center for Biological Diversity", "url": "https://biologicaldiversity.org/feed", "category": "Wildlife"},
    
    # === INDIGENOUS & TRIBAL (111-120) ===
    {"name": "Aleut Community of St. Paul", "url": "https://accsp.com/feed", "category": "Native"},
    {"name": "Tanana Chiefs Conference", "url": "https://tananachiefs.org/feed", "category": "Native"},
    {"name": "Bristol Bay Native Corporation", "url": "https://bbnc.net/feed", "category": "Native"},
    {"name": "Cook Inlet Region Inc", "url": "https://ciri.com/feed", "category": "Native"},
    {"name": "NANA Regional Corporation", "url": "https://nana.com/feed", "category": "Native"},
    {"name": "Alaska Native Heritage Center", "url": "https://alaskanative.net/feed", "category": "Native"},
    {"name": "Alaska Native Tribal Health", "url": "https://anthc.org/feed", "category": "Health"},
    {"name": "Kawerak Inc", "url": "https://kawerak.org/feed", "category": "Native"},
    {"name": "Ahtna Inc", "url": "https://ahtna-inc.com/feed", "category": "Native"},
    {"name": "Koniag Inc", "url": "https://koniag.com/feed", "category": "Native"},
    {"name": "Cook Inlet Housing Authority", "url": "https://www.cookinlethousing.org/feed/", "category": "Housing"},
    
    # === TRANSPORTATION & MARITIME (121-127) ===
    {"name": "Alaska Marine Highway", "url": "https://dot.alaska.gov/amhs/feed", "category": "Transportation"},
    {"name": "Ted Stevens Airport", "url": "https://dot.alaska.gov/anc/feed", "category": "Transportation"},
    {"name": "Fairbanks Airport", "url": "https://dot.alaska.gov/faiiap/feed", "category": "Transportation"},
    {"name": "Coast Guard District 17", "url": "https://news.uscg.mil/feed", "category": "Maritime"},
    {"name": "Alaska Railroad News", "url": "https://alaskarailroad.com/feed", "category": "Transportation"},
    {"name": "Alaska Trucking Association", "url": "https://aktrucking.org/feed", "category": "Transportation"},
    {"name": "Alaska Aviation Safety", "url": "https://alaskaaircrash.com/feed", "category": "Safety"},
    
    # === EMERGENCY & FIRE (128-132) ===
    {"name": "Alaska Fire Service", "url": "https://fire.ak.blm.gov/feed", "category": "Emergency"},
    {"name": "Division of Homeland Security", "url": "https://ready.alaska.gov/feed", "category": "Emergency"},
    {"name": "Alaska Interagency Fire", "url": "https://akfireinfo.com/feed", "category": "Emergency"},
    {"name": "NWS Tsunami Center", "url": "https://tsunami.gov/feed", "category": "Emergency"},
    {"name": "AK Earthquake Center", "url": "https://earthquake.alaska.edu/feed", "category": "Emergency"},
    
    # === EDUCATION & RESEARCH (133-140) ===
    {"name": "University of Alaska System", "url": "https://alaska.edu/feed", "category": "Education"},
    {"name": "Alaska Center for Energy", "url": "https://acep.uaf.edu/feed", "category": "Research"},
    {"name": "Alaska SeaLife Center", "url": "https://alaskasealife.org/feed", "category": "Research"},
    {"name": "North Pacific Research", "url": "https://nprb.org/feed", "category": "Research"},
    {"name": "Institute of the North", "url": "https://institutenorth.org/feed", "category": "Research"},
    {"name": "Arctic Research Consortium", "url": "https://arcus.org/feed", "category": "Research"},
    {"name": "Alaska Climate Center", "url": "https://akclimate.org/feed", "category": "Climate"},
    {"name": "Scenarios Network AK", "url": "https://uaf-snap.org/feed/", "category": "Climate"},
    
    # === HEALTH & SOCIAL (141-145) ===
    {"name": "Alaska Div of Public Health", "url": "https://health.alaska.gov/feed", "category": "Health"},
    {"name": "Providence Alaska Medical", "url": "https://alaska.providence.org/feed", "category": "Health"},
    {"name": "Alaska Mental Health Trust", "url": "https://alaskamentalhealthtrust.org/feed", "category": "Health"},
    {"name": "Alaska Food Bank", "url": "https://alaskafoodbank.org/feed", "category": "Social"},
    {"name": "United Way of Anchorage", "url": "https://liveunitedanc.org/rss.xml", "category": "Social"},
    
    # === BUSINESS & DEVELOPMENT (146-150) ===
    {"name": "Anchorage Economic Dev", "url": "https://aedcweb.com/feed", "category": "Economy"},
    {"name": "Alaska Venture Fund", "url": "https://akventure.org/feed", "category": "Business"},
    {"name": "Alaska Small Business Dev", "url": "https://aksbdc.org/feed", "category": "Business"},
    {"name": "Alaska Policy Forum", "url": "https://alaskapolicyforum.org/feed", "category": "Politics"},
    {"name": "Northern Economics", "url": "https://northerneconomics.com/feed", "category": "Economy"},
    
    # ===================================================================
    # NEXT-50 CATALOG SOURCES (151-197) — RSS-VERIFIED
    # ===================================================================

    # === TV & COMMERCIAL NEWS ===
    {"name": "Alaska's News Source (KTUU)", "url": "https://www.alaskasnewssource.com/feed", "category": "News"},
    {"name": "News Talk KFQD 750", "url": "https://kfqd.com/feed", "category": "News"},
    {"name": "Peninsula Clarion", "url": "https://www.peninsulaclarion.com/feed", "category": "Regional"},
    {"name": "Kenaitze Indian Tribe", "url": "https://www.kenaitze.org/feed/", "category": "Native"},
    {"name": "Salamatof Tribe News", "url": "https://www.salamatoftribe.com/news", "category": "Native"},
    {"name": "Anchorage Press", "url": "https://www.anchoragepress.com/feed", "category": "News"},
    {"name": "Senior Voice Alaska", "url": "https://seniorvoicealaska.com/rss", "category": "Health"},
    {"name": "Alaska Magazine", "url": "https://www.alaskamagazine.com/feed", "category": "News"},
    {"name": "Daily Sitka Sentinel", "url": "https://sitkasentinel.com/rss", "category": "Regional"},
    {"name": "Ketchikan Daily News", "url": "http://www.ketchikandailynews.com/search/?f=rss&t=article&c=news&l=50&s=start_time&sd=desc", "category": "Regional"},
    {"name": "AP Alaska Tag", "url": "https://apnews.com/hub/alaska/feed", "category": "News"},

    # === PUBLIC RADIO — VERIFIED FEEDS ===
    {"name": "KRBD Ketchikan", "url": "https://www.krbd.org/feed", "category": "Radio"},
    {"name": "KDLG Dillingham", "url": "https://www.kdlg.org/news.rss", "category": "Radio"},
    {"name": "KUCB Unalaska", "url": "https://www.kucb.org/feed", "category": "Radio"},
    {"name": "KNBA Anchorage", "url": "https://www.knba.org/news.rss", "category": "Radio"},
    {"name": "KUAC Fairbanks", "url": "https://fm.kuac.org/feed", "category": "Radio"},
    {"name": "KSTK Wrangell", "url": "https://www.kstk.org/feed", "category": "Radio"},
    {"name": "KFSK Petersburg", "url": "https://www.kfsk.org/comments/feed/", "category": "Radio"},

    # === MUNI OF ANCHORAGE — SPECIFIC RSS ENDPOINTS ===
    {"name": "Muni Anchorage Mayor Releases", "url": "https://www.muni.org/Departments/Mayor/PressReleases/RSS/Press_Releases.xml", "category": "Government"},
    {"name": "Muni Public Notices", "url": "https://www.muni.org/Departments/Mayor/PressReleases/RSS/Public_Notices.xml", "category": "Government"},

    # === ADF&G SPECIFIC FISHERIES ===
    {"name": "ADF&G All Regions Fish News", "url": "https://www.adfg.alaska.gov/index.cfm?adfg=rss.main", "category": "Fisheries"},
    {"name": "ADF&G Emergency Orders", "url": "https://www.adfg.alaska.gov/index.cfm?adfg=rss.eo", "category": "Fisheries"},
    {"name": "North Pacific Fishery Mgmt Council", "url": "https://www.npfmc.org/feed", "category": "Fisheries"},
    {"name": "Alaska Seafood Marketing Institute", "url": "https://www.alaskaseafood.org/feed", "category": "Fisheries"},
    {"name": "Pacific Fishing Magazine", "url": "https://www.pacificfishing.com/feed", "category": "Fisheries"},

    # === RCA & REGULATORY (VERIFIED) ===
    {"name": "RCA Alaska Issued Orders", "url": "https://rca.alaska.gov/RCAWeb/RSS/IssuedOrders", "category": "Government"},
    {"name": "RCA Alaska Press Releases", "url": "https://rca.alaska.gov/RCAWeb/RSS/PressReleases", "category": "Government"},

    # === FEDERAL / COAST GUARD / AVIATION ===
    {"name": "Coast Guard District 17 Alaska", "url": "https://www.news.uscg.mil/RSS/tabid/197/ctl/GetFeed/mid/804/Default.aspx?feed=17thdistrict", "category": "Maritime"},
    {"name": "NTSB Aviation Accidents AK", "url": "https://www.ntsb.gov/investigations/Pages/aviation.aspx/rss.xml", "category": "Safety"},
    {"name": "FAA Safety Alerts", "url": "https://rss.faa.gov/safetyalertsforoperators.xml", "category": "Safety"},
    {"name": "Arctic Web Map / NOAA Arctic", "url": "https://arctic.noaa.gov/about/feed", "category": "Science"},

    # === ALASKA STATE LEGISLATURE ===
    {"name": "Alaska Senate Majority", "url": "https://alaskasenate.org/feed", "category": "Government"},
    {"name": "Alaska House Majority", "url": "https://akhouse.org/feed", "category": "Government"},

    # === SPECIALIZED REGIONAL (VERIFIED LIVE) ===
    {"name": "Ketchikan Gateway Borough", "url": "https://www.kgbak.us/CivicAlerts.aspx?format=rss", "category": "Government"},
    {"name": "Homer Electric Association", "url": "https://www.homerelectric.com/feed", "category": "Infrastructure"},
    {"name": "Golden Valley Electric", "url": "https://www.gvea.com/news-releases_category/news/feed/", "category": "Infrastructure"},
    {"name": "Chugach Electric Association", "url": "https://www.chugachelectric.com/feed", "category": "Infrastructure"},
    {"name": "Matanuska Electric Association", "url": "https://www.mea.coop/feed", "category": "Infrastructure"},
    {"name": "Alaska Village Electric Coop", "url": "https://avec.org/feed", "category": "Infrastructure"},
    {"name": "Alaska Process Industry", "url": "https://www.akpic.org/feed", "category": "Industry"},

    # === ENVIRONMENT & LAND ===
    {"name": "Alaska DEC Spill Reports", "url": "https://dec.alaska.gov/Applications/SPAR/PubMapViewer/feed", "category": "Environment"},
    {"name": "AOGCC Oil Gas Incidents", "url": "https://aogcc.alaska.gov/feed", "category": "Energy"},
    {"name": "Alaska Statewide Parks", "url": "https://dnr.alaska.gov/parks/news/feed", "category": "Parks"},
    {"name": "Arctic Audubon", "url": "https://ak.audubon.org/feed", "category": "Wildlife"},
    {"name": "Cook Inletkeeper", "url": "https://inletkeeper.org/feed", "category": "Environment"},

    # === CORRECTIONS & JUSTICE ===
    {"name": "Alaska DOC News", "url": "https://doc.alaska.gov/news/feed", "category": "Government"},
    {"name": "Federal Court Alaska", "url": "https://akd.uscourts.gov/rss-opinions.xml", "category": "Legal"},

    # === HEALTH & EMERGENCY ===
    {"name": "Alaska DHS&EM Alerts", "url": "https://ready.alaska.gov/feed", "category": "Emergency"},
    {"name": "Alaska AK Department of Health", "url": "https://health.alaska.gov/feed", "category": "Health"},

    # ===================================================================
    # ALL 12 ANCSA REGIONAL NATIVE CORPORATIONS
    # ===================================================================

    # === SOUTHEAST ===
    {"name": "Sealaska Corporation", "url": "https://www.sealaska.com/feed", "category": "Native"},
    {"name": "Sealaska Heritage Institute", "url": "https://www.sealaskaheritage.org/feed", "category": "Native"},

    # === SOUTHCENTRAL ===
    {"name": "Cook Inlet Region Inc (CIRI)", "url": "https://www.ciri.com/feed", "category": "Native"},
    {"name": "Chugach Alaska Corporation", "url": "https://www.chugach.com/feed", "category": "Native"},
    {"name": "Ahtna Inc", "url": "https://www.ahtna.com/feed", "category": "Native"},

    # === INTERIOR ===
    {"name": "Doyon Limited", "url": "https://www.doyon.com/feed", "category": "Native"},

    # === NORTHWEST/ARCTIC ===
    {"name": "NANA Regional Corporation", "url": "https://www.nana.com/feed", "category": "Native"},
    {"name": "Bering Straits Native Corp", "url": "https://www.beringstraits.com/feed", "category": "Native"},
    {"name": "Arctic Slope Regional Corp (ASRC)", "url": "https://www.asrc.com/feed", "category": "Native"},

    # === WESTERN/SOUTHWEST ===
    {"name": "Calista Corporation", "url": "https://www.calistacorp.com/feed", "category": "Native"},
    {"name": "Bristol Bay Native Corp (BBNC)", "url": "https://www.bbnc.net/feed", "category": "Native"},

    # === SOUTHWEST/ALEUTIAN ===
    {"name": "The Aleut Corporation", "url": "https://www.aleutcorp.com/feed", "category": "Native"},
    {"name": "Koniag Inc", "url": "https://www.koniag.com/feed", "category": "Native"},

    # === ANCSA REGIONAL ASSOCIATION ===
    {"name": "ANCSA Regional Association", "url": "https://www.ancsaregional.com/feed", "category": "Native"},
    {"name": "AK Native Village Corp Association", "url": "https://www.anvca.biz/feed", "category": "Native"},

    # ===================================================================
    # TRIBAL CONSORTIA & HEALTH CORPORATIONS
    # ===================================================================

    # === TRIBAL HEALTH NETWORKS ===
    {"name": "Southcentral Foundation (SCF)", "url": "https://www.southcentralfoundation.com/feed", "category": "Health"},
    {"name": "Yukon-Kuskokwim Health Corp (YKHC)", "url": "https://www.ykhc.org/feed", "category": "Health"},
    {"name": "Maniilaq Association", "url": "https://www.maniilaq.org/feed", "category": "Health"},
    {"name": "Norton Sound Health Corp", "url": "https://www.nshcorp.org/feed", "category": "Health"},
    {"name": "Kodiak Area Native Assoc (KANA)", "url": "https://www.kanaweb.org/feed", "category": "Health"},
    {"name": "Chugachmiut", "url": "https://www.chugachmiut.org/feed", "category": "Health"},
    {"name": "Bristol Bay Area Health Corp", "url": "https://www.bbahc.org/feed", "category": "Health"},
    {"name": "Copper River Native Assoc", "url": "https://www.crnative.org/feed", "category": "Health"},
    {"name": "Interior Regional Health Services", "url": "https://www.irhs.org/feed", "category": "Health"},
    {"name": "Southeast AK Regional Health (SEARHC)", "url": "https://www.searhc.org/feed", "category": "Health"},
    {"name": "SCF Nuka Podcast", "url": "https://scfnuka.com/feed/podcast", "category": "Health"},

    # === TRIBAL POLITICAL ORGANIZATIONS ===
    {"name": "Central Council Tlingit Haida", "url": "https://www.ccthita.org/feed", "category": "Native"},
    {"name": "Assoc of Village Council Presidents (AVCP)", "url": "https://www.avcp.org/feed", "category": "Native"},
    {"name": "Copper River Native Assoc Tribal", "url": "https://www.crnativetribal.org/feed", "category": "Native"},
    {"name": "Kenaitze Indian Tribe", "url": "https://www.kenaitze.org/feed/", "category": "Native"},
    {"name": "Salamatof Tribe", "url": "https://www.salamatoftribe.com/feed", "category": "Native"},
    {"name": "Sitka Tribe of Alaska", "url": "https://www.sitkatribe.org/feed", "category": "Native"},
    {"name": "Native Village of Barrow", "url": "https://www.inupiatcommunity.com/feed", "category": "Native"},
    {"name": "Eklutna Inc (Chugach OG)", "url": "https://www.eklutna.com/feed", "category": "Native"},
    {"name": "Metlakatla Indian Community", "url": "https://www.metlakatla.com/feed", "category": "Native"},
    {"name": "Metlakatla Indian Community", "url": "https://www.metlakatla.com/events/feed/", "category": "Native"},

    # === ALASKA NATIVE ADVOCACY & POLICY ===
    {"name": "Alaska Federation of Natives", "url": "https://www.nativefederation.org/feed", "category": "Native"},
    # RETIRED: {"name": "First Alaskans Institute", "url": "https://www.firstalaskans.org/feed", "category": "Native"},
    {"name": "Alaska Native Coalition", "url": "https://www.alaskanativecoalition.org/feed", "category": "Native"},
    {"name": "Kawerak Inc (Bering Strait)", "url": "https://www.kawerak.org/feed", "category": "Native"},
    {"name": "Association of AK Housing Auth", "url": "https://theaaha.org/feed", "category": "Native"},
    {"name": "Rural Alaska Community Action (RurAL CAP)", "url": "https://www.ruralcap.com/feed", "category": "Native"},

    # === MUSIC & MEDIA ===
    {"name": "Indigefi", "url": "https://www.indigefi.org/feed/", "category": "Music & Media"},
    {"name": "The Alaska Music Podcast", "url": "https://feed.podbean.com/kurtriemann/feed.xml", "category": "Music & Media"},
    {"name": "Alaska Signal (Music)", "url": "https://alaskasignal.com/category/music/feed/", "category": "Music & Media"},
    {"name": "AK Concerts", "url": "https://akconcerts.com/feed", "category": "Music & Media"},

    # === NATIVE MEDIA & NEWS ===
    {"name": "Alaska Native News", "url": "https://alaska-native-news.com/feed", "category": "Native"},
    {"name": "KNBA Native Radio Anchorage", "url": "https://www.knba.org/news.rss", "category": "Native"},
    {"name": "Native News Online", "url": "https://www.nativenews.net/feed/", "category": "Native"},
    {"name": "KYUK Bethel Indigenous Radio", "url": "https://www.kyuk.org/feed", "category": "Native"},
    {"name": "KNOM Nome Indigenous Radio", "url": "https://www.knom.org/feed", "category": "Native"},
    {"name": "Indian Country Today Alaska", "url": "https://ictnews.org/tag/alaska/feed", "category": "Native"},
    {"name": "Native Voice One", "url": "https://www.nv1.org/feed", "category": "Native"},

    # === EDUCATION & CULTURAL ===
    {"name": "Alaska Native Heritage Center", "url": "https://www.alaskanative.net/feed", "category": "Native"},
    {"name": "Goldbelt Heritage Foundation", "url": "https://www.goldbeltheritage.org/feed", "category": "Native"},
    {"name": "Doyon Foundation Education", "url": "https://www.doyonfoundation.com/feed", "category": "Native"},

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

    # === ALASKA HIDDEN WARNING SIGNALS (DEEP CUTS) ===
    {"name": "USGS Volcano Aviation (VONA)", "url": "https://volcanoes.usgs.gov/vns2/vonas.rss", "category": "Emergency", "filter_keyword": "alaska"},
    {"name": "Hatcher Pass Avalanche", "url": "https://hatcherpassavalanchecenter.org/feed/", "category": "Emergency"},
    {"name": "Valdez Avalanche", "url": "https://www.alaskasnow.org/valdez/feed/", "category": "Emergency"},
    {"name": "NWS Alaska Alerts (CAP)", "url": "https://alerts.weather.gov/cap/ak.php?x=0", "category": "Emergency"},
    {"name": "NWS APRFC River Forecast", "url": "https://water.weather.gov/ahps2/rss/alert/ak.xml", "category": "Emergency"},
    {"name": "DEC Air Quality Advisories", "url": "https://dec.alaska.gov/Applications/Air/airtoolsweb/AqAdvisories/Index/Rss", "category": "Environment"},
    {"name": "USGS Alaska Science", "url": "https://www.usgs.gov/news/feed/science-centers/alaska-science-center", "category": "Science"},
    {"name": "ADF&G Emergency Orders", "url": "http://www.adfg.alaska.gov/sf/EONR/index.cfm?ADFG=rss.RssNR", "category": "Fisheries"},
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


def extract_date_from_url(url: str) -> Optional[datetime]:
    """
    Extract YYYY/MM/DD strictly from URLs (like WordPress permalinks) 
    to prevent old bumped articles from getting today's timestamp.
    """
    match = re.search(r'/((?:19|20)\d{2})/(\d{2})/(\d{2})/', url)
    if match:
        year, month, day = map(int, match.groups())
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


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

    # Filter out any feeds that are on hold or marked stale
    feeds_to_fetch = [f for f in FEEDS if f["name"] not in hold and f["name"] not in stale]

    print(f"Fetching {len(feeds_to_fetch)} of {len(FEEDS)} configured feeds "
          f"(hold={len(hold)}, stale={len(stale)})...")
          
    # Load feed scores and health to determine priority and next check
    scores_data = {}
    source_health = {}
    try:
        if os.path.exists('data/feed_scores.json'):
            with open('data/feed_scores.json', 'r') as f:
                scores_data = json.load(f)
        if os.path.exists('data/source_health.json'):
            with open('data/source_health.json', 'r') as f:
                source_health = json.load(f)
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
    
    for i, feed in enumerate(feeds_to_fetch, 1):
        score_info = scores_data.get(feed['name'], {})
        next_check_str = score_info.get('next_check_due')
        priority = score_info.get('priority', 'high')
        
        # Determine check interval
        intervals = {'high': 15, 'medium': 180, 'low': 720, 'zero-signal': 10080}
        interval_mins = intervals.get(priority, 15)
        
        if next_check_str:
            try:
                next_check = datetime.fromisoformat(next_check_str.replace('Z', '+00:00'))
                if next_check.tzinfo is None:
                    next_check = next_check.replace(tzinfo=timezone.utc)
                    
                if now < next_check:
                    print(f"[{i}/{len(feeds_to_fetch)}] Skipping: {feed['name']} (Due: {next_check.strftime('%H:%M')} UTC - {priority})")
                    continue
            except Exception:
                pass
                
        print(f"[{i}/{len(feeds_to_fetch)}] Fetching: {feed['name']} ({priority})...")
        
        try:
            # request using Chrome-like user-agent to avoid some anti-bot blocks
            parsed = feedparser.parse(feed['url'], agent=CHROME_UA)
            
            # Check if feed loaded successfully
            if hasattr(parsed, 'status') and parsed.status >= 400:
                print(f"  ⚠️  HTTP {parsed.status} error for {feed['name']} (will retry next run)")
                source_health[feed['name']] = {"last_checked": now.isoformat(), "status": f"HTTP {parsed.status}", "entries": 0, "category": feed['category']}
                continue
                
            if not parsed.entries:
                print(f"  ⚠️  No entries found for {feed['name']} (will retry next run)")
                source_health[feed['name']] = {"last_checked": now.isoformat(), "status": "Empty Feed", "entries": 0, "category": feed['category']}
                continue
            
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
                
                # Exclude non-Alaska earthquakes
                if feed['name'] == 'USGS Earthquake Center':
                    title_lower = title.lower()
                    if 'alaska' not in title_lower and ', ak' not in title_lower and 'aleutian' not in title_lower:
                        continue
                
                # Generate hash for deduplication
                item_hash = generate_hash(title, link)
                
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
                        try:
                            soup = BeautifulSoup(content, 'html.parser')
                            # Look for meta og:image or twitter:image
                            meta_img = soup.find('meta', property=re.compile(r'^(og|twitter):image$'))
                            if meta_img and meta_img.get('content'):
                                image_url = meta_img['content'].strip()
                            
                            # Fallback: Look for the first <img> tag with a valid src
                            if not image_url:
                                img_tag = soup.find('img', src=True)
                                if img_tag:
                                    src = img_tag['src'].strip()
                                    if not src.startswith('data:') and 'pixel' not in src and 'tracker' not in src:
                                        image_url = src
                        except Exception:
                            pass
                
                url_date = extract_date_from_url(link)
                
                published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                if published_struct:
                    feed_date = datetime(*published_struct[:6], tzinfo=timezone.utc)
                    # Use URL date if it exists and contradicts the feed year (usually meaning the feed date is an updated timestamp)
                    if url_date and url_date.year != feed_date.year:
                        published_iso = url_date.isoformat()
                    else:
                        published_iso = feed_date.isoformat()
                else:
                    if url_date:
                        published_iso = url_date.isoformat()
                    # For AST/DPS sources, scrape_ast.py owns the timestamps — skip
                    # items that have no published date rather than stamping with now().
                    elif feed['name'] in ('Alaska State Troopers', 'Alaska DPS'):
                        continue
                    else:
                        published_iso = datetime.now(timezone.utc).isoformat()

                # Override published_iso for USGS earthquakes to actual event time
                if feed['name'] == 'USGS Earthquake Center':
                    time_match = re.search(r'<dt>Time</dt><dd>([^<]+ UTC)</dd>', raw_summary)
                    if time_match:
                        try:
                            eq_time_str = time_match.group(1).replace(' UTC', '')
                            published_iso = datetime.strptime(eq_time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).isoformat()
                        except ValueError:
                            pass

                # Drop signals older than 3650 days to avoid ancient posts resurfacing (like 2025 items)
                try:
                    dt = datetime.fromisoformat(published_iso.replace('Z', '+00:00'))
                    if (datetime.now(timezone.utc) - dt).days > 3650:
                        continue
                except ValueError:
                    pass

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
                intel_data.append(item)
            
            # After fetch, update next_check_due
            score_info['next_check_due'] = (now + timedelta(minutes=interval_mins)).isoformat()
            scores_data[feed['name']] = score_info
            
            entries_fetched = len(parsed.entries)
            source_health[feed['name']] = {"last_checked": now.isoformat(), "status": "OK", "entries": entries_fetched, "category": feed['category']}
            print(f"  ✓ Retrieved {entries_fetched} entries")
            
        except Exception as e:
            # Add backoff for errors
            score_info['next_check_due'] = (now + timedelta(minutes=60)).isoformat()
            scores_data[feed['name']] = score_info
            source_health[feed['name']] = {"last_checked": now.isoformat(), "status": f"Error: {str(e)[:50]}", "entries": 0, "category": feed['category']}
            print(f"  ✗ Error fetching {feed['name']}: {str(e)}")
            continue
    
    # Feed status: only persist manual holds, never auto-stale
    # (stale list was causing permanent blacklisting of 209+ feeds)
    try:
        os.makedirs(os.path.dirname(FEED_STATUS_FILE), exist_ok=True)
        with open(FEED_STATUS_FILE, "w") as f:
            json.dump({"hold": sorted(list(hold)), "stale": []}, f, indent=2)
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
    """Post-processing pass: link signals that share region+sector within 48h or share entities."""
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
        
        
    # Cap latest_intel.json to a 60-Day rolling window for blazing fast UI loads
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
    xml_str = ET.tostring(root, encoding='utf-8', method='xml').decode('utf-8')
    
    # Simple formatting hack since minidom often crashes on dirty RSS text:
    pretty_xml = xml_str.replace("><url>", ">\n  <url>").replace("</url></urlset>", "</url>\n</urlset>")
    
    os.makedirs('public', exist_ok=True)
    with open('public/sitemap-news.xml', 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + pretty_xml)
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
    
    # Merge standalone custom JSON scrapers
    custom_sources = [
        'data/usace_notices.json',
        'data/cdvsa_psas.json',
        'data/akleg_bill.json',
        'data/muni_alerts.json',
        'data/frontiersman_legals.json'
    ]
    for cs in custom_sources:
        if os.path.exists(cs):
            try:
                with open(cs, 'r') as f:
                    cs_data = json.load(f)
                    if isinstance(cs_data, list):
                        new_intel.extend(cs_data)
                        print(f"Merged {len(cs_data)} standalone items from {cs}")
            except Exception as e:
                print(f"Warning: Could not merge custom source {cs}: {e}")
                
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
            
    # Inject ADN Marketplace Legals
    adn_path = 'data/adn_legals.json'
    if os.path.exists(adn_path):
        try:
            with open(adn_path, 'r') as af:
                adn_legals = json.load(af)
            with open('data/latest_intel.json', 'r') as f:
                current_feed = json.load(f)
                
            existing_hashes = {item.get('hash') for item in current_feed if item.get('hash')}
            injected = 0
            
            for item in adn_legals:
                h = item.get('hash')
                if not h or h in existing_hashes:
                    continue
                current_feed.append(item)
                existing_hashes.add(h)
                injected += 1
                
            if injected > 0:
                current_feed.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                with open('data/latest_intel.json', 'w') as f:
                    json.dump(current_feed, f, indent=2)
                print(f"✓ Injected {injected} new ADN Legal notices into main feed")
        except Exception as e:
            print(f"Warning: Could not merge ADN Legals: {e}")
    
    # Load all merged data for sitemap generation and chunking
    with open('data/latest_intel.json', 'r') as f:
        all_data = json.load(f)
        
    # --- DATA STREAMING / CHUNKING ---
    now = datetime.now(timezone.utc)
    latest_24h = []
    latest_7d = []
    
    for item in all_data:
        ts_str = item.get('timestamp')
        if not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
                
            delta = now - dt
            if delta.total_seconds() <= 24 * 3600:
                latest_24h.append(item)
            if delta.total_seconds() <= 7 * 24 * 3600:
                latest_7d.append(item)
        except ValueError:
            pass

    with open('data/latest_24h.json', 'w') as f:
        json.dump(latest_24h, f, indent=2)
    with open('data/latest_7d.json', 'w') as f:
        json.dump(latest_7d, f, indent=2)
    
    print(f"✓ Streamed {len(latest_24h)} signals to 24h lake")
    print(f"✓ Streamed {len(latest_7d)} signals to 7d lake")
    # ---------------------------------

    generate_news_sitemap(all_data)
    
    # Per-feed sitemaps + sitemap index
    try:
        sys.path.insert(0, os.path.dirname(__file__))
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
