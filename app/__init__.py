from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import timedelta
import os

try:
    from flask_compress import Compress
    _compress = Compress()
except ImportError:
    _compress = None

db = SQLAlchemy()

def create_app():
    """Initialize Flask app, database, and register Blueprints."""
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY")
    # Detect environment for correct DB connection.
    # app.py sets USE_TEST_DB=1 so dev hits PyOrchestrator_Test; wsgi.py doesn't,
    # so prod stays on the live OpenOrchestrator DB.
    USE_TEST_DB = 0

    if USE_TEST_DB:
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('OpenOrchestratorTestSQL')
        print("[FlaskOrchestrator] Using TEST database: PyOrchestrator_Test")
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('OpenOrchestratorSQL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Cache /static/* in the browser for 1 day. Bump or version filenames after a
    # static asset change if users see stale CSS/JS.
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = timedelta(days=1)

    # Gzip HTML / JSON / CSS / JS responses if Flask-Compress is installed.
    # Cuts the home + stats + logs pages down to ~20-40% of their size on the wire.
    if _compress is not None:
        _compress.init_app(app)

    db.init_app(app)

    with app.app_context():
        from app.database import initialize_database
        initialize_database()  # Load models dynamically

    # Import and register Blueprints
    from app.routes import main, logs, queues, triggers, credentials, constants, schedulers, jobs, stats
    app.register_blueprint(main.bp)
    app.register_blueprint(logs.bp)
    app.register_blueprint(queues.bp)
    app.register_blueprint(triggers.bp)
    app.register_blueprint(credentials.bp)
    app.register_blueprint(constants.bp)
    app.register_blueprint(schedulers.bp)
    app.register_blueprint(jobs.bp)
    app.register_blueprint(stats.bp)

    return app
