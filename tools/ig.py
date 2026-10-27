"""
LayerX - Publicador de Instagram (API de Instagram con Instagram Login)

Uso:
  python ig.py check                          -> verifica el token y muestra tu usuario
  python ig.py post-image URL "caption"       -> publica una foto (JPEG en URL publica)
  python ig.py post-reel  URL "caption" [URL_PORTADA] -> publica un reel (MP4 en URL publica), portada opcional
  python ig.py post-carousel "caption" URL1 URL2 ... -> carrusel de 2 a 10 fotos/videos
  python ig.py refresh                      -> renueva el token (valido ~60 dias) y lo guarda en .env

El token se lee de un archivo .env en esta misma carpeta:
  IG_TOKEN=tu_token
  IG_USER_ID=tu_user_id      (se rellena solo al correr "check")

Solo usa la libreria estandar de Python 3.8+.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://graph.instagram.com"
VERSION = "v23.0"
ENV_PATH = Path(__file__).with_name(".env")


# ---------- .env ----------
def load_env():
    """Prioridad: variables de entorno (GitHub Actions / terminal) > archivo .env local."""
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("IG_TOKEN", "IG_USER_ID"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def save_env(env):
    ENV_PATH.write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")


# ---------- HTTP ----------
def call(method, path, params):
    url = f"{API}/{path}"
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except ValueError:
            msg = body
        sys.exit(f"Error de Instagram ({e.code}): {msg}")


# ---------- acciones ----------
def check(env):
    me = call("GET", "me", {"fields": "user_id,username", "access_token": env["IG_TOKEN"]})
    env["IG_USER_ID"] = str(me["user_id"])
    save_env(env)
    print(f"OK. Cuenta: @{me['username']}  |  user_id: {me['user_id']} (guardado en .env)")


def wait_until_ready(container_id, token, tries=40):
    for _ in range(tries):
        st = call("GET", f"{VERSION}/{container_id}", {"fields": "status_code", "access_token": token})
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            sys.exit("Instagram no pudo procesar el archivo (revisa formato y proporcion).")
        time.sleep(5)
    sys.exit("El archivo tarda demasiado en procesarse. Intenta de nuevo mas tarde.")


def publish(env, url, caption, reel=False, cover=None):
    token, uid = env["IG_TOKEN"], env.get("IG_USER_ID")
    if not uid:
        sys.exit('Falta IG_USER_ID. Corre primero: python ig.py check')
    params = {"caption": caption, "access_token": token}
    if reel:
        params.update({"media_type": "REELS", "video_url": url})
        if cover:
            params["cover_url"] = cover
    else:
        params["image_url"] = url
    container = call("POST", f"{VERSION}/{uid}/media", params)["id"]
    wait_until_ready(container, token)
    post = call("POST", f"{VERSION}/{uid}/media_publish", {"creation_id": container, "access_token": token})
    print(f"Publicado. ID del post: {post['id']}")


def publish_carousel(env, urls, caption):
    token, uid = env["IG_TOKEN"], env.get("IG_USER_ID")
    if not uid:
        sys.exit('Falta IG_USER_ID. Corre primero: python ig.py check')
    children = []
    for u in urls:
        p = {"is_carousel_item": "true", "access_token": token}
        if u.lower().split("?")[0].endswith((".mp4", ".mov")):
            p.update({"media_type": "VIDEO", "video_url": u})
        else:
            p["image_url"] = u
        cid = call("POST", f"{VERSION}/{uid}/media", p)["id"]
        wait_until_ready(cid, token)
        children.append(cid)
    parent = call("POST", f"{VERSION}/{uid}/media", {
        "media_type": "CAROUSEL", "children": ",".join(children),
        "caption": caption, "access_token": token})["id"]
    wait_until_ready(parent, token)
    post = call("POST", f"{VERSION}/{uid}/media_publish", {"creation_id": parent, "access_token": token})
    print(f"Publicado (carrusel de {len(urls)}). ID del post: {post['id']}")


def refresh(env):
    r = call("GET", "refresh_access_token", {"grant_type": "ig_refresh_token", "access_token": env["IG_TOKEN"]})
    env["IG_TOKEN"] = r["access_token"]
    save_env(env)
    days = int(r.get("expires_in", 0)) // 86400
    print(f"Token renovado y guardado. Vence en ~{days} dias.")


def main():
    env = load_env()
    if not env.get("IG_TOKEN"):
        sys.exit("No encuentro IG_TOKEN. Crea un archivo .env con la linea: IG_TOKEN=tu_token")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check":
        check(env)
    elif cmd in ("post-image", "post-reel") and len(sys.argv) >= 4:
        cover = sys.argv[4] if len(sys.argv) >= 5 else None
        publish(env, sys.argv[2], sys.argv[3], reel=(cmd == "post-reel"), cover=cover)
    elif cmd == "post-carousel" and len(sys.argv) >= 4:
        # uso: post-carousel "caption" URL1 URL2 ...
        publish_carousel(env, sys.argv[3:], sys.argv[2])
    elif cmd == "refresh":
        refresh(env)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
