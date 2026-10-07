"""Posts a carousel (or single image) to Instagram through Meta's Graph API.
Needs secrets IG_PAGE_TOKEN and IG_USER_ID. Images must be at public https URLs."""
import os
import time

import requests

import config

GRAPH = f"https://graph.facebook.com/{config.GRAPH_VERSION}"


class InstagramError(Exception):
    pass


def _token():
    tok = os.getenv("IG_PAGE_TOKEN", "").strip()
    if not tok:
        raise InstagramError("IG_PAGE_TOKEN secret is missing.")
    return tok


def _call(method, path, **params):
    params["access_token"] = _token()
    r = requests.request(method, f"{GRAPH}/{path}",
                         data=params if method == "POST" else None,
                         params=params if method == "GET" else None, timeout=90)
    body = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in body:
        err = body.get("error", {})
        raise InstagramError(f"Instagram said: {err.get('message', r.text[:300])} "
                             f"(code {err.get('code')}, subcode {err.get('error_subcode')})")
    return body


def _wait_ready(container_id, tries=30):
    for _ in range(tries):
        status = _call("GET", container_id, fields="status_code,status").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            info = _call("GET", container_id, fields="status")
            raise InstagramError(f"Instagram couldn't process an image: {info.get('status')}")
        time.sleep(4)
    raise InstagramError("Instagram took too long to process the images.")


def publish(image_urls, caption):
    ig = os.getenv("IG_USER_ID", "").strip()
    if not ig:
        raise InstagramError("IG_USER_ID secret is missing.")

    if len(image_urls) == 1:
        cid = _call("POST", f"{ig}/media", image_url=image_urls[0], caption=caption)["id"]
    else:
        children = []
        for url in image_urls[:10]:
            child = _call("POST", f"{ig}/media", image_url=url, is_carousel_item="true")["id"]
            _wait_ready(child)
            children.append(child)
        cid = _call("POST", f"{ig}/media", media_type="CAROUSEL",
                    children=",".join(children), caption=caption)["id"]
    _wait_ready(cid)
    media_id = _call("POST", f"{ig}/media_publish", creation_id=cid)["id"]
    try:
        return _call("GET", media_id, fields="permalink").get("permalink", "")
    except InstagramError:
        return ""
