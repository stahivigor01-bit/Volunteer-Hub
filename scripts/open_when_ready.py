import sys
import time
import urllib.error
import urllib.request
import webbrowser


def main():
    wait_url = sys.argv[1]
    open_url = sys.argv[2] if len(sys.argv) > 2 else wait_url
    deadline = time.monotonic() + 90

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(wait_url, timeout=2) as response:
                if response.status < 500:
                    break
        except (OSError, urllib.error.HTTPError):
            time.sleep(1)

    webbrowser.open(open_url)


if __name__ == '__main__':
    main()
