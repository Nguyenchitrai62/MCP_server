from fastmcp import FastMCP
import datetime
import uuid
import random
import re
import urllib.parse
import urllib.request
import platform
import sys
import socket
import math
from typing import List, Dict, Any, Optional

# Khởi tạo MCP Server
mcp = FastMCP("Utility Tools Server")

# ---------------------------------------------------------
# 🕒 GROUP 1: TIME & DATE
# ---------------------------------------------------------

@mcp.tool()
def get_current_time(timezone: str = "UTC") -> str:
    """Lấy thời gian hiện tại theo múi giờ (mặc định UTC)."""
    if timezone.upper() == "UTC":
        return datetime.datetime.now(datetime.timezone.utc).isoformat()
    # Hỗ trợ đơn giản local time nếu không phải UTC
    return datetime.datetime.now().isoformat()

@mcp.tool()
def human_readable_duration(seconds: int) -> str:
    """Chuyển số giây thành dạng dễ đọc (ví dụ: 1h 30m 10s)."""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    parts = []
    if d > 0: parts.append(f"{d}d")
    if h > 0: parts.append(f"{h}h")
    if m > 0: parts.append(f"{m}m")
    if s > 0 or not parts: parts.append(f"{s}s")
    return " ".join(parts)

@mcp.tool()
def days_between(date1: str, date2: str) -> int:
    """Tính số ngày giữa hai mốc thời gian (format YYYY-MM-DD)."""
    d1 = datetime.datetime.strptime(date1, "%Y-%m-%d")
    d2 = datetime.datetime.strptime(date2, "%Y-%m-%d")
    return abs((d2 - d1).days)

@mcp.tool()
def get_week_number(date_str: str) -> int:
    """Lấy số thứ tự tuần trong năm của một ngày (YYYY-MM-DD)."""
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return dt.isocalendar()[1]

# ---------------------------------------------------------
# 🎲 GROUP 2: RANDOM & GENERATORS
# ---------------------------------------------------------

@mcp.tool()
def generate_uuid() -> str:
    """Sinh UUID v4 (định danh duy nhất)."""
    return str(uuid.uuid4())

@mcp.tool()
def generate_random_password(length: int = 12, include_special: bool = True) -> str:
    """Sinh mật khẩu ngẫu nhiên."""
    import string
    chars = string.ascii_letters + string.digits
    if include_special:
        chars += "!@#$%^&*"
    return ''.join(random.choice(chars) for _ in range(length))

@mcp.tool()
def generate_random_hex_color() -> str:
    """Sinh mã màu HEX ngẫu nhiên."""
    return "#{:06x}".format(random.randint(0, 0xFFFFFF))

@mcp.tool()
def flip_coin() -> str:
    """Tung đồng xu (Heads/Tails)."""
    return random.choice(["Heads", "Tails"])

# ---------------------------------------------------------
# 🌐 GROUP 3: NETWORK & URL
# ---------------------------------------------------------

@mcp.tool()
def get_public_ip() -> str:
    """Lấy địa chỉ IP Public hiện tại (qua api.ipify.org)."""
    try:
        with urllib.request.urlopen('https://api.ipify.org') as response:
            return response.read().decode('utf-8')
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def check_website_status(url: str) -> Dict[str, Any]:
    """Kiểm tra trạng thái HTTP của website."""
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        with urllib.request.urlopen(url, timeout=5) as response:
            return {"url": url, "status_code": response.getcode(), "status": "Online"}
    except urllib.error.HTTPError as e:
        return {"url": url, "status_code": e.code, "status": "Error"}
    except Exception as e:
        return {"url": url, "error": str(e), "status": "Unreachable"}

@mcp.tool()
def parse_url_params(url: str) -> Dict[str, List[str]]:
    """Trích xuất tham số query từ URL."""
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.parse_qs(parsed.query)

@mcp.tool()
def is_valid_domain(domain: str) -> bool:
    """Kiểm tra tên miền có hợp lệ không (regex cơ bản)."""
    pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}$"
    return bool(re.match(pattern, domain))

# ---------------------------------------------------------
# 📝 GROUP 4: STRING & TEXT PROCESSING
# ---------------------------------------------------------

@mcp.tool()
def slugify_text(text: str) -> str:
    """Chuyển tiêu đề thành URL slug."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')

@mcp.tool()
def convert_case(text: str, target_case: str) -> str:
    """Chuyển đổi kiểu chữ (snake, camel, kebab, pascal)."""
    # Normalize to words list
    words = re.findall(r'[A-Za-z0-9]+', text)
    
    if target_case == "snake":
        return "_".join(w.lower() for w in words)
    elif target_case == "kebab":
        return "-".join(w.lower() for w in words)
    elif target_case == "camel":
        return words[0].lower() + "".join(w.capitalize() for w in words[1:])
    elif target_case == "pascal":
        return "".join(w.capitalize() for w in words)
    return text

@mcp.tool()
def count_words(text: str) -> Dict[str, int]:
    """Đếm số từ và ký tự."""
    return {
        "char_count": len(text),
        "word_count": len(text.split()),
        "line_count": text.count('\n') + 1
    }

@mcp.tool()
def extract_emails(text: str) -> List[str]:
    """Trích xuất tất cả email từ văn bản."""
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return re.findall(pattern, text)

# ---------------------------------------------------------
# 🧮 GROUP 5: MATH & CONVERTER
# ---------------------------------------------------------

@mcp.tool()
def convert_file_size(size_bytes: int) -> str:
    """Chuyển đổi bytes sang KB, MB, GB."""
    if size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

# ---------------------------------------------------------
# ✅ GROUP 6: DATA VALIDATORS
# ---------------------------------------------------------

@mcp.tool()
def validate_email_format(email: str) -> bool:
    """Kiểm tra định dạng email."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))

@mcp.tool()
def validate_ipv4(ip: str) -> bool:
    """Kiểm tra địa chỉ IPv4."""
    try:
        socket.inet_aton(ip)
        return True
    except socket.error:
        return False

@mcp.tool()
def validate_phone_number(phone: str) -> bool:
    """Kiểm tra số điện thoại (chỉ chấp nhận số và +, độ dài 10-15)."""
    return bool(re.match(r"^\+?[\d\s-]{10,15}$", phone))

# ---------------------------------------------------------
# 🎭 GROUP 7: MOCK DATA
# ---------------------------------------------------------

@mcp.tool()
def generate_fake_profile() -> Dict[str, Any]:
    """Sinh hồ sơ người dùng giả lập."""
    first_names = ["John", "Jane", "Alice", "Bob", "Charlie", "Emma"]
    last_names = ["Doe", "Smith", "Johnson", "Brown", "Wilson", "Taylor"]
    domains = ["gmail.com", "yahoo.com", "outlook.com", "example.com"]
    
    fn = random.choice(first_names)
    ln = random.choice(last_names)
    
    return {
        "full_name": f"{fn} {ln}",
        "email": f"{fn.lower()}.{ln.lower()}@{random.choice(domains)}",
        "age": random.randint(18, 60),
        "phone": f"+1-{random.randint(100, 999)}-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
        "id": str(uuid.uuid4())
    }

@mcp.tool()
def generate_lorem_ipsum(sentences: int = 3) -> str:
    """Sinh văn bản giả Lorem Ipsum."""
    words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit", 
             "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et", "dolore", 
             "magna", "aliqua", "ut", "enim", "ad", "minim", "veniam", "quis", "nostrud"]
    
    result = []
    for _ in range(sentences):
        sentence_len = random.randint(5, 15)
        sentence = " ".join(random.choice(words) for _ in range(sentence_len))
        result.append(sentence.capitalize() + ".")
    
    return " ".join(result)

# ---------------------------------------------------------
# 💻 GROUP 8: SYSTEM INFO
# ---------------------------------------------------------

@mcp.tool()
def get_python_env_info() -> Dict[str, str]:
    """Lấy thông tin môi trường Python."""
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "system": platform.system(),
        "processor": platform.processor(),
        "executable": sys.executable
    }

if __name__ == "__main__":
    # Chạy server trên port 8001 để tránh xung đột với server chính
    mcp.run(transport="sse", host="0.0.0.0", port=8001)
