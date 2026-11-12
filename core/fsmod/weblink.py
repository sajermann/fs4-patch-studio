"""Web links the user (or a pack's manifest) gives for credits: only http(s) addresses are kept."""
from urllib.parse import urlsplit

SCHEMES = ('http', 'https')


def normalize(url):
    """The link as the app keeps it, or None when it is empty or not a web address. An address without a scheme
    ('www.site.com/x', 'site.com') gets https://; any other scheme (javascript:, file:, ...) is refused."""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url or any(c.isspace() for c in url):
        return None
    if '://' not in url:
        if ':' in url.split('/', 1)[0] and not url.split('/', 1)[0].rsplit(':', 1)[-1].isdigit():
            return None  # 'javascript:alert(1)', 'mailto:x' (a port, 'site.com:8080', is fine)
        url = 'https://' + url
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = parts.hostname or ''
    if parts.scheme.lower() not in SCHEMES or not host or ('.' not in host and host != 'localhost'):
        return None
    return url
