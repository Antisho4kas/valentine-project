from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import random
import string
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    username_lower = db.Column(db.String(80), unique=True, nullable=False)  # для поиска без учета регистра
    password = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.String(10), unique=True, nullable=False)
    received_valentines = db.relationship('Valentine', backref='recipient', lazy=True, foreign_keys='Valentine.recipient_id')
    sent_valentines = db.relationship('Valentine', backref='sender', lazy=True, foreign_keys='Valentine.sender_id')

class Valentine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(200), nullable=False, default='static/basevalentine.jpg')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

def generate_user_id():
    while True:
        user_id = ''.join(random.choices(string.digits, k=10))
        if not User.query.filter_by(user_id=user_id).first():
            return user_id

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

with app.app_context():
    db.create_all()
    users = User.query.filter_by(user_id=None).all()
    for user in users:
        user.user_id = generate_user_id()
    db.session.commit()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Проверяем существование пользователя без учета регистра
        if User.query.filter_by(username_lower=username.lower()).first():
            flash('Это имя пользователя уже занято')
            return redirect(url_for('register'))
        
        user_id = generate_user_id()
        hashed_password = generate_password_hash(password)
        new_user = User(
            username=username,
            username_lower=username.lower(),
            password=hashed_password,
            user_id=user_id
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Регистрация успешна!')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Ищем пользователя без учета регистра
        user = User.query.filter_by(username_lower=username.lower()).first()
        
        if user and check_password_hash(user.password, password):
            session['username'] = user.username  # Сохраняем оригинальный username
            session['user_id'] = user.user_id
            session['user_db_id'] = user.id
            return redirect(url_for('valentine'))
        else:
            flash('Неверное имя пользователя или пароль')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/valentine')
def valentine():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = User.query.filter_by(username=session['username']).first()
    active_tab = request.args.get('tab', 'create')
    received_valentines = Valentine.query.filter_by(recipient_id=user.id).all()
    return render_template('valentine.html', 
                         username=session['username'], 
                         user_id=user.user_id,
                         active_tab=active_tab,
                         received_valentines=received_valentines)

@app.route('/send_valentine', methods=['POST'])
def send_valentine():
    if 'username' not in session:
        return redirect(url_for('login'))

    recipient_user_id = request.form['recipient_id']
    message = request.form['message']
    
    recipient = User.query.filter_by(user_id=recipient_user_id).first()
    if not recipient:
        flash('Пользователь с таким ID не найден')
        return redirect(url_for('valentine', tab='send'))

    image_path = 'static/basevalentine.jpg'
    if 'image' in request.files:
        file = request.files['image']
        
        # Проверка размера файла (8 МБ = 8 * 1024 * 1024 байт)
        if file.content_length > 8 * 1024 * 1024:
            flash('Размер изображения не должен превышать 8 МБ')
            return redirect(url_for('valentine', tab='send'))
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            image_path = f"static/uploads/{unique_filename}"

    valentine = Valentine(
        sender_id=session['user_db_id'],
        recipient_id=recipient.id,
        message=message,
        image_path=image_path
    )
    db.session.add(valentine)
    db.session.commit()

    flash('Валентинка успешно отправлена!')
    return redirect(url_for('valentine', tab='send'))

@app.route('/received_valentines')
def received_valentines():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user = User.query.filter_by(username=session['username']).first()
    valentines = Valentine.query.filter_by(recipient_id=user.id).all()
    
    # Получаем информацию об отправителях
    valentines_with_senders = []
    for valentine in valentines:
        sender = User.query.get(valentine.sender_id)
        valentines_with_senders.append({
            'valentine': valentine,
            'sender_username': sender.username
        })
    
    return render_template('received_valentines.html',
                         username=session['username'],
                         user_id=user.user_id,
                         valentines=valentines_with_senders)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
