import sys
import os
import io
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from passenger_wsgi import application

def main():
    environ = dict(os.environ)
    body = sys.stdin.buffer.read()
    environ["wsgi.input"] = io.BytesIO(body)
    environ["CONTENT_LENGTH"] = str(len(body))

    headers_list = []
    status_code = "200 OK"

    def start_response(status, response_headers):
        nonlocal status_code, headers_list
        status_code = status
        headers_list = response_headers

    chunks = application(environ, start_response)

    sys.stdout.write(f"Status: {status_code}\r\n")
    for k, v in headers_list:
        sys.stdout.write(f"{k}: {v}\r\n")
    sys.stdout.write("\r\n")
    sys.stdout.flush()

    for chunk in chunks:
        sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()

if __name__ == "__main__":
    main()
