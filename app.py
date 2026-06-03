"""
NEXRAD Radar Viewer — FastAPI backend
Level 1 info / Level 2 listing / Level 3 full fetch+render

Run:  python app.py
Then: http://localhost:8000
"""

from __future__ import annotations
import io, math, hashlib, pathlib, urllib.request, os, re, struct, bz2, sys
from typing import Optional
from version import __version__

GITHUB_REPO = "pdidygaman/nexrad-radar"

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image

from metpy.io import Level3File
from metpy.plots import colortables

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ─── paths & constants ────────────────────────────────────────────────────────
def _resource_dir() -> pathlib.Path:
    """Folder holding bundled read-only assets (static/). Works frozen or not."""
    if getattr(sys, 'frozen', False):
        return pathlib.Path(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)))
    return pathlib.Path(os.path.dirname(os.path.abspath(__file__)))


def _data_dir() -> pathlib.Path:
    """Writable folder for the cache (per-user when installed)."""
    if getattr(sys, 'frozen', False):
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
        return pathlib.Path(base) / 'NEXRADRadar'
    return pathlib.Path(os.path.dirname(os.path.abspath(__file__)))


RESOURCE_DIR = _resource_dir()
STATIC_DIR   = str(RESOURCE_DIR / 'static')
CACHE = _data_dir() / 'cache'
CACHE.mkdir(parents=True, exist_ok=True)

L2_BASE = 'https://noaa-nexrad-level2.s3.amazonaws.com'
L3_BASE = 'https://unidata-nexrad-level3.s3.amazonaws.com'
RENDER_PX = 1400   # output image size (square) — higher = sharper
L3_MAX_CACHE = 500  # max cached Level-3 files

# ─── NEXRAD sites ─────────────────────────────────────────────────────────────
SITES = {
    'KABR': {'name':'Aberdeen','state':'SD','lat':45.4558,'lon':-98.4132},
    'KABX': {'name':'Albuquerque','state':'NM','lat':35.1497,'lon':-106.8239},
    'KAKQ': {'name':'Wakefield','state':'VA','lat':36.9839,'lon':-77.0073},
    'KAMA': {'name':'Amarillo','state':'TX','lat':35.2333,'lon':-101.7092},
    'KAMX': {'name':'Miami','state':'FL','lat':25.6111,'lon':-80.4128},
    'KAPX': {'name':'Gaylord','state':'MI','lat':44.9072,'lon':-84.7197},
    'KARX': {'name':'La Crosse','state':'WI','lat':43.8228,'lon':-91.1915},
    'KATX': {'name':'Seattle','state':'WA','lat':48.1944,'lon':-122.4958},
    'KBBX': {'name':'Beale AFB','state':'CA','lat':39.4957,'lon':-121.6317},
    'KBGM': {'name':'Binghamton','state':'NY','lat':42.1997,'lon':-75.9847},
    'KBHX': {'name':'Eureka','state':'CA','lat':40.4986,'lon':-124.2917},
    'KBIS': {'name':'Bismarck','state':'ND','lat':46.7708,'lon':-100.7603},
    'KBLX': {'name':'Billings','state':'MT','lat':45.8539,'lon':-108.6067},
    'KBMX': {'name':'Birmingham','state':'AL','lat':33.1722,'lon':-86.7697},
    'KBOX': {'name':'Boston','state':'MA','lat':41.9556,'lon':-71.1369},
    'KBRO': {'name':'Brownsville','state':'TX','lat':25.9159,'lon':-97.4189},
    'KBUF': {'name':'Buffalo','state':'NY','lat':42.9489,'lon':-78.7369},
    'KBYX': {'name':'Key West','state':'FL','lat':24.5975,'lon':-81.7033},
    'KCAE': {'name':'Columbia','state':'SC','lat':33.9487,'lon':-81.1183},
    'KCBW': {'name':'Caribou','state':'ME','lat':46.0392,'lon':-67.8067},
    'KCBX': {'name':'Boise','state':'ID','lat':43.4911,'lon':-116.2358},
    'KCCX': {'name':'State College','state':'PA','lat':40.9228,'lon':-78.0039},
    'KCLE': {'name':'Cleveland','state':'OH','lat':41.4131,'lon':-81.8597},
    'KCLX': {'name':'Charleston','state':'SC','lat':32.6556,'lon':-81.0422},
    'KCRP': {'name':'Corpus Christi','state':'TX','lat':27.7839,'lon':-97.5114},
    'KCXX': {'name':'Burlington','state':'VT','lat':44.5111,'lon':-73.1661},
    'KCYS': {'name':'Cheyenne','state':'WY','lat':41.1517,'lon':-104.8061},
    'KDAX': {'name':'Sacramento','state':'CA','lat':38.5011,'lon':-121.6778},
    'KDDC': {'name':'Dodge City','state':'KS','lat':37.7208,'lon':-99.9686},
    'KDFX': {'name':'Laughlin AFB','state':'TX','lat':29.2731,'lon':-100.2803},
    'KDGX': {'name':'Jackson','state':'MS','lat':32.2797,'lon':-89.9847},
    'KDLH': {'name':'Duluth','state':'MN','lat':46.8369,'lon':-92.2097},
    'KDMX': {'name':'Des Moines','state':'IA','lat':41.7311,'lon':-93.7228},
    'KDOX': {'name':'Dover AFB','state':'DE','lat':38.8256,'lon':-75.4400},
    'KDTX': {'name':'Detroit','state':'MI','lat':42.6997,'lon':-83.4717},
    'KDVN': {'name':'Davenport','state':'IA','lat':41.6117,'lon':-90.5808},
    'KDYX': {'name':'Dyess AFB','state':'TX','lat':32.5383,'lon':-99.2544},
    'KEAX': {'name':'Kansas City','state':'MO','lat':38.8100,'lon':-94.2644},
    'KEMX': {'name':'Tucson','state':'AZ','lat':31.8936,'lon':-110.6308},
    'KENX': {'name':'Albany','state':'NY','lat':42.5864,'lon':-74.0642},
    'KEOX': {'name':'Fort Rucker','state':'AL','lat':31.4606,'lon':-85.4594},
    'KEPZ': {'name':'El Paso','state':'TX','lat':31.8731,'lon':-106.6981},
    'KESX': {'name':'Las Vegas','state':'NV','lat':35.7011,'lon':-114.8914},
    'KEVX': {'name':'Eglin AFB','state':'FL','lat':30.5644,'lon':-85.9214},
    'KEWX': {'name':'Austin/San Antonio','state':'TX','lat':29.7039,'lon':-98.0283},
    'KEYX': {'name':'Edwards AFB','state':'CA','lat':35.0978,'lon':-117.5608},
    'KFCX': {'name':'Roanoke','state':'VA','lat':37.0242,'lon':-80.2742},
    'KFDR': {'name':'Altus AFB','state':'OK','lat':34.3622,'lon':-98.9761},
    'KFDX': {'name':'Cannon AFB','state':'NM','lat':34.6353,'lon':-103.6294},
    'KFFC': {'name':'Atlanta','state':'GA','lat':33.3636,'lon':-84.5658},
    'KFSD': {'name':'Sioux Falls','state':'SD','lat':43.5878,'lon':-96.7294},
    'KFSX': {'name':'Flagstaff','state':'AZ','lat':34.5744,'lon':-111.1983},
    'KFTG': {'name':'Denver','state':'CO','lat':39.7867,'lon':-104.5458},
    'KFWS': {'name':'Dallas/Fort Worth','state':'TX','lat':32.5731,'lon':-97.3031},
    'KGGW': {'name':'Glasgow','state':'MT','lat':48.2064,'lon':-106.6250},
    'KGJX': {'name':'Grand Junction','state':'CO','lat':39.0622,'lon':-108.2136},
    'KGLD': {'name':'Goodland','state':'KS','lat':39.3672,'lon':-101.7008},
    'KGRB': {'name':'Green Bay','state':'WI','lat':44.4986,'lon':-88.1111},
    'KGRK': {'name':'Fort Hood','state':'TX','lat':30.7219,'lon':-97.3828},
    'KGRR': {'name':'Grand Rapids','state':'MI','lat':42.8939,'lon':-85.5447},
    'KGSP': {'name':'Greer','state':'SC','lat':34.8833,'lon':-82.2200},
    'KGWX': {'name':'Columbus AFB','state':'MS','lat':33.8967,'lon':-88.3289},
    'KGYX': {'name':'Portland ME','state':'ME','lat':43.8914,'lon':-70.2567},
    'KHDX': {'name':'Holloman AFB','state':'NM','lat':33.0769,'lon':-106.1219},
    'KHGX': {'name':'Houston','state':'TX','lat':29.4719,'lon':-95.0792},
    'KHNX': {'name':'San Joaquin Valley','state':'CA','lat':36.3142,'lon':-119.6322},
    'KHPX': {'name':'Fort Campbell','state':'KY','lat':36.7367,'lon':-87.2847},
    'KHTX': {'name':'Huntsville','state':'AL','lat':34.9306,'lon':-86.0836},
    'KICT': {'name':'Wichita','state':'KS','lat':37.6544,'lon':-97.4433},
    'KICX': {'name':'Cedar City','state':'UT','lat':37.5908,'lon':-112.8622},
    'KILN': {'name':'Cincinnati','state':'OH','lat':39.4203,'lon':-83.8217},
    'KILX': {'name':'Lincoln','state':'IL','lat':40.1503,'lon':-89.3367},
    'KIND': {'name':'Indianapolis','state':'IN','lat':39.7075,'lon':-86.2803},
    'KINX': {'name':'Tulsa','state':'OK','lat':36.1750,'lon':-95.5644},
    'KIWX': {'name':'Fort Wayne','state':'IN','lat':41.3589,'lon':-85.7000},
    'KJAN': {'name':'Jackson MS','state':'MS','lat':32.1117,'lon':-90.0800},
    'KJAX': {'name':'Jacksonville','state':'FL','lat':30.4847,'lon':-81.7019},
    'KJGX': {'name':'Robins AFB','state':'GA','lat':32.6750,'lon':-83.3511},
    'KJKL': {'name':'Jackson KY','state':'KY','lat':37.5908,'lon':-83.3131},
    'KLBB': {'name':'Lubbock','state':'TX','lat':33.6542,'lon':-101.8142},
    'KLCH': {'name':'Lake Charles','state':'LA','lat':30.1253,'lon':-93.2158},
    'KLIX': {'name':'New Orleans','state':'LA','lat':30.3367,'lon':-89.8253},
    'KLNX': {'name':'North Platte','state':'NE','lat':41.9578,'lon':-100.5758},
    'KLOT': {'name':'Chicago','state':'IL','lat':41.6044,'lon':-88.0847},
    'KLRX': {'name':'Elko','state':'NV','lat':40.7397,'lon':-116.8028},
    'KLSX': {'name':'St. Louis','state':'MO','lat':38.6989,'lon':-90.6828},
    'KLTX': {'name':'Wilmington NC','state':'NC','lat':33.9892,'lon':-78.4292},
    'KLVX': {'name':'Louisville','state':'KY','lat':37.9753,'lon':-85.9439},
    'KLWX': {'name':'Sterling VA','state':'VA','lat':38.9753,'lon':-77.4778},
    'KLZK': {'name':'Little Rock','state':'AR','lat':34.8364,'lon':-92.2619},
    'KMAF': {'name':'Midland','state':'TX','lat':31.9433,'lon':-102.1894},
    'KMAX': {'name':'Medford','state':'OR','lat':42.0811,'lon':-122.7158},
    'KMBX': {'name':'Minot AFB','state':'ND','lat':48.3928,'lon':-100.8644},
    'KMHX': {'name':'Morehead City','state':'NC','lat':34.7761,'lon':-76.8764},
    'KMKX': {'name':'Milwaukee','state':'WI','lat':42.9678,'lon':-88.5508},
    'KMLB': {'name':'Melbourne','state':'FL','lat':28.1133,'lon':-80.6542},
    'KMOB': {'name':'Mobile','state':'AL','lat':30.6794,'lon':-88.2397},
    'KMPX': {'name':'Minneapolis','state':'MN','lat':44.8489,'lon':-93.5653},
    'KMQT': {'name':'Marquette','state':'MI','lat':46.5314,'lon':-87.5483},
    'KMRX': {'name':'Knoxville','state':'TN','lat':36.1686,'lon':-83.4017},
    'KMSX': {'name':'Missoula','state':'MT','lat':47.0411,'lon':-113.9861},
    'KMTX': {'name':'Salt Lake City','state':'UT','lat':41.2628,'lon':-112.4478},
    'KMUX': {'name':'San Francisco','state':'CA','lat':37.1553,'lon':-121.8983},
    'KMVX': {'name':'Grand Forks','state':'ND','lat':47.5278,'lon':-97.3258},
    'KMXX': {'name':'Maxwell AFB','state':'AL','lat':32.5367,'lon':-85.7897},
    'KNKX': {'name':'San Diego','state':'CA','lat':32.9189,'lon':-117.0419},
    'KNQA': {'name':'Memphis','state':'TN','lat':35.3447,'lon':-89.8731},
    'KOAX': {'name':'Omaha','state':'NE','lat':41.3203,'lon':-96.3664},
    'KOHX': {'name':'Nashville','state':'TN','lat':36.2472,'lon':-86.5625},
    'KOKX': {'name':'New York City','state':'NY','lat':40.8656,'lon':-72.8639},
    'KOTX': {'name':'Spokane','state':'WA','lat':47.6803,'lon':-117.6258},
    'KPAH': {'name':'Paducah','state':'KY','lat':37.0683,'lon':-88.7719},
    'KPBZ': {'name':'Pittsburgh','state':'PA','lat':40.5317,'lon':-80.2178},
    'KPDT': {'name':'Pendleton','state':'OR','lat':45.6906,'lon':-118.8528},
    'KPOE': {'name':'Fort Polk','state':'LA','lat':31.1556,'lon':-92.9758},
    'KPUX': {'name':'Pueblo','state':'CO','lat':38.4595,'lon':-104.1817},
    'KRAX': {'name':'Raleigh','state':'NC','lat':35.6656,'lon':-78.4897},
    'KRGX': {'name':'Reno','state':'NV','lat':39.7542,'lon':-119.4614},
    'KRIW': {'name':'Riverton','state':'WY','lat':43.0661,'lon':-108.4775},
    'KRLX': {'name':'Charleston WV','state':'WV','lat':38.3111,'lon':-81.7228},
    'KRTX': {'name':'Portland OR','state':'OR','lat':45.7150,'lon':-122.9650},
    'KSFX': {'name':'Pocatello','state':'ID','lat':43.1056,'lon':-112.6861},
    'KSGF': {'name':'Springfield MO','state':'MO','lat':37.2353,'lon':-93.4006},
    'KSHV': {'name':'Shreveport','state':'LA','lat':32.4508,'lon':-93.8411},
    'KSJT': {'name':'San Angelo','state':'TX','lat':31.3714,'lon':-100.4925},
    'KSOX': {'name':'Santa Ana Mtns','state':'CA','lat':33.8178,'lon':-117.6358},
    'KSRX': {'name':'Fort Smith','state':'AR','lat':35.2906,'lon':-94.3619},
    'KTBW': {'name':'Tampa','state':'FL','lat':27.7056,'lon':-82.4019},
    'KTFX': {'name':'Great Falls','state':'MT','lat':47.4597,'lon':-111.3853},
    'KTLX': {'name':'Oklahoma City','state':'OK','lat':35.3331,'lon':-97.2778},
    'KTWX': {'name':'Topeka','state':'KS','lat':38.9969,'lon':-96.2325},
    'KTYX': {'name':'Montague','state':'NY','lat':43.7558,'lon':-75.6800},
    'KUDX': {'name':'Rapid City','state':'SD','lat':44.1250,'lon':-102.8300},
    'KUEX': {'name':'Hastings','state':'NE','lat':40.3211,'lon':-98.4417},
    'KVAX': {'name':'Moody AFB','state':'GA','lat':30.8903,'lon':-83.0019},
    'KVBX': {'name':'Vandenberg AFB','state':'CA','lat':34.8381,'lon':-120.3975},
    'KVNX': {'name':'Vance AFB','state':'OK','lat':36.7408,'lon':-98.1275},
    'KVTX': {'name':'Los Angeles','state':'CA','lat':34.4117,'lon':-119.1789},
    'KVWX': {'name':'Evansville','state':'IN','lat':38.2603,'lon':-87.7247},
    'KYUX': {'name':'Yuma','state':'AZ','lat':32.4953,'lon':-114.6558},
    # Puerto Rico
    'TJUA': {'name':'San Juan','state':'PR','lat':18.1156,'lon':-66.0781},
    # Hawaii
    'PHKI': {'name':'South Kauai','state':'HI','lat':21.8942,'lon':-159.5522},
    'PHKM': {'name':'Kohala','state':'HI','lat':20.1256,'lon':-155.7783},
    'PHMO': {'name':'Molokai','state':'HI','lat':21.1328,'lon':-157.1803},
    'PHWA': {'name':'South Point','state':'HI','lat':19.0950,'lon':-155.5689},
    # Alaska
    'PABC': {'name':'Bethel','state':'AK','lat':60.7919,'lon':-161.8764},
    'PACG': {'name':'Sitka','state':'AK','lat':56.8528,'lon':-135.5292},
    'PAEC': {'name':'Nome','state':'AK','lat':64.5114,'lon':-165.2950},
    'PAHG': {'name':'Anchorage','state':'AK','lat':60.7258,'lon':-151.3514},
    'PAKC': {'name':'King Salmon','state':'AK','lat':58.6794,'lon':-156.6294},
    'PAPD': {'name':'Fairbanks','state':'AK','lat':65.0353,'lon':-147.5019},
    # Guam
    'PGUA': {'name':'Andersen AFB','state':'GU','lat':13.4544,'lon':144.8111},
}

# ─── TDWR (Terminal Doppler Weather Radar) — airport radars ───────────────────
# Key is 'T'+3-letter so site_3letter() yields the bucket prefix (TDFW → DFW).
TDWR_SITES = {
    'TADW':{'name':'Washington/Andrews','state':'MD','lat':38.6950,'lon':-76.8450},
    'TATL':{'name':'Atlanta','state':'GA','lat':33.6470,'lon':-84.2620},
    'TBNA':{'name':'Nashville','state':'TN','lat':35.9800,'lon':-86.6620},
    'TBOS':{'name':'Boston','state':'MA','lat':42.1580,'lon':-70.9330},
    'TBWI':{'name':'Baltimore','state':'MD','lat':39.0900,'lon':-76.6300},
    'TCLT':{'name':'Charlotte','state':'NC','lat':35.3370,'lon':-80.8850},
    'TCMH':{'name':'Columbus','state':'OH','lat':40.0060,'lon':-82.7150},
    'TCVG':{'name':'Cincinnati','state':'KY','lat':38.8980,'lon':-84.5800},
    'TDAL':{'name':'Dallas Love','state':'TX','lat':32.9260,'lon':-96.9680},
    'TDAY':{'name':'Dayton','state':'OH','lat':40.0220,'lon':-84.1230},
    'TDCA':{'name':'Washington National','state':'VA','lat':38.7590,'lon':-76.9620},
    'TDEN':{'name':'Denver','state':'CO','lat':39.7270,'lon':-104.5260},
    'TDFW':{'name':'Dallas-Fort Worth','state':'TX','lat':33.0650,'lon':-96.9180},
    'TDTW':{'name':'Detroit','state':'MI','lat':42.1110,'lon':-83.5150},
    'TEWR':{'name':'Newark','state':'NJ','lat':40.5940,'lon':-74.2700},
    'TFLL':{'name':'Fort Lauderdale','state':'FL','lat':26.1430,'lon':-80.3440},
    'THOU':{'name':'Houston Hobby','state':'TX','lat':29.5160,'lon':-95.2420},
    'TIAH':{'name':'Houston Bush','state':'TX','lat':30.0650,'lon':-95.5670},
    'TLAS':{'name':'Las Vegas','state':'NV','lat':36.1440,'lon':-115.0070},
    'TMCI':{'name':'Kansas City','state':'MO','lat':39.4990,'lon':-94.7420},
    'TMCO':{'name':'Orlando','state':'FL','lat':28.3440,'lon':-81.3260},
    'TMDW':{'name':'Chicago Midway','state':'IL','lat':41.6510,'lon':-87.7300},
    'TMEM':{'name':'Memphis','state':'TN','lat':34.8960,'lon':-89.9930},
    'TMIA':{'name':'Miami','state':'FL','lat':25.7580,'lon':-80.4910},
    'TMKE':{'name':'Milwaukee','state':'WI','lat':42.8190,'lon':-88.0460},
    'TMSP':{'name':'Minneapolis','state':'MN','lat':44.8710,'lon':-92.9330},
    'TMSY':{'name':'New Orleans','state':'LA','lat':30.0220,'lon':-90.4030},
    'TOKC':{'name':'Oklahoma City','state':'OK','lat':35.2760,'lon':-97.5100},
    'TORD':{'name':'Chicago O\'Hare','state':'IL','lat':41.7970,'lon':-87.8580},
    'TPBI':{'name':'West Palm Beach','state':'FL','lat':26.6880,'lon':-80.2730},
    'TPHL':{'name':'Philadelphia','state':'PA','lat':39.9490,'lon':-75.0700},
    'TPHX':{'name':'Phoenix','state':'AZ','lat':33.4200,'lon':-112.1630},
    'TPIT':{'name':'Pittsburgh','state':'PA','lat':40.5010,'lon':-80.4860},
    'TRDU':{'name':'Raleigh-Durham','state':'NC','lat':36.0020,'lon':-78.6970},
    'TSDF':{'name':'Louisville','state':'KY','lat':38.0460,'lon':-85.6110},
    'TSJU':{'name':'San Juan','state':'PR','lat':18.4740,'lon':-66.1800},
    'TSLC':{'name':'Salt Lake City','state':'UT','lat':40.9670,'lon':-111.9300},
    'TSTL':{'name':'St. Louis','state':'MO','lat':38.8050,'lon':-90.4890},
    'TTPA':{'name':'Tampa','state':'FL','lat':27.8600,'lon':-82.5180},
    'TTUL':{'name':'Tulsa','state':'OK','lat':36.0710,'lon':-95.8260},
    'TCLE':{'name':'Cleveland','state':'OH','lat':41.2900,'lon':-82.0080},
}
for _k, _v in TDWR_SITES.items():
    _v['tdwr'] = True
SITES.update(TDWR_SITES)

# ─── Level-3 product catalog ──────────────────────────────────────────────────
# cmap: MetPy name or matplotlib name.  scale/bias: physical = (raw-2)*scale + bias
PRODUCTS = {
    # ── Reflectivity ──────────────────────────────────────────────────────────
    'N0B':{'name':'Base Reflectivity 0.5°','unit':'dBZ','cat':'Reflectivity','tilt':0.5,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':90,'cmap':'NWSReflectivity'},
    'N1B':{'name':'Base Reflectivity 1.3°','unit':'dBZ','cat':'Reflectivity','tilt':1.3,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':90,'cmap':'NWSReflectivity'},
    'N2B':{'name':'Base Reflectivity 2.4°','unit':'dBZ','cat':'Reflectivity','tilt':2.4,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':90,'cmap':'NWSReflectivity'},
    'N3B':{'name':'Base Reflectivity 3.1°','unit':'dBZ','cat':'Reflectivity','tilt':3.1,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':90,'cmap':'NWSReflectivity'},
    'N0Q':{'name':'Base Reflectivity 0.5° (8-bit)','unit':'dBZ','cat':'Reflectivity','tilt':0.5,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':90,'cmap':'NWSReflectivity'},
    'N1Q':{'name':'Base Reflectivity 1.3° (8-bit)','unit':'dBZ','cat':'Reflectivity','tilt':1.3,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':90,'cmap':'NWSReflectivity'},
    'N2Q':{'name':'Base Reflectivity 2.4° (8-bit)','unit':'dBZ','cat':'Reflectivity','tilt':2.4,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':90,'cmap':'NWSReflectivity'},
    'N3Q':{'name':'Base Reflectivity 3.1° (8-bit)','unit':'dBZ','cat':'Reflectivity','tilt':3.1,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':90,'cmap':'NWSReflectivity'},
    'N0Z':{'name':'Base Reflectivity 0.5° (legacy)','unit':'dBZ','cat':'Reflectivity','tilt':0.5,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':75,'cmap':'NWSStormClearReflectivity'},
    # ── Velocity ──────────────────────────────────────────────────────────────
    # Super-res digital velocity (modern standard — replaces N0U at most sites)
    'N0G':{'name':'Base Velocity 0.5°','unit':'m/s','cat':'Velocity','tilt':0.5,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N1G':{'name':'Base Velocity 0.9°','unit':'m/s','cat':'Velocity','tilt':0.9,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N2G':{'name':'Base Velocity 1.3°','unit':'m/s','cat':'Velocity','tilt':1.3,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N3G':{'name':'Base Velocity 1.8°','unit':'m/s','cat':'Velocity','tilt':1.8,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N0U':{'name':'Base Velocity 0.5° (digital)','unit':'m/s','cat':'Velocity','tilt':0.5,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N1U':{'name':'Base Velocity 1.3°','unit':'m/s','cat':'Velocity','tilt':1.3,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N2U':{'name':'Base Velocity 2.4°','unit':'m/s','cat':'Velocity','tilt':2.4,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N3U':{'name':'Base Velocity 3.1°','unit':'m/s','cat':'Velocity','tilt':3.1,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N0S':{'name':'Storm-Rel Velocity 0.5°','unit':'m/s','cat':'Velocity','tilt':0.5,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N1S':{'name':'Storm-Rel Velocity 1.3°','unit':'m/s','cat':'Velocity','tilt':1.3,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N2S':{'name':'Storm-Rel Velocity 2.4°','unit':'m/s','cat':'Velocity','tilt':2.4,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'N3S':{'name':'Storm-Rel Velocity 3.1°','unit':'m/s','cat':'Velocity','tilt':3.1,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    # ── Spectrum Width ─────────────────────────────────────────────────────────
    'NSW': {'name':'Spectrum Width 0.5°','unit':'m/s','cat':'Spectrum Width','tilt':0.5,'scale':0.5,'bias':0,'vmin':0,'vmax':10,'cmap':'NWSSpectrumWidth'},
    'NSP': {'name':'Spectrum Width 0.5° (8-bit)','unit':'m/s','cat':'Spectrum Width','tilt':0.5,'scale':0.5,'bias':0,'vmin':0,'vmax':10,'cmap':'NWSSpectrumWidth'},
    # ── Dual-Pol ──────────────────────────────────────────────────────────────
    'N0X':{'name':'Diff. Reflectivity (ZDR) 0.5°','unit':'dB','cat':'Dual-Pol','tilt':0.5,'scale':0.0625,'bias':-7.875,'vmin':-8,'vmax':8,'cmap':'RdYlGn'},
    'N1X':{'name':'Diff. Reflectivity (ZDR) 1.3°','unit':'dB','cat':'Dual-Pol','tilt':1.3,'scale':0.0625,'bias':-7.875,'vmin':-8,'vmax':8,'cmap':'RdYlGn'},
    'N2X':{'name':'Diff. Reflectivity (ZDR) 2.4°','unit':'dB','cat':'Dual-Pol','tilt':2.4,'scale':0.0625,'bias':-7.875,'vmin':-8,'vmax':8,'cmap':'RdYlGn'},
    'N3X':{'name':'Diff. Reflectivity (ZDR) 3.1°','unit':'dB','cat':'Dual-Pol','tilt':3.1,'scale':0.0625,'bias':-7.875,'vmin':-8,'vmax':8,'cmap':'RdYlGn'},
    'N0C':{'name':'Correlation Coeff (CC) 0.5°','unit':'','cat':'Dual-Pol','tilt':0.5,'scale':0.003125,'bias':0.2,'vmin':0.2,'vmax':1.05,'cmap':'plasma'},
    'N1C':{'name':'Correlation Coeff (CC) 1.3°','unit':'','cat':'Dual-Pol','tilt':1.3,'scale':0.003125,'bias':0.2,'vmin':0.2,'vmax':1.05,'cmap':'plasma'},
    'N2C':{'name':'Correlation Coeff (CC) 2.4°','unit':'','cat':'Dual-Pol','tilt':2.4,'scale':0.003125,'bias':0.2,'vmin':0.2,'vmax':1.05,'cmap':'plasma'},
    'N3C':{'name':'Correlation Coeff (CC) 3.1°','unit':'','cat':'Dual-Pol','tilt':3.1,'scale':0.003125,'bias':0.2,'vmin':0.2,'vmax':1.05,'cmap':'plasma'},
    'N0K':{'name':'Specific Diff. Phase (KDP) 0.5°','unit':'°/km','cat':'Dual-Pol','tilt':0.5,'scale':0.05,'bias':-2.0,'vmin':-3,'vmax':20,'cmap':'RdYlGn_r'},
    'N1K':{'name':'Specific Diff. Phase (KDP) 1.3°','unit':'°/km','cat':'Dual-Pol','tilt':1.3,'scale':0.05,'bias':-2.0,'vmin':-3,'vmax':20,'cmap':'RdYlGn_r'},
    'N2K':{'name':'Specific Diff. Phase (KDP) 2.4°','unit':'°/km','cat':'Dual-Pol','tilt':2.4,'scale':0.05,'bias':-2.0,'vmin':-3,'vmax':20,'cmap':'RdYlGn_r'},
    'N3K':{'name':'Specific Diff. Phase (KDP) 3.1°','unit':'°/km','cat':'Dual-Pol','tilt':3.1,'scale':0.05,'bias':-2.0,'vmin':-3,'vmax':20,'cmap':'RdYlGn_r'},
    'N0H':{'name':'Hydrometeor Class (HC) 0.5°','unit':'','cat':'Dual-Pol','tilt':0.5,'scale':1,'bias':0,'vmin':0,'vmax':10,'cmap':'tab10'},
    'N1H':{'name':'Hydrometeor Class (HC) 1.3°','unit':'','cat':'Dual-Pol','tilt':1.3,'scale':1,'bias':0,'vmin':0,'vmax':10,'cmap':'tab10'},
    'N2H':{'name':'Hydrometeor Class (HC) 2.4°','unit':'','cat':'Dual-Pol','tilt':2.4,'scale':1,'bias':0,'vmin':0,'vmax':10,'cmap':'tab10'},
    'N3H':{'name':'Hydrometeor Class (HC) 3.1°','unit':'','cat':'Dual-Pol','tilt':3.1,'scale':1,'bias':0,'vmin':0,'vmax':10,'cmap':'tab10'},
    # ── Precipitation ─────────────────────────────────────────────────────────
    'DPR': {'name':'Digital Precip Rate','unit':'mm/hr','cat':'Precipitation','scale':0.001,'bias':0,'vmin':0,'vmax':150,'cmap':'precipitation'},
    'DAA': {'name':'Digital Accum (1 hr)','unit':'mm','cat':'Precipitation','scale':0.001,'bias':0,'vmin':0,'vmax':150,'cmap':'precipitation'},
    'DTA': {'name':'Digital Total Accum','unit':'mm','cat':'Precipitation','scale':0.001,'bias':0,'vmin':0,'vmax':300,'cmap':'precipitation'},
    'DU3': {'name':'Digital 3-hr Accum','unit':'mm','cat':'Precipitation','scale':0.001,'bias':0,'vmin':0,'vmax':300,'cmap':'precipitation'},
    'DU6': {'name':'Digital 6-hr Accum','unit':'mm','cat':'Precipitation','scale':0.001,'bias':0,'vmin':0,'vmax':300,'cmap':'precipitation'},
    'OHA': {'name':'One-Hour Accumulation','unit':'in','cat':'Precipitation','scale':0.1,'bias':0,'vmin':0,'vmax':10,'cmap':'precipitation'},
    'PTA': {'name':'Storm Total Precip','unit':'in','cat':'Precipitation','scale':0.1,'bias':0,'vmin':0,'vmax':20,'cmap':'precipitation'},
    # ── Derived ───────────────────────────────────────────────────────────────
    'DVL': {'name':'Digital VIL','unit':'kg/m²','cat':'Derived','scale':0.125,'bias':0,'vmin':0,'vmax':70,'cmap':'rainbow'},
    'EET': {'name':'Enhanced Echo Tops','unit':'kft','cat':'Derived','scale':1.0,'bias':-2.0,'vmin':5,'vmax':70,'cmap':'rainbow','mask7bit':True},
    'HHC': {'name':'Hybrid Hydrometeor Class','unit':'','cat':'Derived','scale':1,'bias':0,'vmin':0,'vmax':10,'cmap':'tab10'},
    # ── TDWR (terminal airport radar) — only for TDWR sites ────────────────────
    'TZ0': {'name':'Reflectivity 0.5° (TDWR)','unit':'dBZ','cat':'Reflectivity','tilt':0.5,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':90,'cmap':'NWSReflectivity','tdwr':True},
    'TZL': {'name':'Reflectivity Long-Range (TDWR)','unit':'dBZ','cat':'Reflectivity','tilt':0.5,'scale':0.5,'bias':-32.0,'vmin':-32,'vmax':90,'cmap':'NWSReflectivity','tdwr':True},
    'TV0': {'name':'Velocity 0.5° (TDWR)','unit':'m/s','cat':'Velocity','tilt':0.5,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel','tdwr':True},
    'TV1': {'name':'Velocity Mid-Tilt (TDWR)','unit':'m/s','cat':'Velocity','tilt':1.0,'scale':0.5,'bias':-63.5,'vmin':-70,'vmax':70,'cmap':'NWS8bitVel','tdwr':True},
}

# L2 moment definitions (rendering only, no scale needed here)
L2_MOMENTS = {
    'REF': {'name':'Reflectivity','unit':'dBZ','vmin':-32,'vmax':90,'cmap':'NWSReflectivity'},
    'VEL': {'name':'Velocity','unit':'m/s','vmin':-70,'vmax':70,'cmap':'NWS8bitVel'},
    'SW':  {'name':'Spectrum Width','unit':'m/s','vmin':0,'vmax':10,'cmap':'NWSSpectrumWidth'},
    'ZDR': {'name':'Differential Reflectivity','unit':'dB','vmin':-8,'vmax':8,'cmap':'RdYlGn'},
    'PHI': {'name':'Differential Phase','unit':'°','vmin':0,'vmax':360,'cmap':'hsv'},
    'RHO': {'name':'Correlation Coefficient','unit':'','vmin':0.2,'vmax':1.05,'cmap':'plasma'},
}

# ─── helpers ──────────────────────────────────────────────────────────────────

def site_3letter(icao: str) -> str:
    """KTLX → TLX, PABC → ABC  (drop region prefix)."""
    return icao[1:]


def fetch_url(url: str, cache_key: str) -> pathlib.Path:
    """Download url to cache dir, return path.  Cache-hit returns immediately."""
    h = hashlib.md5(cache_key.encode()).hexdigest()
    path = CACHE / h
    if not path.exists():
        try:
            urllib.request.urlretrieve(url, path)
        except Exception as e:
            if path.exists():
                path.unlink()
            raise
    return path


def list_l3_keys(prefix: str, limit: int = 500, max_pages: int = 25) -> list[str]:
    """
    List S3 object keys with given prefix (Level-3 bucket, anonymous).
    Keys come back in lexicographic = chronological order, so we page through
    ALL of them (bounded by max_pages) and return the NEWEST `limit` keys.
    Returning the first N would yield stale scans on busy days (>1000 keys).
    """
    keys: list[str] = []
    continuation = ''
    for _ in range(max_pages):
        qs = f'?list-type=2&prefix={prefix}&max-keys=1000'
        if continuation:
            qs += f'&continuation-token={urllib.parse.quote(continuation)}'
        url = L3_BASE + '/' + qs
        try:
            with urllib.request.urlopen(url, timeout=12) as r:
                body = r.read().decode()
        except Exception:
            break
        keys += re.findall(r'<Key>([^<]+)</Key>', body)
        if '<IsTruncated>true</IsTruncated>' not in body:
            break
        m = re.search(r'<NextContinuationToken>([^<]+)</NextContinuationToken>', body)
        if not m:
            break
        continuation = m.group(1)
    # Newest `limit` keys (the tail), so callers' keys[-1] is the latest scan.
    return keys[-limit:] if limit else keys


import urllib.parse  # needed for list_l3_keys


# Vivid velocity colormap — bright greens (inbound) → light gray (zero) →
# bright reds/magenta (outbound). Much brighter than the muted NWS 8-bit table.
_BRIGHT_VEL = mcolors.LinearSegmentedColormap.from_list('BrightVel', [
    (0.00, '#19e0e0'),  # strongest inbound — cyan
    (0.12, '#00d000'),
    (0.25, '#22ff22'),  # bright green
    (0.40, '#88ff66'),
    (0.48, '#e8f5e8'),  # near zero — near white
    (0.50, '#f2f2f2'),
    (0.52, '#ffe0e0'),
    (0.60, '#ff6a6a'),
    (0.75, '#ff1010'),  # bright red
    (0.88, '#d00000'),
    (1.00, '#ff30ff'),  # strongest outbound — magenta
])

_CUSTOM_CMAPS = {'BrightVel': _BRIGHT_VEL}


def get_colormap(cmap_name: str):
    """Return a matplotlib colormap — custom, then MetPy, then mpl fallback."""
    if cmap_name in _CUSTOM_CMAPS:
        return _CUSTOM_CMAPS[cmap_name]
    try:
        return colortables.get_colortable(cmap_name)
    except Exception:
        return cm.get_cmap(cmap_name)


def compute_bounds(lat: float, lon: float, range_km: float):
    """Geographic bounding box for a radar circle."""
    lat_off = range_km / 111.32
    lon_off = range_km / (111.32 * math.cos(math.radians(lat)))
    return {
        'south': lat - lat_off,
        'west':  lon - lon_off,
        'north': lat + lat_off,
        'east':  lon + lon_off,
    }


# Range-folded "RF" purple, like RadarScope/GR — shown for velocity/SW so the
# storm's folded returns are visible instead of blank.
_RF_RGBA = (140, 0, 200, 235)


def _azimuth_lookup(start_az: np.ndarray, az_deg: np.ndarray) -> np.ndarray:
    """For each screen azimuth, return the index of the radial pointing closest
    to it. Radials are in scan order and start at an arbitrary azimuth, so a
    direct index = az/step mapping rotates the whole image — this fixes that."""
    az = np.asarray(start_az, dtype=np.float64)
    n = az.shape[0]
    order = np.argsort(az)
    az_sorted = az[order]
    pos = np.searchsorted(az_sorted, az_deg)
    lo = (pos - 1) % n
    hi = pos % n
    d_lo = np.abs(((az_deg - az_sorted[lo] + 180.0) % 360.0) - 180.0)
    d_hi = np.abs(((az_deg - az_sorted[hi] + 180.0) % 360.0) - 180.0)
    return order[np.where(d_lo <= d_hi, lo, hi)]


def polar_to_image(raw: np.ndarray, scale: float, bias: float,
                   vmin: float, vmax: float, cmap_name: str,
                   max_range_km: float, start_az: np.ndarray, alpha: int = 210,
                   show_rf: bool = False, fade_low: bool = False) -> bytes:
    """
    Convert (n_az × n_range) uint8 raw radar array → RGBA PNG bytes.

    raw values: 0 = below threshold (transparent), 1 = RF (range-folded),
    2+ = data. physical = (raw - 2) * scale + bias
    `start_az` is the azimuth of each radial — required because radials do NOT
    begin at north. When show_rf, RF gates are drawn purple (matches RadarScope).
    """
    n_az, n_range = raw.shape
    N = RENDER_PX

    # Build cartesian pixel grid in km from radar center
    half = max_range_km
    lin = np.linspace(-half, half, N)
    xx, yy = np.meshgrid(lin, lin[::-1])   # north = up

    rng_km = np.sqrt(xx ** 2 + yy ** 2)
    az_deg = np.degrees(np.arctan2(xx, yy)) % 360.0   # bearing from north, cw

    km_per_bin = max_range_km / n_range

    az_idx  = _azimuth_lookup(start_az, az_deg)        # correct radial per pixel
    rng_idx = np.clip((rng_km / km_per_bin).astype(np.int32), 0, n_range - 1)

    sampled = raw[az_idx, rng_idx]
    in_range = rng_km <= max_range_km
    valid    = in_range & (sampled >= 2)

    phys = np.where(valid, (sampled.astype(np.float32) - 2) * scale + bias, 0.0)

    cmap = get_colormap(cmap_name)
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)

    rgba = (cmap(norm(phys)) * 255).astype(np.uint8)
    rgba[~valid, 3] = 0
    rgba[valid,  3] = alpha

    if fade_low:
        # Fade clear-air / noise (low dBZ) so precipitation stands out — keeps
        # sensitive radars (esp. TDWR) from going all-green. Clear-air stays
        # faintly visible; storms (>~20 dBZ) render at full opacity.
        ramp = np.clip((phys + 10.0) / 30.0, 0.0, 1.0)  # ~0 at -10dBZ, full by 20
        a = (ramp * alpha).astype(np.uint8)
        rgba[..., 3] = np.where(valid, a, 0)

    if show_rf:
        rf = in_range & (sampled == 1)
        rgba[rf] = _RF_RGBA

    img = Image.fromarray(rgba, 'RGBA')
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=False)
    return buf.getvalue()


# ─── Level-3 rendering ────────────────────────────────────────────────────────

# ─── In-memory parsed-data cache (avoids re-parsing on every probe call) ─────
_L3_CACHE: dict = {}
_L3_CACHE_MAX = 40


_PRECIP_VCPS = {11,12,21,80,90,112,121,211,212,215,221}
_CLEAR_VCPS  = {31,32,35}

def vcp_mode(vcp: int) -> str:
    if vcp in _CLEAR_VCPS:  return f'VCP {vcp}: Clear Air Mode'
    if vcp in _PRECIP_VCPS: return f'VCP {vcp}: Precipitation Mode'
    return f'VCP {vcp}' if vcp else ''


def get_parsed_l3(key: str) -> dict:
    """Parse a Level-3 key, caching the numpy array so probe calls are instant."""
    if key in _L3_CACHE:
        return _L3_CACHE[key]
    path = fetch_url(f'{L3_BASE}/{key}', f'l3_{key}')
    f3 = Level3File(str(path))
    d  = f3.sym_block[0][0]
    if not isinstance(d, dict) or 'data' not in d:
        raise ValueError('Non-radial product (text/raster format).')
    raw = np.asarray(d['data'], dtype=np.uint8)
    if raw.ndim != 2:
        raise ValueError('Data is not a 2-D radial array.')
    vcp_raw = getattr(f3.prod_desc, 'vcp', 0) or 0
    # Azimuth of each radial — radials do NOT start at 0°/north, so we must keep
    # the real start_az to map screen direction → correct radial.
    start_az = np.asarray(d.get('start_az', np.arange(raw.shape[0]) * (360.0 / raw.shape[0])),
                          dtype=np.float64)
    parsed = {
        'data':      raw,
        'start_az':  start_az,
        'max_range': float(f3.max_range),
        'lat':       float(f3.lat),
        'lon':       float(f3.lon),
        'thr1':      f3.prod_desc.thr1,
        'thr2':      f3.prod_desc.thr2,
        'vcp':       int(vcp_raw),
    }
    if len(_L3_CACHE) >= _L3_CACHE_MAX:
        del _L3_CACHE[next(iter(_L3_CACHE))]
    _L3_CACHE[key] = parsed
    return parsed


def latlon_to_polar(probe_lat: float, probe_lon: float,
                    radar_lat: float, radar_lon: float,
                    start_az: np.ndarray, max_range_km: float, n_range: int):
    """Convert probe lat/lon to (radial_idx, rng_idx, dist_km, az_deg)."""
    R = 6371.0
    lat1, lat2 = math.radians(radar_lat), math.radians(probe_lat)
    dlat = math.radians(probe_lat - radar_lat)
    dlon = math.radians(probe_lon - radar_lon)
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    dist_km = R * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlon)
    az_deg = math.degrees(math.atan2(y, x)) % 360.0
    # nearest actual radial to this azimuth (radials don't start at north)
    az = np.asarray(start_az, dtype=np.float64)
    radial_idx = int(np.argmin(np.abs(((az - az_deg + 180.0) % 360.0) - 180.0)))
    rng_idx = min(int(dist_km / (max_range_km / n_range)), n_range - 1)
    return radial_idx, rng_idx, dist_km, az_deg


def render_l3(key: str) -> tuple[bytes, dict]:
    """Download + parse + render a Level-3 key. Returns (png_bytes, bounds_dict)."""
    p   = get_parsed_l3(key)      # uses cache
    raw = p['data']

    parts    = key.split('_')
    prod_key = parts[1] if len(parts) > 1 else ''
    pinfo    = PRODUCTS.get(prod_key, {})

    scale = pinfo.get('scale', p['thr2'] / 10.0 if p['thr2'] else 0.5)
    bias  = pinfo.get('bias',  p['thr1'] / 10.0 if p['thr1'] else -32.0)
    vmin  = pinfo.get('vmin', -32)
    vmax  = pinfo.get('vmax',  90)
    cmap  = pinfo.get('cmap', 'NWSReflectivity')
    alpha = 215
    # Velocity/Spectrum-Width: draw range-folded (RF) gates purple like RadarScope
    show_rf  = pinfo.get('cat') in ('Velocity', 'Spectrum Width')
    # Reflectivity: fade clear-air so storms pop (esp. for sensitive TDWR)
    fade_low = pinfo.get('cat') == 'Reflectivity'

    # Some products bit-pack a flag in bit 7 (e.g. Enhanced Echo Tops uses 0x80
    # as a "topped" flag; the height is the low 7 bits). Strip it before scaling.
    if pinfo.get('mask7bit'):
        raw = raw & 0x7F

    png    = polar_to_image(raw, scale, bias, vmin, vmax, cmap, p['max_range'],
                            p['start_az'], alpha, show_rf, fade_low)
    bounds = compute_bounds(p['lat'], p['lon'], p['max_range'])
    return png, bounds


# ─── Level-2 listing ──────────────────────────────────────────────────────────

def list_l2_scans(icao: str, date_str: str) -> list[str]:
    """
    List Level-2 scan file keys for a site on a given YYYY-MM-DD date.
    The noaa-nexrad-level2 bucket requires AWS credentials for listing.
    Returns keys if accessible, empty list otherwise.
    """
    y, mo, d = date_str.split('-')
    prefix = f'{y}/{mo}/{d}/{icao.upper()}/'
    # Try boto3 with anonymous credentials first; the bucket is registered
    # under the NOAA Open Data program but may require a (free) AWS account.
    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
        s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED),
                          region_name='us-east-1')
        r = s3.list_objects_v2(Bucket='noaa-nexrad-level2', Prefix=prefix, MaxKeys=500)
        keys = [o['Key'] for o in r.get('Contents', [])]
        return [k for k in keys if '_V06' in k and not k.endswith('MDM')]
    except Exception:
        pass
    # Fallback: unidata real-time Level-2 chunks bucket (sub-volume chunks)
    try:
        chunk_prefix = f'{icao.upper()}/{y}{mo}{d}/'
        url = f'https://unidata-nexrad-level2-chunks.s3.amazonaws.com/?list-type=2&prefix={chunk_prefix}&max-keys=500'
        with urllib.request.urlopen(url) as r2:
            body = r2.read().decode()
        keys = re.findall(r'<Key>([^<]+)</Key>', body)
        return keys
    except Exception:
        return []


# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title='NEXRAD Radar Viewer')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


@app.middleware('http')
async def _no_cache_dynamic(request, call_next):
    """
    Stop the embedded browser from caching live-data responses. Without this,
    Chromium/WebView2 heuristically caches /api/l3/latest and /api/l3/scans, so
    the 60-second poll keeps getting the SAME stale scan key and the radar never
    advances — i.e. it stops being real-time. Render/colorbar are content-keyed
    (unique per scan) so they keep their caching.
    """
    resp = await call_next(request)
    path = request.url.path
    if path.startswith('/api/') and ('/render' not in path) and ('colorbar' not in path):
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    return resp


@app.get('/api/sites')
def api_sites():
    return SITES


@app.get('/api/products')
def api_products():
    grouped: dict[str, list] = {}
    for code, info in PRODUCTS.items():
        cat = info['cat']
        grouped.setdefault(cat, []).append({'code': code, **info})
    return grouped


@app.get('/api/l1/info')
def api_l1_info():
    return {
        'description': (
            'NEXRAD Level-I (time-series / IQ) data is available via NOAA\'s '
            'National Centers for Environmental Information (NCEI). '
            'It is not distributed in real-time on public S3 buckets.'
        ),
        'access_url': 'https://www.ncdc.noaa.gov/nexradinv/',
        'note': (
            'Level-I files are very large (several GB per site per day) and require '
            'specialised software (e.g. RadxConvert, LROSE) to process.'
        ),
    }


@app.get('/api/l2/scans')
def api_l2_scans(site: str = Query(...), date: str = Query(...)):
    """List Level-2 scans for a site (ICAO) on a date (YYYY-MM-DD)."""
    if site.upper() not in SITES:
        raise HTTPException(404, 'Unknown site')
    keys = list_l2_scans(site.upper(), date)
    # Return just the filename, not the full S3 key
    return {'keys': keys, 'count': len(keys)}


@app.get('/api/l2/moments')
def api_l2_moments():
    return L2_MOMENTS


@app.get('/api/l3/scans')
def api_l3_scans(
    site: str = Query(...),
    product: str = Query(...),
    date: Optional[str] = Query(None, description='YYYY-MM-DD'),
    frames: int = Query(50, ge=1, le=400, description='how many recent frames to return'),
):
    """
    List the most-recent Level-3 scan keys for site + product.
    Only returns the newest `frames` keys (what the user is actually viewing),
    not the whole day — keys[-1] is always the latest scan.
    """
    site_id = site_3letter(site.upper())
    prefix  = f'{site_id}_{product.upper()}'
    if date:
        ymd = date.replace('-', '_')
        prefix += f'_{ymd}'
    keys = list_l3_keys(prefix, limit=frames)
    return {'keys': keys, 'count': len(keys)}


@app.get('/api/l3/latest')
def api_l3_latest(site: str = Query(...), product: str = Query(...)):
    """Return the most recent Level-3 scan key for site + product."""
    from datetime import datetime, timezone, timedelta
    site_id = site_3letter(site.upper())
    prod    = product.upper()

    # Use UTC (the bucket is organised by UTC date), newest day first.
    now = datetime.now(timezone.utc)
    for delta in range(3):
        d = now - timedelta(days=delta)
        prefix = f'{site_id}_{prod}_{d.strftime("%Y_%m_%d")}'
        keys = list_l3_keys(prefix, limit=10)
        if keys:
            return {'key': keys[-1], 'date': d.strftime('%Y-%m-%d')}

    raise HTTPException(404, f'No recent scans found for {site}/{product}')


@app.get('/api/l3/render')
def api_l3_render(key: str = Query(...)):
    """
    Render a Level-3 scan as a transparent RGBA PNG.
    Response headers include X-Radar-Bounds: south,west,north,east
    """
    try:
        png, bounds = render_l3(key)
    except FileNotFoundError:
        raise HTTPException(404, f'Scan not found: {key}')
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f'Render error: {e}')

    bounds_str = f"{bounds['south']:.5f},{bounds['west']:.5f},{bounds['north']:.5f},{bounds['east']:.5f}"
    p   = _L3_CACHE.get(key, {})
    vcp = p.get('vcp', 0)
    return Response(
        content=png,
        media_type='image/png',
        headers={
            'X-Radar-Bounds': bounds_str,
            'X-Radar-VCP':    str(vcp),
            'X-Radar-Mode':   vcp_mode(vcp),
            'Cache-Control':  'max-age=60',
        },
    )


@app.get('/api/l3/colorbar_strip')
def api_l3_colorbar_strip(product: str = Query(...), width: int = 600, height: int = 7):
    """Return just the color gradient with no labels (for the thin top strip)."""
    pinfo = PRODUCTS.get(product.upper())
    if not pinfo:
        raise HTTPException(404, 'Unknown product')
    cmap  = get_colormap(pinfo['cmap'])
    norm  = mcolors.Normalize(vmin=pinfo['vmin'], vmax=pinfo['vmax'])
    x     = np.linspace(pinfo['vmin'], pinfo['vmax'], width)
    rgb   = (cmap(norm(x))[:, :3] * 255).astype(np.uint8)
    arr   = np.tile(rgb[np.newaxis, :, :], (height, 1, 1))
    img   = Image.fromarray(arr, 'RGB')
    buf   = io.BytesIO()
    img.save(buf, 'PNG')
    return Response(content=buf.getvalue(), media_type='image/png',
                    headers={'Cache-Control': 'max-age=3600'})


@app.get('/api/l3/colorbar')
def api_l3_colorbar(product: str = Query(...), width: int = 300, height: int = 30):
    """Return a horizontal colorbar PNG for a product."""
    pinfo = PRODUCTS.get(product.upper())
    if not pinfo:
        raise HTTPException(404, 'Unknown product')

    cmap = get_colormap(pinfo['cmap'])
    norm = mcolors.Normalize(vmin=pinfo['vmin'], vmax=pinfo['vmax'])

    # Use Figure directly (thread-safe; avoids global pyplot state)
    fig = Figure(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_alpha(0)
    ax = fig.add_axes([0.05, 0.4, 0.9, 0.45])
    fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap), cax=ax, orientation='horizontal')
    unit = pinfo.get('unit', '')
    label = f"{pinfo['name']} ({unit})" if unit else pinfo['name']
    ax.set_xlabel(label, fontsize=7, color='white')
    ax.tick_params(labelsize=6, colors='white')
    for spine in ax.spines.values():
        spine.set_edgecolor('white')

    buf = io.BytesIO()
    FigureCanvasAgg(fig).print_png(buf)
    return Response(content=buf.getvalue(), media_type='image/png')


@app.get('/api/l3/probe')
def api_l3_probe(
    key: str   = Query(...),
    lat: float = Query(...),
    lon: float = Query(...),
):
    """Return the radar value at a specific lat/lon for a given scan key."""
    try:
        p = get_parsed_l3(key)
    except Exception as e:
        raise HTTPException(422, str(e))

    raw = p['data']
    n_az, n_range = raw.shape
    az_idx, rng_idx, dist_km, az_deg = latlon_to_polar(
        lat, lon, p['lat'], p['lon'], p['start_az'], p['max_range'], n_range
    )

    parts    = key.split('_')
    prod_key = parts[1] if len(parts) > 1 else ''
    pinfo    = PRODUCTS.get(prod_key, {})
    scale = pinfo.get('scale', p['thr2'] / 10.0 if p['thr2'] else 0.5)
    bias  = pinfo.get('bias',  p['thr1'] / 10.0 if p['thr1'] else -32.0)
    unit  = pinfo.get('unit', '')

    if dist_km > p['max_range']:
        return {'value': None, 'display': 'OOR', 'unit': unit,
                'dist_km': round(dist_km, 1), 'az': round(az_deg, 1)}

    rv = int(raw[az_idx, rng_idx])
    if pinfo.get('mask7bit'):
        rv &= 0x7F   # strip the "topped" flag (e.g. Enhanced Echo Tops)
    if rv < 2:
        return {'value': None, 'display': 'ND', 'unit': unit,
                'dist_km': round(dist_km, 1), 'az': round(az_deg, 1)}

    phys = (rv - 2) * scale + bias
    return {
        'value':   round(float(phys), 2),
        'display': f'{phys:.1f}',
        'unit':    unit,
        'raw':     rv,
        'dist_km': round(dist_km, 1),
        'az':      round(az_deg, 1),
    }


import json as _json
import time as _time

_HTTP_CACHE: dict = {}   # url -> (expires_ts, bytes)


def _fetch_raw(url: str, timeout: int = 12, ttl: int = 60) -> bytes:
    """Fetch a URL with a small TTL cache. Returns raw bytes."""
    now = _time.time()
    hit = _HTTP_CACHE.get(url)
    if hit and hit[0] > now:
        return hit[1]
    req = urllib.request.Request(url, headers={'User-Agent': 'NEXRAD-Viewer/1.0 (radar app)'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    _HTTP_CACHE[url] = (now + ttl, data)
    return data


def _upstream_json(url: str, timeout: int = 12, ttl: int = 60) -> Response:
    """Proxy an upstream JSON URL through the backend (avoids browser CORS issues)."""
    try:
        data = _fetch_raw(url, timeout, ttl)
        return Response(content=data, media_type='application/json',
                        headers={'Cache-Control': f'max-age={ttl}',
                                 'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        raise HTTPException(502, f'Upstream error: {e}')


def _json_response(obj) -> Response:
    return Response(content=_json.dumps(obj), media_type='application/json',
                    headers={'Access-Control-Allow-Origin': '*'})


# ─── NWS alert category keyword filters ──────────────────────────────────────
_ALERT_CATS = {
    'all':     None,
    # Storm-based WARNINGS only — tight polygons that follow actual storms
    # (no broad marine advisories / watches / statements that sit over clear air).
    'stormwarn': ('Tornado Warning', 'Severe Thunderstorm Warning',
                  'Flash Flood Warning', 'Special Marine Warning',
                  'Snow Squall Warning', 'Extreme Wind Warning', 'Dust Storm Warning'),
    'severe':  ('Tornado', 'Severe Thunderstorm', 'Extreme Wind', 'Dust Storm'),
    'tropical':('Hurricane', 'Tropical Storm', 'Storm Surge', 'Tropical Depression', 'Typhoon'),
    'flood':   ('Flood', 'Flash Flood', 'Hydrologic', 'Seiche'),
    'fire':    ('Red Flag', 'Fire Weather', 'Fire Warning'),
    'winter':  ('Winter', 'Snow', 'Ice Storm', 'Blizzard', 'Freeze', 'Frost',
                'Wind Chill', 'Cold', 'Lake Effect', 'Avalanche', 'Sleet'),
    'marine':  ('Small Craft', 'Gale', 'Marine', 'Hurricane Force', 'Storm Warning',
                'Ashfall', 'Brisk Wind', 'Hazardous Seas', 'Rip Current', 'Beach'),
    'heat':    ('Heat', 'Excessive Heat'),
    'wind':    ('Wind Advisory', 'High Wind', 'Extreme Wind', 'Lake Wind'),
}


@app.get('/api/overlay/alerts')
def api_overlay_alerts(cat: str = Query('all')):
    """Active NWS alerts, optionally filtered to a category by event keywords."""
    cat = cat.lower()
    if cat not in _ALERT_CATS:
        raise HTTPException(400, f'Unknown category: {cat}')
    try:
        raw = _fetch_raw(
            'https://api.weather.gov/alerts/active?status=actual&message_type=alert',
            ttl=15,   # keep up with rapidly-issued warnings during severe weather
        )
        data = _json.loads(raw)
    except Exception as e:
        raise HTTPException(502, f'NWS error: {e}')

    keywords = _ALERT_CATS[cat]
    feats = data.get('features', [])
    if keywords:
        kw = tuple(k.lower() for k in keywords)
        feats = [f for f in feats
                 if any(k in (f.get('properties', {}).get('event', '') or '').lower()
                        for k in kw)]
    return _json_response({'type': 'FeatureCollection', 'features': feats})


# ─── Zone-geometry resolution (for zone-based alerts like watches) ────────────
import concurrent.futures
_ZONE_CACHE: dict = {}   # UGC -> geometry dict (or None)


def _zone_geometry(ugc: str):
    """Resolve a UGC code (e.g. 'SDC033') to its polygon via the NWS zone API."""
    if ugc in _ZONE_CACHE:
        return _ZONE_CACHE[ugc]
    geom = None
    try:
        typ = 'county' if len(ugc) >= 3 and ugc[2] == 'C' else 'forecast'
        raw = _fetch_raw(f'https://api.weather.gov/zones/{typ}/{ugc}', ttl=86400)
        geom = _json.loads(raw).get('geometry')
    except Exception:
        geom = None
    _ZONE_CACHE[ugc] = geom
    return geom


def _resolve_zone_features(features: list) -> list:
    """Give null-geometry alerts a polygon built from their UGC county zones."""
    need = set()
    for f in features:
        if not f.get('geometry'):
            for u in f.get('properties', {}).get('geocode', {}).get('UGC', []):
                if u not in _ZONE_CACHE:
                    need.add(u)
    if need:
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            list(ex.map(_zone_geometry, need))
    out = []
    for f in features:
        if f.get('geometry'):
            out.append(f)
            continue
        polys = []
        for u in f.get('properties', {}).get('geocode', {}).get('UGC', []):
            g = _zone_geometry(u)
            if not g:
                continue
            if g['type'] == 'Polygon':
                polys.append(g['coordinates'])
            elif g['type'] == 'MultiPolygon':
                polys.extend(g['coordinates'])
        if polys:
            f = dict(f)
            f['geometry'] = {'type': 'MultiPolygon', 'coordinates': polys}
        out.append(f)
    return out


@app.get('/api/overlay/watches')
def api_overlay_watches():
    """Tornado / Severe T-storm / Flash Flood WATCHES with county shapes resolved."""
    try:
        data = _json.loads(_fetch_raw(
            'https://api.weather.gov/alerts/active?status=actual&message_type=alert', ttl=15))
    except Exception as e:
        raise HTTPException(502, f'NWS error: {e}')
    kw = ('tornado watch', 'severe thunderstorm watch', 'flash flood watch')
    feats = [f for f in data.get('features', [])
             if any(k in (f.get('properties', {}).get('event', '') or '').lower() for k in kw)]
    feats = _resolve_zone_features(feats)
    return _json_response({'type': 'FeatureCollection', 'features': feats})


@app.get('/api/overlay/mesoscale')
def api_overlay_mesoscale():
    """SPC Mesoscale Discussions (active), polygon geometry."""
    return _upstream_json(
        'https://mesonet.agron.iastate.edu/api/1/nws/spc_mcd.geojson', ttl=120)


# phenomena code → event name (IEM SBW)
_PHEN_EVENT = {
    'TO': 'Tornado Warning', 'SV': 'Severe Thunderstorm Warning',
    'FF': 'Flash Flood Warning', 'FA': 'Areal Flood Warning',
    'MA': 'Special Marine Warning', 'SQ': 'Snow Squall Warning',
    'EW': 'Extreme Wind Warning', 'DS': 'Dust Storm Warning',
}


# Default radar warnings = storm-based warning POLYGONS from IEM SBW. This feed
# is built straight from the raw NWS warning products (LDM) and is far more
# complete/timely than api.weather.gov/alerts/active, which badly under-reports
# during high-volume severe weather. Falls back to the NWS API on error.
@app.get('/api/overlay/warnings')
def api_overlay_warnings():
    from datetime import datetime, timezone
    try:
        data = _json.loads(_fetch_raw(
            'https://mesonet.agron.iastate.edu/geojson/sbw.geojson', ttl=20))
    except Exception:
        return api_overlay_alerts('stormwarn')

    now = datetime.now(timezone.utc)
    best = {}
    for f in data.get('features', []):
        p = f.get('properties', {})
        if p.get('significance') != 'W' or not f.get('geometry'):
            continue
        if p.get('status') in ('CAN', 'EXP', 'UPG'):
            continue
        ev = _PHEN_EVENT.get(p.get('phenomena'))
        if not ev:
            continue
        exp = p.get('expire_utc') or p.get('expire')
        try:
            if exp and datetime.fromisoformat(exp.replace('Z', '+00:00')) < now:
                continue
        except Exception:
            pass
        params = {}
        if p.get('hailtag'):   params['maxHailSize'] = [str(p['hailtag'])]
        if p.get('windtag'):   params['maxWindGust'] = [f"{int(float(p['windtag']))} mph"]
        if p.get('tornadotag'):params['tornadoDetection'] = [p['tornadotag']]
        if p.get('damagetag'): params['thunderstormDamageThreat'] = [p['damagetag']]
        if p.get('floodtag_damage'): params['flashFloodDamageThreat'] = [p['floodtag_damage']]
        key = f"{p.get('wfo')}-{p.get('phenomena')}-{p.get('eventid')}"
        feat = {
            'type': 'Feature', 'geometry': f['geometry'], 'id': key,
            'properties': {
                'event': ev, 'expires': exp, 'ends': exp,
                'parameters': params, 'senderName': p.get('wfo', ''),
                'areaDesc': '', 'description': '',
                'isEmergency': p.get('is_emergency'), 'href': p.get('href'),
                'product_id': p.get('product_id'),   # for on-demand full text
            },
        }
        prev = best.get(key)
        if not prev or (p.get('issue', '') > prev[1]):
            best[key] = (feat, p.get('issue', ''))
    return _json_response({'type': 'FeatureCollection',
                           'features': [v[0] for v in best.values()]})


@app.get('/api/alert/text')
def api_alert_text(pid: str = Query(...)):
    """Fetch the full raw NWS product text for a warning, by IEM product_id."""
    if not re.fullmatch(r'[0-9A-Za-z_\-]+', pid):
        raise HTTPException(400, 'bad product id')
    try:
        txt = _fetch_raw(
            f'https://mesonet.agron.iastate.edu/api/1/nwstext/{pid}', ttl=600
        ).decode('utf-8', 'replace')
    except Exception as e:
        raise HTTPException(502, f'text fetch error: {e}')
    return Response(content=txt, media_type='text/plain',
                    headers={'Cache-Control': 'max-age=600',
                             'Access-Control-Allow-Origin': '*'})


# Everything (incl. marine advisories, watches, statements) for those who want it
@app.get('/api/overlay/allalerts')
def api_overlay_allalerts():
    return api_overlay_alerts('all')


@app.get('/api/overlay/spc/{layer}')
def api_overlay_spc(layer: str):
    if layer not in {'cat', 'torn', 'wind', 'hail'}:
        raise HTTPException(400, 'Invalid layer')
    return _upstream_json(
        f'https://www.spc.noaa.gov/products/outlook/day1otlk_{layer}.nolyr.geojson',
        ttl=300,
    )


@app.get('/api/overlay/metar')
def api_overlay_metar():
    return _upstream_json(
        'https://aviationweather.gov/api/data/metar'
        '?bbox=-130,24,-60,50&format=geojson&taf=false&hours=1',
        ttl=300,
    )


@app.get('/api/overlay/lsr')
def api_overlay_lsr(hours: int = 24):
    """Local Storm Reports (Iowa Environmental Mesonet)."""
    return _upstream_json(
        f'https://mesonet.agron.iastate.edu/geojson/lsr.geojson?hours={hours}',
        ttl=120,
    )


@app.get('/api/overlay/sps')
def api_overlay_sps():
    """Special Weather Statements (polygon)."""
    return _upstream_json(
        'https://mesonet.agron.iastate.edu/geojson/sps.geojson', ttl=120,
    )


@app.get('/api/overlay/sbw')
def api_overlay_sbw():
    """Storm-Based Warnings (precise warning polygons)."""
    return _upstream_json(
        'https://mesonet.agron.iastate.edu/geojson/sbw.geojson', ttl=60,
    )


@app.get('/api/overlay/spotter')
def api_overlay_spotter():
    """
    Spotter Network active spotters → GeoJSON.
    Parses the Placefile feed (no API key needed for the public positions feed).
    """
    try:
        raw = _fetch_raw('https://www.spotternetwork.org/feeds/reports.txt', ttl=60)
        text = raw.decode('utf-8', 'replace')
    except Exception as e:
        raise HTTPException(502, f'Spotter Network error: {e}')

    feats = []
    cur_latlon = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('Object:'):
            try:
                _, coords = line.split(':', 1)
                la, lo = coords.split(',')
                cur_latlon = (float(la), float(lo))
            except Exception:
                cur_latlon = None
        elif cur_latlon and (line.startswith('Text:') or line.startswith('Icon:')):
            # Label is the last quoted string on the line, if any
            label = ''
            if '"' in line:
                label = line.rsplit('"', 2)[-2] if line.count('"') >= 2 else ''
            feats.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [cur_latlon[1], cur_latlon[0]]},
                'properties': {'label': label or 'Spotter'},
            })
            cur_latlon = None  # one marker per object
        elif line == 'End:':
            cur_latlon = None
    return _json_response({'type': 'FeatureCollection', 'features': feats})


@app.get('/api/geoip')
def api_geoip():
    """Approximate location from IP (GPS fallback for the desktop app)."""
    try:
        raw = _fetch_raw('http://ip-api.com/json/?fields=status,lat,lon,city,region', ttl=3600)
        d = _json.loads(raw)
        if d.get('status') == 'success':
            return {'lat': d['lat'], 'lon': d['lon'],
                    'city': d.get('city', ''), 'region': d.get('region', '')}
    except Exception:
        pass
    # Fallback: center of CONUS
    return {'lat': 39.5, 'lon': -98.35, 'city': '', 'region': ''}


# ═══════════════════════════════════════════════════════════════════════════
# RadarHub research radars  (OU Advanced Radar Research Center)
# ─────────────────────────────────────────────────────────────────────────
# Public real-time HTTP archive feed at https://radarhub.arrc.ou.edu serves
# full polar sweeps (one small binary file per scan + moment). We decode them
# and push them through the SAME map-overlay pipeline as NEXRAD, using
# RadarHub's own colormap.png for a pixel-faithful match. No WebSocket needed —
# the /data/ archive endpoints give complete sweeps with ~20 s latency,
# cacheable and far more reliable than the ray-by-ray socket stream.
# Confirmed live pathways: px1000 (PX-1000), px10k (PX-10k), raxpol (RaXPol).
# ═══════════════════════════════════════════════════════════════════════════
RADARHUB_BASE = 'https://radarhub.arrc.ou.edu'

# lat/lon are defaults for the map marker. The sweep file carries its own
# lat/lon, so render bounds always use the true location (RaXPol is mobile).
RADARHUB_SITES = {
    'PX1000': {'name':'PX-1000','state':'OK','lat':34.9824,'lon':-97.5207,'pathway':'px1000','radarhub':True},
    'PX10K':  {'name':'PX-10k','state':'OK','lat':35.2369,'lon':-97.4638,'pathway':'px10k','radarhub':True},
    'RAXPOL': {'name':'RaXPol','state':'OK','lat':35.1817,'lon':-97.4380,'pathway':'raxpol','radarhub':True,'mobile':True},
}
SITES.update(RADARHUB_SITES)

# Moments. symbol = RadarHub one-letter code; row = row index in colormap.png.
RADARHUB_PRODUCTS = {
    'RHZ': {'name':'Reflectivity','unit':'dBZ','cat':'Reflectivity','symbol':'Z','row':0,'radarhub':True},
    'RHV': {'name':'Velocity','unit':'m/s','cat':'Velocity','symbol':'V','row':1,'radarhub':True},
    'RHW': {'name':'Spectrum Width','unit':'m/s','cat':'Spectrum Width','symbol':'W','row':2,'radarhub':True},
    'RHD': {'name':'Diff. Reflectivity (ZDR)','unit':'dB','cat':'Dual-Pol','symbol':'D','row':3,'radarhub':True},
    'RHP': {'name':'Diff. Phase (PhiDP)','unit':'deg','cat':'Dual-Pol','symbol':'P','row':4,'radarhub':True},
    'RHR': {'name':'Correlation Coeff (CC)','unit':'','cat':'Dual-Pol','symbol':'R','row':5,'radarhub':True},
}


def _rh_site(site: str) -> dict:
    s = RADARHUB_SITES.get((site or '').upper())
    if not s:
        raise HTTPException(404, f'Unknown RadarHub site: {site}')
    return s


def _rh_prod(product: str) -> dict:
    p = RADARHUB_PRODUCTS.get((product or '').upper())
    if not p:
        raise HTTPException(404, f'Unknown RadarHub product: {product}')
    return p


# RadarHub's /data/ API rejects requests that don't advertise gzip (its
# is_dirty_request guard → HTTP 405), so every call must send Accept-Encoding.
_RH_JSON_CACHE: dict = {}


def _rh_get(url: str, ttl: int = 12) -> bytes:
    now = _time.time()
    hit = _RH_JSON_CACHE.get(url)
    if hit and hit[0] > now:
        return hit[1]
    req = urllib.request.Request(url, headers={
        'User-Agent': 'NEXRAD-Viewer/1.0 (radar app)', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = r.read()
        enc = r.headers.get('Content-Encoding', '')
    if enc == 'gzip' or data[:2] == b'\x1f\x8b':
        import gzip as _gz
        data = _gz.decompress(data)
    _RH_JSON_CACHE[url] = (now + ttl, data)
    return data


# ── colormap (downloaded once, cached on disk + in memory) ──────────────────
_RH_LUT = None   # ndarray (rows, 256, 4) uint8


def radarhub_luts():
    """RadarHub's colormap.png as a (rows, 256, 4) uint8 LUT. Row order:
    0=Z 1=V 2=W 3=ZDR 4=PhiDP 5=RhoHV 6=labels. Indexed directly by gate byte."""
    global _RH_LUT
    if _RH_LUT is not None:
        return _RH_LUT
    data = None
    cpath = CACHE / 'radarhub_colormap.png'
    try:
        if cpath.exists():
            data = cpath.read_bytes()
    except Exception:
        data = None
    if not data:
        data = _rh_get(f'{RADARHUB_BASE}/static/images/colormap.png?v=20230822', ttl=86400)
        try:
            cpath.write_bytes(data)
        except Exception:
            pass
    im = Image.open(io.BytesIO(data)).convert('RGBA')
    _RH_LUT = np.asarray(im, dtype=np.uint8).copy()
    return _RH_LUT


# ── binary sweep fetch + decode ─────────────────────────────────────────────
def _rh_fetch_binary(url: str, cache_key: str) -> bytes:
    """Download a RadarHub binary (sets a non-blocked UA). Each scan key is
    unique + immutable, so we cache to disk forever once fetched."""
    h = hashlib.md5(cache_key.encode()).hexdigest()
    path = CACHE / ('rhb_' + h)
    if path.exists():
        try:
            return path.read_bytes()
        except Exception:
            pass
    req = urllib.request.Request(url, headers={
        'User-Agent': 'NEXRAD-Viewer/1.0 (radar app)', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
        enc = r.headers.get('Content-Encoding', '')
    if enc == 'gzip' or data[:2] == b'\x1f\x8b':
        import gzip as _gz
        data = _gz.decompress(data)
    try:
        path.write_bytes(data)
    except Exception:
        pass
    return data


def radarhub_decode(buf: bytes) -> dict:
    """Decode a RadarHub sweep blob (little-endian). Layout (from the project's
    sweepParser): nb,nr,nx,attr u16; time,lat,lon,alt f64; offXYZ+pad f32×4;
    sweepEl,sweepAz,rangeStart,rangeSpacing f32; info[nx]; ei16[nb]; au16[nb];
    values[nb*nr] u8 (beam-major)."""
    o = 0
    nb, nr, nx, attr = struct.unpack_from('<HHHH', buf, o); o += 8
    t, lat, lon, alt = struct.unpack_from('<dddd', buf, o); o += 32
    o += 16  # offsetX, offsetY, offsetZ, _notused4 (bistatic; unused for PPI)
    sweep_el, sweep_az, r_start, r_spacing = struct.unpack_from('<ffff', buf, o); o += 16
    info = buf[o:o + nx].decode('utf-8', 'replace'); o += nx
    ei16 = np.frombuffer(buf, '<i2', nb, o); o += nb * 2
    au16 = np.frombuffer(buf, '<u2', nb, o); o += nb * 2
    vals = np.frombuffer(buf, '<u1', nb * nr, o).reshape(nb, nr)
    az = (au16.astype(np.float64) * 360.0 / 65536.0) % 360.0   # BAM16 → degrees
    el = ei16.astype(np.float64) * 180.0 / 32768.0
    return {'nb': nb, 'nr': nr, 'attr': attr, 'time': t, 'lat': lat, 'lon': lon,
            'alt': alt, 'az': az, 'el': el, 'sweep_el': sweep_el, 'sweep_az': sweep_az,
            'r_start': r_start, 'r_spacing': r_spacing, 'info': info, 'values': vals}


_RH_SWEEP_CACHE: dict = {}
_RH_SWEEP_MAX = 96


def radarhub_sweep(pathway: str, item: str, symbol: str) -> dict:
    """Fetch + decode one sweep (cached)."""
    ck = f'{pathway}/{item}-{symbol}'
    if ck in _RH_SWEEP_CACHE:
        return _RH_SWEEP_CACHE[ck]
    url = f'{RADARHUB_BASE}/data/load/{pathway}/{item}-{symbol}/'
    buf = _rh_fetch_binary(url, f'rh_{ck}')
    s = radarhub_decode(buf)
    if len(_RH_SWEEP_CACHE) >= _RH_SWEEP_MAX:
        del _RH_SWEEP_CACHE[next(iter(_RH_SWEEP_CACHE))]
    _RH_SWEEP_CACHE[ck] = s
    return s


def radarhub_to_image(s: dict, row: int, alpha: int = 235) -> tuple[bytes, dict]:
    """Render a decoded sweep to a transparent RGBA PNG (north up, square,
    spanning ±max_range) using RadarHub's colormap row. Returns (png, bounds)."""
    vals = s['values']                  # (nb, nr) uint8
    az = s['az']                        # (nb,)
    nb, nr = vals.shape
    r_start, r_spacing = s['r_start'], s['r_spacing']
    if r_spacing <= 0:
        r_spacing = 1.0
    max_range_km = r_start + nr * r_spacing
    N = RENDER_PX

    lin = np.linspace(-max_range_km, max_range_km, N)
    xx, yy = np.meshgrid(lin, lin[::-1])           # north = up
    rng_km = np.sqrt(xx * xx + yy * yy)
    scr_az = np.degrees(np.arctan2(xx, yy)) % 360.0

    az_idx = _azimuth_lookup(az, scr_az)            # nearest real beam per pixel
    rng_idx = np.clip(((rng_km - r_start) / r_spacing).astype(np.int32), 0, nr - 1)
    sampled = vals[az_idx, rng_idx]

    lut = radarhub_luts()
    row = min(max(row, 0), lut.shape[0] - 1)
    rgba = lut[row][sampled].copy()                 # (N, N, 4)

    # Beam spacing → blank pixels whose nearest beam is too far (sector scans,
    # partial-azimuth research radars) so they don't smear across the disk.
    if nb > 1:
        steps = np.abs(((np.diff(np.sort(az)) + 180.0) % 360.0) - 180.0)
        steps = steps[steps > 1e-6]
        step = float(np.median(steps)) if steps.size else 1.0
    else:
        step = 360.0
    gap = max(2.0, step * 1.8)
    beam_az = az[az_idx]
    dz = np.abs(((scr_az - beam_az + 180.0) % 360.0) - 180.0)

    valid = (rng_km <= max_range_km) & (rng_km >= r_start) & (sampled > 0) & (dz <= gap)
    a = rgba[..., 3].astype(np.uint16)
    a = (a * alpha // 255).astype(np.uint8)         # respect LUT alpha, scaled
    rgba[..., 3] = np.where(valid, a, 0)

    img = Image.fromarray(rgba, 'RGBA')
    bio = io.BytesIO()
    img.save(bio, 'PNG', optimize=False)
    bounds = compute_bounds(s['lat'], s['lon'], max_range_km)
    return bio.getvalue(), bounds


# ── scan listing (pick a coherent PPI elevation to display + animate) ───────
def _rh_scan_of(item: str) -> str:
    parts = item.split('-')
    return parts[2] if len(parts) > 2 else ''


def _rh_item_iso(item: str) -> str:
    d, t = item[:8], item[9:15]
    return f'{d[:4]}-{d[4:6]}-{d[6:8]}T{t[:2]}:{t[2:4]}:{t[4:6]}Z'


def _rh_prev_hour(dts: str) -> str:
    from datetime import datetime, timedelta
    base = datetime.strptime(dts[:11], '%Y%m%d-%H')
    return (base - timedelta(hours=1)).strftime('%Y%m%d-%H00')


def _rh_elev(scan: str) -> float:
    try:
        return float(scan[1:])
    except Exception:
        return 999.0


def _rh_ppi_items(pathway: str, want: int) -> list[str]:
    """Recent PPI (E-type) scan items oldest→newest. Pulls the previous hour's
    table too if the current hour doesn't have enough frames yet."""
    try:
        j = _json.loads(_rh_get(f'{RADARHUB_BASE}/data/catchup/{pathway}/', ttl=12))
    except Exception:
        return []
    items = list(j.get('items', []))
    E = [it for it in items if _rh_scan_of(it).startswith('E')]
    if len(E) < want:
        dts = j.get('dateTimeString', '')
        if len(dts) >= 11:
            try:
                pj = _json.loads(_rh_get(
                    f'{RADARHUB_BASE}/data/table/{pathway}/{_rh_prev_hour(dts)}/', ttl=30))
                pe = [it for it in pj.get('items', []) if _rh_scan_of(it).startswith('E')]
                E = pe + E
            except Exception:
                pass
    return E


def _rh_select(pathway: str, frames: int):
    """Return (keys oldest→newest, target_scan). Locks onto the lowest tilt in
    the recent set (base scan = best storm view) so animation loops are coherent."""
    E = _rh_ppi_items(pathway, want=max(frames * 4, 40))
    if not E:
        return [], None
    recent = E[-max(frames * 3, 24):]
    tilts = sorted({_rh_scan_of(it) for it in recent}, key=_rh_elev)
    target = tilts[0] if tilts else _rh_scan_of(E[-1])
    same = [it for it in E if _rh_scan_of(it) == target]
    return same[-frames:], target


def _rh_phys(symbol: str, b: int):
    """Gate byte → physical value (RadarKit/RadarHub scaling). None = no data."""
    b = int(b)
    if b == 0:
        return None
    if symbol == 'Z':
        return (b - 64) / 2.0
    if symbol == 'V':
        return (b - 128) / 2.0
    if symbol == 'W':
        return b / 20.0
    if symbol == 'D':
        return (b - 100) / 10.0
    if symbol == 'P':
        return (b - 128) * 180.0 / 128.0
    if symbol == 'R':
        if b > 106:
            return (b + 824.0) / 1000.0
        if b > 37:
            return (b + 173.0) / 300.0
        return b / 52.8751
    return float(b)


@app.get('/api/radarhub/products')
def api_rh_products():
    grouped: dict[str, list] = {}
    for code, info in RADARHUB_PRODUCTS.items():
        grouped.setdefault(info['cat'], []).append({'code': code, **info})
    return grouped


@app.get('/api/radarhub/scans')
def api_rh_scans(site: str = Query(...), product: str = Query(...),
                 frames: int = Query(30, ge=1, le=200)):
    s = _rh_site(site)
    _rh_prod(product)
    keys, target = _rh_select(s['pathway'], frames)
    return {'keys': keys, 'tilt': target, 'count': len(keys)}


@app.get('/api/radarhub/latest')
def api_rh_latest(site: str = Query(...), product: str = Query(...)):
    s = _rh_site(site)
    _rh_prod(product)
    keys, target = _rh_select(s['pathway'], 1)
    if not keys:
        raise HTTPException(404, f'No recent PPI scans for {site}')
    return {'key': keys[-1], 'tilt': target, 'date': keys[-1][:8]}


@app.get('/api/radarhub/render')
def api_rh_render(site: str = Query(...), product: str = Query(...), key: str = Query(...)):
    s = _rh_site(site)
    p = _rh_prod(product)
    try:
        sweep = radarhub_sweep(s['pathway'], key, p['symbol'])
    except Exception as e:
        code = getattr(e, 'code', None)
        if code == 404:
            raise HTTPException(404, f'Scan/moment not available for {product}')
        raise HTTPException(502, f'RadarHub fetch error: {e}')
    try:
        png, bounds = radarhub_to_image(sweep, p['row'])
    except Exception as e:
        raise HTTPException(500, f'Render error: {e}')

    nr, rsp = sweep['nr'], sweep['r_spacing']
    max_km = sweep['r_start'] + nr * rsp
    tilt = _rh_scan_of(key)
    info = {}
    try:
        info = _json.loads(sweep.get('info') or '{}')
    except Exception:
        info = {}
    mode = f"{s['name']} · {('El '+tilt[1:]+'°') if tilt.startswith('E') else tilt} · {int(round(rsp*1000))} m gates"
    if info.get('prf'):
        mode += f" · PRF {info['prf']} Hz"
    bounds_str = f"{bounds['south']:.5f},{bounds['west']:.5f},{bounds['north']:.5f},{bounds['east']:.5f}"
    return Response(content=png, media_type='image/png', headers={
        'X-Radar-Bounds': bounds_str,
        'X-Radar-Time': _rh_item_iso(key),
        'X-Radar-Mode': mode,
        'X-Radar-Loc': f"{sweep['lat']:.5f},{sweep['lon']:.5f}",
        'X-Radar-Range': f'{max_km:.1f}',
        'Cache-Control': 'max-age=120',
    })


@app.get('/api/radarhub/colorbar_strip')
def api_rh_colorbar_strip(product: str = Query(...), width: int = 700, height: int = 6):
    p = _rh_prod(product)
    lut = radarhub_luts()
    row = min(max(p['row'], 0), lut.shape[0] - 1)
    idx = np.clip(np.linspace(0, 255, width).astype(int), 0, 255)
    strip = lut[row][idx][:, :3]                       # drop alpha for the strip
    arr = np.tile(strip[np.newaxis, :, :], (height, 1, 1)).astype(np.uint8)
    bio = io.BytesIO()
    Image.fromarray(arr, 'RGB').save(bio, 'PNG')
    return Response(content=bio.getvalue(), media_type='image/png',
                    headers={'Cache-Control': 'max-age=3600'})


@app.get('/api/radarhub/probe')
def api_rh_probe(site: str = Query(...), product: str = Query(...),
                 key: str = Query(...), lat: float = Query(...), lon: float = Query(...)):
    s = _rh_site(site)
    p = _rh_prod(product)
    try:
        sweep = radarhub_sweep(s['pathway'], key, p['symbol'])
    except Exception as e:
        raise HTTPException(422, str(e))
    nr, rsp = sweep['nr'], sweep['r_spacing']
    max_km = sweep['r_start'] + nr * rsp
    ridx, gidx, dist, az = latlon_to_polar(lat, lon, sweep['lat'], sweep['lon'],
                                           sweep['az'], max_km, nr)
    if dist > max_km:
        return {'value': None, 'display': 'out of range', 'unit': p['unit']}
    b = int(sweep['values'][ridx, gidx])
    val = _rh_phys(p['symbol'], b)
    if val is None:
        return {'value': None, 'display': 'no data', 'unit': p['unit']}
    disp = f'{val:.2f}' if p['symbol'] == 'R' else f'{val:.1f}'
    return {'value': val, 'display': disp, 'unit': p['unit'],
            'dist_km': round(dist, 2), 'azimuth': round(az, 1)}


# ═══════════════════════════════════════════════════════════════════════════
# FARM / DOW mobile radars  (svr.guru live plot viewer)
# ─────────────────────────────────────────────────────────────────────────
# The Doppler-on-Wheels / COW radars (FARM facility, now UAH) have NO public
# raw real-time feed — only pre-rendered PLOT images on the third-party live
# display svr.guru. They're standalone scope plots (not raw data, not
# georeferenced, and the trucks are mobile), so they show in an in-app IMAGE
# VIEWER rather than on the map. We parse svr.guru's listing + frame URLs and
# proxy the images (avoids browser CORS/hotlink issues, adds caching).
# ═══════════════════════════════════════════════════════════════════════════
SVRGURU = 'https://svr.guru'
_SVR_CACHE: dict = {}


def _svr_text(path: str, ttl: int = 20) -> str:
    url = f'{SVRGURU}/{path.lstrip("/")}'
    now = _time.time()
    hit = _SVR_CACHE.get(url)
    if hit and hit[0] > now:
        return hit[1]
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = r.read()
        enc = r.headers.get('Content-Encoding', '')
    if enc == 'gzip' or data[:2] == b'\x1f\x8b':
        import gzip as _gz
        data = _gz.decompress(data)
    text = data.decode('utf-8', 'replace')
    _SVR_CACHE[url] = (now + ttl, text)
    return text


def _svr_img(path: str) -> bytes:
    """Fetch a svr.guru plot image (immutable, timestamped → cache on disk)."""
    h = hashlib.md5(path.encode()).hexdigest()
    fp = CACHE / ('dow_' + h + '.png')
    if fp.exists():
        try:
            return fp.read_bytes()
        except Exception:
            pass
    req = urllib.request.Request(f'{SVRGURU}/{path}', headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    try:
        fp.write_bytes(data)
    except Exception:
        pass
    return data


@app.get('/api/dow/list')
def api_dow_list():
    """Radars currently live on svr.guru (only those with plots in ~90 days)."""
    try:
        html = _svr_text('index.php', ttl=60)
    except Exception as e:
        raise HTTPException(502, f'svr.guru unreachable: {e}')
    radars = []
    pat = re.compile(
        r'data\.php\?id=(\d+)&prod=([A-Za-z0-9_]+)">([^<]+)</a>.*?'
        r'Last Plot:\s*<span[^>]*>([^<]+)</span>', re.S)
    for m in pat.finditer(html):
        radars.append({'id': int(m.group(1)), 'prod': m.group(2),
                       'name': m.group(3).strip(), 'last': m.group(4).strip()})
    return {'radars': radars}


@app.get('/api/dow/frames')
def api_dow_frames(id: int = Query(...), prod: str = Query('DBZHC'),
                   scan: str = Query('PPI')):
    """Frame image paths + timestamps for a radar/product/scan-type, oldest→newest,
    plus the list of products available for that radar."""
    try:
        html = _svr_text(f'data.php?id={id}&prod={prod}', ttl=20)
    except Exception as e:
        raise HTTPException(502, f'svr.guru error: {e}')
    name_m = re.search(r'<title>([^<]+?)\s*Data</title>', html)
    radar_name = name_m.group(1).strip() if name_m else f'DOW {id}'
    products = []
    seen_p = set()
    for m in re.finditer(rf'data\.php\?id={id}&prod=([A-Za-z0-9_]+)">([^<]+)</a>', html):
        code = m.group(1)
        if code not in seen_p:
            seen_p.add(code)
            products.append({'code': code, 'name': m.group(2).strip()})
    frames = []
    seen_f = set()
    fpat = re.compile(r'src="(img/\d+/[A-Z0-9]+-(PPI|RHI)-[A-Za-z0-9_]+-(\d{14})-\d+\.png)"')
    for m in fpat.finditer(html):
        path, sc, ts = m.group(1), m.group(2), m.group(3)
        if sc.upper() != scan.upper():
            continue
        if path in seen_f:
            continue
        seen_f.add(path)
        frames.append({'path': path, 'ts': ts, 'scan': sc})
    frames.sort(key=lambda f: f['ts'])
    return {'id': id, 'name': radar_name, 'prod': prod, 'scan': scan,
            'products': products, 'frames': frames, 'count': len(frames)}


@app.get('/api/dow/img')
def api_dow_img(p: str = Query(...)):
    """Proxy a svr.guru plot image (validated path, cached)."""
    if not re.fullmatch(r'img/\d+/[A-Za-z0-9_\-]+\.png', p):
        raise HTTPException(400, 'bad image path')
    try:
        data = _svr_img(p)
    except Exception as e:
        raise HTTPException(502, f'image fetch error: {e}')
    return Response(content=data, media_type='image/png',
                    headers={'Cache-Control': 'max-age=600'})


# ── DOW location from the plot image (OCR town labels → gazetteer) ───────────
# The svr.guru plots have no coordinates, but they DO render nearby town names.
# We OCR those names (Windows.Media.Ocr — built into Win10/11), look them up in
# a bundled US gazetteer, and triangulate the radar's position. Matching by
# NAME (not blob position) is what makes this reliable — a constellation of
# real town names uniquely pins the location; positions alone don't.
_DOW_LOC_CACHE: dict = {}   # id -> {lat,lon,range_km,n,ts}
_GAZ_BY_NAME: dict = {}     # lowercased name -> [(name,lat,lon), ...]
_GAZ_NAMES_BY_INITIAL: dict = {}


def _load_gazetteer():
    """Load the bundled CONUS gazetteer once (name -> [(name,lat,lon)])."""
    global _GAZ_BY_NAME, _GAZ_NAMES_BY_INITIAL
    if _GAZ_BY_NAME:
        return _GAZ_BY_NAME
    path = RESOURCE_DIR / 'gazetteer.tsv'
    try:
        with open(path, encoding='utf-8') as fh:
            for ln in fh:
                parts = ln.rstrip('\n').split('\t')
                if len(parts) != 3:
                    continue
                nm, la, lo = parts
                key = nm.lower()
                _GAZ_BY_NAME.setdefault(key, []).append((nm, float(la), float(lo)))
        for key in _GAZ_BY_NAME:
            if key:
                _GAZ_NAMES_BY_INITIAL.setdefault(key[0], []).append(key)
    except Exception:
        pass
    return _GAZ_BY_NAME


def _ocr_words(img_bytes: bytes, upscale: int = 3):
    """OCR an image via the bundled Windows.Media.Ocr helper. Returns list of
    {text,x,y,w,h} in UPSCALED pixel coords, plus the upscale factor.
    Windows-only; on macOS/Linux this returns [] so DOW auto-locate simply
    falls back to a regional view (no OCR engine bundled there yet)."""
    import subprocess, tempfile, json as _j
    if sys.platform != 'win32':
        return [], upscale
    ps1 = RESOURCE_DIR / 'ocr_win.ps1'
    if not ps1.exists():
        return [], upscale
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    W, H = img.size
    big = img.resize((W * upscale, H * upscale), Image.LANCZOS)
    tmp = pathlib.Path(tempfile.gettempdir()) / f'dowocr_{abs(hash(img_bytes)) & 0xffffff}.png'
    try:
        big.save(tmp)
        flags = 0x08000000 if os.name == 'nt' else 0   # CREATE_NO_WINDOW
        r = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ps1), str(tmp)],
            capture_output=True, encoding='utf-8', errors='replace', timeout=60, creationflags=flags)
        data = _j.loads(r.stdout.strip() or '[]')
        if isinstance(data, dict):     # {"error": ...}
            return [], upscale
        return data, upscale
    except Exception:
        return [], upscale
    finally:
        try: tmp.unlink()
        except Exception: pass


def _ring_scale(arr):
    """km-per-pixel from the innermost 15 km range ring (radial brightness peak)."""
    import math as _math
    from scipy.signal import find_peaks
    H, W = arr.shape[:2]
    gray = arr.mean(axis=2)
    cx, cy = W // 2, H // 2
    max_r = min(cx, cy) - 5
    rb = []
    for r_test in range(20, max_r, 2):
        n = max(60, int(2 * _math.pi * r_test))
        ang = np.linspace(0, 2*_math.pi, n, endpoint=False)
        ry = np.clip((cy + r_test*np.sin(ang)).astype(int), 0, H-1)
        rx = np.clip((cx + r_test*np.cos(ang)).astype(int), 0, W-1)
        rb.append(float(gray[ry, rx].mean()))
    smooth = np.convolve(np.array(rb), np.ones(7)/7, mode='same')
    peaks, _ = find_peaks(smooth, distance=15, prominence=2.0)
    rings = [20 + 2*int(p) for p in peaks if 20 + 2*int(p) >= 30]
    return (15.0 / rings[0]) if rings else None, max_r


def _dow_image_location(img_bytes: bytes):
    """OCR town labels → gazetteer → triangulate radar lat/lon.
    Returns (lat, lon, max_range_km, n_towns) or None (low confidence)."""
    try:
        import math as _math, re as _re, difflib
        from collections import defaultdict
        gaz = _load_gazetteer()
        if not gaz:
            return None
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        arr = np.array(img, dtype=np.float32)
        H, W = arr.shape[:2]
        cx, cy = W // 2, H // 2
        scale, max_r = _ring_scale(arr)
        if not scale:
            return None

        words, up = _ocr_words(img_bytes)
        if not words:
            return None

        # fuzzy-match OCR words to gazetteer town names
        hits = []   # (name, lat, lon, px, py)
        for wd in words:
            t = _re.sub(r'[^A-Za-z]', '', wd.get('text', ''))
            if len(t) < 4:
                continue
            tl = t.lower()
            cand = None
            if tl in gaz:
                cand = tl
            else:
                pool = _GAZ_NAMES_BY_INITIAL.get(tl[0], [])
                close = difflib.get_close_matches(tl, pool, n=1, cutoff=0.82)
                if close:
                    cand = close[0]
            if not cand:
                continue
            px = (wd['x'] + wd['w'] / 2) / up
            py = (wd['y'] + wd['h'] / 2) / up
            for (nm, la, lo) in gaz[cand]:
                hits.append((nm, la, lo, px, py))
        if not hits:
            return None

        # disambiguate: pick the geographic region where the most DISTINCT town
        # names co-locate (handles names that repeat across many states)
        grid = defaultdict(list)
        for h in hits:
            grid[(round(h[1]), round(h[2]))].append(h)

        def region_score(key):
            names = set()
            for dla in (-1, 0, 1):
                for dlo in (-1, 0, 1):
                    for hh in grid.get((key[0]+dla, key[1]+dlo), []):
                        names.add(hh[0])
            return len(names)

        best_key = max(grid.keys(), key=region_score)
        region = {}
        for dla in (-1, 0, 1):
            for dlo in (-1, 0, 1):
                for hh in grid.get((best_key[0]+dla, best_key[1]+dlo), []):
                    region.setdefault(hh[0], hh)   # one estimate per town name
        region = list(region.values())
        if len(region) < 2:
            return None    # need ≥2 agreeing town names for confidence

        rlats, rlons = [], []
        for (nm, la, lo, px, py) in region:
            dx_km = (px - cx) * scale
            dy_km = -(py - cy) * scale
            rlats.append(la - dy_km / 111.32)
            rlons.append(lo - dx_km / (111.32 * _math.cos(_math.radians(la))))
        rlat = float(np.median(rlats))
        rlon = float(np.median(rlons))
        # consistency: reject if the triangulated points disagree wildly
        spread = max(float(np.std(rlats)) * 111.0, float(np.std(rlons)) * 88.0)
        if spread > 90.0:
            return None
        return rlat, rlon, scale * max_r, len(region)
    except Exception:
        return None


@app.get('/api/dow/location')
def api_dow_location(id: int = Query(...)):
    """Best-estimate lat/lon of a DOW radar, read from its latest plot image."""
    now = _time.time()
    cached = _DOW_LOC_CACHE.get(id)
    if cached and (now - cached['ts']) < 600:   # 10-min cache (trucks move slowly)
        return {**{k: cached[k] for k in ('lat', 'lon', 'range_km', 'n')}, 'cached': True}
    prod_map = {3: 'DBZHC', 4: 'DBZHC', 9: 'DBZHC_F'}
    name_map = {3: 'DOW6', 4: 'DOW7', 9: 'COW2'}
    prod  = prod_map.get(id, 'DBZHC')
    rname = name_map.get(id, f'DOW{id}')
    try:
        html = _svr_text(f'data.php?id={id}&prod={prod}', ttl=20)
    except Exception as e:
        raise HTTPException(502, f'svr.guru error: {e}')
    pat = fr'img/{id}/{re.escape(rname)}-PPI-{re.escape(prod)}-(\d{{14}})-(\d+)\.png'
    matches = sorted(set(re.findall(pat, html)))
    if not matches:
        raise HTTPException(404, 'no PPI frames available')
    ts, num = matches[-1]
    path = f'img/{id}/{rname}-PPI-{prod}-{ts}-{num}.png'
    try:
        img_bytes = _svr_img(path)
    except Exception as e:
        raise HTTPException(502, f'image fetch error: {e}')
    result = _dow_image_location(img_bytes)
    if result is None:
        raise HTTPException(422, 'could not confidently determine location from image')
    lat, lon, rng, n = result
    entry = {'lat': round(lat, 4), 'lon': round(lon, 4), 'range_km': round(rng, 1), 'n': n, 'ts': now}
    _DOW_LOC_CACHE[id] = entry
    return {'lat': entry['lat'], 'lon': entry['lon'], 'range_km': entry['range_km'], 'n': n}


# ── DOW echoes as a georeferenced MAP OVERLAY ───────────────────────────────
# Extract just the colorful radar echoes from the plot (drop tan background,
# colorbar, range rings, town labels via saturation+disk masking), then place
# them on the map using the OCR-derived radar location + the ring scale.
def _dow_latlon(id: int):
    """Radar lat/lon (cached OCR, or compute). Returns (lat, lon) or None."""
    now = _time.time()
    c = _DOW_LOC_CACHE.get(id)
    if c and (now - c['ts']) < 600:
        return c['lat'], c['lon']
    prod_map = {3: 'DBZHC', 4: 'DBZHC', 9: 'DBZHC_F'}
    name_map = {3: 'DOW6', 4: 'DOW7', 9: 'COW2'}
    prod = prod_map.get(id, 'DBZHC'); rname = name_map.get(id, f'DOW{id}')
    try:
        html = _svr_text(f'data.php?id={id}&prod={prod}', ttl=20)
        m = sorted(set(re.findall(
            fr'img/{id}/{re.escape(rname)}-PPI-{re.escape(prod)}-(\d{{14}})-(\d+)\.png', html)))
        if not m:
            return None
        ts, num = m[-1]
        res = _dow_image_location(_svr_img(f'img/{id}/{rname}-PPI-{prod}-{ts}-{num}.png'))
        if res is None:
            return None
        lat, lon, rng, n = res
        _DOW_LOC_CACHE[id] = {'lat': round(lat, 4), 'lon': round(lon, 4),
                              'range_km': round(rng, 1), 'n': n, 'ts': now}
        return lat, lon
    except Exception:
        return None


def _dow_echo_png(img_bytes: bytes):
    """Colorful echoes only → (rgba_png, scale_km_per_px, W, H) or None."""
    try:
        from scipy.signal import find_peaks
        import math as _m
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        arr = np.array(img); H, W = arr.shape[:2]; cx, cy = W // 2, H // 2
        gray = arr.mean(axis=2); max_r = min(cx, cy) - 5; rb = []
        for rt in range(20, max_r, 2):
            n = max(60, int(2 * _m.pi * rt))
            a = np.linspace(0, 2 * _m.pi, n, endpoint=False)
            yy = np.clip((cy + rt * np.sin(a)).astype(int), 0, H - 1)
            xx = np.clip((cx + rt * np.cos(a)).astype(int), 0, W - 1)
            rb.append(float(gray[yy, xx].mean()))
        sm = np.convolve(np.array(rb), np.ones(7) / 7, mode='same')
        pk, _ = find_peaks(sm, distance=15, prominence=2.0)
        rings = [20 + 2 * int(p) for p in pk if 20 + 2 * int(p) >= 30]
        if not rings:
            return None
        scale = 15.0 / rings[0]
        disk_r = min(cx, cy) * 0.98
        if 0.9 * min(cx, cy) > rings[-1] > 0.6 * min(cx, cy):
            disk_r = rings[-1] * 1.02
        af = arr.astype(np.float32) / 255.0
        mx = af.max(axis=2); mn = af.min(axis=2)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0); val = mx
        yy, xx = np.mgrid[0:H, 0:W]
        inside = ((xx - cx) ** 2 + (yy - cy) ** 2) <= disk_r ** 2
        keep = inside & (sat > 0.45) & (val > 0.25)
        keep[:, :int(W * 0.07)] = False              # drop the left colorbar strip
        out = np.dstack([arr, np.where(keep, 230, 0).astype(np.uint8)])
        bio = io.BytesIO()
        Image.fromarray(out, 'RGBA').save(bio, 'PNG')
        return bio.getvalue(), scale, W, H
    except Exception:
        return None


@app.get('/api/dow/overlay')
def api_dow_overlay(id: int = Query(...), p: str = Query(...)):
    """Transparent echo PNG georeferenced for the map. Headers: X-Radar-Bounds/Time."""
    import math as _m
    if not re.fullmatch(r'img/\d+/[A-Za-z0-9_\-]+\.png', p):
        raise HTTPException(400, 'bad image path')
    loc = _dow_latlon(id)
    if not loc:
        raise HTTPException(422, 'radar location unavailable')
    lat, lon = loc
    try:
        img_bytes = _svr_img(p)
    except Exception as e:
        raise HTTPException(502, f'image fetch error: {e}')
    res = _dow_echo_png(img_bytes)
    if res is None:
        raise HTTPException(422, 'could not process plot image')
    png, scale, W, H = res
    half_ew = (W / 2) * scale
    half_ns = (H / 2) * scale
    north = lat + half_ns / 111.32
    south = lat - half_ns / 111.32
    east = lon + half_ew / (111.32 * _m.cos(_m.radians(lat)))
    west = lon - half_ew / (111.32 * _m.cos(_m.radians(lat)))
    bounds = f'{south:.5f},{west:.5f},{north:.5f},{east:.5f}'
    mt = re.search(r'-(\d{14})-\d+\.png', p)
    iso = ''
    if mt:
        t = mt.group(1)
        iso = f'{t[:4]}-{t[4:6]}-{t[6:8]}T{t[8:10]}:{t[10:12]}:{t[12:14]}Z'
    return Response(content=png, media_type='image/png', headers={
        'X-Radar-Bounds': bounds, 'X-Radar-Time': iso, 'Cache-Control': 'max-age=300'})


# ── Auto-update (GitHub Releases) ────────────────────────────────────────────
_upd_dl_path: str | None = None
_upd_dl_state: dict = {'status': 'idle', 'pct': 0}


def _ver_tuple(v: str):
    try:
        return tuple(int(x) for x in v.strip().split('.'))
    except Exception:
        return (0, 0, 0)


@app.get('/api/update/check')
def api_update_check():
    """Check GitHub Releases for a newer version. Fast (cached 10 min)."""
    try:
        url = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'
        req = urllib.request.Request(url, headers={
            'User-Agent': f'NEXRAD-Radar/{__version__}',
            'Accept': 'application/vnd.github+json',
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
        latest = data.get('tag_name', '').lstrip('v')
        # Pick the asset for THIS platform: .dmg on macOS, .exe on Windows.
        want = '.dmg' if sys.platform == 'darwin' else '.exe'
        dl_url = next((a['browser_download_url'] for a in data.get('assets', [])
                       if a['name'].lower().endswith(want)), None)
        has_update = bool(latest) and _ver_tuple(latest) > _ver_tuple(__version__)
        return {
            'update':   has_update,
            'current':  __version__,
            'latest':   latest,
            'platform': sys.platform,
            'url':      dl_url if has_update else None,
            'page':     f'https://github.com/{GITHUB_REPO}/releases/latest',
            'notes':    (data.get('body') or '')[:600],
        }
    except Exception as e:
        return {'update': False, 'current': __version__, 'platform': sys.platform, 'error': str(e)}


@app.get('/api/open')
def api_open(url: str = Query(...)):
    """Open a (GitHub) URL in the system default browser — used by the macOS
    update flow to send the user to the releases page."""
    if not url.startswith('https://github.com/'):
        raise HTTPException(400, 'only github.com URLs allowed')
    try:
        import webbrowser
        webbrowser.open(url)
        return {'opened': True}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get('/api/update/download')
def api_update_download(url: str = Query(...)):
    """Start downloading the installer in the background."""
    import threading as _th, tempfile as _tmp

    def _dl(dl_url: str):
        global _upd_dl_path, _upd_dl_state
        try:
            _upd_dl_state = {'status': 'downloading', 'pct': 0}
            dest = pathlib.Path(_tmp.gettempdir()) / 'NEXRAD-Radar-Update.exe'
            req = urllib.request.Request(dl_url,
                                         headers={'User-Agent': f'NEXRAD-Radar/{__version__}'})
            with urllib.request.urlopen(req, timeout=120) as r:
                total = int(r.headers.get('Content-Length') or 0)
                done = 0
                with open(dest, 'wb') as fh:
                    while chunk := r.read(65536):
                        fh.write(chunk)
                        done += len(chunk)
                        if total:
                            _upd_dl_state = {'status': 'downloading',
                                             'pct': int(done / total * 100)}
            _upd_dl_path = str(dest)
            _upd_dl_state = {'status': 'ready', 'pct': 100}
        except Exception as exc:
            _upd_dl_state = {'status': 'error', 'pct': 0, 'error': str(exc)}

    _th.Thread(target=_dl, args=(url,), daemon=True).start()
    return {'started': True}


@app.get('/api/update/progress')
def api_update_progress():
    return _upd_dl_state


@app.get('/api/update/install')
def api_update_install():
    """Hand off to the detached updater helper, then exit so the running app's
    files unlock. The helper waits for us to close, installs silently, relaunches."""
    import subprocess as _sp, threading as _th
    global _upd_dl_path
    if not _upd_dl_path or not pathlib.Path(_upd_dl_path).exists():
        raise HTTPException(400, 'No installer downloaded yet')
    helper  = RESOURCE_DIR / 'updater.ps1'
    app_exe = sys.executable   # frozen → the NEXRAD Radar.exe to relaunch
    try:
        if helper.exists() and getattr(sys, 'frozen', False):
            # CREATE_NO_WINDOW (0x08000000); child survives our os._exit by default
            _sp.Popen(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                       '-File', str(helper), '-Installer', _upd_dl_path,
                       '-AppExe', app_exe],
                      creationflags=0x08000000, close_fds=True)
        else:
            # dev fallback: just run the installer
            _sp.Popen([_upd_dl_path, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                      creationflags=0x08000000)

        def _bye():
            import time; time.sleep(1.5); os._exit(0)
        _th.Thread(target=_bye, daemon=True).start()
        return {'installing': True}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get('/api/version')
def api_version():
    return {'version': __version__, 'repo': GITHUB_REPO}


# Serve static files (index.html etc.)
app.mount('/', StaticFiles(directory=STATIC_DIR, html=True), name='static')


if __name__ == '__main__':
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f'Starting NEXRAD Radar Viewer on http://localhost:{port}')
    uvicorn.run(app, host='0.0.0.0', port=port, log_level='info')
