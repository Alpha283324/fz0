from flask import Flask, render_template_string, jsonify, request
import requests
import time

app = Flask(__name__)

# You provided this key — using it for both WAQI token and OpenWeatherMap appid
WAQI_TOKEN = "35e692ca0b6ee561d13029088333b798a0418a8b"
OWM_KEY = "35e692ca0b6ee561d13029088333b798a0418a8b"

CACHE = {"data": [], "timestamp": 0}
CACHE_EXPIRY = 600
WORLD_BOUNDS = [-90, -180, 90, 180]

@app.route("/")
def home():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>QuantumFlux Global AQI Heatmap</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
        <style>
            body { margin:0; padding:0; background:#0d1117; color:#c3f0fc; font-family:"Segoe UI",sans-serif; text-align:center;}
            h1 {font-weight:600;margin:15px 0;color:#9ae7fc;text-shadow:0 0 5px #00d8ff,0 0 10px #00d8ff;}
            #map {width:100%; height:88vh; border-top:2px solid #00d8ff; border-bottom:2px solid #00d8ff; box-shadow:0 0 20px rgba(0,216,255,0.3);}
            #search-bar {display:inline-block; background: rgba(0,216,255,0.1); padding:10px 20px; margin:10px; border-radius:12px; box-shadow:0 0 10px rgba(0,216,255,0.2); backdrop-filter: blur(5px);}
            input {padding:8px 12px; font-size:16px; border-radius:8px; border:1px solid #00d8ff; background: rgba(255,255,255,0.05); color:#c3f0fc; outline:none; transition:0.2s all;}
            input:focus {border-color:#00ffff; box-shadow:0 0 5px #00ffff;}
            button {padding:8px 16px; font-size:16px; border-radius:8px; border:none; background:linear-gradient(45deg,#00d8ff,#00ffff); color:#0d1117; font-weight:bold; cursor:pointer; transition:0.2s all; margin-left:5px; box-shadow:0 0 10px rgba(0,216,255,0.3);}
            button:hover {background:linear-gradient(45deg,#00ffff,#00d8ff); box-shadow:0 0 15px rgba(0,255,255,0.5);}
            .legend { background: rgba(13,17,23,0.85); padding: 12px; color: #fff; line-height: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,216,255,0.3); font-size: 14px; font-weight: 500; }
            .legend span { display:inline-block; width: 20px; height: 20px; margin-right: 8px; border-radius: 4px; box-shadow: 0 0 5px rgba(0,216,255,0.4); }
            .leaflet-popup-content { background: rgba(0,0,0,0.85); color: #c3f0fc; font-weight: 500; font-size: 14px; padding: 8px 12px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,216,255,0.5); }
            .leaflet-popup-tip { background: rgba(0,0,0,0.85); }
            .wind-arrow { width: 28px; height: 28px; display: block; transform-origin: 50% 50%; filter: drop-shadow(0 2px 3px rgba(0,0,0,0.6)); }
            .info-box { background: rgba(0,0,0,0.85); color: #c3f0fc; padding: 8px; border-radius: 8px; font-weight: 600; font-size: 13px; }
        </style>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>
    </head>
    <body>
        <h1>QuantumFlux Global AQI Heatmap</h1>
        <div id="search-bar">
            <input type="text" id="city" placeholder="Enter city (e.g., Dubai or London,uk)">
            <button onclick="searchCity()">Check AQI & Weather</button>
        </div>
        <div id="map"></div>

        <script>
            const map = L.map('map').setView([20, 0], 2);
            const hour = new Date().getHours();
            const tileURL = (hour >= 6 && hour <= 18) ?
                'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}' :
                'https://tiles.stadiamaps.com/tiles/alidade_dark/{z}/{x}/{y}{r}.png';
            L.tileLayer(tileURL, { maxZoom: 19, attribution: 'Map data &copy; Esri, OpenStreetMap contributors' }).addTo(map);

            let heatLayer;
            let cityMarker;
            let windLayer = L.layerGroup().addTo(map);

            const legend = L.control({position: 'bottomright'});
            legend.onAdd = function(map) {
                const div = L.DomUtil.create('div', 'legend');
                div.innerHTML += '<strong>AQI</strong><br>';
                div.innerHTML += '<span style="background:green"></span> 0-50<br>';
                div.innerHTML += '<span style="background:yellow"></span> 51-100<br>';
                div.innerHTML += '<span style="background:orange"></span> 101-150<br>';
                div.innerHTML += '<span style="background:red"></span> 151-200<br>';
                div.innerHTML += '<span style="background:purple"></span> 201-300<br>';
                div.innerHTML += '<span style="background:maroon"></span> 301+';
                return div;
            };
            legend.addTo(map);

            function aqiColor(aqi){
                if(aqi === null || aqi === undefined) return '#999';
                if(aqi <= 50) return 'green';
                else if(aqi <= 100) return 'yellow';
                else if(aqi <= 150) return 'orange';
                else if(aqi <= 200) return 'red';
                else if(aqi <= 300) return 'purple';
                else return 'maroon';
            }

            async function loadMap(){
                const res = await fetch('/stations');
                const stations = await res.json();

                const heatPoints = stations
                    .filter(s => s.aqi !== null && s.aqi !== undefined && s.lat && s.lon)
                    .map(s => [s.lat, s.lon, Math.min(s.aqi/300, 1)]);
                
                heatLayer = L.heatLayer(heatPoints, {
                    radius: 25,
                    blur: 15,
                    maxZoom: 15,
                    gradient: {0.0: 'green', 0.2: 'yellow', 0.4: 'orange', 0.6: 'red', 0.8: 'purple', 1.0: 'maroon'}
                }).addTo(map);

                stations.forEach(s => {
                    if(!s.lat || !s.lon) return;
                    L.circleMarker([s.lat, s.lon], {
                        radius: 7,
                        fillColor: aqiColor(s.aqi),
                        color: '#000',
                        fillOpacity: 0.7,
                        weight: 1
                    }).addTo(map)
                      .bindPopup(`<strong>${s.station ?? "Unknown"}</strong><br>AQI: ${s.aqi}`);
                });
            }

            // helper to create SVG arrow icon rotated later
            function createArrowIcon(size = 28, color = "#00ffff"){
                const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24">
                    <g transform="translate(12,12)">
                        <path d="M0,-10 L4,0 L1,-2 L-1,0 Z" fill="${color}"/>
                        <rect x="-0.8" y="-0.5" width="1.6" height="10" fill="${color}" />
                    </g>
                </svg>`;
                const uri = 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
                return L.divIcon({
                    className: 'wind-icon',
                    html: `<img class="wind-arrow" src="${uri}" style="transform:rotate(0deg);">`,
                    iconSize: [size, size],
                    iconAnchor: [size/2, size/2]
                });
            }

            async function searchCity(){
                const city = document.getElementById('city').value.trim();
                if(!city) return;
                try {
                    const res = await fetch('/pm25?city=' + encodeURIComponent(city));
                    const data = await res.json();
                    if(!data || !data.lat || !data.lon) {
                        alert("City not found or data unavailable");
                        return;
                    }

                    // remove previous markers
                    if(cityMarker) { try { map.removeLayer(cityMarker); } catch(e) {} }
                    windLayer.clearLayers();

                    // draw city circle
                    cityMarker = L.circle([data.lat, data.lon], {
                        radius: 50000 + (data.aqi ?? 0)*2000,
                        fillColor: aqiColor(data.aqi),
                        color: '#000',
                        fillOpacity: 0.8,
                        weight: 2
                    }).addTo(map)
                      .bindPopup(`<div class="info-box"><strong>${data.station}</strong><br>
                                  AQI: ${data.aqi ?? 'N/A'}<br>
                                  PM2.5: ${data.pm25 ?? 'N/A'}<br>
                                  Temp: ${data.temp ?? 'N/A'} °C<br>
                                  Humidity: ${data.humidity ?? 'N/A'}%<br>
                                  Precipitation: ${data.precip ?? 'N/A'} mm (1h/3h)<br>
                                  Wind Speed: ${data.wind_speed ?? 'N/A'} m/s<br>
                                  Wind Dir: ${data.wind_dir ?? 'N/A'}°</div>`)
                      .openPopup();

                    map.setView([data.lat, data.lon], 7);

                    // add wind arrow if we have wind info (OWM gives degrees meteorological — where wind is coming FROM)
                    const windSpeed = data.wind_speed;
                    const windDir = data.wind_dir;
                    if(windSpeed !== null && windSpeed !== undefined && windDir !== null && windDir !== undefined){
                        const icon = createArrowIcon(Math.max(18, 10 + windSpeed * 1.8), "#00ffff");
                        const marker = L.marker([data.lat, data.lon], {icon: icon, interactive: false}).addTo(windLayer);
                        // rotate arrow to point TO where wind is going (meteorological windDir is where it's coming from)
                        const rotationTo = ((windDir + 180) % 360);
                        const el = marker.getElement();
                        if(el){
                            const img = el.querySelector('img.wind-arrow');
                            if(img) img.style.transform = `rotate(${rotationTo}deg)`;
                        }
                    }

                } catch (err) {
                    console.error(err);
                    alert("Search failed: " + (err.message || err));
                }
            }

            loadMap();
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route("/stations")
def stations():
    if time.time() - CACHE["timestamp"] < CACHE_EXPIRY:
        return jsonify(CACHE["data"])
    try:
        url = f"https://api.waqi.info/map/bounds/?token={WAQI_TOKEN}&latlng={WORLD_BOUNDS[0]},{WORLD_BOUNDS[1]},{WORLD_BOUNDS[2]},{WORLD_BOUNDS[3]}"
        r = requests.get(url, timeout=10).json()
        stations = []
        if r.get("status") == "ok":
            for s in r.get("data", []):
                lat = s.get("lat"); lon = s.get("lon")
                aqi_raw = s.get("aqi")
                try:
                    aqi = int(aqi_raw)
                    if aqi < 0: aqi = 0
                except:
                    aqi = None
                station_name = s.get("station") if not isinstance(s.get("station"), dict) else s.get("station", {}).get("name")
                stations.append({"lat": lat, "lon": lon, "aqi": aqi, "station": station_name or "Unknown",
                                 "temp": None, "humidity": None, "wind_speed": None, "wind_dir": None})
        CACHE["data"] = stations
        CACHE["timestamp"] = time.time()
        return jsonify(stations)
    except Exception as e:
        print("Error fetching stations:", e)
        return jsonify([])

@app.route("/pm25")
def get_pm25():
    city = request.args.get("city", "Mussafah")
    # 1) WAQI feed for AQI / iaqi
    waqi_url = f"https://api.waqi.info/feed/{city}/?token={WAQI_TOKEN}"
    try:
        r = requests.get(waqi_url, timeout=10).json()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if r.get("status") != "ok":
        return jsonify({"error": r.get("data") or "WAQI error"}), 400

    data = r.get("data", {})
    iaqi = data.get("iaqi", {})
    city_info = data.get("city", {})
    lat = None; lon = None
    if isinstance(city_info.get("geo"), list) and len(city_info.get("geo")) >= 2:
        lat = city_info.get("geo")[0]; lon = city_info.get("geo")[1]

    # extract WAQI values where available
    aqi = data.get("aqi")
    pm25 = iaqi.get("pm25", {}).get("v") if isinstance(iaqi.get("pm25"), dict) else None
    temp_waqi = iaqi.get("t", {}).get("v") if isinstance(iaqi.get("t"), dict) else None
    humidity_waqi = iaqi.get("h", {}).get("v") if isinstance(iaqi.get("h"), dict) else None
    wind_speed_waqi = None
    wind_dir_waqi = None
    if "w" in iaqi and isinstance(iaqi["w"], dict):
        wind_speed_waqi = iaqi["w"].get("v")
    if "wind" in iaqi and isinstance(iaqi["wind"], dict):
        wind_speed_waqi = wind_speed_waqi or iaqi["wind"].get("v")
    # WAQI rarely contains wind_dir; skip if missing

    # 2) OpenWeatherMap for precipitation + fallback wind/temp/humidity if missing
    precip = None
    wind_speed = wind_speed_waqi
    wind_dir = wind_dir_waqi
    temp = temp_waqi
    humidity = humidity_waqi

    if lat is not None and lon is not None:
        try:
            owm_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OWM_KEY}&units=metric"
            o = requests.get(owm_url, timeout=8).json()
            # precipitation: OWM provides rain dict e.g. {"1h": 0.3} or {"3h": ...}
            rain = o.get("rain", {})
            if isinstance(rain, dict):
                precip = rain.get("1h") or rain.get("3h") or 0
            else:
                precip = 0
            # wind
            w = o.get("wind", {})
            if isinstance(w, dict):
                wind_speed = w.get("speed", wind_speed)
                wind_dir = w.get("deg", wind_dir)
            # temp / humidity fallback
            main = o.get("main", {})
            if isinstance(main, dict):
                temp = main.get("temp", temp)
                humidity = main.get("humidity", humidity)
        except Exception as e:
            # OWM failed — continue with WAQI partial data
            print("OWM error:", e)

    result = {
        "aqi": aqi,
        "pm25": pm25,
        "temp": temp,
        "humidity": humidity,
        "precip": precip,
        "wind_speed": wind_speed,
        "wind_dir": wind_dir,
        "station": city_info.get("name", city),
        "lat": lat,
        "lon": lon
    }
    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True)
