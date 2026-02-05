from fastmcp import FastMCP
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

# Create an MCP server
mcp = FastMCP("Shapes Database Server")

# Load shapes database
SHAPES_DB_PATH = Path(__file__).parent / "39_shapes.json"
shapes_database = []

def load_shapes_database():
    """Load shapes data from JSON file."""
    global shapes_database
    try:
        if SHAPES_DB_PATH.exists():
            with open(SHAPES_DB_PATH, 'r', encoding='utf-8') as f:
                shapes_database = json.load(f)
            import sys
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
                  dn: Optional[int] = None, object_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Count objects in the shapes database based on criteria.
    
    Args:
        shape_name: Filter by shape name (e.g., "Sprinkler", "Tee", "Elbow", "Line")
        pipe_id: Filter by pipe ID
        dn: Filter by DN (pipe diameter)
        object_type: Filter by object type (e.g., "pipe", "sprinkler")
    
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
    if object_type:
        filtered = [s for s in filtered if s.get('object_type') == object_type]
    
    # Count by shape_name
    shape_counts = {}
    objects_with_vertices = []
    for shape in filtered:
        sname = shape.get('shape_name', 'Unknown')
        shape_counts[sname] = shape_counts.get(sname, 0) + 1
        
        # Collect vertices for FE UI control
        objects_with_vertices.append({
            "id": shape.get('id'),
            "shape_name": sname,
            "vertices": shape.get('vertices', [])
        })
    
    return {
        "total_count": len(filtered),
        "shape_breakdown": shape_counts,
        "objects": objects_with_vertices,  # Returned for UI control
        "filters_applied": {
            "shape_name": shape_name,
            "pipe_id": pipe_id,
            "dn": dn,
            "object_type": object_type
        }
    }

@mcp.tool()
def find_objects(shape_name: Optional[str] = None, pipe_id: Optional[int] = None,
                 dn: Optional[int] = None, limit: int = 50) -> Dict[str, Any]:
    """
    Find objects matching the specified criteria.
    
    Args:
        shape_name: Filter by shape name
        pipe_id: Filter by pipe ID
        dn: Filter by DN value
        limit: Maximum number of results to return (default: 50)
    
    Returns:
        Dictionary with matched objects and their details, including vertices.
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
    # If limit is applied, we might miss some, but for 'find' usually we want pagination or limits.
    # However, the user said "any" question related to statistics. 'Find' is search, not just stats.
    # But let's add vertices to be safe.
    for shape in filtered[:limit]:
        results.append({
            "id": shape.get('id'),
            "shape_name": shape.get('shape_name'),
            "object_type": shape.get('object_type'),
            "pipe_id": shape.get('pipe_id'),
            "DN": shape.get('DN'),
            "type": shape.get('type'),
            "vertices": shape.get('vertices', []), # Added vertices
            "connectors_count": len(shape.get('connectors', []))
        })
    
    return {
        "found": len(filtered),
        "returned": len(results),
        "results": results
    }

@mcp.tool()
def get_object_by_id(object_id: int) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a specific object by its ID.
    
    Args:
        object_id: The ID of the object to retrieve
    
    Returns:
        Full object data or None if not found
    """
    for shape in shapes_database:
        if shape.get('id') == object_id:
            return shape
    return None

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
    object_types = {}
    pipe_ids = set()
    dns = set()
    
    for shape in shapes_database:
        # Count shape names
        sname = shape.get('shape_name', 'Unknown')
        shape_types[sname] = shape_types.get(sname, 0) + 1
        
        # Count object types
        otype = shape.get('object_type', 'Unknown')
        object_types[otype] = object_types.get(otype, 0) + 1
        
        # Collect pipe IDs
        if shape.get('pipe_id'):
            pipe_ids.add(shape.get('pipe_id'))
        
        # Collect DN values
        for dn in shape.get('DN', []):
            dns.add(dn)
    
    return {
        "total_objects": len(shapes_database),
        "shape_types": dict(sorted(shape_types.items(), key=lambda x: x[1], reverse=True)),
        "object_types": object_types,
        "unique_pipe_ids": sorted(list(pipe_ids)),
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
    for shape in filtered[:50]:
        results.append({
            "id": shape.get('id'),
            "shape_name": shape.get('shape_name'),
            "pipe_id": shape.get('pipe_id'),
            "DN": shape.get('DN'),
            "type": shape.get('type'),
            "vertices": shape.get('vertices', [])
        })
    
    return {
        "total_matches": len(filtered),
        "returned": len(results),
        "results": results,
        "applied_filters": filters
    }

# if __name__ == "__main__":
#     import argparse
#     import sys
    
#     # Define arguments
#     parser = argparse.ArgumentParser(description="Shapes Database MCP Server")
#     parser.add_argument("--transport", default="sse", choices=["stdio", "sse"], help="Transport protocol: 'sse' (default) or 'stdio'")
#     parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (for SSE) - default: 0.0.0.0")
#     parser.add_argument("--port", type=int, default=8000, help="Port to bind to (for SSE) - default: 8000")
    
#     args = parser.parse_args()
    
#     if args.transport == "sse":
#         print(f"Starting MCP server on http://{args.host}:{args.port}/sse", file=sys.stderr)
#         print(f"Health check available at http://{args.host}:{args.port}/health", file=sys.stderr)
#         mcp.run(transport="sse", host=args.host, port=args.port)
#     else:
#         # Default to stdio for local editor integration
#         mcp.run(transport="stdio")
