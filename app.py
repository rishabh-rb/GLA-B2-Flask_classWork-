import os
from pathlib import Path
from urllib.parse import quote_plus, urlparse, urlunparse, parse_qsl, urlencode
import sqlalchemy as sa

from flask import Flask, render_template, redirect, session, url_for, request, jsonify
from flask_migrate import Migrate
from form import RegistrationForm, LoginForm, UserForm
from model.users import db, User


def load_local_env_file() -> None:
    """Load key=value pairs from .env for local runs."""
    env_file = Path('.env')
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def normalize_database_url(raw_url: str) -> str:
    """Normalize DATABASE_URL for SQLAlchemy/Render compatibility."""
    if raw_url.startswith('postgres://'):
        raw_url = raw_url.replace('postgres://', 'postgresql://', 1)

    parsed = urlparse(raw_url)
    if parsed.scheme.startswith('postgresql') and parsed.hostname not in {'localhost', '127.0.0.1'}:
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault('sslmode', 'require')
        parsed = parsed._replace(query=urlencode(query))
        return urlunparse(parsed)

    return raw_url

app = Flask(__name__)

load_local_env_file()

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_secret_key')

database_url = os.getenv('DATABASE_URL')
if database_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = normalize_database_url(database_url)
else:
    # Fallback for existing POSTGRES_* variable setup.
    db_user = os.getenv('POSTGRES_USER', 'rishabhbarnwal')
    db_password = quote_plus(os.getenv('POSTGRES_PASSWORD', 'Root@123'))
    db_host = os.getenv('POSTGRES_HOST', 'localhost')
    db_name = os.getenv('POSTGRES_DB', 'rishabhbarnwal')
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f'postgresql://{db_user}:{db_password}@{db_host}/{db_name}'
    )

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

db.init_app(app)
migrate = Migrate(app, db)


def ensure_user_table_exists() -> None:
    """Create User table if missing on fresh production databases."""
    user_table_name = User.__table__.name
    inspector = sa.inspect(db.engine)
    if not inspector.has_table(user_table_name):
        User.__table__.create(bind=db.engine, checkfirst=True)


with app.app_context():
    # Keep this as a broad safety net.
    db.create_all()
    # Also enforce the specific user table needed by login/register.
    ensure_user_table_exists()

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter(
            (User.username == form.username.data) | (User.email == form.email.data)
        ).first()
        if existing_user:
            return render_template(
                'register.html',
                form=form,
                message="Username or email already exists."
            )
        user = User(
            username=form.username.data,
            email=form.email.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_form = LoginForm()
        return render_template(
            "login.html",
            form=login_form,
            message="Registration Successful! Please log in."
        )
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('dashboard'))
        return render_template(
            "login.html",
            form=form,
            message="Login mismatch. Please try again or create an account."
        )
    return render_template('login.html', form=form)


@app.route('/dashboard')
def dashboard():
    username = session.get('username')
    if not username:
        return redirect(url_for('login'))
    users = User.query.all()
    form = UserForm()
    return render_template('dashboard.html', username=username, users=users, form=form)


# API endpoints for CRUD operations
@app.route('/api/users', methods=['GET'])
def get_users():
    """Get all users"""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    users = User.query.all()
    return jsonify([{
        'id': user.id,
        'username': user.username,
        'email': user.email
    } for user in users])


@app.route('/api/users', methods=['POST'])
def create_user():
    """Create a new user"""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    # Check if user already exists
    existing = User.query.filter(
        (User.username == data.get('username')) | (User.email == data.get('email'))
    ).first()
    if existing:
        return jsonify({'error': 'Username or email already exists'}), 400
    
    try:
        user = User(
            username=data.get('username'),
            email=data.get('email')
        )
        user.set_password(data.get('password'))
        db.session.add(user)
        db.session.commit()
        return jsonify({
            'id': user.id,
            'username': user.username,
            'email': user.email
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get a specific user"""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email
    })


@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """Update a user"""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    try:
        
        if 'email' in data:
            # Check if new email is available
            existing = User.query.filter(
                (User.email == data['email']) & (User.id != user_id)
            ).first()
            if existing:
                return jsonify({'error': 'Email already exists'}), 400
            user.email = data['email']
        
        if 'password' in data and data['password']:
            user.set_password(data['password'])
        
        db.session.commit()
        return jsonify({
            'id': user.id,
            'username': user.username,
            'email': user.email
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user"""
    if not session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Prevent deleting the current user
    if session.get('user_id') == user_id:
        session.clear()
        return jsonify({
                'message': 'Account deleted successfully',
                'redirect': url_for('login')
            })
    
    user = User.query.get_or_404(user_id)
    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({'message': 'User deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug = True, port=5003)