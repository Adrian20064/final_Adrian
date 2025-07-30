from django.shortcuts import render
from .forms import TripForm
import requests
from datetime import datetime
from pymongo import MongoClient

MONGO_URL = "mongodb://54.196.17.228:27017"
client = MongoClient(MONGO_URL)
db = client["travel_db"]
history_collection = db["queries"]

GEO_DB_API_URL = "https://wft-geo-db.p.rapidapi.com/v1/geo/countries/CA/regions/BC/cities?limit=20"
GEO_DB_KEY = "7a15765511msh56a61309a87d00cp1483f3jsn949e5ba2536c"  # solo si la necesitas para headers
OPENWEATHER_API_KEY = "01fc4f1f8daea0e2af1d3bbf3cc4f0fb"
ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImY0ZmU0NDI3MTEzOWQxMjkzODFmYzllMDVkZDAxZWIyMTk4NzMyNjY1YzNiNjZmNGI0MDVlZjc4IiwiaCI6Im11cm11cjY0In0"

def get_weather(city):
    try:
        response = requests.get(
            f"http://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"},
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        return f"{data['main']['temp']}°C, {data['weather'][0]['description']}"
    except Exception:
        return "Weather data unavailable"

def get_cities():
    try:
        # Si tu API geo-db requiere header x-rapidapi-key (según documentación)
        headers = {
            "X-RapidAPI-Key": GEO_DB_KEY,
            "X-RapidAPI-Host": "wft-geo-db.p.rapidapi.com"
        }
        response = requests.get(GEO_DB_API_URL, headers=headers, timeout=5)
        response.raise_for_status()
        cities = response.json().get("data", [])
        if not cities:
            raise Exception("Empty cities list")
        return cities
    except Exception:
        fallback = [
            {"name": "Victoria", "latitude": 48.4284, "longitude": -123.3656},
            {"name": "Vancouver", "latitude": 49.2827, "longitude": -123.1207},
            {"name": "Kelowna", "latitude": 49.8880, "longitude": -119.4960},
            {"name": "Burnaby", "latitude": 49.2488, "longitude": -122.9805},
            {"name": "Richmond", "latitude": 49.1666, "longitude": -123.1336},
            {"name": "Surrey", "latitude": 49.1044, "longitude": -122.8011},
        ]
        return fallback

def index(request):
    cities = get_cities()

    if request.method == "POST":
        form = TripForm(request.POST, cities=cities)
        if form.is_valid():
            start_city = form.cleaned_data['start_city']
            end_city = form.cleaned_data['end_city']

            # Validar que las ciudades no sean iguales
            if start_city == end_city:
                error = "Error: La ciudad de inicio y la ciudad de destino no pueden ser iguales."
                return render(request, "guides/index.html", {"form": form, "error": error})

            start_weather = get_weather(start_city)
            end_weather = get_weather(end_city)

            start_coords = next((c for c in cities if c["name"] == start_city), None)
            end_coords = next((c for c in cities if c["name"] == end_city), None)

            if not start_coords or not end_coords:
                error = "Error: Could not find city coordinates."
                return render(request, "guides/index.html", {"form": form, "error": error})

            route_url = "https://api.openrouteservice.org/v2/directions/driving-car/json"
            headers = {
                "Authorization": ORS_API_KEY,
                "Content-Type": "application/json"
            }
            body = {
                "coordinates": [
                    [start_coords['longitude'], start_coords['latitude']],
                    [end_coords['longitude'], end_coords['latitude']]
                ]
            }

            route_response = requests.post(route_url, headers=headers, json=body, timeout=10)
            route_response.raise_for_status()
            route_data = route_response.json()


            summary = route_data["features"][0]["properties"]["summary"]
            distance = summary["distance"] / 1000
            duration = summary["duration"] / 60
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
    else:
        form = TripForm(cities=cities)

    return render(request, "guides/index.html", {"form": form})


def history(request):
    records = list(history_collection.find().sort("timestamp", -1))
    for r in records:
        r["timestamp"] = r["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
    return render(request, "guides/history.html", {"records": records})
