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

def get_raindrops(collection_id=0, search=""):
    url = f"{BASE_URL}/raindrops/{collection_id}"
    params = {}
    if search:
        params['search'] = search
    response = requests.get(url, headers=get_headers(), params=params)
    response.raise_for_status()
    return response.json().get("items", [])

def add_raindrop(link, title=None, collection_id=0, tags=None):
    url = f"{BASE_URL}/raindrop"
    payload = {
        "link": link,
        "collectionId": collection_id
    }
    if title:
        payload["title"] = title
    if tags:
        payload["tags"] = tags
    
    response = requests.post(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("item", {})

def edit_raindrop(raindrop_id, title=None, tags=None):
    url = f"{BASE_URL}/raindrop/{raindrop_id}"
    payload = {}
    if title:
        payload["title"] = title
    if tags is not None:
        payload["tags"] = tags
        
    response = requests.put(url, headers=get_headers(), json=payload)
    response.raise_for_status()
    return response.json().get("item", {})

def delete_raindrop(raindrop_id):
    url = f"{BASE_URL}/raindrop/{raindrop_id}"
    response = requests.delete(url, headers=get_headers())
    response.raise_for_status()
    return response.json().get("result", False)
