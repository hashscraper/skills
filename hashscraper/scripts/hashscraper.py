#!/usr/bin/env python3
"""HashScraper Agent Skill — collect public web data with HashScraper bots (standard library only).

  python3 hashscraper.py login                               # connect your account in the browser (once)
  python3 hashscraper.py catalog [--search coupang]          # bots in this bundle
  python3 hashscraper.py me                                  # today's free credits
  python3 hashscraper.py run DemoCoupangDetailWorker --input param1="https://www.coupang.com/vp/products/..."
  python3 hashscraper.py run DynNaverBlogWorker --input param1="성수동 카페" --input param5=50 --csv out.csv
  python3 hashscraper.py fetch 270261461                     # rows of an earlier run (waits while it is still collecting)

Runs use only the daily free credits. Add --use-credits to continue with your own credits when they run out.
The key from `login` is saved in ~/.config/hashscraper/credentials (owner-only). HASHSCRAPER_API_KEY, if set, is used first.
`logout` deletes the saved key. `rotate` swaps the saved key for a new one and deletes the old key on the server.
"""
import argparse
import csv
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser

VERSION = "0.4.0"
CLIENT = f"agent-skill/{VERSION}"
BASE = os.environ.get("HASHSCRAPER_BASE_URL", "https://www.hashscraper.com/v5/api").rstrip("/")
SITE = "https://www.hashscraper.com"
UTM = "utm_source=agent_skill&utm_medium=skill&utm_campaign=bundle"
SIGN_UP = f"{SITE}/users/sign_up?{UTM}"
BOT_CATALOG = f"{SITE}/schedules/catalog?{UTM}"
FOOTER = f"Daily monitoring & bulk collection -> HashScraper {SITE}/quotes/new?{UTM}"
CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "catalog.json")
POLL_SECONDS = 15
MAX_WAIT_SECONDS = 20 * 60
ENDED = ("done", "attention", "failed", "canceled")
GET_RETRIES = 3
CREDENTIALS_PATH = os.path.join(os.path.expanduser("~"), ".config", "hashscraper", "credentials")
PENDING_PATH = os.path.join(os.path.expanduser("~"), ".config", "hashscraper", "login_pending")  # login --start -> --wait
LOGIN_HINT = "Run `python3 scripts/hashscraper.py login` to connect your HashScraper account in the browser"


class ApiError(Exception):
    def __init__(self, status, payload):
        self.status = status
        self.code = payload.get("code", "HTTP_ERROR")
        self.message = payload.get("message", "")
        self.details = payload.get("details") or {}
        super().__init__(f"{status} {self.code}: {self.message}")


def saved_key():
    """The key saved by `login`, or None. Never printed.

    The key is used only with the server it came from (base_url saved at login) — never sent to another
    HASHSCRAPER_BASE_URL.
    """
    try:
        with open(CREDENTIALS_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if (data.get("base_url") or "").rstrip("/") != BASE:
        print(f"The saved key belongs to {data.get('base_url')}, not {BASE}. It was not used. "
              "Run login for this server (or set HASHSCRAPER_API_KEY).", file=sys.stderr)
        return None
    return (data.get("api_key") or "").strip() or None


def api_key():
    key = os.environ.get("HASHSCRAPER_API_KEY", "").strip() or saved_key()
    if not key:
        sys.exit(f"Not connected yet. {LOGIN_HINT} (free sign-up included), "
                 "or set HASHSCRAPER_API_KEY to a key from My page -> API.")
    return key


def write_private(path, payload):
    """Write JSON readable only by you (folder 0700, file 0600)."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    temp = path + ".tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    os.replace(temp, path)
    os.chmod(path, 0o600)


def save_key(data):
    """Save the key from login to ~/.config/hashscraper/credentials."""
    write_private(CREDENTIALS_PATH, {"api_key": data["api_key"], "key_name": data.get("key_name"),
                                     "expires_at": data.get("expires_at"), "base_url": BASE,
                                     "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})


def remove_quietly(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def call(method, path, key, body=None, query=None, idempotency_key=None, use_credits=False):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {"Accept": "application/json", "X-HashScraper-Client": CLIENT}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if use_credits:
        headers["X-HashScraper-Use-Credits"] = "true"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    attempts = GET_RETRIES if method == "GET" else 1  # only reads are retried; a start is never sent twice
    for attempt in range(attempts):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode("utf-8"))
            except ValueError:
                payload = {"message": str(e)}
            if method == "GET" and e.code >= 500 and attempt + 1 < attempts:
                time.sleep(5)
                continue
            raise ApiError(e.code, payload) from None
        except urllib.error.URLError:
            if attempt + 1 < attempts:
                time.sleep(5)
                continue
            raise


def load_catalog():
    with open(CATALOG_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def catalog_entry(worker):
    for entry in load_catalog()["bots"]:
        if entry["worker"] == worker:
            return entry
    return None


def explain(error):
    """Print an API error for the user. Limit errors are final for this run — never retried."""
    lines = [f"HashScraper API error — {error.code}: {error.message}"]
    details = error.details
    if error.code == "DAILY_FREE_USED_UP":
        if details.get("hint"):
            lines.append(details["hint"])
        lines.append(f"Free credits refill at {details.get('resets_at', 'midnight KST')}. "
                     f"Your own credits: {details.get('balance', '?')}. Re-run with --use-credits to use them.")
    elif error.code in ("CREDIT_EXHAUSTED", "TICKET_EXPIRED"):
        lines.append(f"Top up credits at {SITE}/plans?{UTM}")
    elif error.code in ("MISSING_API_KEY", "INVALID_API_KEY"):
        if os.environ.get("HASHSCRAPER_API_KEY", "").strip():
            lines.append("Check HASHSCRAPER_API_KEY (My page -> API). It is used before the key saved by login.")
        else:
            lines.append(f"The saved key was turned off, deleted or expired. {LOGIN_HINT} again.")
    elif error.code == "RATE_LIMITED":
        lines.append("Too many requests. Wait a minute before trying again.")
    elif details:
        lines.append(json.dumps(details, ensure_ascii=False))
    print("\n".join(lines), file=sys.stderr)
    return 2


def start_login(args):
    """Ask the server for a code and print the link. Returns the started session (dict) or exits."""
    try:
        started = call("POST", "/auth/device", None, body={})
    except ApiError as e:
        if e.status == 404:
            sys.exit("Browser login is not available yet. Set HASHSCRAPER_API_KEY to a key from My page -> API "
                     f"(free sign-up: {SIGN_UP}).")
        sys.exit(explain(e))
    link = started["verification_uri_complete"]
    print(f"Open this link and approve the connection:\n  {link}\n"
          f"Code: {started['user_code']} (check that the page shows the same code; it expires in "
          f"{started['expires_in'] // 60} minutes)", file=sys.stderr)
    if not args.no_browser:
        try:
            webbrowser.open(link)
        except Exception:  # noqa: BLE001 — no browser here (SSH, server); the link above is enough
            pass
    started["deadline"] = time.time() + int(started["expires_in"])
    return started


def wait_login(started):
    """Poll until the user approves in the browser, then save the key."""
    interval = max(int(started.get("interval") or 5), 1)
    while time.time() < started["deadline"]:
        time.sleep(interval)
        try:
            data = call("POST", "/auth/token", None, body={"device_code": started["device_code"]})["data"]
        except ApiError as e:
            if e.code == "authorization_pending":
                continue
            if e.code == "slow_down":
                interval += 5
                continue
            remove_quietly(PENDING_PATH)
            if e.code == "access_denied":
                if (e.details or {}).get("reason") == "key_limit":
                    sys.exit("Your account already has the maximum number of API keys. "
                             "Delete one in My page -> API, then run login again.")
                sys.exit("The connection was not approved in the browser. Nothing was saved.")
            if e.code == "expired_token":
                sys.exit("The code expired or was already used. Run login again.")
            return explain(e)
        except urllib.error.URLError:
            continue  # a dropped connection while waiting — try again at the next interval
        remove_quietly(PENDING_PATH)
        save_key(data)
        print(f"Connected. Saved the key \"{data.get('key_name')}\" to {CREDENTIALS_PATH} (only you can read it).",
              file=sys.stderr)
        if data.get("expires_at"):
            print(f"The key expires at {data['expires_at']}. Run login again after that.", file=sys.stderr)
        if os.environ.get("HASHSCRAPER_API_KEY", "").strip():
            print("Note: HASHSCRAPER_API_KEY is set, so it is still used before the saved key.", file=sys.stderr)
        return 0
    remove_quietly(PENDING_PATH)
    sys.exit("The code expired before it was approved. Run login again.")


def cmd_login(args):
    """Device-code login (like Claude Code / GitHub CLI): open a link, approve, and the key is saved here.

    login           start, print the link, wait for approval (for a terminal the user can see)
    login --start   only start and print the link, then exit (an agent shows the link to the user)
    login --wait    wait for the approval of the last --start
    """
    if args.wait:
        try:
            with open(PENDING_PATH, encoding="utf-8") as handle:
                started = json.load(handle)
        except (OSError, ValueError):
            sys.exit("No login is waiting. Run login --start first.")
        if not isinstance(started, dict) or (started.get("base_url") or "").rstrip("/") != BASE:
            sys.exit("The waiting login was started for another server. Run login --start again for this server.")
        return wait_login(started)
    started = start_login(args)
    if args.start:
        pending = {k: started[k] for k in ("device_code", "interval", "deadline")}
        pending["base_url"] = BASE  # --wait sends the code only to this server
        write_private(PENDING_PATH, pending)
        print("After the user approves, run: python3 scripts/hashscraper.py login --wait", file=sys.stderr)
        return 0
    return wait_login(started)


def cmd_logout(args):
    remove_quietly(PENDING_PATH)
    try:
        os.remove(CREDENTIALS_PATH)
        print(f"Deleted {CREDENTIALS_PATH}. To turn the key off on the server too, use My page -> API.", file=sys.stderr)
    except FileNotFoundError:
        print("No saved key.", file=sys.stderr)
    return 0


def cmd_rotate(args):
    """Swap the key saved by login for a new one. The server deletes the old key right away (it no longer counts)."""
    if os.environ.get("HASHSCRAPER_API_KEY", "").strip():
        sys.exit("HASHSCRAPER_API_KEY is set. rotate only changes the key saved by login. "
                 "Change that key in My page -> API (or unset it and use the saved key).")
    key = saved_key()
    if not key:
        sys.exit(f"No saved key to rotate. {LOGIN_HINT} first.")
    try:
        data = call("POST", "/auth/rotate", key, body={})["data"]
    except ApiError as e:
        if e.status == 404:
            sys.exit("Key rotation is not available yet. Nothing was changed.")
        if e.code == "FORBIDDEN":
            sys.exit(e.details.get("hint") or "This key cannot be rotated here. Change it in My page -> API.")
        return explain(e)
    except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError):
        # dropped connection, timeout or a cut-off answer — the server may already have rotated the key. Never retried.
        sys.exit("The connection dropped before the full answer arrived. If the server already rotated the key, "
                 f"the saved key no longer works — run `python3 scripts/hashscraper.py me` to check, and {LOGIN_HINT} if it fails.")
    try:
        save_key(data)
    except OSError as e:
        sys.exit(f"The server made a new key and deleted the old one, but saving to {CREDENTIALS_PATH} failed ({e.strerror}). "
                 f"The saved key no longer works. Fix the folder, then {LOGIN_HINT} to connect again.")
    print(f"Rotated. Saved the new key \"{data.get('key_name')}\" to {CREDENTIALS_PATH} (only you can read it). "
          "The old key was deleted on the server.", file=sys.stderr)
    if data.get("expires_at"):
        print(f"The new key expires at {data['expires_at']}.", file=sys.stderr)
    return 0


def cmd_catalog(args):
    bots = load_catalog()["bots"]
    if args.search:
        needle = args.search.lower()
        bots = [b for b in bots if needle in json.dumps(b, ensure_ascii=False).lower()]
    if args.json:
        print(json.dumps(bots, ensure_ascii=False, indent=2))
        return 0
    for bot in bots:
        inputs = ", ".join(f"{i['key']}={i.get('name_en') or i['name']}" for i in bot["inputs"])
        print(f"{bot['worker']}  [{bot.get('site_en') or bot.get('site')}] {bot['name']}  "
              f"{bot['credits_per_row']:g} credits/row\n    {bot.get('summary') or ''}\n    inputs: {inputs}")
    print(f"{len(bots)} bots", file=sys.stderr)
    return 0


def cmd_me(args):
    key = api_key()
    try:
        data = call("GET", "/me", key)["data"]
    except ApiError as e:
        return explain(e)
    free = data.get("daily_free")
    print(json.dumps({"email": data.get("email"), "daily_free": free}, ensure_ascii=False))
    if free is None:
        print("Daily free credits are not offered on this account right now. Use --use-credits to run with your own credits.",
              file=sys.stderr)
    return 0


def find_bot(key, worker):
    cursor = None
    while True:
        query = {"limit": 100}
        if cursor:
            query["cursor"] = cursor
        page = call("GET", "/bots", key, query=query)
        for bot in page.get("data", []):
            if (bot.get("worker_source") or {}).get("name") == worker:
                return bot["id"]
        cursor = page.get("next_cursor")
        if not cursor:
            return None


def import_bot(key, worker):
    """Add the catalog bot for this worker to the account. Returns its id, or None when it cannot be added."""
    try:
        added = call("POST", "/bots/import", key, body={"worker": worker})["data"]
    except ApiError as e:
        if e.code in ("BOT_NOT_FOUND", "RATE_LIMITED"):
            print(f"Could not add {worker} to your account ({e.code}).", file=sys.stderr)
            return None
        raise
    if added.get("created"):
        print(f"Added {added.get('name') or worker} to your account.", file=sys.stderr)
    return added["id"]


def parse_inputs(pairs, entry):
    """--input param1=value or --input "<input name>=value" -> {"param1": "value"}"""
    names = {}
    for item in (entry or {}).get("inputs", []):
        for label in (item["key"], item.get("name"), item.get("name_en")):
            if label:
                names[label.strip().lower()] = item["key"]
    inputs = {}
    for pair in pairs or []:
        if "=" not in pair:
            sys.exit(f"--input needs name=value (got {pair!r})")
        name, value = pair.split("=", 1)
        key = names.get(name.strip().lower()) or (name.strip() if name.strip().startswith("param") else None)
        if not key:
            sys.exit(f"Unknown input {name!r}. See: python3 hashscraper.py catalog --search {entry['worker'] if entry else ''}")
        inputs[key] = value
    return inputs


def fetch_rows(key, dataset_id):
    rows, cursor = [], None
    while True:
        query = {"limit": 1000}
        if cursor:
            query["cursor"] = cursor
        page = call("GET", f"/datasets/{dataset_id}/results", key, query=query)
        rows.extend(page.get("data", []))
        cursor = page.get("next_cursor")
        if not cursor:
            return rows


def cmd_run(args):
    key = api_key()
    entry = catalog_entry(args.worker)
    if entry is None:
        print(f"{args.worker} is not in this bundle's catalog. Trying it anyway.", file=sys.stderr)
    inputs = parse_inputs(args.input, entry)
    try:
        me = call("GET", "/me", key)["data"]
        free = me.get("daily_free")
        if free is None and not args.use_credits:
            sys.exit("Daily free credits are not offered on this account right now, so nothing was collected. "
                     "Re-run with --use-credits to use your own credits.")
        if free is not None:
            print(f"daily free credits left today: {free.get('remaining')} / {free.get('amount')}", file=sys.stderr)

        bot_id = find_bot(key, args.worker) or (import_bot(key, args.worker) if entry else None)
        if not bot_id:
            sys.exit(f"Your account has no bot for {args.worker}. Add it from the bot catalog ({BOT_CATALOG}), then run again.")

        started = call("POST", f"/bots/{bot_id}/collections", key,
                       body={"inputs": inputs, "save_to_settings": False},
                       idempotency_key=str(uuid.uuid4()), use_credits=args.use_credits)
        dataset_id = started["data"]["id"]
        print(f"collecting with {args.worker} (dataset {dataset_id})...", file=sys.stderr)
        return finish(key, dataset_id, args)
    except ApiError as e:
        return explain(e)


def wait_dataset(key, dataset_id, max_wait):
    waited = 0
    while True:
        dataset = call("GET", f"/datasets/{dataset_id}", key)["data"]
        if dataset["status"] in ENDED:
            return dataset
        if waited >= max_wait:
            sys.exit(f"Still collecting after {max_wait // 60} minutes. Get the rows later with: "
                     f"python3 hashscraper.py fetch {dataset_id}")
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        print(f"  {dataset['status']} ({waited}s, {dataset.get('data_count', 0)} rows)", file=sys.stderr)


def cmd_fetch(args):
    key = api_key()
    try:
        return finish(key, args.dataset_id, args)
    except ApiError as e:
        return explain(e)


def finish(key, dataset_id, args):
    """Wait for the dataset, then print its rows and a one-line summary."""
    dataset = wait_dataset(key, dataset_id, args.max_wait)
    rows = fetch_rows(key, dataset_id)
    after = (call("GET", "/me", key)["data"].get("daily_free") or {})

    if args.csv:
        columns = list(dict.fromkeys(k for row in rows for k in row))
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        print(f"{len(rows)} rows -> {args.csv}", file=sys.stderr)
    else:
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
    summary = f"status {dataset['status']} · {len(rows)} rows · own credits used so far {dataset.get('credits_used', 0)} (updates a few minutes later)"
    if after:
        summary += f" · daily free left {after.get('remaining')}"
    if dataset["status"] == "attention" and dataset.get("empty_reason"):
        summary += f" · empty reason: {dataset['empty_reason']}"
    print(summary, file=sys.stderr)
    print(FOOTER, file=sys.stderr)
    return 0


def main():
    parser = argparse.ArgumentParser(description="HashScraper bots via the v5 API (agent skill)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="connect your HashScraper account in the browser and save the key")
    p_login.add_argument("--no-browser", action="store_true", help="only print the link (do not try to open a browser)")
    p_login.add_argument("--start", action="store_true", help="only print the link and exit; then run login --wait")
    p_login.add_argument("--wait", action="store_true", help="wait for the approval started by login --start")
    p_login.set_defaults(func=cmd_login)

    p_logout = sub.add_parser("logout", help="delete the key saved by login")
    p_logout.set_defaults(func=cmd_logout)

    p_rotate = sub.add_parser("rotate", help="swap the key saved by login for a new one (the old key is deleted)")
    p_rotate.set_defaults(func=cmd_rotate)

    p_catalog = sub.add_parser("catalog", help="list bots in this bundle")
    p_catalog.add_argument("--search", help="filter by text (site, name, worker)")
    p_catalog.add_argument("--json", action="store_true", help="print the raw catalog entries")
    p_catalog.set_defaults(func=cmd_catalog)

    p_me = sub.add_parser("me", help="show today's free credits")
    p_me.set_defaults(func=cmd_me)

    p_run = sub.add_parser("run", help="collect with one bot")
    p_run.add_argument("worker", help="worker name from the catalog, e.g. DemoCoupangDetailWorker")
    p_run.add_argument("--input", action="append", help="param1=value (or the input name); repeat for more inputs")
    p_run.add_argument("--use-credits", action="store_true", help="continue with your own credits after the daily free credits")
    p_run.add_argument("--csv", help="write rows to this CSV file instead of JSON lines")
    p_run.add_argument("--max-wait", type=int, default=MAX_WAIT_SECONDS, help="seconds to wait for the collection (default 1200)")
    p_run.set_defaults(func=cmd_run)

    p_fetch = sub.add_parser("fetch", help="get the rows of an earlier run by dataset id")
    p_fetch.add_argument("dataset_id", type=int)
    p_fetch.add_argument("--csv", help="write rows to this CSV file instead of JSON lines")
    p_fetch.add_argument("--max-wait", type=int, default=MAX_WAIT_SECONDS, help="seconds to wait if it is still collecting")
    p_fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
