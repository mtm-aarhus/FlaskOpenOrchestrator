from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

db = SQLAlchemy()

def create_app():
    """Initialize Flask app, database, and register Blueprints."""
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY")
    # Detect environment for correct DB connection
    USE_SQLITE = False  

    if USE_SQLITE:
        SQLITE_DB_PATH = os.path.join(os.getcwd(), "pyorchestrator_test.db")
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{SQLITE_DB_PATH}'
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('OpenOrchestratorSQL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        from app.database import initialize_database
        initialize_database()  # Load models dynamically

    # Import and register Blueprints
    from app.routes import main, logs, queues, triggers, credentials, constants, schedulers
    app.register_blueprint(main.bp)
    app.register_blueprint(logs.bp)
    app.register_blueprint(queues.bp)
    app.register_blueprint(triggers.bp)
    app.register_blueprint(credentials.bp)
    app.register_blueprint(constants.bp) 
    app.register_blueprint(schedulers.bp)

    return app
