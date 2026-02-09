from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    household_id = db.Column(db.String(50), nullable=False)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.String(50))
    unit_price = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, default=0.0)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    bought = db.Column(db.Boolean, default=False)
    is_draft = db.Column(db.Boolean, default=True)
    is_archived = db.Column(db.Boolean, default=False)
    household_id = db.Column(db.String(50), nullable=False)

class CatalogItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    last_unit_price = db.Column(db.Float)
    frequency = db.Column(db.Integer, default=1)
    household_id = db.Column(db.String(50), nullable=False)

class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(db.String(50), unique=True)
    monthly_limit = db.Column(db.Float, default=0.0)
    trip_limit = db.Column(db.Float, default=0.0)