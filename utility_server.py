import sys
import os
import json
import time
import platform
import uuid
import hashlib
import base64
import math
import random
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.request import urlopen

from fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("Utility Belt Server")

# --- TIME & DATE TOOLS ---

@mcp.tool()
def get_current_time(timezone: str = "local") -> str:
    """
    Get the current time in a specific timezone or local time.
    
    Args:
        timezone: Timezone string (e.g., "UTC", "Asia/Ho_Chi_Minh", "local")
    """
    if timezone.lower() == "local":
        return datetime.now().isoformat()
    elif timezone.upper() == "UTC":
        return datetime.utcnow().isoformat()
    else:
        # Simple fallback for now, real timezone support would require pytz or zoneinfo
        try:
            import zoneinfo
            return datetime.now(zoneinfo.ZoneInfo(timezone)).isoformat()
        except ImportError:
            return f"Timezone support requires Python 3.9+ or 'tzdata'. Returning local: {datetime.now().isoformat()} (requested: {timezone})"
        except Exception as e:
            return f"Error getting time for {timezone}: {str(e)}"

# --- SYSTEM TOOLS ---

@mcp.tool()
def get_system_info() -> Dict[str, str]:
    """Get basic system information (OS, Python version, Processor)."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": sys.version,
        "hostname": platform.node()
    }

@mcp.tool()
def generate_uuid(version: int = 4) -> str:
    """Generate a UUID."""
    if version == 1:
        return str(uuid.uuid1())
    return str(uuid.uuid4())

# --- TEXT TOOLS ---

@mcp.tool()
def base64_encode(text: str) -> str:
    """Encode text to Base64."""
    return base64.b64encode(text.encode('utf-8')).decode('utf-8')

@mcp.tool()
def base64_decode(encoded_text: str) -> str:
    """Decode Base64 text."""
    try:
        return base64.b64decode(encoded_text).decode('utf-8')
    except Exception as e:
        return f"Error decoding: {str(e)}"

@mcp.tool()
def calculate_hash(text: str, algorithm: str = "sha256") -> str:
    """Calculate hash of text (md5, sha1, sha256)."""
    if algorithm == "md5":
        return hashlib.md5(text.encode()).hexdigest()
    elif algorithm == "sha1":
        return hashlib.sha1(text.encode()).hexdigest()
    else:
        return hashlib.sha256(text.encode()).hexdigest()

@mcp.tool()
def generate_lorem_ipsum(sentences: int = 3) -> str:
    """Generate simple Lorem Ipsum text."""
    lorem = [
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.",
        "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.",
        "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."
    ]
    return " ".join(random.choices(lorem, k=sentences))

# --- NETWORK & INTERNET TOOLS ---

@mcp.tool()
def get_public_ip() -> str:
    """Get the public IP address of the server."""
    try:
        with urlopen("https://api.ipify.org") as response:
            return response.read().decode('utf-8')
    except Exception as e:
        return f"Error getting IP: {str(e)}"

# --- WEATHER TOOLS (Public API) ---

@mcp.tool()
def get_weather(city: str) -> Dict[str, Any]:
    """
    Get current weather for a city using Open-Meteo (No API key required).
    First converts City to Lat/Lon via geocoding, then fetches weather.
    """
    try:
        # 1. Geocoding
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        with urlopen(geo_url) as response:
            geo_data = json.loads(response.read().decode())
        
        if not geo_data.get("results"):
            return {"error": f"City '{city}' not found."}
        
        location = geo_data["results"][0]
        lat, lon = location["latitude"], location["longitude"]
        name = location["name"]
        
        # 2. Weather
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        with urlopen(weather_url) as response:
            weather_data = json.loads(response.read().decode())
            
        return {
            "city": name,
            "latitude": lat,
            "longitude": lon,
            "country": location.get("country"),
            "current_weather": weather_data.get("current_weather")
        }
    except Exception as e:
        return {"error": f"Failed to fetch weather: {str(e)}"}

# --- MATH & CONVERSION TOOLS ---

@mcp.tool()
def calculate(expression: str) -> float:
    """
    Evaluate a secure mathematical expression.
    Supports basic operators +, -, *, /, %, power (**), sqrt().
    """
    allowed_names = {
        "sin": math.sin, "cos": math.cos, "tan": math.tan, 
        "sqrt": math.sqrt, "pi": math.pi, "e": math.e, 
        "pow": math.pow, "abs": abs
    }
    # Security note: eval is dangerous, but we are restricting globals/locals.
    # Still, purely for demonstration.
    try:
        # Simple sanitizer
        if "__" in expression or ";" in expression:
            return "Error: Unsafe expression detected."
        return eval(expression, {"__builtins__": None}, allowed_names)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """
    Convert currency (Mocked data, as real API requires key).
    Supports USD, EUR, VND, JPY, GBP.
    """
    rates = {
        "USD": 1.0,
        "EUR": 0.92,
        "VND": 25400.0,
        "JPY": 150.0,
        "GBP": 0.79
    }
    
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    
    if from_currency not in rates or to_currency not in rates:
        return f"Error: Unsupported currency. Supported: {', '.join(rates.keys())}"
    
    # Convert to USD first, then to target
    amount_in_usd = amount / rates[from_currency]
    result = amount_in_usd * rates[to_currency]
    
    return f"{amount} {from_currency} = {result:.2f} {to_currency}"

@mcp.tool()
def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """
    Simple unit converter (Length, Mass).
    Supported: m, km, cm, mm, inch, ft, mile, kg, g, lb.
    """
    # Length factors to meters
    length_rates = {
        "m": 1, "km": 1000, "cm": 0.01, "mm": 0.001,
        "inch": 0.0254, "ft": 0.3048, "mile": 1609.34
    }
    # Mass factors to kg
    mass_rates = {
        "kg": 1, "g": 0.001, "lb": 0.453592
    }
    
    from_unit = from_unit.lower()
    to_unit = to_unit.lower()
    
    if from_unit in length_rates and to_unit in length_rates:
        val_in_m = value * length_rates[from_unit]
        res = val_in_m / length_rates[to_unit]
        return f"{value} {from_unit} = {res:.4f} {to_unit}"
        
    elif from_unit in mass_rates and to_unit in mass_rates:
        val_in_kg = value * mass_rates[from_unit]
        res = val_in_kg / mass_rates[to_unit]
        return f"{value} {from_unit} = {res:.4f} {to_unit}"
        
    else:
        return "Error: Incompatible or unsupported units."


if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Utility Belt MCP Server")
    parser.add_argument("--transport", default="sse", choices=["stdio", "sse"], help="Transport: 'sse' or 'stdio'")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="Port (default: 8001)")
    
    args = parser.parse_args()
    
    if args.transport == "sse":
        print(f"Starting Utility MCP server on http://{args.host}:{args.port}/sse", file=sys.stderr)
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
