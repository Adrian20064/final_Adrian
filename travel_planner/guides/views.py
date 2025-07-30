import requests
from django.shortcuts import render
from django.http import HttpResponse
from datetime import datetime
from pymongo import MongoClient

# MongoDB setup
MONGO_URI = "mongodb://54.196.17.228:27017"
mongo_client = MongoClient(MONGO_URI)
database = mongo_client["travel_db"]
history_collection = database["queries"]

# Your API keys
GEO_DB_API_KEY = "7a15765511msh56a61309a87d00cp1483f3jsn949e5ba2536c"
OPENWEATHER_API_KEY = "01fc4f1f8daea0e2af1d3bbf3cc4f0fb"
ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImY0ZmU0NDI3MTEzOWQxMjkzODFmYzllMDVkZDAxZWIyMTk4NzMyNjY1YzNiNjZmNGI0MDVlZjc4IiwiaCI6Im11cm11cjY0In0"

def fetch_bc_cities():
    endpoint = "https://wft-geo-db.p.rapidapi.com/v1/geo/countries/CA/regions/BC/cities?limit=20"
    headers = {
        "X-RapidAPI-Key": GEO_DB_API_KEY,
        "X-RapidAPI-Host": "wft-geo-db.p.rapidapi.com"
    }

    try:
        response = requests.get(endpoint, headers=headers, timeout=5)
        response.raise_for_status()
        cities_info = response.json().get("data", [])
        if not cities_info:
            return fallback_cities()
        return [city["name"] for city in cities_info]
    except Exception:
        return fallback_cities()

def fallback_cities():
    # Static fallback list of BC cities
    return [
        "Vancouver", "Victoria", "Burnaby", "Richmond", "Surrey",
        "Langley", "Abbotsford", "Coquitlam", "Kelowna", "Kamloops",
        "Prince George", "Nanaimo", "Chilliwack", "Vernon", "Penticton",
        "Mission", "North Vancouver", "New Westminster", "White Rock", "Delta"
    ]

def home_view(request):
    cities = fetch_bc_cities()
    return render(request, "index.html", {"cities": cities})

def get_city_weather(city_name):
    weather_api_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": f"{city_name},CA",
        "appid": OPENWEATHER_API_KEY,
        "units": "metric"
    }
    try:
        response = requests.get(weather_api_url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        temp = data["main"]["temp"]
        description = data["weather"][0]["description"]
        return f"{temp}°C, {description}"
    except Exception:
        return "Weather data unavailable"

def get_city_coordinates(city_name):
    geo_api_url = f"https://wft-geo-db.p.rapidapi.com/v1/geo/countries/CA/regions/BC/cities?namePrefix={city_name}"
    headers = {
        "X-RapidAPI-Key": GEO_DB_API_KEY,
        "X-RapidAPI-Host": "wft-geo-db.p.rapidapi.com"
    }

    try:
        response = requests.get(geo_api_url, headers=headers, timeout=5)
        response.raise_for_status()
        city_data_list = response.json().get("data", [])
        if not city_data_list:
            raise ValueError("City not found")

        for city_data in city_data_list:
            if city_data["name"].lower() == city_name.lower():
                return city_data["latitude"], city_data["longitude"]

        # If no exact match found, return first city's coords
        first_city = city_data_list[0]
        return first_city["latitude"], first_city["longitude"]

    except Exception:
        # Provide fallback coordinates for some common cities
        fallback_coords = {
            "vancouver": (49.2827, -123.1207),
            "victoria": (48.4284, -123.3656),
            "burnaby": (49.2488, -122.9805),
            "richmond": (49.1666, -123.1336),
            "surrey": (49.1913, -122.8490),
            "kelowna": (49.8880, -119.4960),
            "kamloops": (50.6745, -120.3273)
        }
        key = city_name.lower()
        if key in fallback_coords:
            return fallback_coords[key]
        raise ValueError(f"Coordinates not found for city: {city_name}")

def get_route(start_coords, end_coords):
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "coordinates": [
            [start_coords[1], start_coords[0]],
            [end_coords[1], end_coords[0]]
        ]
    }
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()
    route_data = response.json()
    if "features" not in route_data or not route_data["features"]:
        raise ValueError("Invalid route response")

    route_summary = route_data["features"][0]["properties"]["summary"]
    route_steps = route_data["features"][0]["properties"]["segments"][0]["steps"]
    return route_summary, route_steps

def results_view(request):
    start_city = request.GET.get("start_city")
    end_city = request.GET.get("end_city")

    if not start_city or not end_city:
        return HttpResponse("Please provide both start and end cities.", status=400)

    weather_start = get_city_weather(start_city)
    weather_end = get_city_weather(end_city)

    try:
        start_coords = get_city_coordinates(start_city)
        end_coords = get_city_coordinates(end_city)
    except ValueError as e:
        return HttpResponse(str(e), status=400)

    try:
        summary, steps = get_route(start_coords, end_coords)
    except Exception as e:
        return HttpResponse(f"Failed to fetch route: {e}", status=400)

    current_hour = datetime.now().hour
    advice = ("Good time to start your trip!" 
              if "rain" not in weather_start.lower() and 6 <= current_hour <= 20 
              else "Consider delaying your trip due to weather conditions.")

    # Save query to MongoDB
    try:
        history_collection.insert_one({
            "start_city": start_city,
            "end_city": end_city,
            "timestamp": datetime.now(),
            "distance_meters": summary["distance"],
            "duration_seconds": summary["duration"],
            "advice": advice
        })
    except Exception as err:
        print(f"Warning: Failed to save history - {err}")

    context = {
        "start_city": start_city,
        "end_city": end_city,
        "weather_start": weather_start,
        "weather_end": weather_end,
        "distance_km": round(summary["distance"] / 1000, 2),
        "duration_min": round(summary["duration"] / 60, 2),
        "route_steps": steps,
        "advice": advice,
    }
    return render(request, "results.html", context)

def history_view(request):
    try:
        records = list(history_collection.find().sort("timestamp", -1))
        # Format timestamps for display
        for record in records:
            if "timestamp" in record and hasattr(record["timestamp"], "strftime"):
                record["timestamp"] = record["timestamp"].strftime("%Y-%m-%d %H:%M")
        return render(request, "history.html", {"records": records})
    except Exception as err:
        return HttpResponse(f"Could not load history: {err}", status=500)
