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
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from urllib.request import urlopen, Request
from urllib.parse import urlparse

from fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("Advanced Utility Belt Server")

# ==============================================================================
# 1. ADVANCED TIME & DATE TOOLS (Xử lý thời gian chi tiết)
# ==============================================================================

@mcp.tool()
def get_current_time(timezone: str = "local", format: str = "iso") -> str:
    """
    Get the current time with formatting options.
    
    Args:
        timezone: 'local', 'UTC', or specific offset like '+07:00'
        format: 'iso' (default), 'timestamp', 'readable' (e.g. YYYY-MM-DD HH:MM:SS)
    """
    now = datetime.now() if timezone == "local" else datetime.utcnow()
    
    if format == "timestamp":
        return str(now.timestamp())
    elif format == "readable":
        return now.strftime("%Y-%m-%d %H:%M:%S")
    else:
        return now.isoformat()

@mcp.tool()
def time_calculation(base_date: str, days: int = 0, weeks: int = 0, months: int = 0, years: int = 0, hours: int = 0) -> str:
    """
    Perform arithmetic on dates (Add/Subtract time).
    Useful for questions like "What date was it last week?" (weeks=-1).
    
    Args:
        base_date: Date string (ISO format or YYYY-MM-DD)
        days: Days to add (negative to subtract)
        weeks: Weeks to add
        months: Months to add (approx 30 days)
        years: Years to add (approx 365 days)
        hours: Hours to add
    """
    try:
        # Flexible parsing
        dt = None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                dt = datetime.strptime(base_date.split('T')[0] if 'T' in base_date else base_date, fmt)
                break
            except:
                pass
        
        if not dt:
            dt = datetime.fromisoformat(base_date)

        # Approximate months/years for simple tool usage
        total_days = days + (weeks * 7) + (months * 30) + (years * 365)
        delta = timedelta(days=total_days, hours=hours)
        
        result_date = dt + delta
        return result_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        return f"Error calculating date: {str(e)}"

@mcp.tool()
def get_date_difference(start_date: str, end_date: str, unit: str = "days") -> float:
    """
    Calculate the difference between two dates.
    
    Args:
        unit: 'seconds', 'minutes', 'hours', 'days', 'weeks'
    """
    try:
        d1 = datetime.fromisoformat(start_date)
        d2 = datetime.fromisoformat(end_date)
        diff = d2 - d1
        
        if unit == "seconds": return diff.total_seconds()
        if unit == "minutes": return diff.total_seconds() / 60
        if unit == "hours": return diff.total_seconds() / 3600
        if unit == "weeks": return diff.days / 7
        return float(diff.days)
    except Exception as e:
        return -1.0

@mcp.tool()
def get_weekday(date_string: str) -> str:
    """
    Get the day of the week for a specific date.
    
    Args:
        date_string: Date in YYYY-MM-DD format
    """
    try:
        dt = datetime.strptime(date_string.split("T")[0], "%Y-%m-%d")
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return days[dt.weekday()]
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def leap_year_check(year: int) -> bool:
    """Check if a year is a leap year."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

# ==============================================================================
# 2. SYSTEM & NETWORK TOOLS
# ==============================================================================

@mcp.tool()
def get_system_comprehensive_info() -> Dict[str, Any]:
    """Get detailed system specifications."""
    return {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "architecture": platform.architecture()[0]
        },
        "hardware": {
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cores": os.cpu_count()
        },
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable
        }
    }

@mcp.tool()
def inspect_url(url: str) -> Dict[str, Any]:
    """
    Analyze a URL and return its components (Scheme, Netloc, Path, Query).
    """
    parsed = urlparse(url)
    return {
        "scheme": parsed.scheme,
        "domain": parsed.netloc,
        "path": parsed.path,
        "params": parsed.params,
        "query": parsed.query,
        "fragment": parsed.fragment,
        "port": parsed.port
    }

# ==============================================================================
# 3. CRYPTO & SECURITY TOOLS
# ==============================================================================

@mcp.tool()
def generate_password(length: int = 12, include_special: bool = True, include_numbers: bool = True) -> str:
    """
    Generate a secure random password.
    """
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if include_numbers:
        chars += "0123456789"
    if include_special:
        chars += "!@#$%^&*()-_=+"
        
    return "".join(random.choice(chars) for _ in range(length))

@mcp.tool()
def hash_text(text: str, algorithm: str = "sha256") -> str:
    """
    Calculate hash of text. 
    Supported algorithms: md5, sha1, sha256, sha512.
    """
    text_bytes = text.encode('utf-8')
    if algorithm == "md5": return hashlib.md5(text_bytes).hexdigest()
    if algorithm == "sha1": return hashlib.sha1(text_bytes).hexdigest()
    if algorithm == "sha256": return hashlib.sha256(text_bytes).hexdigest()
    if algorithm == "sha512": return hashlib.sha512(text_bytes).hexdigest()
    return "Unsupported algorithm"

# ==============================================================================
# 4. MATH & CONVERSION TOOLS
# ==============================================================================

@mcp.tool()
def solve_linear_equation(a: float, b: float) -> str:
    """
    Solve linear equation ax + b = 0.
    """
    if a == 0:
        return "No solution" if b != 0 else "Infinite solutions"
    return str(-b / a)

@mcp.tool()
def prime_check(number: int) -> bool:
    """Check if a number is prime."""
    if number <= 1: return False
    if number <= 3: return True
    if number % 2 == 0 or number % 3 == 0: return False
    i = 5
    while i * i <= number:
        if number % i == 0 or number % (i + 2) == 0:
            return False
        i += 6
    return True

@mcp.tool()
def statistics_calculator(numbers: List[float]) -> Dict[str, float]:
    """
    Calculate basic statistics for a list of numbers (Mean, Median, Max, Min).
    """
    if not numbers:
        return {}
    
    sorted_nums = sorted(numbers)
    n = len(numbers)
    mean = sum(numbers) / n
    
    if n % 2 == 0:
        median = (sorted_nums[n//2 - 1] + sorted_nums[n//2]) / 2
    else:
        median = sorted_nums[n//2]
        
    return {
        "count": n,
        "sum": sum(numbers),
        "mean": mean,
        "median": median,
        "min": min(numbers),
        "max": max(numbers)
    }

# ==============================================================================
# 5. CONTENT & FAKE DATA TOOLS
# ==============================================================================

@mcp.tool()
def text_analyzer(text: str) -> Dict[str, int]:
    """
    Analyze text content (Word count, char count, sentence count).
    """
    return {
        "length_chars": len(text),
        "length_words": len(text.split()),
        "length_sentences": len(re.split(r'[.!?]+', text)) - 1,
        "upper_case": sum(1 for c in text if c.isupper()),
        "lower_case": sum(1 for c in text if c.islower()),
        "numbers": sum(1 for c in text if c.isdigit())
    }

@mcp.tool()
def generate_fake_profile(locale: str = "en") -> Dict[str, str]:
    """
    Generate a fake user profile (Mocked data).
    """
    first_names = ["John", "Jane", "Alice", "Bob", "Charlie", "David", "Eva", "Frank"]
    last_names = ["Smith", "Doe", "Johnson", "Brown", "Taylor", "Miller", "Wilson"]
    domains = ["gmail.com", "yahoo.com", "outlook.com", "example.org"]
    
    first = random.choice(first_names)
    last = random.choice(last_names)
    
    return {
        "full_name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}@{random.choice(domains)}",
        "username": f"{first.lower()}{random.randint(10,999)}",
        "age": random.randint(18, 80),
        "id": str(uuid.uuid4())
    }

# ==============================================================================
# 6. EXTERNAL API TOOLS (No Key Required)
# ==============================================================================

@mcp.tool()
def get_weather_forecast(city: str, days: int = 1) -> Dict[str, Any]:
    """
    Get weather forecast unique for N days using Open-Meteo.
    """
    try:
        # Geo-coding
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        with urlopen(geo_url) as r:
            geo = json.loads(r.read().decode())
        
        if not geo.get("results"):
            return {"error": "City not found"}
        
        lat = geo["results"][0]["latitude"]
        lon = geo["results"][0]["longitude"]
        
        # Forecast
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto&forecast_days={days}"
        with urlopen(url) as r:
            data = json.loads(r.read().decode())
            
        return {
            "city": geo["results"][0]["name"],
            "daily_units": data.get("daily_units"),
            "daily": data.get("daily")
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def get_random_joke() -> str:
    """Get a random programming joke (Mocked to avoid network dependency on unverified APIs)."""
    jokes = [
        "Why do programmers prefer dark mode? Because light attracts bugs.",
        "How many programmers does it take to change a light bulb? None, that's a hardware problem.",
        "I told my computer I needed a break, and now it won't stop sending me Kit-Kats.",
        "There are 10 types of people in the world: Those who understand binary, and those who don't."
    ]
    return random.choice(jokes)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Advanced Utility Belt MCP Server")
    parser.add_argument("--transport", default="sse", choices=["stdio", "sse"], help="Transport: 'sse' or 'stdio'")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="Port (default: 8001)")
    
    args = parser.parse_args()
    
    if args.transport == "sse":
        print(f"Starting Advanced Utility MCP on http://{args.host}:{args.port}/sse", file=sys.stderr)
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")
