import requests
from datetime import datetime
from django.shortcuts import render, redirect
from .forms import TravelForm
from pymongo import MongoClient
from django.http import HttpResponse
from django.contrib import messages

GEO_API_KEY = "7a15765511msh56a61309a87d00cp1483f3jsn949e5ba2536c"
WEATHER_API_KEY = "01fc4f1f8daea0e2af1d3bbf3cc4f0fb"
ROUTES_API_KEY = "f4fe44271139d129381fc9e05dd01eb2198732665c3b66f4b405ef78"
MONGO_URI = "mongodb://54.162.107.60:27017"

client = MongoClient(MONGO_URI)
db = client["travel_planner"]
history_collection = db["history"]

def get_bc_cities():
    url = "http://geodb-free-service.wirefreethought.com/v1/geo/countries/CA/regions/BC/cities?limit=10"
    headers = {"X-RapidAPI-Key": GEO_API_KEY}
    response = requests.get(url, headers=headers)
    data = response.json()
    if "data" not in data:
        raise ValueError(f"No 'data' in API response: {data}")
    cities = data["data"]
    return sorted([city["city"] for city in cities])

def get_city_coords(city_name):
    url = f"http://geodb-free-service.wirefreethought.com/v1/geo/cities?namePrefix={city_name}&countryIds=CA&limit=1"
    headers = {"X-RapidAPI-Key": GEO_API_KEY}
    res = requests.get(url, headers=headers)
    data = res.json()
    if "data" not in data or not data["data"]:
        raise ValueError(f"City '{city_name}' not found.")
    city_data = data["data"][0]
    return {"lat": city_data["latitude"], "lon": city_data["longitude"]}

def get_weather_by_coords(lat, lon):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": WEATHER_API_KEY,
        "units": "metric"
    }
    res = requests.get(url, params=params)
    data = res.json()
    if "weather" not in data:
        raise ValueError(f"Weather API error at coords ({lat},{lon}): {data.get('message', 'Unknown error')}")
    return {
        "temp": data["main"]["temp"],
        "desc": data["weather"][0]["description"],
        "coord": {"lat": lat, "lon": lon}
    }
    
def geocode_city(city_name):
    url = "https://api.openrouteservice.org/geocode/search"
    headers = {"Authorization": ROUTES_API_KEY}
    params = {"text": city_name, "size": 1}
    res = requests.get(url, headers=headers, params=params)
    data = res.json()
    
    if "features" not in data or not data["features"]:
        raise ValueError(f"City '{city_name}' not found")
    
    coords = data["features"][0]["geometry"]["coordinates"]  # [lon, lat]
    return {"lon": coords[0], "lat": coords[1]}

def get_route(start_coords, end_coords):
    url = "https://api.openrouteservice.org/v2/directions/driving-car/json"
    headers = {
        "Authorization": ROUTES_API_KEY,
        "Content-Type": "application/json"
    }
    body = {
        "coordinates": [
            [start_coords["lon"], start_coords["lat"]],
            [end_coords["lon"], end_coords["lat"]]
        ]
    }
    res = requests.post(url, json=body, headers=headers)
    data = res.json()

    
    if "features" in data and data["features"]:
        route = data["features"][0]["properties"]
        segment = route["segments"][0]

    
    elif "routes" in data and data["routes"]:
        route = data["routes"][0]
        segment = route["segments"][0]

    else:
        raise ValueError(f"Route API error or no route found: {data}")

    return {
        "distance": round(segment["distance"] / 1000, 2),  # km
        "duration": round(segment["duration"] / 60, 2),   # minutos
        "steps": [
            {
                "text": step["instruction"],
                "distance": round(step["distance"], 1)
            } for step in segment["steps"]
        ]
    }


def get_advice(weather, time):
    if weather["desc"] in ["clear sky", "few clouds"] and 6 <= time.hour <= 18:
        return "Good time to start your trip!"
    return "Consider delaying your trip due to bad weather."

def index(request):
    cities = get_bc_cities()
    return render(request, 'guides/index.html', {"cities": cities})

def result(request):
    if request.method == "POST":
        start = request.POST.get('start_city')
        end = request.POST.get('end_city')

        if not start or not end:
            messages.error(request, "Please select both start and end cities.")
            return redirect("index")

        try:
            start_coords = get_city_coords(start)
            end_coords = get_city_coords(end)

            start_weather = get_weather_by_coords(start_coords["lat"], start_coords["lon"])
            end_weather = get_weather_by_coords(end_coords["lat"], end_coords["lon"])

            route = get_route(start_coords, end_coords)
            advice = get_advice(start_weather, datetime.now())

            entry = {
                "start_city": start,
                "end_city": end,
                "timestamp": str(datetime.now()),
                "route": route
            }
            history_collection.insert_one(entry)

            duration_minutes = route["duration"]
            duration_hours = int(duration_minutes // 60)
            duration_remainder = int(duration_minutes % 60)

            print({
                "start": start,
                "end": end,
                "start_weather": start_weather,
                "end_weather": end_weather,
                "route": route,
                "advice": advice, 
                "duration_hours": duration_hours,
                "duration_remainder": duration_remainder,
            })

            return render(request, 'guides/result.html', {
                "start": start,
                "end": end,
                "start_weather": start_weather,
                "end_weather": end_weather,
                "route": route,
                "advice": advice,
                "duration_hours": duration_hours,
                "duration_remainder": duration_remainder,
            })

        except Exception as e:
            print(f"Error in result view: {e}")
            
            return HttpResponse(f"<h1>Error:</h1><pre>{e}</pre>")

   
    return HttpResponse("Method Not Allowed", status=405)


def history(request):
    results = list(history_collection.find().sort("_id", -1))
    return render(request, "guides/history.html", {"results": results})
