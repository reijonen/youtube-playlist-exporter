import csv
from argparse import ArgumentParser
import requests
import json
import urllib.parse
import re

INVIDIOUS_INSTANCES_API_BASE_URL="https://api.invidious.io/instances.json"

def fetch_api_instances():
	params = urllib.parse.urlencode({"sort_by": "type,users"}, safe=",")
	res = requests.get(INVIDIOUS_INSTANCES_API_BASE_URL, params, timeout=5)
	if res.status_code != 200:
		print(f"Failed to fetch invidious instances: {res.content}")
		exit(1)

	try:
		instances = res.json()
	except:
		print(f"Failed to fetch invidious instances. JSON error: {res.content}")

	good_instances = []
	for instance in instances:
		if instance[1]["api"] == False or instance[1]["type"] != "https":
			continue

		res = requests.get(instance[1]["uri"])
		if res.status_code != 200:
			continue

		good_instances.append({
			"uri": instance[1]["uri"],
			"latency_ms": res.elapsed.total_seconds() * 1000
		})

	return sorted(good_instances, key=lambda x: x["latency_ms"])

def is_valid_video_id(id):
	return re.match("[a-zA-Z0-9_-]{11}", id) != None

def save(results, fails):
	with open("results.json", "w") as f: 
		json.dump(results, f)

	if len(fails) > 0:
		with open("fails.csv", "w") as f:
			csv_writer = csv.writer(f, dialect="unix")
			for video_id in fails:
				csv_writer.writerow([video_id])

def csv_to_video_ids(csv_path):
	with open(csv_path, newline="") as f:
		file = csv.reader(f, delimiter=",", quotechar='"')
		
		video_ids = []
		for row in file:
			if len(row) == 0:
				continue

			video_id = row[0].strip()
			if len(video_id) < 1 or is_valid_video_id(video_id) == False:
				continue

			video_ids.append(video_id)

		return video_ids

def from_csv(api_instances, csv_path):
	video_ids = csv_to_video_ids(csv_path)

	current_api = api_instances.pop(0)

	results = []
	fails = []

	err_counter = 0
	for idx, video_id in enumerate(video_ids):
		res = requests.get(f"{current_api["uri"]}/api/v1/videos/{video_id}")
		if res.status_code != 200 or len(res.text) < 1:
			fails.append(video_id)
			print(f"({idx}) {video_id} => failed to fetch")

			if res.text.lower().find("this video is not available") == -1:
				err_counter += 1
				if err_counter == 3:
					if len(api_instances) < 1:
						print("Out of working API instances")
						save(results, fails)
						exit(1)
					else:
						new_api = api_instances.pop(0)
						print(f"Too many errors {current_api['uri']}, switching to {new_api['uri']}")
						current_api = new_api
						err_counter = 0

			continue

		try:
			video = res.json()
			entry = {
				"title": video["title"],
				"author": video["author"]
			}
			results.append(entry)
			print(f"({idx}) {video_id} => {entry}")
		except:
			fails.append(video_id)
			print(f"({idx}) {video_id} => JSON error: {res.content}")

	save(results, fails)

def from_playlist(api_instances, playlist_url):
	playlist_id = re.search("(?<=list=)([\\w-]+)", playlist_url)
	if playlist_id == None:
		print("Invalid playlist url")
		exit(1)

	playlist_id = playlist_id.group()

	errors = []

	for current_api in api_instances:
		res = requests.get(f"{current_api["uri"]}/api/v1/playlists/{playlist_id}")
		if res.status_code == 404:
			print("Failed to find the playlist. Is it private?")
			exit(0)

		if res.status_code != 200:
			errors.append([current_api['uri'], f"{res.status_code} {res.text}"])
			continue

		results = []

		try:
			videos = res.json()["videos"]
		except:
			errors.append([current_api['uri'], f"Invalid JSON: {res.content}"])
			continue
			
		for v in videos:
			results.append({
				"title": v["title"],
				"author": v["author"]
			})

		save(results, [])

		exit(0)

	print(f"Failed to fetch playlist. Errors by instance:")
	for e in errors:
		print(f"{e[0]} => {e[1]}")

def main():
	parser = ArgumentParser()
	parser.add_argument("-purl", "--playlist-url", dest="playlist_url")
	parser.add_argument("-csvp", "--csv-path", dest="csv_path")
	args = parser.parse_args()
	if args.playlist_url == None and args.csv_path == None:
		print("Source required")
		exit(1)

	print("Fetching API instances")
	api_instances = fetch_api_instances()

	if args.playlist_url:
		print("Fetching playlist")
		from_playlist(api_instances, args.playlist_url)
	elif args.csv_path:
		print("Fetching videos")
		from_csv(api_instances, args.csv_path)

if __name__ == "__main__":
    main()
