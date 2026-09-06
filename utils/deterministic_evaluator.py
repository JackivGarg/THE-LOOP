"""Deterministic quality checks for generated single-page HTML websites."""

from __future__ import annotations

import ipaddress
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_SEMANTIC_TAGS = {"header", "main", "footer"}
_SECTION_KEYWORDS = {
    "about", "skills", "projects", "portfolio", "contact", "services", "pricing",
    "testimonials", "blog", "experience", "education", "team", "features", "gallery",
    "menu", "progress", "analytics",
}
_STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "the", "to", "with", "your"}


class _HTMLInspector(HTMLParser):
    """Collect structure and accessibility-relevant data using the standard library."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.errors: list[str] = []
        self.stack: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self._heading_level: int | None = None
        self._heading_parts: list[str] = []
        self._current_tag: str | None = None
        self._script_parts: list[str] = []
        self.inline_scripts: list[str] = []
        self.text_parts: list[str] = []
        self.inputs: list[dict[str, str]] = []
        self.labels_for: set[str] = set()
        self._label_for: str | None = None
        self._label_parts: list[str] = []
        self.buttons: list[tuple[dict[str, str], str]] = []
        self._button_attrs: dict[str, str] | None = None
        self._button_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {key.lower(): value or "" for key, value in attrs}
        self.tags.append((tag, attributes))
        if tag not in _VOID_TAGS:
            self.stack.append(tag)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_level = int(tag[1])
            self._heading_parts = []
        if tag == "script" and not attributes.get("src"):
            self._script_parts = []
        if tag in {"input", "textarea", "select"}:
            self.inputs.append(attributes)
        if tag == "label":
            self._label_for = attributes.get("for")
            self._label_parts = []
        if tag == "button":
            self._button_attrs = attributes
            self._button_parts = []
        self._current_tag = tag

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag not in _VOID_TAGS:
            if not self.stack or self.stack[-1] != tag:
                self.errors.append(f"Mismatched closing tag: </{tag}>")
            else:
                self.stack.pop()
        if self._heading_level is not None and tag == f"h{self._heading_level}":
            self.headings.append((self._heading_level, " ".join(self._heading_parts).strip()))
            self._heading_level = None
        if tag == "script" and self._script_parts:
            self.inline_scripts.append("".join(self._script_parts))
        if tag == "label":
            label_text = " ".join(self._label_parts).strip()
            if self._label_for and label_text:
                self.labels_for.add(self._label_for)
            self._label_for = None
        if tag == "button" and self._button_attrs is not None:
            self.buttons.append((self._button_attrs, " ".join(self._button_parts).strip()))
            self._button_attrs = None
        self._current_tag = self.stack[-1] if self.stack else None

    def handle_data(self, data: str) -> None:
        if self._heading_level is not None:
            self._heading_parts.append(data)
        if self._current_tag == "script":
            self._script_parts.append(data)
        if self._label_for is not None:
            self._label_parts.append(data)
        if self._button_attrs is not None:
            self._button_parts.append(data)
        if data.strip():
            self.text_parts.append(data)


def _check(name: str, score: float, weight: float, details: str, issues: list[str]) -> dict[str, Any]:
    return {"name": name, "score": round(max(0.0, min(1.0, score)), 3), "weight": weight, "details": details, "issues": issues}


def _is_safe_external_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.hostname.lower() == "localhost":
        return False
    try:
        return not ipaddress.ip_address(parsed.hostname).is_private
    except ValueError:
        return True


def _resource_status(url: str, timeout_seconds: float = 2.0) -> tuple[str, bool, str]:
    if not _is_safe_external_url(url):
        return url, False, "Skipped unsafe or non-public URL"
    try:
        request = Request(url, method="HEAD", headers={"User-Agent": "THE-LOOP-Validator/1.0"})
        with urlopen(request, timeout=timeout_seconds) as response:
            return url, 200 <= response.status < 400, f"HTTP {response.status}"
    except HTTPError as error:
        # Some CDNs reject HEAD but accept normal GET requests.
        if error.code not in {403, 405}:
            return url, False, f"HTTP {error.code}"
        try:
            request = Request(url, method="GET", headers={"User-Agent": "THE-LOOP-Validator/1.0"})
            with urlopen(request, timeout=timeout_seconds) as response:
                return url, 200 <= response.status < 400, f"HTTP {response.status}"
        except (HTTPError, URLError, TimeoutError, socket.timeout) as fallback_error:
            return url, False, str(fallback_error)
    except (URLError, TimeoutError, socket.timeout) as error:
        return url, False, str(error)


def _has_balanced_delimiters(script: str) -> bool:
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    for char in script:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char in pairs:
            stack.append(pairs[char])
        elif char in {")", "]", "}"}:
            if not stack or stack.pop() != char:
                return False
    return quote is None and not stack


def _requested_sections(title: str, description: str) -> set[str]:
    tokens = set(re.findall(r"[a-z]{3,}", f"{title} {description}".lower()))
    return {token for token in tokens if token in _SECTION_KEYWORDS and token not in _STOP_WORDS}


def evaluate_html(html_code: str, *, title: str = "", description: str = "", check_external_resources: bool = True) -> dict[str, Any]:
    """Run objective quality checks and return a normalized 0–10 score and report."""
    inspector = _HTMLInspector()
    try:
        inspector.feed(html_code)
        inspector.close()
    except Exception as error:
        inspector.errors.append(f"Parser error: {error}")
    if inspector.stack:
        inspector.errors.append(f"Unclosed tags: {', '.join(inspector.stack[-5:])}")

    tags = [tag for tag, _ in inspector.tags]
    attrs_by_tag: dict[str, list[dict[str, str]]] = {}
    for tag, attrs in inspector.tags:
        attrs_by_tag.setdefault(tag, []).append(attrs)
    checks: list[dict[str, Any]] = []

    valid_document = bool(re.search(r"<!doctype\s+html", html_code, re.IGNORECASE)) and {"html", "head", "body"}.issubset(set(tags)) and not inspector.errors
    checks.append(_check("valid_html", float(valid_document), 1.0, "Valid document structure" if valid_document else "HTML structure is incomplete or malformed", inspector.errors))

    h1_count = sum(1 for level, _ in inspector.headings if level == 1)
    checks.append(_check("single_h1", float(h1_count == 1), 0.9, f"Found {h1_count} h1 element(s)", [] if h1_count == 1 else ["Use exactly one h1"]))

    hierarchy_issues: list[str] = []
    previous_level = 0
    for level, text in inspector.headings:
        if previous_level and level > previous_level + 1:
            hierarchy_issues.append(f"Heading jump from h{previous_level} to h{level} near '{text[:40]}'")
        previous_level = level
    checks.append(_check("heading_hierarchy", float(not hierarchy_issues), 0.8, "Heading order is sequential" if not hierarchy_issues else "Heading hierarchy has skips", hierarchy_issues))

    missing_semantics = sorted(_SEMANTIC_TAGS - set(tags))
    checks.append(_check("semantic_structure", 1 - len(missing_semantics) / len(_SEMANTIC_TAGS), 0.8, "Semantic landmarks present" if not missing_semantics else "Missing semantic landmarks", [f"Missing <{tag}>" for tag in missing_semantics]))

    images = attrs_by_tag.get("img", [])
    missing_alt = [image.get("src", "unnamed image") for image in images if "alt" not in image]
    image_score = 1.0 if not images else 1 - len(missing_alt) / len(images)
    checks.append(_check("image_alt_text", image_score, 0.8, "All images have alt attributes" if not missing_alt else "Images are missing alt attributes", [f"Missing alt: {src}" for src in missing_alt]))

    viewport_tags = [attrs for attrs in attrs_by_tag.get("meta", []) if attrs.get("name", "").lower() == "viewport"]
    has_viewport = any("width=device-width" in attrs.get("content", "").replace(" ", "").lower() for attrs in viewport_tags)
    checks.append(_check("responsive_viewport", float(has_viewport), 0.7, "Responsive viewport meta tag present" if has_viewport else "Missing responsive viewport meta tag", [] if has_viewport else ["Add meta viewport with width=device-width"]))

    external_urls = sorted({attrs.get(key, "") for tag, attrs in inspector.tags for key in ("src", "href") if (tag in {"script", "img", "link"}) and attrs.get(key, "").startswith(("http://", "https://"))})
    external_issues: list[str] = []
    if check_external_resources and external_urls:
        statuses: list[tuple[str, bool, str]] = []
        with ThreadPoolExecutor(max_workers=min(4, len(external_urls))) as executor:
            futures = [executor.submit(_resource_status, url) for url in external_urls[:8]]
            statuses = [future.result() for future in as_completed(futures)]
        failures = [(url, detail) for url, success, detail in statuses if not success]
        external_issues = [f"Unavailable resource: {url} ({detail})" for url, detail in failures]
        external_score = 1.0 if not failures else 1 - len(failures) / len(statuses)
        external_details = f"Verified {len(statuses)} external resource(s)"
    elif external_urls:
        external_score, external_details = 1.0, "External resource checks skipped"
    else:
        external_score, external_details = 1.0, "No external resources to verify"
    checks.append(_check("external_resources", external_score, 0.6, external_details, external_issues))

    script_issues = ["Inline script has unbalanced brackets or quotes" for script in inspector.inline_scripts if not _has_balanced_delimiters(script)]
    checks.append(_check("inline_javascript", float(not script_issues), 0.5, "Inline JavaScript passed static syntax checks" if not script_issues else "Inline JavaScript has a structural syntax issue", script_issues))

    overflow_patterns = [r"(?:min-)?width\s*:\s*(?:[1-9]\d{3,}|1\d{2,})px", r"w-\[\d{4,}px\]", r"translate-x-\[?[1-9]\d{2,}"]
    overflow_issues = [f"Potential horizontal overflow pattern: {match.group(0)}" for pattern in overflow_patterns for match in re.finditer(pattern, html_code, re.IGNORECASE)]
    checks.append(_check("horizontal_overflow", float(not overflow_issues), 0.7, "No static horizontal-overflow risk found" if not overflow_issues else "Potential horizontal overflow found", overflow_issues[:5]))

    html_attrs = attrs_by_tag.get("html", [{}])[0]
    has_title = bool(attrs_by_tag.get("title"))
    unlabeled_inputs = [attrs.get("name") or attrs.get("id") or attrs.get("type", "input") for attrs in inspector.inputs if attrs.get("type", "").lower() not in {"hidden", "submit", "button"} and not (attrs.get("id") in inspector.labels_for or attrs.get("aria-label") or attrs.get("aria-labelledby"))]
    unnamed_buttons = [text for attrs, text in inspector.buttons if not (text or attrs.get("aria-label") or attrs.get("aria-labelledby"))]
    accessibility_issues = ([] if html_attrs.get("lang") else ["Missing lang attribute on <html>"]) + ([] if has_title else ["Missing document title"]) + [f"Unlabeled form control: {item}" for item in unlabeled_inputs] + (["Button has no accessible name"] if unnamed_buttons else [])
    checks.append(_check("basic_accessibility", 1 - min(len(accessibility_issues), 4) / 4, 1.2, "Basic accessibility checks passed" if not accessibility_issues else "Accessibility improvements needed", accessibility_issues))

    required = _requested_sections(title, description)
    searchable_document = " ".join(inspector.text_parts + [attrs.get("id", "") + " " + attrs.get("class", "") for _, attrs in inspector.tags]).lower()
    missing_sections = sorted(section for section in required if section not in searchable_document)
    section_score = 1.0 if not required else 1 - len(missing_sections) / len(required)
    checks.append(_check("requested_sections", section_score, 1.0, "Requested sections matched" if not missing_sections else "Some requested sections were not found", [f"Requested section not found: {section}" for section in missing_sections]))

    weighted_score = sum(check["score"] * check["weight"] for check in checks)
    total_weight = sum(check["weight"] for check in checks)
    score = round(10 * weighted_score / total_weight, 2) if total_weight else 0.0
    issues = [issue for check in checks for issue in check["issues"]]
    return {"score": score, "checks": checks, "issues": issues, "external_resources_checked": len(external_urls), "required_sections": sorted(required)}
