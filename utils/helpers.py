import html 

def escape_html_tags(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    return html.escape(text)
