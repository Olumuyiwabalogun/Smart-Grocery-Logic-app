import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from models import db, User, Expense, CatalogItem, Budget

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///groceries.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@app.before_request
def create_tables():
    if not hasattr(app, '_db_initialized'):
        db.create_all()
        app._db_initialized = True

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- THE FULL MASTER CATALOG ---
MASTER_CATALOG = {
    "Grains & Tubers": ["Rice", "Beans", "Yam", "Garlic", "Potatoes", "Pasta", "Semovita", "Garri", "Noodles"],
    "Proteins": ["Beef", "Chicken", "Eggs", "Fish", "Turkey", "Pork"],
    "Veggies & Fruits": ["Onions", "Tomato", "Pepper", "Carrot", "Cabbage", "Spinach", "Banana", "Apple"],
    "Pantry & Spices": ["Salt", "Sugar", "Vegetable Oil", "Palm Oil", "Maggi", "Curry", "Thyme", "Butter"],
    "Household": ["Soap", "Tissue", "Detergent", "Bleach", "Bulbs"]
}

@app.route('/')
@login_required
def index():
    hid = current_user.household_id
    budget_obj = Budget.query.filter_by(household_id=hid).first()
    trip_limit = budget_obj.trip_limit if budget_obj else 0.0
    
    # 1. PREDICTIVE LOGIC
    all_master = [item for sub in MASTER_CATALOG.values() for item in sub]
    user_history = [item.name for item in CatalogItem.query.filter_by(household_id=hid).all()]
    suggestions = list(set(all_master + user_history))
    
    # 2. QUICK PICKS
    quick_picks = CatalogItem.query.filter_by(household_id=hid).order_by(CatalogItem.frequency.desc()).limit(8).all()
    
    # 3. METER & LIST LOGIC
    checklist_active = Expense.query.filter_by(household_id=hid, is_draft=False, is_archived=False).all()
    to_buy = [i for i in checklist_active if not i.bought]
    bought_this_trip = [i for i in checklist_active if i.bought]
    
    trip_spent = sum(item.total_price for item in bought_this_trip)
    trip_remaining = trip_limit - trip_spent
    trip_percent = (trip_spent / trip_limit * 100) if trip_limit > 0 else 0
    
    drafts = Expense.query.filter_by(household_id=hid, is_draft=True).all()
    draft_total = sum(d.total_price for d in drafts)

    return render_template('add_item.html', 
                           checklist=to_buy, bought_items=bought_this_trip,
                           trip_spent=trip_spent, trip_limit=trip_limit,
                           trip_percent=round(trip_percent), trip_remaining=trip_remaining,
                           drafts=drafts, draft_total=draft_total, suggestions=suggestions,
                           quick_picks=quick_picks, master_catalog=MASTER_CATALOG, hid=hid)

@app.route('/add', methods=['POST'])
@login_required
def add():
    name = request.form.get('item_name', '').strip().title()
    if not name:
        return redirect(url_for('index'))

    qty_str = request.form.get('quantity') or "1"
    price = float(request.form.get('cost') or 0)
    hid = current_user.household_id
    
    try:
        total = float(qty_str) * price
    except ValueError:
        total = price

    cat_item = CatalogItem.query.filter_by(name=name, household_id=hid).first()
    if cat_item:
        cat_item.frequency += 1
        cat_item.last_unit_price = price
    else:
        db.session.add(CatalogItem(name=name, household_id=hid, last_unit_price=price))
        
    db.session.add(Expense(item_name=name, quantity=qty_str, unit_price=price, total_price=total, household_id=hid, is_draft=True))
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    hid = current_user.household_id
    budget_obj = Budget.query.filter_by(household_id=hid).first()
    m_limit = budget_obj.monthly_limit if budget_obj else 0.0
    
    total_monthly = db.session.query(func.sum(Expense.total_price)).filter_by(
        household_id=hid, bought=True).filter(
        Expense.date_added >= datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    ).scalar() or 0
    
    m_percent = round((total_monthly / m_limit * 100), 1) if m_limit > 0 else 0
    
    top_item = Expense.query.filter_by(household_id=hid, bought=True).order_by(Expense.unit_price.desc()).first()
    frequent = CatalogItem.query.filter_by(household_id=hid).order_by(CatalogItem.frequency.desc()).limit(3).all()
    
    return render_template('dashboard.html', total=total_monthly, m_limit=m_limit, 
                           m_percent=m_percent, top_item=top_item, frequent=frequent)

@app.route('/toggle/<int:id>')
@login_required
def toggle(id):
    item = Expense.query.get_or_404(id)
    if item.household_id == current_user.household_id:
        item.bought = not item.bought
        item.is_draft = False 
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/ready_to_shop')
@login_required
def ready_to_shop():
    Expense.query.filter_by(household_id=current_user.household_id, is_draft=True).update({"is_draft": False})
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/end_trip')
@login_required
def end_trip():
    Expense.query.filter_by(household_id=current_user.household_id, bought=True, is_archived=False).update({"is_archived": True})
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    hid = current_user.household_id
    budget_obj = Budget.query.filter_by(household_id=hid).first()
    if request.method == 'POST':
        m_lim = request.form.get('monthly_limit')
        t_lim = request.form.get('trip_limit')
        if budget_obj:
            budget_obj.monthly_limit = float(m_lim or 0)
            budget_obj.trip_limit = float(t_lim or 0)
        else:
            db.session.add(Budget(household_id=hid, monthly_limit=float(m_lim or 0), trip_limit=float(t_lim or 0)))
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('settings.html', budget=budget_obj)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        hid = email.split('@')[0]
        if not User.query.filter_by(email=email).first():
            db.session.add(User(email=email, password=generate_password_hash(pwd), household_id=hid))
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/history')
@login_required
def history():
    past = Expense.query.filter_by(household_id=current_user.household_id, bought=True).order_by(Expense.date_added.desc()).all()
    return render_template('history.html', history=past)

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    item = Expense.query.get_or_404(id)
    if item.household_id == current_user.household_id:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)