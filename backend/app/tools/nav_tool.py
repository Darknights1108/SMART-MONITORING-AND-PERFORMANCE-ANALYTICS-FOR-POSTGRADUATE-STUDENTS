from smolagents import tool
import json


_PAGE_BASE_URLS: dict[str, str] = {
    "dashboard": "/dashboard",
    "students": "/students",
    "risk": "/risk",
    "analytics": "/analytics",
    "student_detail": "/students",
}


@tool
def navigate_to(page: str, filters: str = "{}") -> str:
    """
    Navigate the user's browser to a specific page in the application.
    Returns a nav_action payload that the frontend will intercept to perform the navigation.

    Args:
        page: Target page — one of: 'dashboard', 'students', 'risk', 'analytics', 'student_detail'.
        filters: Optional JSON string with filter parameters, e.g. '{"risk": "High"}' or
                 '{"student_id": 42}' for student_detail.
    """
    valid_pages = list(_PAGE_BASE_URLS.keys())
    if page not in valid_pages:
        return f"Unknown page '{page}'. Valid options: {', '.join(valid_pages)}"

    try:
        filter_dict: dict = json.loads(filters) if filters.strip() else {}
    except json.JSONDecodeError:
        return f"Invalid filters JSON: {filters}"

    base = _PAGE_BASE_URLS[page]

    if page == "student_detail":
        student_id = filter_dict.get("student_id")
        if not student_id:
            return "student_detail requires 'student_id' in filters, e.g. '{\"student_id\": 42}'"
        url = f"{base}/{student_id}"
    elif page == "students" and "risk" in filter_dict:
        url = f"{base}?risk={filter_dict['risk']}"
    else:
        url = base

    payload = {
        "__nav_action__": True,
        "page": page,
        "filters": filter_dict,
        "url": url,
    }
    return json.dumps(payload)
