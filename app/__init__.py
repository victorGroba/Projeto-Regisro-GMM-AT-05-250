from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'sua-chave-secreta'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///temperatura.db'
    db.init_app(app)
    Migrate(app, db)

    from . import routes
    app.register_blueprint(routes.bp)

    return app
