from flask import Flask,render_template,redirect,request,url_for,flash
from flask_sqlalchemy import SQLAlchemy
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'hira04'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///parking.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['CHART_FOLDER'] = os.path.join(app.static_folder, 'charts')
    os.makedirs(app.config['CHART_FOLDER'], exist_ok=True)
    app.config['PASSWORD_HASH'] = 'hira04' 
    db.init_app(app)

    return app 


db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'user'
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
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', password=generate_password_hash('hira04'), fullname='Admin User', address='Admin Address', pincode='123456')
        db.session.add(admin)
        db.session.commit()

app = create_app()
app.app_context().push()
with app.app_context():
    db.create_all()
    create_admin()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        print(username, password)
        user = User.query.filter_by(username=username).first()
        if user :
            if not check_password_hash(user.password, password):
                flash('Invalid credentials')
                return redirect(url_for('login'))
            if user.username == 'admin':
                session['username'] = user.username
                return redirect(url_for('admin'))
            else:
                session['username'] = user.username
                session['user_id'] = user.id
                return redirect(url_for('user'))
                
    return render_template('login.html', error='Invalid credentials')

@app.route('/signup', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        fullname = request.form['fullname']
        address = request.form['address']
        pincode = request.form['pincode']

        new_user = User(username=username, password=generate_password_hash(password), fullname=fullname, address=address, pincode=pincode)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/user', methods=['GET', 'POST'])
def user():
    if 'username' not in session:
        return redirect(url_for('login'))
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
def parkings():
    if 'username' not in session:
        return redirect(url_for('login'))
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
def add_spots():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        location_name = request.form['location_name']
        address = request.form['address']
        pincode = request.form['pincode']
        price = request.form['price']
        number_of_slots = int(request.form['number_of_slots'])

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
def modify_parking(parking_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    parking = Parking.query.get_or_404(parking_id)
    if request.method == 'POST':
        parking.location_name = request.form['location_name']
        parking.address = request.form['address']
        parking.pincode = request.form['pincode']
        parking.price = request.form['price']
        new_number_of_slots = int(request.form['number_of_slots'])
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
        db.session.commit()
        return redirect(url_for('parkings'))
    return render_template('modify_parking.html', parking=parking)

@app.route('/available_occupied/<int:spot_id>')
def available_occupied(spot_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    spot = parkingSpot.query.get_or_404(spot_id)
    return render_template('available_occupied.html', spot=spot)

@app.route('/spot_detail/<int:spot_id>')
def spot_detail(spot_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    spot = parkingSpot.query.get_or_404(spot_id)
    return render_template('spot_detail.html', spot=spot)


@app.route('/remove_spot/<int:spot_id>', methods=['GET','POST'])
def remove_spot(spot_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    spot = parkingSpot.query.get_or_404(spot_id)
    if spot.status == 'O':
        flash('Cannot delete occupied spot.', 'error')
        return redirect(url_for('parkings'))
    db.session.delete(spot)
    db.session.commit()
    return redirect(url_for('parkings'))

@app.route('/remove_parking/<int:parking_id>', methods=['GET','POST'])
def remove_parking(parking_id):
    if 'username' not in session :
        return redirect(url_for('login'))
    parking = Parking.query.get_or_404(parking_id)
    if parking.spots:
        for spot in parking.spots:
            if spot.status == 'O':
                flash('Cannot delete parking with current booked spots.' , 'error')
                return redirect(url_for('parkings'))
            db.session.delete(spot)
    db.session.delete(parking)
    db.session.commit()
    return redirect(url_for('parkings'))

@app.route('/reserve_spot/<int:parking_id>', methods=['GET', 'POST'])
def reserve_spot(parking_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    parking = Parking.query.filter_by(id=parking_id).first()
    if not parking:
        return redirect(url_for('user'))

    if request.method == 'POST':
        vehicle_number = request.form['vehicle_number']
       
        user_id = session['user_id']
        available_spot = parkingSpot.query.filter_by(parking_id=parking_id, status='A').first()
        if not available_spot:
            flash('No available spots for this parking.', 'error')
            return redirect(url_for('user'))
        available_spot.status = 'O'
        booking = Booking( user_id=user_id, vehicle_number=vehicle_number, spot_id=available_spot.id, start_time=datetime.now())
        db.session.add(booking)
        db.session.commit()
        return redirect(url_for('booking_details', parking_id=parking_id))
    return render_template('reserve_spot.html', parking_id=parking_id, parking=parking, user_id=session['user_id'])

@app.route('/booking_details/<int:parking_id>')
def booking_details(parking_id):
    if 'username' not in session:
        return redirect(url_for('login'))

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
def records():
    if 'username' not in session:
        return redirect(url_for('login'))
    bookings = Booking.query.filter_by(user_id=session['user_id']).all()
    return render_template('records.html', bookings=bookings) 

@app.route('/release/<int:booking_id>', methods=['GET', 'POST'])
def release(booking_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    booking = Booking.query.get_or_404(booking_id)
    simulated_end_time = datetime.now()
    time_span = simulated_end_time - booking.start_time
    time_in_hours = time_span.total_seconds() / 3600
    estimated_cost = max(round(time_in_hours * booking.spot.parking.price, 2), 20)

    return render_template('release.html', booking=booking,simulated_end_time=simulated_end_time,estimated_cost=estimated_cost)
    

@app.route('/end_booking/<int:booking_id>', methods=['GET', 'POST'])
def end_booking(booking_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    booking = Booking.query.get_or_404(booking_id)
    if booking.end_time:
        flash('Booking already ended.', 'error')
        return redirect(url_for('records'))

    booking.end_time = datetime.now()
    time_span = booking.end_time - booking.start_time
    time_in_hours = int(time_span.total_seconds() // 3600)
    booking.parking_cost = max(round(time_in_hours * booking.spot.parking.price, 2), 20)
    booking.spot.status = 'A'  
    booking.status = 'Released'
    db.session.commit()
    return redirect(url_for('records'))
    


@app.route('/admin_user_management', methods=['GET', 'POST'])
def admin_user_management():
    if 'username' not in session:
        return redirect(url_for('login'))

    users = User.query.filter(User.username != 'admin').all()

    user_status = {}
    for user in users:
        active_booking = Booking.query.filter_by(user_id=user.id, end_time=None).first()
        user_status[user.id] = 'active' if active_booking else 'inactive'

    return render_template('user_management.html', users=users, user_status=user_status)




@app.route('/delete_user/<int:user_id>', methods=['GET', 'POST'])
def delete_user(user_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
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
def summary():
    if 'username' not in session:
        return redirect(url_for('login'))
    
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
    plt.figure(figsize=(10, 6))
    plt.bar(x=slots_name, height=slots_available_count, color='green', label='Available Slots')
    plt.bar(x=slots_name, height=slots_occupied_count, color='red', label='Occupied Slots', bottom=slots_available_count)
    plt.xlabel('Parking Locations')
    plt.ylabel('Number of Slots')
    plt.title('Parking Slot Availability')
    plt.legend()
    plt.tight_layout()
    chart_path = os.path.join(app.config['CHART_FOLDER'], 'bar_chart.png')
    plt.savefig(chart_path)
    plt.close()

    # Create pie chart for revenue generated
    plt.figure(figsize=(10, 6))
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
    revenue_chart_path = os.path.join(app.config['CHART_FOLDER'], 'pie_chart.png')
    plt.savefig(revenue_chart_path)
    plt.close()

    bar_chart_url = url_for('static', filename='charts/bar_chart.png',v = datetime.now())
    pie_chart_url = url_for('static', filename='charts/pie_chart.png',v = datetime.now())
    return render_template('summary.html', 
                           bar_chart_url=bar_chart_url, 
                           pie_chart_url=pie_chart_url,
                           slots_name=slots_name,
                           slots_available_count=slots_available_count,
                           slots_occupied_count=slots_occupied_count,
                           revenue_generated=revenue_generated)


@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    if session['username'] == 'admin':
        return redirect(url_for('admin'))
    else:
        return render_template('dashboard.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = User.query.filter_by(username=session['username']).first()
    if request.method == 'POST':
        user.username = request.form['username']
        user.fullname = request.form['fullname']
        user.address = request.form['address']
        user.pincode = request.form['pincode']
        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('profile'))
    return render_template('edit_profile.html', user=user)




if __name__ == '__main__':
    app.run(debug=True)





