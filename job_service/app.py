import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super-secret-key-change-in-production'
DATABASE = 'job.db'

# ---------- Подключение к БД ----------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    # Выполняем schema.sql с указанием кодировки
    with app.open_resource('database/schema.sql', mode='r', encoding='utf-8') as f:
        db.executescript(f.read())
    # На всякий случай добавим колонку is_active, если её нет (для совместимости)
    try:
        db.execute('ALTER TABLE vacancies ADD COLUMN is_active INTEGER DEFAULT 1')
    except sqlite3.OperationalError:
        pass
    db.commit()
    db.close()

# ---------- Аутентификация ----------
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

def login_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

# ---------- Маршруты ----------
@app.route('/')
def index():
    db = get_db()
    if g.user and g.user['role'] == 'applicant':
        vacancies = db.execute('''
            SELECT * FROM vacancies
            WHERE is_active = 1 AND id NOT IN (SELECT vacancy_id FROM applications WHERE user_id = ?)
            ORDER BY created_at DESC
        ''', (g.user['id'],)).fetchall()
    else:
        vacancies = db.execute('SELECT * FROM vacancies WHERE is_active = 1 ORDER BY created_at DESC').fetchall()
    return render_template('index.html', vacancies=vacancies)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        role = request.form.get('role', 'applicant')
        db = get_db()
        error = None
        if not username or not password:
            error = 'Имя пользователя и пароль обязательны.'
        elif db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            error = f'Пользователь {username} уже существует.'
        if error is None:
            cursor = db.execute(
                'INSERT INTO users (username, password_hash, full_name, email, phone, role) VALUES (?,?,?,?,?,?)',
                (username, generate_password_hash(password), full_name, email, phone, role)
            )
            db.commit()
            session.clear()
            session['user_id'] = cursor.lastrowid
            flash('Регистрация прошла успешно! Вы вошли в систему.', 'success')
            return redirect(url_for('profile'))
        flash(error, 'danger')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user is None or not check_password_hash(user['password_hash'], password):
            flash('Неверное имя пользователя или пароль.', 'danger')
        else:
            session.clear()
            session['user_id'] = user['id']
            flash(f'Добро пожаловать, {user["username"]}!', 'success')
            return redirect(url_for('profile'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    user = g.user
    if request.method == 'POST':
        full_name = request.form['full_name'].strip()
        email = request.form['email'].strip()
        phone = request.form['phone'].strip()
        db.execute('UPDATE users SET full_name=?, email=?, phone=? WHERE id=?',
                   (full_name, email, phone, user['id']))
        db.commit()
        flash('Профиль обновлён.', 'success')
        return redirect(url_for('profile'))

    if user['role'] == 'employer':
        my_vacancies = db.execute('SELECT * FROM vacancies WHERE employer_id = ? ORDER BY created_at DESC',
                                  (user['id'],)).fetchall()
        return render_template('profile.html', user=user, my_vacancies=my_vacancies)
    else:
        applications = db.execute('''
            SELECT a.id, a.status, a.created_at, v.title, v.company, v.id as vacancy_id
            FROM applications a JOIN vacancies v ON a.vacancy_id = v.id
            WHERE a.user_id = ?
            ORDER BY a.created_at DESC
        ''', (user['id'],)).fetchall()
        return render_template('profile.html', user=user, applications=applications)

@app.route('/vacancies')
def vacancies():
    db = get_db()
    if g.user and g.user['role'] == 'applicant':
        all_vacancies = db.execute('''
            SELECT * FROM vacancies
            WHERE is_active = 1 AND id NOT IN (SELECT vacancy_id FROM applications WHERE user_id = ?)
            ORDER BY created_at DESC
        ''', (g.user['id'],)).fetchall()
    else:
        all_vacancies = db.execute('SELECT * FROM vacancies WHERE is_active = 1 ORDER BY created_at DESC').fetchall()
    return render_template('vacancies.html', vacancies=all_vacancies)

@app.route('/vacancy/<int:id>')
def vacancy_detail(id):
    db = get_db()
    vac = db.execute('SELECT * FROM vacancies WHERE id = ?', (id,)).fetchone()
    if vac is None:
        flash('Вакансия не найдена.', 'warning')
        return redirect(url_for('vacancies'))
    already_applied = False
    if g.user and g.user['role'] == 'applicant':
        app_count = db.execute('SELECT COUNT(*) FROM applications WHERE user_id = ? AND vacancy_id = ?',
                               (g.user['id'], id)).fetchone()[0]
        already_applied = app_count > 0
    return render_template('vacancy_detail.html', vacancy=vac, already_applied=already_applied)

@app.route('/apply/<int:vacancy_id>', methods=['POST'])
@login_required
def apply(vacancy_id):
    if g.user['role'] != 'applicant':
        flash('Только соискатели могут откликаться на вакансии.', 'danger')
        return redirect(url_for('vacancy_detail', id=vacancy_id))
    db = get_db()
    # Проверяем, активна ли вакансия
    vac = db.execute('SELECT * FROM vacancies WHERE id = ? AND is_active = 1', (vacancy_id,)).fetchone()
    if vac is None:
        flash('Эта вакансия уже закрыта.', 'warning')
        return redirect(url_for('vacancies'))
    try:
        db.execute('INSERT INTO applications (user_id, vacancy_id) VALUES (?,?)',
                   (g.user['id'], vacancy_id))
        db.commit()
        flash('Вы успешно откликнулись на вакансию!', 'success')
    except sqlite3.IntegrityError:
        flash('Вы уже откликались на эту вакансию.', 'warning')
    return redirect(url_for('vacancy_detail', id=vacancy_id))

@app.route('/create_vacancy', methods=['GET', 'POST'])
@login_required
def create_vacancy():
    if g.user['role'] != 'employer':
        flash('Только работодатели могут создавать вакансии.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form['description'].strip()
        salary = request.form['salary'].strip()
        company = request.form['company'].strip()
        if not title:
            flash('Название вакансии обязательно.', 'danger')
        else:
            db = get_db()
            db.execute('INSERT INTO vacancies (title, description, salary, company, employer_id) VALUES (?,?,?,?,?)',
                       (title, description, salary, company, g.user['id']))
            db.commit()
            flash('Вакансия создана!', 'success')
            return redirect(url_for('profile'))
    return render_template('create_vacancy.html')

@app.route('/employer/vacancy/<int:id>')
@login_required
def employer_vacancy(id):
    if g.user['role'] != 'employer':
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))
    db = get_db()
    vac = db.execute('SELECT * FROM vacancies WHERE id = ? AND employer_id = ?',
                     (id, g.user['id'])).fetchone()
    if vac is None:
        flash('Вакансия не найдена.', 'warning')
        return redirect(url_for('profile'))
    apps = db.execute('''
        SELECT a.id, a.status, a.created_at, u.full_name, u.email, u.phone
        FROM applications a JOIN users u ON a.user_id = u.id
        WHERE a.vacancy_id = ?
        ORDER BY a.created_at DESC
    ''', (id,)).fetchall()
    return render_template('employer_vacancy.html', vacancy=vac, applications=apps)

@app.route('/update_application/<int:app_id>/<string:new_status>', methods=['POST'])
@login_required
def update_application(app_id, new_status):
    if g.user['role'] != 'employer':
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))
    if new_status not in ('accepted', 'rejected'):
        flash('Недопустимый статус.', 'danger')
        return redirect(request.referrer or url_for('profile'))
    db = get_db()
    app = db.execute('SELECT * FROM applications WHERE id = ?', (app_id,)).fetchone()
    if app is None:
        flash('Отклик не найден.', 'warning')
        return redirect(request.referrer or url_for('profile'))
    vac = db.execute('SELECT * FROM vacancies WHERE id = ? AND employer_id = ?',
                     (app['vacancy_id'], g.user['id'])).fetchone()
    if vac is None:
        flash('Вы не являетесь владельцем этой вакансии.', 'danger')
        return redirect(request.referrer or url_for('profile'))
    db.execute('UPDATE applications SET status = ? WHERE id = ?', (new_status, app_id))
    if new_status == 'accepted':
        # Закрываем вакансию
        db.execute('UPDATE vacancies SET is_active = 0 WHERE id = ?', (app['vacancy_id'],))
    db.commit()
    flash('Статус обновлён.', 'success')
    return redirect(url_for('employer_vacancy', id=vac['id']))

# ---------- Запуск ----------
if __name__ == '__main__':
    init_db()
    app.run(debug=True)