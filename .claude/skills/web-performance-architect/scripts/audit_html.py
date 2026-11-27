#!/usr/bin/env python3
"""Heuristic HTML performance audit.

This checks selected markup patterns only. It cannot measure Core Web Vitals,
identify the actual LCP element, inspect runtime JavaScript, CSS layout, network
waterfalls, accessibility, or security. Use Lighthouse/browser traces/RUM too.
"""
import json
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urlparse

ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def external_host(url):
    parsed = urlparse(url or "")
    if parsed.scheme in ("http", "https"):
        return parsed.netloc
    if (url or "").startswith("//"):
        return urlparse("https:" + url).netloc
    return None


class Audit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.findings = []
        self.in_head = False
        self.in_style = False
        self.style_buf = []
        self.style_line = 1
        self.has_viewport = False
        self.preloads = 0
        self.connected = set()
        self.external = {}
        self.image_count = 0

    def add(self, severity, rule, message, line=None):
        self.findings.append({
            "severity": severity, "rule": rule, "message": message,
            "line": line or self.getpos()[0],
        })

    def note_external(self, url):
        host = external_host(url)
        if host:
            self.external.setdefault(host, self.getpos()[0])

    def handle_starttag(self, tag, attrs):
        attrs = {k: (v if v is not None else "") for k, v in attrs}
        if tag == "head":
            self.in_head = True
        elif tag == "meta" and attrs.get("name", "").lower() == "viewport":
            self.has_viewport = True
        elif tag == "link":
            rel = attrs.get("rel", "").lower().split()
            href = attrs.get("href", "")
            if "preconnect" in rel or "dns-prefetch" in rel:
                host = external_host(href)
                if host:
                    self.connected.add(host)
            if "preload" in rel:
                self.preloads += 1
            if "stylesheet" in rel:
                self.note_external(href)
                if "fonts.googleapis.com" in href and "display=" not in href:
                    self.add("MEDIUM", "font-display",
                             "Google Fonts URL has no display= parameter; consider display=swap after checking font metrics.")
        elif tag == "script":
            src = attrs.get("src")
            if src:
                self.note_external(src)
                blocking = ("async" not in attrs and "defer" not in attrs
                            and attrs.get("type", "").lower() != "module")
                if blocking and self.in_head:
                    self.add("HIGH", "render-blocking-script",
                             f"Head script {src!r} has no async/defer/module behavior.")
                elif blocking and external_host(src):
                    self.add("MEDIUM", "blocking-third-party",
                             f"External script {src!r} loads synchronously.")
        elif tag == "style":
            self.in_style = True
            self.style_line = self.getpos()[0]
            self.style_buf = []
        elif tag == "img":
            self.image_count += 1
            self.note_external(attrs.get("src", ""))
            style = attrs.get("style", "").lower()
            has_dimensions = ("width" in attrs and "height" in attrs) or "aspect-ratio" in style
            if not has_dimensions:
                self.add("MEDIUM", "img-dimensions",
                         "Image has no width/height attributes or inline aspect-ratio; verify reserved layout space.")
            if "loading" not in attrs and self.image_count > 1:
                self.add("LOW", "img-lazy-candidate",
                         "Image has no loading attribute; consider lazy loading only if below the fold.")
            if "alt" not in attrs:
                self.add("LOW", "img-alt", "Image has no alt attribute; decide whether it is informative or decorative.")
        elif tag in ("iframe", "video"):
            style = attrs.get("style", "").lower()
            if not (("width" in attrs and "height" in attrs) or "aspect-ratio" in style):
                self.add("MEDIUM", f"{tag}-dimensions",
                         f"{tag} has no dimensions/aspect ratio; verify layout space is reserved.")
            if tag == "iframe" and "loading" not in attrs:
                self.add("LOW", "iframe-lazy-candidate",
                         "Consider loading=lazy for below-the-fold iframe content.")

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False
        elif tag == "style":
            self.in_style = False
            css = "".join(self.style_buf)
            for match in re.finditer(r"@font-face\s*{([^}]*)}", css, re.I):
                if "font-display" not in match.group(1).lower():
                    self.add("MEDIUM", "font-display",
                             "@font-face has no font-display declaration; verify font loading and layout behavior.",
                             self.style_line)

    def handle_data(self, data):
        if self.in_style:
            self.style_buf.append(data)

    def finish(self):
        if not self.has_viewport:
            self.add("HIGH", "viewport", "Missing viewport meta tag; verify mobile viewport configuration.", 1)
        if self.preloads > 5:
            self.add("LOW", "preload-overuse",
                     f"{self.preloads} preload links found; verify each is critical and does not compete for bandwidth.", 1)
        for host, line in self.external.items():
            if host not in self.connected:
                self.add("LOW", "preconnect-candidate",
                         f"External origin {host} has no preconnect/dns-prefetch; add only if it is a critical origin.", line)


def main():
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print(__doc__)
        return 2
    with open(args[0], encoding="utf-8", errors="replace") as handle:
        html = handle.read()
    audit = Audit()
    audit.feed(html)
    audit.close()
    audit.finish()
    findings = sorted(audit.findings, key=lambda item: (ORDER[item["severity"]], item["line"]))
    counts = {severity: sum(item["severity"] == severity for item in findings) for severity in ORDER}
    if as_json:
        print(json.dumps({"file": args[0], "counts": counts, "findings": findings}, indent=2))
    else:
        for item in findings:
            print(f"[{item['severity']:<6}] line {item['line']:<4} {item['rule']}: {item['message']}")
        print(f"\n{counts['HIGH']} high, {counts['MEDIUM']} medium, {counts['LOW']} low")
    return 1 if counts["HIGH"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
