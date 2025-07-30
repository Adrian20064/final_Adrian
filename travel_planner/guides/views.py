import os
import requests
from datetime import datetime
from django.shortcuts import render, redirect
from .forms import TravelForm
from dotenv import load_dotenv
from pymongo import MongoClient


GEO_API_KEY = "7a15765511msh56a61309a87d00cp1483f3jsn949e5ba2536c"
WEATHER_API_KEY = "01fc4f1f8daea0e2af1d3bbf3cc4f0fb"
ROUTES_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6ImY0ZmU0NDI3MTEzOWQxMjkzODFmYzllMDVkZDAxZWIyMTk4NzMyNjY1YzNiNjZmNGI0MDVlZjc4IiwiaCI6Im11cm11cjY0In0="
MONGO_URI = "mongodb://54.172.19.24:27017"

client = MongoClient(MONGO_URI)
db = client["travel_planner"]
history_collection = db["history"]


def get_bc_cities():
    url = "http://geodb-free-service.wirefreethought.com/v1/geo/countries/CA/regions/BC/cities?limit=20"
    headers = {"X-RapidAPI-Key": GEO_API_KEY}
    response = requests.get(url, headers=headers)

    print(response.status_code)
    print(response.text)  # para ver qué devuelve la API

    data = response.json()
    if "data" not in data:
        raise ValueError(f"La respuesta de la API no contiene 'data': {data}")

    cities = data["data"]
    return sorted([city["city"] for city in cities])

def get_weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city},CA&appid={WEATHER_API_KEY}&units=metric"
    data = requests.get(url).json()
    return {
        "temp": data["main"]["temp"],
        "desc": data["weather"][0]["description"],
        "coord": data["coord"]
    }

def get_route(start_coords, end_coords):
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {"Authorization": ROUTES_API_KEY}
    body = {
        "coordinates": [[start_coords["lon"], start_coords["lat"]], [end_coords["lon"], end_coords["lat"]]]
    }
    res = requests.post(url, json=body, headers=headers)
    route = res.json()["features"][0]["properties"]
    return {
        "distance": round(route["segments"][0]["distance"] / 1000, 2),
        "duration": round(route["segments"][0]["duration"] / 60, 2),
        "steps": [
            {
                "text": step["instruction"],
                "distance": round(step["distance"], 1)
            } for step in route["segments"][0]["steps"]
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
        form = TravelForm(request.POST)
        if form.is_valid():
            start = form.cleaned_data['start_city']
            end = form.cleaned_data['end_city']
            start_weather = get_weather(start)
            end_weather = get_weather(end)
            route = get_route(start_weather['coord'], end_weather['coord'])
            advice = get_advice(start_weather, datetime.now())

            entry = {
                "start_city": start,
                "end_city": end,
                "timestamp": str(datetime.now()),
                "route": route
            }
            history_collection.insert_one(entry)

            return render(request, 'guides/result.html', {
                "start": start,
                "end": end,
                "start_weather": start_weather,
                "end_weather": end_weather,
                "route": route,
                "advice": advice
            })
    return redirect("index")

def history(request):
    results = list(history_collection.find().sort("_id", -1))
    return render(request, "guides/history.html", {"results": results})