# Local SMTP sink for tests: stores each received message as /tmp/t97_mail/<n>.eml
# Run: python3 tests/t97_smtp_sink.py &   (listens on 127.0.0.1:1025)
import asyncore
import os
import smtpd
import time

OUT = "/tmp/t97_mail"
os.makedirs(OUT, exist_ok=True)


class Sink(smtpd.SMTPServer):
    def process_message(self, peer, mailfrom, rcpttos, data, **kw):
        n = f"{time.time():.6f}"
        with open(os.path.join(OUT, f"{n}.eml"), "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode())
        with open(os.path.join(OUT, f"{n}.rcpt"), "w") as f:
            f.write(",".join(rcpttos))


Sink(("127.0.0.1", 1025), None, decode_data=False)
asyncore.loop()
