from django.shortcuts import render
from .forms import TripForm
import requests
import os
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = "mongodb://54.196.17.228:27017"
client = MongoClient(MONGO_URL)
db = client["travel_db"]
history_collection = db["queries"]

GEO_DB_API_URL = os.getenv("geo_db_url")
GEO_DB_KEY = os.getenv("geo_db_key")
OPENWEATHER_API_KEY = os.getenv("weather_api_key")
OPENROUTE_API_KEY = os.getenv("heigit_key")

def get_weather(city):
    try:
        response = requests.get(
            f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        )
        response.raise_for_status()
        data = response.json()
        return f"{data['main']['temp']}°C, {data['weather'][0]['description']}"
    except Exception:
        return "Weather data unavailable"

def get_cities():
    try:
        response = requests.get(GEO_DB_API_URL)
        response.raise_for_status()
        cities = response.json().get("data", [])
        if not cities:
            raise Exception()
        return cities
    except Exception:
        fallback = ["Victoria", "Vancouver", "Kelowna", "Burnaby", "Richmond", "Surrey"]
        return [{"name": city} for city in fallback]

def index(request):
    cities = get_cities()
    form = TripForm(cities=cities)

    if request.method == "POST":
        form = TripForm(request.POST, cities=cities)
        if form.is_valid():
            start_city = form.cleaned_data['start_city']
            end_city = form.cleaned_data['end_city']

            start_weather = get_weather(start_city)
            end_weather = get_weather(end_city)

            start_coords = next((c for c in cities if c["name"] == start_city), None)
            end_coords = next((c for c in cities if c["name"] == end_city), None)

            if not start_coords or not end_coords:
                error = "Error: Could not find city coordinates."
                return render(request, "guides/index.html", {"form": form, "error": error})

            route_url = (
                f"https://api.openrouteservice.org/v2/directions/driving-car"
                f"?api_key={OPENROUTE_API_KEY}"
                f"&start={start_coords['longitude']},{start_coords['latitude']}"
                f"&end={end_coords['longitude']},{end_coords['latitude']}"
            )
            route_data = requests.get(route_url).json()

            distance = route_data["features"][0]["properties"]["summary"]["distance"] / 1000
            duration = route_data["features"][0]["properties"]["summary"]["duration"] / 60
            steps = [step["instruction"] for step in route_data["features"][0]["properties"]["segments"][0]["steps"]]

            advice = "Good time to start your trip!" if "rain" not in start_weather.lower() else "Consider delaying your trip."

            history_collection.insert_one({
                "start": start_city,
                "end": end_city,
                "timestamp": datetime.now(),
                "distance_km": distance,
                "duration_min": duration
            })

            return render(request, "guides/result.html", {
                "start": start_city,
                "end": end_city,
                "start_weather": start_weather,
                "end_weather": end_weather,
                "distance": distance,
                "duration": duration,
                "steps": steps,
                "advice": advice
            })

    return render(request, "guides/index.html", {"form": form})

def history(request):
    records = list(history_collection.find().sort("timestamp", -1))
    for r in records:
        r["timestamp"] = r["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
    return render(request, "guides/history.html", {"records": records})
