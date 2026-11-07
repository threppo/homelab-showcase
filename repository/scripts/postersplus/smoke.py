#!/usr/bin/env python3
"""Run inside PostersPlus after deployment; generates a few real cache entries."""

import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image
import config as server_config


BASE = "http://127.0.0.1:8000"


def request(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    # Never print the URL: its query contains the rendering access key.
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.status, response.headers.get("Content-Type", ""), response.read()


def main():
    # Saved dashboard settings take precedence over Compose environment values.
    access_key = server_config.ACCESS_KEY or ""
    admin_key = os.environ.get("ADMIN_KEY", "")
    if access_key.startswith("CHANGE_ME"):
        raise RuntimeError("Replace the placeholder rendering access key before testing")
    if len(admin_key) < 12 or admin_key == access_key or admin_key.startswith("CHANGE_ME"):
        raise RuntimeError("Set a separate real admin key of at least 12 characters")

    status, _, body = request("/health")
    if status != 200 or json.loads(body).get("status") != "ok":
        raise RuntimeError("Health response failed")
    print("PASS: health", flush=True)

    if access_key:
        try:
            request("/poster", {"tmdb_id": "157336", "type": "movie"})
        except urllib.error.HTTPError as error:
            if error.code != 403:
                raise RuntimeError("Unexpected unauthenticated response") from None
        else:
            raise RuntimeError("Rendering endpoint accepted an unauthenticated request")
        print("PASS: unauthenticated rendering rejected", flush=True)
    else:
        status, _, _ = request("/poster", {"tmdb_id": "157336", "type": "movie"})
        if status != 200:
            raise RuntimeError("Rendering did not match the saved access-key setting")
        print("PASS: rendering follows the saved setting with no access key", flush=True)

    common = {
        "access_key": access_key,
        "use_original_art": "true",
        "rating_display_mode": "3",
        "minimalist_append_mode": "1",
        "rating_badges": "imdb,tomatoes",
        "rating_badge_scale": "native",
        "sash_mode": "hidden",
        "show_quality_badges": "false",
        "show_award_sash": "false",
        "resolution": "500",
    }
    cases = [
        ("movie", {"tmdb_id": "157336", "imdb_id": "tt0816692", "type": "movie"}),
        ("series", {"tmdb_id": "1399", "imdb_id": "tt0944947", "type": "series"}),
        ("anime", {"stremio_id": "kitsu:1", "type": "series"}),
        ("landscape", {"tmdb_id": "157336", "type": "movie", "shape": "landscape"}),
    ]
    for label, ids in cases:
        params = {**common, **ids}
        started = time.monotonic()
        status, content_type, image_bytes = request("/poster", params)
        if status != 200 or not content_type.startswith("image/"):
            raise RuntimeError(f"{label}: endpoint did not return an image")
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            width, height = image.size
        if min(width, height) < 100:
            raise RuntimeError(f"{label}: image dimensions too small")
        if label == "landscape" and width <= height:
            raise RuntimeError("Landscape request returned a portrait image")
        if label != "landscape" and height <= width:
            raise RuntimeError(f"{label}: portrait request returned the wrong shape")
        elapsed = time.monotonic() - started
        print(f"PASS: {label}, {width}x{height}, {elapsed:.1f}s", flush=True)
        if label == "movie":
            _, _, repeated = request("/poster", params)
            if hashlib.sha256(repeated).digest() != hashlib.sha256(image_bytes).digest():
                raise RuntimeError("Repeated movie render changed; inspect cache/provisional response")
            print("PASS: repeated movie render has identical bytes", flush=True)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        print(f"FAIL: HTTP {error.code}; inspect server privately", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError:
        print("FAIL: endpoint unreachable or timed out", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, ValueError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
