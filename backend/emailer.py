import re
import ssl
import base64
import asyncio
import logging
import smtplib
import ipaddress
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html.parser import HTMLParser
from urllib.parse import urlparse
from fastapi import HTTPException

logger = logging.getLogger(__name__)

_SHORTENERS = ("bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly")
_CRED_ASK = ("reply with your password", "reply with the code", "send your password", "cvv",
             "send us your password", "enter your password below", "confirm your card number",
             "your full card number", "seed phrase", "recovery phrase", "verify your card",
             "social security number", "confirm your bank details")
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return shown == real or real.endswith("." + shown) or shown.endswith("." + real)


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(f"Email asks the recipient for credentials: {p!r}")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith(("https://", "http://")):
            raise ValueError(f"Email links must be absolute http(s): {url!r}")
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(f"Shortened or credential-bearing URL: {url!r}")
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(f"Anchor text {m.group(1)!r} != real link host {real!r}")


def _build(smtp: dict, to: str, subject: str, html: str, reply_to: str | None, attachments: list | None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((smtp.get("from_name") or "", smtp["from_email"]))
    msg["To"] = to
    msg["Message-ID"] = make_msgid(domain=smtp["from_email"].split("@")[-1])
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(re.sub(r"<[^>]+>", " ", html))
    msg.add_alternative(html, subtype="html")
    for a in attachments or []:
        msg.add_attachment(base64.b64decode(a["content"]), maintype="application", subtype="pdf", filename=a["filename"])
    return msg


def _deliver(smtp: dict, msg: EmailMessage) -> None:
    host, port, sec = smtp["host"], int(smtp["port"]), smtp.get("security") or "starttls"
    ctx = ssl.create_default_context()
    cls = smtplib.SMTP_SSL if sec == "ssl" else smtplib.SMTP
    kw = {"context": ctx} if sec == "ssl" else {}
    with cls(host, port, timeout=30, **kw) as s:
        if sec == "starttls":
            s.starttls(context=ctx)
        if smtp.get("username"):
            s.login(smtp["username"], smtp.get("password") or "")
        s.send_message(msg)


async def send_email(*, smtp: dict, to: str, subject: str, html: str, reply_to: str | None = None, attachments: list | None = None) -> str:
    _assert_safe_email(subject, html)
    msg = _build(smtp, to, subject, html, reply_to, attachments)
    try:
        await asyncio.to_thread(_deliver, smtp, msg)
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(502, "Il server SMTP ha rifiutato utente o password")
    except smtplib.SMTPRecipientsRefused:
        raise HTTPException(502, "Il server SMTP ha rifiutato il destinatario")
    except (smtplib.SMTPException, OSError) as e:
        logger.error(f"SMTP send error ({smtp.get('host')}): {e}")
        raise HTTPException(502, f"Invio email non riuscito: {str(e)[:150] or 'server SMTP non raggiungibile'}")
    return msg["Message-ID"]
