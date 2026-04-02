# Run this: python debug_hn.py
# Ye batayega actual bytes kya hain "Â·" ke

import requests
from bs4 import BeautifulSoup

hits = requests.get(
    "https://hn.algolia.com/api/v1/search?query=who+is+hiring&tags=story&hitsPerPage=1",
    timeout=10
).json().get("hits", [])

thread_id = hits[0]["objectID"]
comments = requests.get(
    f"https://hn.algolia.com/api/v1/search?tags=comment,story_{thread_id}&hitsPerPage=5",
    timeout=10
).json().get("hits", [])

for comment in comments[:2]:
    raw_html = comment.get("comment_text", "")
    text = BeautifulSoup(raw_html, "html.parser").get_text(separator=" ")
    
    # Find Â· in text
    idx = text.find("Â")
    if idx != -1:
        snippet = text[max(0,idx-5):idx+10]
        print(f"Found at {idx}: {repr(snippet)}")
        print(f"Bytes: {snippet.encode('utf-8')}")
        print()
        
        # Try fix
        try:
            fixed = text.encode("latin-1").decode("utf-8")
            print(f"latin-1 fix worked: {repr(fixed[max(0,idx-5):idx+10])}")
        except Exception as e:
            print(f"latin-1 fix failed: {e}")
            
        try:
            fixed2 = text.encode("utf-8").decode("utf-8")
            print(f"utf-8 passthrough: {repr(fixed2[max(0,idx-5):idx+10])}")
        except Exception as e:
            print(f"utf-8 passthrough failed: {e}")
    else:
        print("No Â found in this comment")
    print("---")