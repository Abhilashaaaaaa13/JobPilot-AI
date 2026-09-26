# frontend/components/formatting.py
"""Small shared display helpers used by multiple pages."""


def short_url(url: str) -> str:
    """'https://www.example.com/pricing' -> 'example.com' — for compact link labels."""
    if not url:
        return ""
    return (
        url.replace("https://", "")
           .replace("http://", "")
           .replace("www.", "")
           .rstrip("/")
           .split("/")[0]
    )
