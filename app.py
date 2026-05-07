import os

# Dev entry point. Anything imported via wsgi.py won't see this, so prod stays on prod DB.
os.environ.setdefault("USE_TEST_DB", "0")

from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
