import os
import requests

BASE_URL = "https://api.raindrop.io/rest/v1"

def get_token():
    token = os.environ.get("RAINDROP_TEST_TOKEN")
    if not token:
        raise ValueError("RAINDROP_TEST_TOKEN environment variable is not set. Please set it or use a .env file.")
    return token

def get_headers():
    return {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json"
    }

# --- RAINDROPS ---

def get_raindrops(collection_id=0, search="", sort="-created", page=0, perpage=50, nested=False):
    url = f"{BASE_URL}/raindrops/{collection_id}"
    params = {"sort": sort, "page": page, "perpage": perpage, "nested": nested}
    if search:
        params['search'] = search
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json().get("items", [])

def get_raindrop(raindrop_id):
    url = f"{BASE_URL}/raindrop/{raindrop_id}"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json().get("item", {})

def add_raindrop(link, title=None, collection_id=0, tags=None, excerpt=None, note=None, important=False):
    url = f"{BASE_URL}/raindrop"
    payload = {
        "link": link,
        "collectionId": collection_id,
        "important": important
    }
    if title: payload["title"] = title
    if tags: payload["tags"] = tags
    if excerpt: payload["excerpt"] = excerpt
    if note: payload["note"] = note
    
    response = requests.post(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("item", {})

def edit_raindrop(raindrop_id, title=None, tags=None, collection_id=None, important=None, excerpt=None, note=None):
    url = f"{BASE_URL}/raindrop/{raindrop_id}"
    payload = {}
    if title is not None: payload["title"] = title
    if tags is not None: payload["tags"] = tags
    if collection_id is not None: payload["collection"] = {"$id": collection_id}
    if important is not None: payload["important"] = important
    if excerpt is not None: payload["excerpt"] = excerpt
    if note is not None: payload["note"] = note
        
    response = requests.put(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("item", {})

def delete_raindrop(raindrop_id):
    url = f"{BASE_URL}/raindrop/{raindrop_id}"
    response = requests.delete(url, headers=get_headers())
    response.raise_for_status()
    return response.json().get("result", False)

def delete_raindrops(collection_id, ids):
    url = f"{BASE_URL}/raindrops/{collection_id}"
    payload = {"ids": ids}
    response = requests.delete(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("modified", 0)

# --- COLLECTIONS ---

def get_collections():
    url = f"{BASE_URL}/collections"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json().get("items", [])

def get_child_collections():
    url = f"{BASE_URL}/collections/childrens"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json().get("items", [])

def get_collection(collection_id):
    url = f"{BASE_URL}/collection/{collection_id}"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json().get("item", {})

def create_collection(title, view="list", sort=0, public=False, parent_id=None):
    url = f"{BASE_URL}/collection"
    payload = {
        "title": title,
        "view": view,
        "sort": sort,
        "public": public
    }
    if parent_id is not None:
        payload["parent"] = {"$id": parent_id}
        
    response = requests.post(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("item", {})

def update_collection(collection_id, title=None, view=None, sort=None, public=None, parent_id=None):
    url = f"{BASE_URL}/collection/{collection_id}"
    payload = {}
    if title is not None: payload["title"] = title
    if view is not None: payload["view"] = view
    if sort is not None: payload["sort"] = sort
    if public is not None: payload["public"] = public
    if parent_id is not None: payload["parent"] = {"$id": parent_id}
        
    response = requests.put(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("item", {})

def delete_collection(collection_id):
    url = f"{BASE_URL}/collection/{collection_id}"
    response = requests.delete(url, headers=get_headers())
    response.raise_for_status()
    return response.json().get("result", False)

# --- TAGS ---

def get_tags(collection_id=None):
    url = f"{BASE_URL}/tags" + (f"/{collection_id}" if collection_id else "")
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json().get("items", [])

def rename_tag(old_name, new_name, collection_id=None):
    url = f"{BASE_URL}/tags" + (f"/{collection_id}" if collection_id else "")
    payload = {"replace": new_name, "tags": [old_name]}
    response = requests.put(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("result", False)

def delete_tags(tags, collection_id=None):
    url = f"{BASE_URL}/tags" + (f"/{collection_id}" if collection_id else "")
    payload = {"tags": tags}
    response = requests.delete(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("result", False)

# --- HIGHLIGHTS ---

def get_all_highlights(page=0, perpage=25):
    url = f"{BASE_URL}/highlights"
    params = {"page": page, "perpage": perpage}
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json().get("items", [])

def get_raindrop_highlights(raindrop_id):
    url = f"{BASE_URL}/raindrop/{raindrop_id}"
    response = requests.get(url, headers=get_headers())
    response.raise_for_status()
    return response.json().get("item", {}).get("highlights", [])

def add_highlight(raindrop_id, text, color="yellow", note=""):
    url = f"{BASE_URL}/raindrop/{raindrop_id}"
    payload = {
        "highlights": [
            {"text": text, "color": color, "note": note}
        ]
    }
    response = requests.put(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("item", {}).get("highlights", [])

def delete_highlight(raindrop_id, highlight_id):
    url = f"{BASE_URL}/raindrop/{raindrop_id}"
    payload = {
        "highlights": [
            {"_id": highlight_id, "text": ""}
        ]
    }
    response = requests.put(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("result", False)
