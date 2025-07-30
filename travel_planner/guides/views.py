import requests
from django.shortcuts import render
from django.http import HttpResponse
from datetime import datetime
from pymongo import MongoClient


client = MongoClient("mongodb://54.196.17.228:27017")
db = client["travel_db"]
logs = db["queries"]


GEO_API_KEY = "7a15765511msh56a61309a87d00cp1483f3jsn949e5ba2536c"
WEATHER_API_KEY = "01fc4f1f8daea0e2af1d3bbf3cc4f0fb"
ROUTES_API_KEY = "eyJvcmciOiI1YjNjZ...truncated..."

def get_bc_cities():
    url = "https://wft-geo-db.p.rapidapi.com/v1/geo/countries/CA/regions/BC/cities?limit=20"
    headers = {
        "X-RapidAPI-Key": GEO_API_KEY,
        "X-RapidAPI-Host": "wft-geo-db.p.rapidapi.com"
    }

    try:
        res = requests.get(url, headers=headers, timeout=6)
        res.raise_for_status()
        data = res.json().get("data", [])
        return [city["name"] for city in data] if data else backup_city_list()
    except:
        return backup_city_list()


def backup_city_list():
    return [
        "Vancouver", "Victoria", "Kelowna", "Surrey", "Richmond",
        "Burnaby", "Abbotsford", "Kamloops", "Nanaimo", "Delta",
        "Coquitlam", "White Rock", "Langley", "Prince George", "Vernon",
        "Mission", "Penticton", "Chilliwack", "New Westminster", "North Vancouver"
    ]


def home_page(request):
    cities = get_bc_cities()
    return render(request, "index.html", {"cities": cities})


def fetch_weather(city):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": f"{city},CA",
        "appid": WEATHER_API_KEY,
        "units": "metric"
    }
    try:
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        return f"{data['main']['temp']}°C, {data['weather'][0]['description']}"
    except:
        return "Weather info not available"


def locate_city(city):
    url = f"https://wft-geo-db.p.rapidapi.com/v1/geo/countries/CA/regions/BC/cities?namePrefix={city}"
    headers = {
        "X-RapidAPI-Key": GEO_API_KEY,
        "X-RapidAPI-Host": "wft-geo-db.p.rapidapi.com"
    }

    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        data = res.json().get("data", [])

        if not data:
            raise ValueError("City not found in database.")

        for entry in data:
            if entry["name"].lower() == city.lower():
                return entry["latitude"], entry["longitude"]

        return data[0]["latitude"], data[0]["longitude"]
    except:
        fallback = {
            "vancouver": (49.2827, -123.1207),
            "victoria": (48.4284, -123.3656),
            "kelowna": (49.8880, -119.4960),
            "burnaby": (49.2488, -122.9805),
            "richmond": (49.1666, -123.1336),
            "kamloops": (50.6745, -120.3273)
        }
        return fallback.get(city.lower(), (None, None))


def calculate_route(origin, destination):
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {
        "Authorization": ROUTES_API_KEY,
        "Content-Type": "application/json"
    }
    body = {
        "coordinates": [
            [origin[1], origin[0]],
            [destination[1], destination[0]]
        ]
    }

    res = requests.post(url, headers=headers, json=body, timeout=10)
    res.raise_for_status()
    route = res.json()
    feature = route.get("features", [])[0]

    return feature["properties"]["summary"], feature["properties"]["segments"][0]["steps"]


def travel_results(request):
    city_from = request.GET.get("start_city")
    city_to = request.GET.get("end_city")

    if not city_from or not city_to:
        return HttpResponse("Both cities must be selected.", status=400)

    weather_origin = fetch_weather(city_from)
    weather_destination = fetch_weather(city_to)

    try:
        origin_coords = locate_city(city_from)
        dest_coords = locate_city(city_to)
    except Exception as err:
        return HttpResponse(f"Location error: {err}", status=400)

    if None in origin_coords or None in dest_coords:
        return HttpResponse("Coordinates not found.", status=400)

    try:
        route_summary, route_steps = calculate_route(origin_coords, dest_coords)
    except Exception as e:
        return HttpResponse(f"Route fetch failed: {e}", status=400)

    now_hour = datetime.now().hour
    suggestion = "Ideal time to travel." if "rain" not in weather_origin.lower() and 6 <= now_hour <= 20 else "Consider postponing due to poor conditions."

   
    try:
        logs.insert_one({
            "from": city_from,
            "to": city_to,
            "time": datetime.now(),
            "distance": route_summary["distance"],
            "duration": route_summary["duration"],
            "note": suggestion
        })
    except Exception as e:
        print(f"[Warning] Logging failed: {e}")

    context = {
        "from_city": city_from,
        "to_city": city_to,
        "weather_from": weather_origin,
        "weather_to": weather_destination,
        "distance_km": round(route_summary["distance"] / 1000, 2),
        "duration_min": round(route_summary["duration"] / 60, 2),
        "steps": route_steps,
        "recommendation": suggestion
    }

    return render(request, "results.html", context)

def travel_log(request):
    try:
        records = list(logs.find().sort("time", -1))
        for r in records:
            if isinstance(r.get("time"), datetime):
                r["time"] = r["time"].strftime("%Y-%m-%d %H:%M")
        return render(request, "history.html", {"records": records})
    except Exception as err:
        return HttpResponse(f"Could not load history: {err}", status=500)
