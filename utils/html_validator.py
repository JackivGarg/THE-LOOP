"""
HTML Validator — extracts clean HTML from LLM output.
LLMs often wrap code in markdown fences or add preamble text.
This module strips all of that and returns only the raw HTML.
"""

import re


def extract_html(raw_output: str) -> str | None:
    """
    Extract a valid HTML document from raw LLM output.
    
    Tries three strategies in order:
      1. Regex match from <!DOCTYPE html> to </html>
      2. Regex match from <html to </html> (no doctype)
      3. Strip markdown code fences and try again
    
    Returns the extracted HTML string, or None if no valid HTML found.
    """
    if not raw_output or not isinstance(raw_output, str):
        return None

    # Strategy 1: Full doctype match (case-insensitive)
    match = re.search(
        r'(<!DOCTYPE\s+html[^>]*>.*?</html>)',
        raw_output,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    # Strategy 2: <html> to </html> without doctype
    match = re.search(
        r'(<html[^>]*>.*?</html>)',
        raw_output,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return "<!DOCTYPE html>\n" + match.group(1).strip()

    # Strategy 3: Strip markdown fences and retry
    cleaned = re.sub(r'```(?:html)?\s*\n?', '', raw_output)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned, flags=re.MULTILINE)

    match = re.search(
        r'(<!DOCTYPE\s+html[^>]*>.*?</html>)',
        cleaned,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    match = re.search(
        r'(<html[^>]*>.*?</html>)',
        cleaned,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return "<!DOCTYPE html>\n" + match.group(1).strip()

    # Last resort: if the cleaned output looks like it starts with a tag, return as-is
    stripped = cleaned.strip()
    if stripped.startswith('<') and stripped.endswith('>'):
        return stripped

    return None
