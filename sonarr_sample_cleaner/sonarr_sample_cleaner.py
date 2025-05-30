#!/usr/bin/env python3
import requests
import logging
from datetime import datetime
import time
import os
import shutil

API_KEY = 'your_api_key_here'
BASE_URL = 'http://0.0.0.0:8989/api/v3'
LOG_FILE = 'sonarr_sample_cleaner.log'

NZBGET_URL = 'http://0.0.0.0:6789/jsonrpc'  # Adjust to match your NZBGet setup
NZBGET_USERNAME = 'nzbget_user'
NZBGET_PASSWORD = 'nzbget_password'

HEADERS = {
    'X-Api-Key': API_KEY,
    'Content-Type': 'application/json'
}

# Configure logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(message)s')

def trigger_rss_sync():
    data = {"name": "RssSync"}
    response = requests.post(f'{BASE_URL}/command', json=data, headers=HEADERS)
    response.raise_for_status()
    logging.info("Triggered Sonarr RSS Sync")

def get_queue():
    response = requests.get(f'{BASE_URL}/queue', headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return data.get("records", [])

def get_series_history(series_id):
    response = requests.get(f'{BASE_URL}/history?seriesId={series_id}', headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return data.get("records", [])

def block_release_from_history(history_items, title):
    for item in history_items:
        source_title = item.get('sourceTitle', '').lower()
        if title.lower() in source_title and 'guid' in item:
            data = {
                "title": item['sourceTitle'],
                "guid": item['guid'],
                "indexerId": item['indexerId'],
                "seriesId": item['seriesId'],
                "approved": False
            }
            r = requests.post(f'{BASE_URL}/release', json=data, headers=HEADERS)
            r.raise_for_status()
            logging.info(f"Blocked release: {item['sourceTitle']}")
            return True
    logging.warning(f"No matching history item found to block for: {title}")
    return False

# def block_release(item):
#     data = {
#         "title": item['title'],
#         "guid": item['release']['guid'],
#         "indexerId": item['release']['indexerId'],
#         "seriesId": item['series']['id'],
#         "approved": False
#     }
#     r = requests.post(f'{BASE_URL}/release', json=data, headers=HEADERS)
#     r.raise_for_status()
#     logging.info(f"Blocked: {item['title']}")

def search_episode(episode_id):
    data = {
        "name": "EpisodeSearch",
        "episodeIds": [episode_id]
    }
    r = requests.post(f'{BASE_URL}/command', json=data, headers=HEADERS)
    r.raise_for_status()
    logging.info(f"Triggered search for episode ID: {episode_id}")

def is_sample(item):
    try:
        messages = item.get('statusMessages', [])
        for msg in messages:
            for m in msg.get('messages', []):
                if 'sample' in m.lower():
                    return True
        # Fallback: also check title
        title = item.get('title', '')
        return isinstance(title, str) and 'sample' in title.lower()
    except Exception as e:
        logging.warning(f"Could not check for sample in item: {item} — {e}")
        return False

def delete_nzbget_download(download_id):
    payload = {
        "method": "editqueue",
        "params": ["GroupDelete", 0, "", download_id],
        "id": 1
    }
    response = requests.post(NZBGET_URL, json=payload, auth=(NZBGET_USERNAME, NZBGET_PASSWORD))
    response.raise_for_status()
    logging.info(f"Deleted NZBGet download: {download_id}")

def rescan_series(series_id):
    data = {
        "name": "RescanSeries",
        "seriesId": series_id
    }
    response = requests.post(f'{BASE_URL}/command', json=data, headers=HEADERS)
    response.raise_for_status()
    logging.info(f"Triggered rescan for series ID: {series_id}")

def main():
    queue = get_queue()

    if not isinstance(queue, list):
        logging.error("Expected queue to be a list, got: %s", type(queue))
        return

    for item in queue:
        logging.info(f"Inspecting queue item: {item}")
        if is_sample(item):
            logging.info(f"Sample detected: {item.get('title')}")
            try:
                episode_id = item['episodeId']
                series_id = item['seriesId']
                title = item.get('title')
                download_id = item.get('downloadId')
                history = get_series_history(series_id)
                matching_history = [h for h in history if h.get('episodeId') == episode_id]
                if not block_release_from_history(matching_history, title):
                    delete_nzbget_download(download_id)
                    # Attempt to remove from Sonarr queue directly
                    try:
                        queue_id = item.get('id')
                        if queue_id:
                            max_retries = 3
                            for attempt in range(max_retries):
                                del_response = requests.delete(f"{BASE_URL}/queue/{queue_id}", headers=HEADERS)
                                if del_response.status_code == 200:
                                    logging.info(f"Successfully removed item from Sonarr queue: {queue_id} on attempt {attempt+1}")
                                    break
                                else:
                                    logging.warning(f"Attempt {attempt+1}: Failed to remove queue item from Sonarr: {queue_id} — Status Code: {del_response.status_code}")
                                    time.sleep(2)
                            else:
                                logging.error(f"Failed to remove queue item after {max_retries} attempts: {queue_id}")
                        else:
                            logging.warning(f"No queue ID found for item: {item.get('title')}")
                    except Exception as e:
                        logging.error(f"Error while removing item from Sonarr queue: {e}")
                    # Remove the sample from disk
                    output_path = item.get('outputPath')
                    if output_path and os.path.exists(output_path):
                        try:
                            if os.path.isdir(output_path):
                                shutil.rmtree(output_path)
                                logging.info(f"Deleted directory at: {output_path}")
                            else:
                                os.remove(output_path)
                                logging.info(f"Deleted file at: {output_path}")
                        except Exception as e:
                            logging.warning(f"Failed to delete outputPath {output_path}: {e}")
                    else:
                        logging.warning(f"Output path not found or does not exist: {output_path}")
                    trigger_rss_sync()
                    rescan_series(series_id)
                search_episode(episode_id)
            except Exception as e:
                logging.error(f"Error handling {item.get('title', 'unknown')}: {e}")

    time.sleep(10)
    queue = get_queue()
    for item in queue:
        if is_sample(item):
            logging.warning(f"Sample still present after cleanup: {item.get('title')} (Download ID: {item.get('downloadId')})")

    logging.info("Dumping first queue item for structure review:")
    if queue:
        import json
        logging.info(json.dumps(queue[0], indent=2))
    else:
        logging.info("Queue is empty.")

if __name__ == "__main__":
    main()
