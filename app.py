from flask import Flask,render_template,redirect,request,url_for,flash,abort,g
from flask_sqlalchemy import SQLAlchemy
from flask import session
from flask_wtf.csrf import CSRFProtect, CSRFError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv
import base64
import hashlib
import io
import math
import os
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

load_dotenv()

MIN_CHARGE = 20
MAX_ACTIVE_BOOKINGS = 3

def debug_mode():
    return os.environ.get('FLASK_DEBUG') == '1'

def create_app():
    app = Flask(__name__)
    secret_key = os.environ.get('SECRET_KEY', '')
    if len(secret_key) < 32:
        if not debug_mode():
            raise RuntimeError('SECRET_KEY must be set to a random string of at least 32 characters. Copy .env.example to .env and fill it in.')
        # Local debug runs only: sessions reset whenever the app restarts
        secret_key = os.urandom(32).hex()
    app.config['SECRET_KEY'] = secret_key
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    # Set SESSION_COOKIE_SECURE=1 when the app is served over HTTPS
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE') == '1'
    database_url = os.environ.get('DATABASE_URL') or 'sqlite:///parking.db'
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # The CSRF token is tied to the session, so it does not need its own expiry
    app.config['WTF_CSRF_TIME_LIMIT'] = None
    db.init_app(app)
    csrf.init_app(app)

    return app


db = SQLAlchemy()
csrf = CSRFProtect()

class User(db.Model):
    __tablename__ = 'user'
    __table_args__ = {'sqlite_autoincrement': True}
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    fullname = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(150), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)

    booking= db.relationship('Booking', back_populates='user', cascade='all, delete-orphan')

class Parking(db.Model):
    __tablename__ = 'parking'
    id = db.Column(db.Integer, primary_key=True)
    location_name = db.Column(db.String(150),unique=True, nullable=False)
    address = db.Column(db.String(150), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)
    price = db.Column(db.Float, nullable=False)
    number_of_slots = db.Column(db.Integer, nullable=False)

    spots = db.relationship('parkingSpot', back_populates='parking', cascade='all, delete-orphan')

class parkingSpot(db.Model):
    __tablename__ = 'parking_spot'
    id = db.Column(db.Integer, primary_key=True)
    parking_id = db.Column(db.Integer, db.ForeignKey('parking.id'), nullable=False)
    slot_number = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(10), nullable=False, default='A')

    parking = db.relationship('Parking', back_populates='spots')
    booking = db.relationship('Booking', back_populates='spot', cascade='all, delete-orphan')

class Booking(db.Model):
    __tablename__ = 'booking'
    __table_args__ = {'sqlite_autoincrement': True}
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spot.id'), nullable=False)
    vehicle_number = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(10), nullable=False, default='O')
    parking_cost = db.Column(db.Float)

    user= db.relationship('User', back_populates='booking')
    spot= db.relationship('parkingSpot', back_populates='booking')

def create_admin():
    admin_password = os.environ.get('ADMIN_PASSWORD', '')
    admin = User.query.filter_by(username='admin').first()
    if len(admin_password) < 8:
        if not debug_mode():
            raise RuntimeError('ADMIN_PASSWORD must be set (at least 8 characters). Copy .env.example to .env and fill it in.')
        if admin:
            # Lock the existing admin so no old password keeps working
            admin.password = generate_password_hash(os.urandom(32).hex())
            db.session.commit()
        print('ADMIN_PASSWORD is not set, so the admin account is locked. Set it in .env and restart.')
        return
    if not admin:
        admin = User(username='admin', password=generate_password_hash(admin_password), fullname='Admin User', address='Admin Address', pincode='123456')
        db.session.add(admin)
        db.session.commit()
    elif not check_password_hash(admin.password, admin_password):
        # Keep the admin password in sync with ADMIN_PASSWORD (replaces old passwords)
        admin.password = generate_password_hash(admin_password)
        db.session.commit()

def username_taken(username, exclude_id=None):
    if username.lower() == 'admin':
        return True
    query = User.query.filter(func.lower(User.username) == username.lower())
    if exclude_id is not None:
        query = query.filter(User.id != exclude_id)
    return query.first() is not None

def valid_lot_numbers(price, number_of_slots):
    return math.isfinite(price) and price >= 0 and number_of_slots >= 1

def parking_cost(start_time, end_time, price_per_hour):
    hours = (end_time - start_time).total_seconds() / 3600
    return max(round(hours * price_per_hour, 2), MIN_CHARGE)

def chart_data_uri(fig):
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png')
    plt.close(fig)
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')

def password_fingerprint(user):
    """Short hash of the stored password hash. Changes whenever the password changes."""
    return hashlib.sha256(user.password.encode()).hexdigest()[:16]

def start_session(user):
    session.clear()
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth'] = password_fingerprint(user)

def load_current_user():
    """Return the logged-in User, or None. Clears sessions whose user no longer matches."""
    if 'current_user' in g:
        return g.current_user
    user = None
    user_id = session.get('user_id')
    if user_id is not None:
        user = db.session.get(User, user_id)
        if (user is None or user.username != session.get('username')
                or session.get('auth') != password_fingerprint(user)):
            session.clear()
            user = None
    g.current_user = user
    return user

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not load_current_user():
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = load_current_user()
        if not user:
            return redirect(url_for('login'))
        if user.username != 'admin':
            flash('That page is only for the admin.', 'error')
            return redirect(url_for('user'))
        return view(*args, **kwargs)
    return wrapped

def user_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = load_current_user()
        if not user:
            return redirect(url_for('login'))
        if user.username == 'admin':
            return redirect(url_for('admin'))
        return view(*args, **kwargs)
    return wrapped

app = create_app()
with app.app_context():
    db.create_all()
    create_admin()

@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    flash('Your form expired. Please try again.', 'error')
    return redirect(request.referrer or url_for('login'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        # trim() also matches older accounts saved with stray spaces
        user = User.query.filter(func.trim(User.username) == username).first()
        if not user or not check_password_hash(user.password, password):
            flash('Invalid username or password.', 'error')
            return redirect(url_for('login'))
        start_session(user)
        if user.username == 'admin':
            return redirect(url_for('admin'))
        return redirect(url_for('user'))

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        fullname = request.form['fullname'].strip()
        address = request.form['address'].strip()
        pincode = request.form['pincode'].strip()

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('register'))
        if not (fullname and address and pincode):
            flash('Please fill in all the fields.', 'error')
            return redirect(url_for('register'))
        if not username or username_taken(username):
            flash('That username is already taken.', 'error')
            return redirect(url_for('register'))
        new_user = User(username=username, password=generate_password_hash(password), fullname=fullname, address=address, pincode=pincode)
        db.session.add(new_user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('That username is already taken.', 'error')
            return redirect(url_for('register'))
        flash('Account created. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    return render_template('admin.html')

@app.route('/user', methods=['GET', 'POST'])
@user_required
def user():
    query = request.args.get('query')
    if query:
        parkings = [p for p in Parking.query.all() if query.lower() in p.location_name.lower() or query.lower() in p.address.lower() or query in p.pincode]
    else:
        parkings = Parking.query.all()
    available_spots = {}
    for parking in parkings:
        available_spots[parking.id] = parkingSpot.query.filter_by(parking_id=parking.id, status='A').count()
    return render_template('user.html', parkings=parkings, available_spots=available_spots)

@app.route('/parkings' , methods=['GET', 'POST'])
@admin_required
def parkings():
    available_spots_count = {}
    total_spots_count = {}
    query = request.args.get('query')
    
    if query:
        parking = [p for p in Parking.query.all() if query.lower() in p.location_name.lower() or query.lower() in p.address.lower() or query in p.pincode]

    else:
        parking = Parking.query.all()
    for park in parking:
        available_spots_count[park.id] = parkingSpot.query.filter_by(parking_id=park.id, status='A').count()
        total_spots_count[park.id] = parkingSpot.query.filter_by(parking_id=park.id).count()
    return render_template('parkings.html', parking=parking, available_spots_count=available_spots_count, total_spots_count=total_spots_count)
    
@app.route('/add_spots', methods=['GET', 'POST'])
@admin_required
def add_spots():
    if request.method == 'POST':
        location_name = request.form['location_name'].strip()
        address = request.form['address']
        pincode = request.form['pincode']
        try:
            price = float(request.form['price'])
            number_of_slots = int(request.form['number_of_slots'])
        except ValueError:
            flash('Price and number of slots must be numbers.', 'error')
            return redirect(url_for('add_spots'))
        if not valid_lot_numbers(price, number_of_slots):
            flash('Price must be a non-negative number and a lot needs at least 1 slot.', 'error')
            return redirect(url_for('add_spots'))
        if Parking.query.filter_by(location_name=location_name).first():
            flash('A parking lot with that name already exists.', 'error')
            return redirect(url_for('add_spots'))

        new_parking = Parking(location_name=location_name, address=address, pincode=pincode, price=price, number_of_slots=number_of_slots)
        db.session.add(new_parking)
        db.session.flush()
        for i in range(1, number_of_slots + 1):
            new_spot = parkingSpot(parking_id=new_parking.id, slot_number=i, status='A')
            db.session.add(new_spot)
        db.session.commit()
        return redirect(url_for('parkings'))
    return render_template('add_spots.html')

@app.route('/modify_parking/<int:parking_id>', methods=['GET', 'POST'])
@admin_required
def modify_parking(parking_id):
    parking = Parking.query.get_or_404(parking_id)
    if request.method == 'POST':
        try:
            new_price = float(request.form['price'])
            new_number_of_slots = int(request.form['number_of_slots'])
        except ValueError:
            flash('Price and number of slots must be numbers.', 'error')
            return redirect(url_for('modify_parking', parking_id=parking.id))
        if not valid_lot_numbers(new_price, new_number_of_slots):
            flash('Price must be a non-negative number and a lot needs at least 1 slot.', 'error')
            return redirect(url_for('modify_parking', parking_id=parking.id))
        new_name = request.form['location_name'].strip()
        if Parking.query.filter(Parking.location_name == new_name, Parking.id != parking.id).first():
            flash('A parking lot with that name already exists.', 'error')
            return redirect(url_for('modify_parking', parking_id=parking.id))
        parking.location_name = new_name
        parking.address = request.form['address']
        parking.pincode = request.form['pincode']
        parking.price = new_price
        present_spots = {int(spot.slot_number): spot for spot in parking.spots}
        # Add new spots if increased
        for i in range(1, new_number_of_slots + 1):
            if i not in present_spots:
                spot = parkingSpot(parking_id=parking.id, slot_number=str(i), status='A')
                db.session.add(spot)
        # Remove spots if decreased (only if not booked and available)
        for i in range(new_number_of_slots + 1, parking.number_of_slots + 1):
            spot = present_spots.get(i)
            if spot:
                previous_data = Booking.query.filter_by(spot_id=spot.id).first()
                if spot.status == 'A' and not previous_data:
                    db.session.delete(spot)
        parking.number_of_slots = new_number_of_slots
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('A parking lot with that name already exists.', 'error')
            return redirect(url_for('modify_parking', parking_id=parking_id))
        return redirect(url_for('parkings'))
    return render_template('modify_parking.html', parking=parking)

@app.route('/available_occupied/<int:spot_id>')
@admin_required
def available_occupied(spot_id):
    spot = parkingSpot.query.get_or_404(spot_id)
    return render_template('available_occupied.html', spot=spot)

@app.route('/spot_detail/<int:spot_id>')
@admin_required
def spot_detail(spot_id):
    spot = parkingSpot.query.get_or_404(spot_id)
    return render_template('spot_detail.html', spot=spot)


@app.route('/remove_spot/<int:spot_id>', methods=['POST'])
@admin_required
def remove_spot(spot_id):
    spot = parkingSpot.query.get_or_404(spot_id)
    if spot.status == 'O':
        flash('Cannot delete occupied spot.', 'error')
        return redirect(url_for('parkings'))
    db.session.delete(spot)
    db.session.commit()
    return redirect(url_for('parkings'))

@app.route('/remove_parking/<int:parking_id>', methods=['POST'])
@admin_required
def remove_parking(parking_id):
    parking = Parking.query.get_or_404(parking_id)
    if any(spot.status == 'O' for spot in parking.spots):
        flash('Cannot delete parking with current booked spots.' , 'error')
        return redirect(url_for('parkings'))
    # Spots (and their bookings) are removed by the cascade on Parking.spots
    db.session.delete(parking)
    db.session.commit()
    return redirect(url_for('parkings'))

@app.route('/reserve_spot/<int:parking_id>', methods=['GET', 'POST'])
@user_required
def reserve_spot(parking_id):
    parking = Parking.query.filter_by(id=parking_id).first()
    if not parking:
        return redirect(url_for('user'))

    if request.method == 'POST':
        vehicle_number = request.form['vehicle_number'].strip().upper()
        if not vehicle_number:
            flash('Please enter a vehicle number.', 'error')
            return redirect(url_for('reserve_spot', parking_id=parking_id))

        user_id = session['user_id']
        active_bookings = Booking.query.filter_by(user_id=user_id, end_time=None)
        if active_bookings.count() >= MAX_ACTIVE_BOOKINGS:
            flash(f'You can have at most {MAX_ACTIVE_BOOKINGS} active bookings. Release one first.', 'error')
            return redirect(url_for('records'))
        if active_bookings.filter_by(vehicle_number=vehicle_number).first():
            flash('That vehicle is already parked.', 'error')
            return redirect(url_for('records'))

        available_spot = parkingSpot.query.filter_by(parking_id=parking_id, status='A').first()
        if not available_spot:
            flash('No available spots for this parking.', 'error')
            return redirect(url_for('user'))
        # Claim the spot only if it is still free, so two requests cannot book the same spot
        claimed = parkingSpot.query.filter_by(id=available_spot.id, status='A').update({'status': 'O'})
        if not claimed:
            db.session.rollback()
            flash('That spot was just taken. Please try again.', 'error')
            return redirect(url_for('reserve_spot', parking_id=parking_id))
        booking = Booking( user_id=user_id, vehicle_number=vehicle_number, spot_id=available_spot.id, start_time=datetime.now())
        db.session.add(booking)
        db.session.commit()
        return redirect(url_for('booking_details', parking_id=parking_id))
    return render_template('reserve_spot.html', parking_id=parking_id, parking=parking, user_id=session['user_id'])

@app.route('/booking_details/<int:parking_id>')
@user_required
def booking_details(parking_id):

    booking = Booking.query.join(parkingSpot).filter(
        Booking.user_id == session['user_id'],
        parkingSpot.parking_id == parking_id,
        Booking.spot_id == parkingSpot.id,
        Booking.end_time == None
    ).first()

    if not booking:
        flash('No active booking found.', 'error')
        return redirect(url_for('user'))

    return render_template('booking_details.html', booking=booking)


@app.route('/records', methods=['GET', 'POST'])
@user_required
def records():
    bookings = Booking.query.filter_by(user_id=session['user_id']).all()
    return render_template('records.html', bookings=bookings) 

@app.route('/release/<int:booking_id>', methods=['GET', 'POST'])
@user_required
def release(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != session['user_id']:
        abort(404)
    if booking.end_time:
        flash('Booking already ended.', 'error')
        return redirect(url_for('records'))
    simulated_end_time = datetime.now()
    estimated_cost = parking_cost(booking.start_time, simulated_end_time, booking.spot.parking.price)

    return render_template('release.html', booking=booking,simulated_end_time=simulated_end_time,estimated_cost=estimated_cost)


@app.route('/end_booking/<int:booking_id>', methods=['POST'])
@user_required
def end_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != session['user_id']:
        abort(404)
    if booking.end_time:
        flash('Booking already ended.', 'error')
        return redirect(url_for('records'))

    booking.end_time = datetime.now()
    booking.parking_cost = parking_cost(booking.start_time, booking.end_time, booking.spot.parking.price)
    booking.spot.status = 'A'  
    booking.status = 'Released'
    db.session.commit()
    return redirect(url_for('records'))
    


@app.route('/admin_user_management', methods=['GET', 'POST'])
@admin_required
def admin_user_management():

    users = User.query.filter(User.username != 'admin').all()

    user_status = {}
    for user in users:
        active_booking = Booking.query.filter_by(user_id=user.id, end_time=None).first()
        user_status[user.id] = 'active' if active_booking else 'inactive'

    return render_template('user_management.html', users=users, user_status=user_status)




@app.route('/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    
    user = User.query.get_or_404(user_id)

    if user.username == 'admin':
        flash('Cannot delete admin user.', 'error')
        return redirect(url_for('admin_user_management'))

    # Check active bookings
    active_booking = Booking.query.filter_by(user_id=user.id, end_time=None).first()
    if active_booking:
        flash('Cannot delete user with active bookings.', 'error')
        return redirect(url_for('admin_user_management'))

    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully.', 'success')
    return redirect(url_for('admin_user_management'))

@app.route('/summary', methods=['GET', 'POST'])
@admin_required
def summary():
    
    slots = Parking.query.order_by(Parking.location_name).all()
    slots_name=[]
    slots_available_count = []
    slots_occupied_count = []
    revenue_generated = []
    for slot in slots:
        slots_name.append(slot.location_name)
        slots_available_count.append(parkingSpot.query.filter_by(parking_id=slot.id, status='A').count())
        slots_occupied_count.append(parkingSpot.query.filter_by(parking_id=slot.id, status='O').count())
        
        # Calculate total revenue for this parking location
        total_revenue = 0
        for spot in slot.spots:
            for book in spot.booking:
                if book.parking_cost is not None:
                    total_revenue += book.parking_cost
        revenue_generated.append(total_revenue)
    
    # Create bar chart
    bar_fig = plt.figure(figsize=(10, 6))
    plt.bar(x=slots_name, height=slots_available_count, color='green', label='Available Slots')
    plt.bar(x=slots_name, height=slots_occupied_count, color='red', label='Occupied Slots', bottom=slots_available_count)
    plt.xlabel('Parking Locations')
    plt.ylabel('Number of Slots')
    plt.title('Parking Slot Availability')
    plt.legend()
    plt.tight_layout()
    bar_chart_url = chart_data_uri(bar_fig)

    # Create pie chart for revenue generated
    pie_fig = plt.figure(figsize=(10, 6))
    # Only show locations with revenue
    revenue_labels = []
    revenue_values = []
    for i, revenue in enumerate(revenue_generated):
        if revenue > 0:
            revenue_labels.append(slots_name[i])
            revenue_values.append(revenue)
    
    if revenue_values:  # Only create pie chart if there's revenue data
        plt.pie(revenue_values, labels=revenue_labels, autopct='%1.1f%%')
        plt.title('Revenue Generated by Parking Locations')
    else:
        plt.text(0.5, 0.5, 'No revenue data available', ha='center', va='center', transform=plt.gca().transAxes)
        plt.title('Revenue Generated by Parking Locations')
    
    plt.tight_layout()
    pie_chart_url = chart_data_uri(pie_fig)

    return render_template('summary.html', 
                           bar_chart_url=bar_chart_url, 
                           pie_chart_url=pie_chart_url,
                           slots_name=slots_name,
                           slots_available_count=slots_available_count,
                           slots_occupied_count=slots_occupied_count,
                           revenue_generated=revenue_generated)


@app.route('/dashboard')
@login_required
def dashboard():
    if load_current_user().username == 'admin':
        return redirect(url_for('admin'))
    else:
        return render_template('dashboard.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = load_current_user()
    if request.method == 'POST':
        new_username = request.form['username'].strip()
        if new_username != user.username:
            if user.username == 'admin':
                flash('The admin username cannot be changed.', 'error')
                return redirect(url_for('profile'))
            if not new_username or username_taken(new_username, exclude_id=user.id):
                flash('That username is already taken.', 'error')
                return redirect(url_for('profile'))
        user.username = new_username
        user.fullname = request.form['fullname']
        user.address = request.form['address']
        user.pincode = request.form['pincode']
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('That username is already taken.', 'error')
            return redirect(url_for('profile'))
        session['username'] = user.username
        flash('Profile updated successfully', 'success')
        return redirect(url_for('profile'))
    return render_template('edit_profile.html', user=user)


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')





