from fastmcp import FastMCP
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Create an MCP server
mcp = FastMCP("Shapes Database Server")

# Load shapes database
SHAPES_DB_PATH = r"D:\Source_code\MCP_server\39_shapes.json"
shapes_database = []

def load_shapes_database():
    """Load shapes data from JSON file."""
    global shapes_database
    try:
        if os.path.exists(SHAPES_DB_PATH):
            with open(SHAPES_DB_PATH, 'r', encoding='utf-8') as f:
                shapes_database = json.load(f)
            print(f"Loaded {len(shapes_database)} shapes from database", file=sys.stderr)
        else:
            print(f"Warning: Database file not found at {SHAPES_DB_PATH}", file=sys.stderr)
            shapes_database = []
    except Exception as e:
        print(f"Error loading database: {e}", file=sys.stderr)
        shapes_database = []

# Load database on startup
load_shapes_database()

@mcp.tool()
def count_objects(shape_name: Optional[str] = None, pipe_id: Optional[int] = None, 
                  dn: Optional[int] = None) -> Dict[str, Any]:
    """
    Count objects in the shapes database based on criteria.
    Returns statistical counts without heavy object lists by default.
    
    Args:
        shape_name: Filter by shape name (e.g., "Sprinkler", "Tee", "Elbow", "Line")
        pipe_id: Filter by pipe ID
        dn: Filter by DN (pipe diameter)
    
    Returns:
        Dictionary with count and breakdown by shape types
    """
    filtered = shapes_database
    
    if shape_name:
        filtered = [s for s in filtered if s.get('shape_name') == shape_name]
    if pipe_id is not None:
        filtered = [s for s in filtered if s.get('pipe_id') == pipe_id]
    if dn is not None:
        filtered = [s for s in filtered if dn in s.get('DN', [])]
    
    # Count by shape_name
    shape_counts = {}
    for shape in filtered:
        sname = shape.get('shape_name', 'Unknown')
        shape_counts[sname] = shape_counts.get(sname, 0) + 1
    
    # Return purely statistical data to save token usage
    return {
        "total_count": len(filtered),
        "shape_breakdown": shape_counts,
        "filters_applied": {
            "shape_name": shape_name,
            "pipe_id": pipe_id,
            "dn": dn
        },
        "note": "Use 'find_objects' or 'analyze_pipe_group' to get specific object details."
    }

@mcp.tool()
def find_objects(shape_name: Optional[str] = None, pipe_id: Optional[int] = None,
                 dn: Optional[int] = None, limit: int = 20) -> Dict[str, Any]:
    """
    Find objects matching the specified criteria.
    Returns a limited list of objects with essential details (NO vertices).
    
    Args:
        shape_name: Filter by shape name
        pipe_id: Filter by pipe ID
        dn: Filter by DN value
        limit: Maximum number of results to return (default: 20)
    
    Returns:
        Dictionary with matched objects summary.
    """
    filtered = shapes_database
    
    if shape_name:
        filtered = [s for s in filtered if s.get('shape_name') == shape_name]
    if pipe_id is not None:
        filtered = [s for s in filtered if s.get('pipe_id') == pipe_id]
    if dn is not None:
        filtered = [s for s in filtered if dn in s.get('DN', [])]
    
    # Extract essential info for each match
    results = []
    # Limit results to avoid context overflow
    safe_limit = min(limit, 50)  # Hard cap at 50
    
    for shape in filtered[:safe_limit]:
        obj_info = {
            "id": shape.get('id'),
            "shape_name": shape.get('shape_name'),
            "pipe_id": shape.get('pipe_id'),
            "DN": shape.get('DN'),
            # Vertices removed to save space
            "connectors_count": len(shape.get('connectors', []))
        }
        
        # Add special fields for sprinkler
        if shape.get('shape_name') == 'Sprinkler':
            obj_info["type"] = shape.get('type')
            obj_info["arm"] = shape.get('arm')
        
        results.append(obj_info)
    
    return {
        "found": len(filtered),
        "returned": len(results),
        "results": results
    }

@mcp.tool()
def get_object_locations(shape_name: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """
    Get location information (vertices and connectors) for objects.
    
    Args:
        shape_name: Filter by shape name
        limit: Maximum number of results
    
    Returns:
        Dictionary with location data
    """
    filtered = shapes_database
    
    if shape_name:
        filtered = [s for s in filtered if s.get('shape_name') == shape_name]
    
    results = []
    for shape in filtered[:limit]:
        vertices = shape.get('vertices', [])
        connectors = shape.get('connectors', [])
        
        # Calculate bounding box if vertices exist
        bbox = None
        if vertices:
            xs = [v.get('x', 0) for v in vertices]
            ys = [v.get('y', 0) for v in vertices]
            if xs and ys:
                bbox = {
                    "min_x": min(xs),
                    "max_x": max(xs),
                    "min_y": min(ys),
                    "max_y": max(ys)
                }
        
        results.append({
            "id": shape.get('id'),
            "shape_name": shape.get('shape_name'),
            "vertices_count": len(vertices),
            "connectors_count": len(connectors),
            "bbox": bbox,
            "vertices": vertices[:5] if len(vertices) > 5 else vertices  # Limit vertices
        })
    
    return {
        "found": len(filtered),
        "returned": len(results),
        "results": results
    }

@mcp.tool()
def list_available_shapes() -> Dict[str, Any]:
    """
    List all available shape types in the database.
    
    Returns:
        Dictionary with shape type statistics
    """
    shape_types = {}
    pipe_ids = set()
    dns = set()
    sprinkler_types = {"end": 0, "center": 0}
    
    for shape in shapes_database:
        # Count shape names
        sname = shape.get('shape_name', 'Unknown')
        shape_types[sname] = shape_types.get(sname, 0) + 1
        
        # Count sprinkler types
        if sname == 'Sprinkler':
            spr_type = shape.get('type')
            if spr_type in sprinkler_types:
                sprinkler_types[spr_type] += 1
        
        # Collect pipe IDs
        if shape.get('pipe_id'):
            pipe_ids.add(shape.get('pipe_id'))
        
        # Collect DN values
        for dn in shape.get('DN', []):
            dns.add(dn)
    
    return {
        "total_objects": len(shapes_database),
        "shape_types": dict(sorted(shape_types.items(), key=lambda x: x[1], reverse=True)),
        "sprinkler_breakdown": sprinkler_types,
        "unique_pipe_ids": sorted(list(pipe_ids)),
        "pipe_groups_count": len(pipe_ids),
        "unique_dn_values": sorted(list(dns))
    }

@mcp.tool()
def get_statistics() -> Dict[str, Any]:
    """
    Get comprehensive statistics about the shapes database.
    
    Returns:
        Detailed statistics about the database
    """
    total = len(shapes_database)
    
    with_vertices = sum(1 for s in shapes_database if s.get('vertices'))
    with_connectors = sum(1 for s in shapes_database if s.get('connectors'))
    
    # DN distribution
    dn_counts = {}
    for shape in shapes_database:
        for dn in shape.get('DN', []):
            dn_counts[dn] = dn_counts.get(dn, 0) + 1
    
    # Pipe ID distribution
    pipe_id_counts = {}
    for shape in shapes_database:
        pid = shape.get('pipe_id')
        if pid:
            pipe_id_counts[pid] = pipe_id_counts.get(pid, 0) + 1
    
    return {
        "total_objects": total,
        "objects_with_vertices": with_vertices,
        "objects_with_connectors": with_connectors,
        "dn_distribution": dict(sorted(dn_counts.items())),
        "pipe_id_distribution": dict(sorted(pipe_id_counts.items())),
        "top_pipe_ids": dict(sorted(pipe_id_counts.items(), key=lambda x: x[1], reverse=True)[:10])
    }

@mcp.tool()
def search_by_criteria(criteria: str) -> Dict[str, Any]:
    """
    Advanced search using multiple criteria as JSON string.
    
    Args:
        criteria: JSON string with search criteria, e.g.:
                 '{"shape_name": ["Tee", "Elbow"], "DN": 25, "pipe_id": 17}'
    
    Returns:
        Matching objects
    """
    try:
        filters = json.loads(criteria)
    except:
        return {"error": "Invalid JSON criteria"}
    
    filtered = shapes_database
    
    # Apply filters
    if 'shape_name' in filters:
        names = filters['shape_name'] if isinstance(filters['shape_name'], list) else [filters['shape_name']]
        filtered = [s for s in filtered if s.get('shape_name') in names]
    
    if 'pipe_id' in filters:
        pids = filters['pipe_id'] if isinstance(filters['pipe_id'], list) else [filters['pipe_id']]
        filtered = [s for s in filtered if s.get('pipe_id') in pids]
    
    if 'DN' in filters:
        dns = filters['DN'] if isinstance(filters['DN'], list) else [filters['DN']]
        filtered = [s for s in filtered if any(dn in s.get('DN', []) for dn in dns)]
    
    if 'type' in filters:
        filtered = [s for s in filtered if s.get('type') == filters['type']]
    
    # Return summary
    results = []
    for shape in filtered[:20]: # Hard limit to 20 for safety
        results.append({
            "id": shape.get('id'),
            "shape_name": shape.get('shape_name'),
            "pipe_id": shape.get('pipe_id'),
            "DN": shape.get('DN'),
            "type": shape.get('type'),
            # Vertices removed
        })
    
    return {
        "total_matches": len(filtered),
        "returned": len(results),
        "results": results,
        "applied_filters": filters
    }

@mcp.tool()
def analyze_sprinklers(pipe_id: Optional[int] = None, sprinkler_type: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """
    Phân tích chi tiết các vòi phun (sprinkler) trong hệ thống.
    
    Args:
        pipe_id: Lọc theo nhóm đường ống (pipe_id)
        sprinkler_type: Lọc theo loại vòi phun ("end" hoặc "center")
        limit: Giới hạn số lượng kết quả trả về (mặc định 20)
    
    Returns:
        Thông tin thống kê và danh sách rút gọn.
    """
    # Lọc chỉ lấy sprinkler
    filtered = [s for s in shapes_database if s.get('shape_name') == 'Sprinkler']
    
    if pipe_id is not None:
        filtered = [s for s in filtered if s.get('pipe_id') == pipe_id]
    
    if sprinkler_type:
        filtered = [s for s in filtered if s.get('type') == sprinkler_type]
    
    # Phân tích
    type_counts = {"end": 0, "center": 0}
    arm_lengths = []
    results = []
    
    # Tính toán thống kê trên TOÀN BỘ kết quả lọc
    for sprinkler in filtered:
        spr_type = sprinkler.get('type', 'unknown')
        if spr_type in type_counts:
            type_counts[spr_type] += 1
        
        # Thu thập thông tin arm
        arm = sprinkler.get('arm')
        if arm is not None:
            arm_lengths.append(arm)

    # Chỉ trả về danh sách giới hạn
    safe_limit = min(limit, 50)
    for sprinkler in filtered[:safe_limit]:
        results.append({
            "id": sprinkler.get('id'),
            "pipe_id": sprinkler.get('pipe_id'),
            "type": sprinkler.get('type'),
            "arm": sprinkler.get('arm'),
            "DN": sprinkler.get('DN'),
            # Vertices removed
            "connectors_count": len(sprinkler.get('connectors', []))
        })
    
    # Thống kê arm
    arm_stats = None
    if arm_lengths:
        arm_stats = {
            "min": min(arm_lengths),
            "max": max(arm_lengths),
            "average": round(sum(arm_lengths) / len(arm_lengths), 2),
            "count": len(arm_lengths)
        }
    
    return {
        "total_sprinklers": len(filtered),
        "returned_count": len(results),
        "type_breakdown": type_counts,
        "arm_statistics": arm_stats,
        "sprinklers": results,
        "filters_applied": {
            "pipe_id": pipe_id,
            "type": sprinkler_type
        },
        "note": f"Showing first {len(results)} items. Use filters to narrow down."
    }

@mcp.tool()
def analyze_pipe_group(pipe_id: int, limit: int = 20) -> Dict[str, Any]:
    """
    Phân tích chi tiết một nhóm đường ống theo pipe_id.
    
    Args:
        pipe_id: ID của nhóm đường ống cần phân tích
        limit: Giới hạn số lượng object trả về trong danh sách (mặc định 20)
    
    Returns:
        Thông tin thống kê nhóm và danh sách object rút gọn.
    """
    filtered = [s for s in shapes_database if s.get('pipe_id') == pipe_id]
    
    if not filtered:
        return {
            "error": f"Không tìm thấy nhóm đường ống với pipe_id = {pipe_id}",
            "total_objects": 0
        }
    
    # Phân tích theo shape_name
    shape_breakdown = {}
    dn_set = set()
    
    for obj in filtered:
        sname = obj.get('shape_name', 'Unknown')
        shape_breakdown[sname] = shape_breakdown.get(sname, 0) + 1
        
        for dn in obj.get('DN', []):
            dn_set.add(dn)
    
    # Tạo danh sách chi tiết giới hạn
    safe_limit = min(limit, 50)
    objects_detail = []
    for obj in filtered[:safe_limit]:
        obj_info = {
            "id": obj.get('id'),
            "shape_name": obj.get('shape_name'),
            "DN": obj.get('DN'),
            # Vertices removed
            "connectors_count": len(obj.get('connectors', []))
        }
        
        # Thêm trường đặc biệt cho sprinkler
        if obj.get('shape_name') == 'Sprinkler':
            obj_info["type"] = obj.get('type')
            obj_info["arm"] = obj.get('arm')
        
        objects_detail.append(obj_info)
    
    return {
        "pipe_id": pipe_id,
        "total_objects": len(filtered),
        "returned_count": len(objects_detail),
        "shape_breakdown": dict(sorted(shape_breakdown.items())),
        "dn_values": sorted(list(dn_set)),
        "objects": objects_detail,
        "note": f"Showing first {len(objects_detail)} items of {len(filtered)}. Vertices omitted."
    }

@mcp.tool()
def analyze_connections(object_id: int) -> Dict[str, Any]:
    """
    Phân tích các kết nối (connectors) của một object.
    Trả về thông tin về object và các object mà nó kết nối tới.
    
    Args:
        object_id: ID của object cần phân tích kết nối
    
    Returns:
        Thông tin về object và các kết nối của nó
    """
    # Tìm object gốc
    source_obj = None
    for obj in shapes_database:
        if obj.get('id') == object_id:
            source_obj = obj
            break
    
    if not source_obj:
        return {"error": f"Không tìm thấy object với id = {object_id}"}
    
    # Lấy danh sách connectors
    connector_ids = source_obj.get('connectors', [])
    
    # Tìm các object được kết nối
    connected_objects = []
    for conn_id in connector_ids:
        for obj in shapes_database:
            if obj.get('id') == conn_id:
                connected_objects.append({
                    "id": obj.get('id'),
                    "shape_name": obj.get('shape_name'),
                    "pipe_id": obj.get('pipe_id'),
                    "DN": obj.get('DN'),
                    "type": obj.get('type'),
                    "vertices": obj.get('vertices', [])
                })
                break
    
    return {
        "source_object": {
            "id": source_obj.get('id'),
            "shape_name": source_obj.get('shape_name'),
            "pipe_id": source_obj.get('pipe_id'),
            "DN": source_obj.get('DN'),
            "type": source_obj.get('type'),
            "vertices": source_obj.get('vertices', []),
            "connectors": connector_ids
        },
        "connection_count": len(connector_ids),
        "connected_objects": connected_objects,
        "missing_connections": len(connector_ids) - len(connected_objects)
    }

@mcp.tool()
def get_shape_type_info() -> Dict[str, Any]:
    """
    Trả về thông tin chi tiết về từng loại shape trong hệ thống đường ống phòng cháy.
    
    Returns:
        Mô tả chi tiết về các loại object:
        - Line: Đường ống thẳng
        - Tee: Khớp nối chữ T (3 hướng)
        - Elbow: Khớp nối khuỷu (góc)
        - Sprinkler: Vòi phun (có type: end hoặc center, nếu end có thêm arm)
    """
    return {
        "shape_types": {
            "Line": {
                "description": "Đường ống thẳng",
                "properties": ["id", "shape_name", "pipe_id", "vertices (2 điểm)", "DN", "connectors"],
                "note": "Kết nối 2 điểm, tạo thành đoạn ống thẳng"
            },
            "Tee": {
                "description": "Khớp nối chữ T (3 hướng)",
                "properties": ["id", "shape_name", "pipe_id", "vertices (1 điểm)", "DN (có thể có nhiều giá trị)", "connectors (thường 3 hoặc 4)"],
                "note": "Điểm phân nhánh, kết nối 3-4 đường ống"
            },
            "Elbow": {
                "description": "Khớp nối khuỷu (góc)",
                "properties": ["id", "shape_name", "pipe_id", "vertices (1 điểm)", "DN", "connectors (2)"],
                "note": "Điểm uốn góc, thay đổi hướng đường ống"
            },
            "Sprinkler": {
                "description": "Vòi phun nước chữa cháy",
                "properties": ["id", "shape_name", "pipe_id", "vertices (4 điểm)", "DN", "type", "arm (nếu type=end)", "connectors"],
                "types": {
                    "end": "Vòi phun ở cuối đường ống, có cánh tay (arm) nối từ đường ống chính",
                    "center": "Vòi phun ở giữa đường ống, kết nối trực tiếp với đường ống chính"
                },
                "note": "Type 'end' có thêm trường 'arm' - độ dài cánh tay từ đường ống đến vòi phun"
            }
        },
        "common_fields": {
            "id": "ID duy nhất của object",
            "shape_name": "Loại hình dạng (Line/Tee/Elbow/Sprinkler)",
            "pipe_id": "ID nhóm đường ống - các object cùng pipe_id thuộc cùng 1 hệ thống",
            "DN": "Đường kính danh nghĩa (Diameter Nominal) - kích thước ống",
            "vertices": "Tọa độ các điểm định nghĩa hình dạng",
            "connectors": "Danh sách ID các object được kết nối"
        },
        "statistics": {
            "total_pipe_groups": len(set(s.get('pipe_id') for s in shapes_database if s.get('pipe_id'))),
            "total_objects": len(shapes_database)
        }
    }

if __name__ == "__main__":
    # import argparse
    # import sys
    
    # # Define arguments
    # parser = argparse.ArgumentParser(description="Shapes Database MCP Server")
    # parser.add_argument("--transport", default="sse", choices=["stdio", "sse"], help="Transport protocol: 'sse' (default) or 'stdio'")
    # parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (for SSE) - default: 0.0.0.0")
    # parser.add_argument("--port", type=int, default=8000, help="Port to bind to (for SSE) - default: 8000")
    
    # args = parser.parse_args()
    
    # if args.transport == "sse":
    #     print(f"Starting MCP server on http://{args.host}:{args.port}/sse", file=sys.stderr)
    #     print(f"Health check available at http://{args.host}:{args.port}/health", file=sys.stderr)
    #     mcp.run(transport="sse", host=args.host, port=args.port)
    # else:
    #     # Default to stdio for local editor integration
    #     mcp.run(transport="stdio")

    mcp.run(transport="sse", host="0.0.0.0", port=8000)
