import sqlite3, os, uuid
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'super-secret-key-change-in-production'
DATABASE = 'job.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
    with app.open_resource('database/schema.sql', mode='r', encoding='utf-8') as f:
        db.executescript(f.read())

    try: db.execute('ALTER TABLE vacancies ADD COLUMN is_active INTEGER DEFAULT 1')
    except sqlite3.OperationalError: pass
    try: db.execute('ALTER TABLE vacancies ADD COLUMN salary_from INTEGER')
    except sqlite3.OperationalError: pass
    try: db.execute('ALTER TABLE vacancies ADD COLUMN salary_to INTEGER')
    except sqlite3.OperationalError: pass
    for col in ['company', 'skills', 'avatar_file', 'resume_file']:
        try: db.execute(f'ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT ""')
        except sqlite3.OperationalError: pass

    if db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
        db.execute('INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)',
                   ('admin', generate_password_hash('admin123'), 'admin', 'Администратор Системы'))
    db.commit()
    db.close()

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
        if g.user is None: return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def admin_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None or g.user['role'] != 'admin':
            flash('Доступ только для администратора.', 'danger')
            return redirect(url_for('index'))
        return view(**kwargs)
    return wrapped_view

def format_salary(vac):
    fr = vac['salary_from']
    to = vac['salary_to']
    if fr and to:
        return f"{fr:,} – {to:,} руб."
    elif fr:
        return f"от {fr:,} руб."
    elif to:
        return f"до {to:,} руб."
    return "не указана"
app.jinja_env.globals.update(format_salary=format_salary)

# ---------- ГЛАВНАЯ ----------
@app.route('/')
def index():
    db = get_db()
    total_vacancies = db.execute('SELECT COUNT(*) FROM vacancies WHERE is_active = 1').fetchone()[0]
    total_applicants = db.execute("SELECT COUNT(*) FROM users WHERE role = 'applicant'").fetchone()[0]
    total_employers = db.execute("SELECT COUNT(*) FROM users WHERE role = 'employer'").fetchone()[0]
    return vacancy_list('index.html', stats={'vacancies': total_vacancies, 'applicants': total_applicants, 'employers': total_employers})

@app.route('/vacancies')
def vacancies():
    return vacancy_list('vacancies.html')

def vacancy_list(template, stats=None):
    page = request.args.get('page', 1, type=int)
    per_page = 5
    search = request.args.get('search', '').strip()
    salary_from = request.args.get('salary_from', '').strip()
    salary_to = request.args.get('salary_to', '').strip()
    sort = request.args.get('sort', 'date_desc')
    last_7_days = request.args.get('last_7_days', '0')

    db = get_db()
    query = 'SELECT * FROM vacancies WHERE is_active = 1'
    params = []
    if g.user and g.user['role'] == 'applicant':
        query += ' AND id NOT IN (SELECT vacancy_id FROM applications WHERE user_id = ?)'
        params.append(g.user['id'])

    all_vacancies = db.execute(query, params).fetchall()

    if search:
        search_lower = search.lower()
        all_vacancies = [v for v in all_vacancies if
                         search_lower in (v['title'] or '').lower() or
                         search_lower in (v['company'] or '').lower() or
                         search_lower in (v['description'] or '').lower()]

    if salary_from:
        sf = int(salary_from)
        all_vacancies = [v for v in all_vacancies if v['salary_from'] is not None and v['salary_from'] >= sf]
    if salary_to:
        st = int(salary_to)
        all_vacancies = [v for v in all_vacancies if v['salary_to'] is not None and v['salary_to'] <= st]

    if last_7_days == '1':
        cutoff = datetime.now() - timedelta(days=7)
        def parse_date(v):
            try: return datetime.strptime(v['created_at'], '%Y-%m-%d %H:%M:%S')
            except: return datetime.min
        all_vacancies = [v for v in all_vacancies if parse_date(v) >= cutoff]

    if sort == 'date_asc':
        all_vacancies.sort(key=lambda v: v['created_at'])
    elif sort == 'salary_asc':
        all_vacancies.sort(key=lambda v: (v['salary_from'] or 0))
    elif sort == 'salary_desc':
        all_vacancies.sort(key=lambda v: (v['salary_from'] or 0), reverse=True)
    else:
        all_vacancies.sort(key=lambda v: v['created_at'], reverse=True)

    total_vacancies = len(all_vacancies)
    total_pages = (total_vacancies + per_page - 1) // per_page
    offset = (page - 1) * per_page
    paginated = all_vacancies[offset:offset + per_page]

    return render_template(template, vacancies=paginated, page=page, total_pages=total_pages,
                           search=search, salary_from=salary_from, salary_to=salary_to,
                           sort=sort, last_7_days=last_7_days, stats=stats)

# ---------- РЕГИСТРАЦИЯ И ВХОД ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        password2 = request.form['password2']
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        role = request.form.get('role', 'applicant')
        company = request.form.get('company', '').strip()
        skills = request.form.get('skills', '').strip()
        db = get_db()
        error = None
        if not username or not password:
            error = 'Имя пользователя и пароль обязательны.'
        elif password != password2:
            error = 'Пароли не совпадают.'
        elif len(password) < 4:
            error = 'Пароль должен быть не менее 4 символов.'
        elif db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone():
            error = f'Пользователь {username} уже существует.'
        if error is None:
            cursor = db.execute(
                'INSERT INTO users (username, password_hash, full_name, email, phone, role, company, skills) VALUES (?,?,?,?,?,?,?,?)',
                (username, generate_password_hash(password), full_name, email, phone, role, company, skills)
            )
            db.commit()
            session.clear()
            session['user_id'] = cursor.lastrowid
            flash('Регистрация успешна! Вы вошли.', 'success')
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
    flash('Вы вышли.', 'info')
    return redirect(url_for('index'))

# ---------- ПРОФИЛЬ ----------
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    user = g.user
    if request.method == 'POST':
        full_name = request.form['full_name'].strip()
        email = request.form['email'].strip()
        phone = request.form['phone'].strip()
        company = request.form.get('company', '').strip()
        skills = request.form.get('skills', '').strip()

        avatar_file = request.files.get('avatar')
        if avatar_file and avatar_file.filename != '' and allowed_file(avatar_file.filename):
            filename = secure_filename(avatar_file.filename)
            unique = f"avatar_{user['id']}_{uuid.uuid4().hex}_{filename}"
            avatar_file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique))
            db.execute('UPDATE users SET avatar_file = ? WHERE id = ?', (unique, user['id']))

        resume_file = request.files.get('resume')
        if resume_file and resume_file.filename != '' and allowed_file(resume_file.filename):
            filename = secure_filename(resume_file.filename)
            unique = f"resume_{user['id']}_{uuid.uuid4().hex}_{filename}"
            resume_file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique))
            db.execute('UPDATE users SET resume_file = ? WHERE id = ?', (unique, user['id']))

        db.execute('UPDATE users SET full_name=?, email=?, phone=?, company=?, skills=? WHERE id=?',
                   (full_name, email, phone, company, skills, user['id']))
        db.commit()
        flash('Профиль обновлён.', 'success')
        return redirect(url_for('profile'))

    user = db.execute('SELECT * FROM users WHERE id = ?', (user['id'],)).fetchone()
    if user['role'] == 'employer':
        my_vacancies = db.execute('SELECT * FROM vacancies WHERE employer_id = ? ORDER BY created_at DESC', (user['id'],)).fetchall()
        return render_template('profile.html', user=user, my_vacancies=my_vacancies)
    else:
        applications = db.execute('''
            SELECT a.id, a.status, a.created_at, v.title, v.company, v.salary_from, v.salary_to, v.id as vacancy_id
            FROM applications a JOIN vacancies v ON a.vacancy_id = v.id
            WHERE a.user_id = ? ORDER BY a.created_at DESC
        ''', (user['id'],)).fetchall()
        return render_template('profile.html', user=user, applications=applications)

@app.route('/withdraw_application/<int:app_id>', methods=['POST'])
@login_required
def withdraw_application(app_id):
    if g.user['role'] != 'applicant':
        flash('Только соискатели могут отзывать отклики.', 'danger')
        return redirect(url_for('profile'))
    db = get_db()
    app = db.execute('SELECT * FROM applications WHERE id = ? AND user_id = ?', (app_id, g.user['id'])).fetchone()
    if app is None:
        flash('Отклик не найден.', 'warning')
    elif app['status'] != 'pending':
        flash('Можно отозвать только отклик на рассмотрении.', 'danger')
    else:
        db.execute('DELETE FROM applications WHERE id = ?', (app_id,))
        db.commit()
        flash('Отклик отозван.', 'info')
    return redirect(url_for('profile'))

# ---------- ВАКАНСИИ ----------
@app.route('/vacancy/<int:id>')
def vacancy_detail(id):
    db = get_db()
    vac = db.execute('SELECT * FROM vacancies WHERE id = ?', (id,)).fetchone()
    if vac is None:
        flash('Вакансия не найдена.', 'warning')
        return redirect(url_for('vacancies'))
    already_applied = False
    app_count = db.execute('SELECT COUNT(*) FROM applications WHERE vacancy_id = ?', (id,)).fetchone()[0]
    if g.user and g.user['role'] == 'applicant':
        app = db.execute('SELECT * FROM applications WHERE user_id = ? AND vacancy_id = ?', (g.user['id'], id)).fetchone()
        already_applied = app is not None
    return render_template('vacancy_detail.html', vacancy=vac, already_applied=already_applied, app_count=app_count)

@app.route('/apply/<int:vacancy_id>', methods=['POST'])
@login_required
def apply(vacancy_id):
    if g.user['role'] != 'applicant':
        flash('Только соискатели могут откликаться.', 'danger')
        return redirect(url_for('vacancy_detail', id=vacancy_id))
    db = get_db()
    vac = db.execute('SELECT * FROM vacancies WHERE id = ? AND is_active = 1', (vacancy_id,)).fetchone()
    if vac is None:
        flash('Вакансия уже закрыта.', 'warning')
        return redirect(url_for('vacancies'))
    try:
        db.execute('INSERT INTO applications (user_id, vacancy_id) VALUES (?,?)', (g.user['id'], vacancy_id))
        db.commit()
        flash('Вы откликнулись!', 'success')
    except sqlite3.IntegrityError:
        flash('Вы уже откликались.', 'warning')
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
        salary_from = request.form.get('salary_from', '').strip()
        salary_to = request.form.get('salary_to', '').strip()
        company = request.form.get('company', '').strip()
        if not title:
            flash('Название обязательно.', 'danger')
        else:
            db = get_db()
            db.execute('INSERT INTO vacancies (title, description, salary_from, salary_to, company, employer_id) VALUES (?,?,?,?,?,?)',
                       (title, description, int(salary_from) if salary_from else None, int(salary_to) if salary_to else None, company, g.user['id']))
            db.commit()
            flash('Вакансия создана!', 'success')
            return redirect(url_for('profile'))
    return render_template('create_vacancy.html', user=g.user)

@app.route('/employer/vacancy/<int:id>')
@login_required
def employer_vacancy(id):
    if g.user['role'] != 'employer':
        flash('Доступ запрещён.', 'danger')
        return redirect(url_for('index'))
    db = get_db()
    vac = db.execute('SELECT * FROM vacancies WHERE id = ? AND employer_id = ?', (id, g.user['id'])).fetchone()
    if vac is None:
        flash('Вакансия не найдена.', 'warning')
        return redirect(url_for('profile'))
    apps = db.execute('''
        SELECT a.id, a.status, a.created_at, u.full_name, u.email, u.phone
        FROM applications a JOIN users u ON a.user_id = u.id
        WHERE a.vacancy_id = ? ORDER BY a.created_at DESC
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
    vac = db.execute('SELECT * FROM vacancies WHERE id = ? AND employer_id = ?', (app['vacancy_id'], g.user['id'])).fetchone()
    if vac is None:
        flash('Вы не владелец вакансии.', 'danger')
        return redirect(request.referrer or url_for('profile'))
    db.execute('UPDATE applications SET status = ? WHERE id = ?', (new_status, app_id))
    if new_status == 'accepted':
        db.execute('UPDATE vacancies SET is_active = 0 WHERE id = ?', (app['vacancy_id'],))
    db.commit()
    flash('Статус обновлён.', 'success')
    return redirect(url_for('employer_vacancy', id=vac['id']))

# ---------- АДМИНКА ----------
@app.route('/admin')
@admin_required
def admin_panel():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY id').fetchall()
    vacancies = db.execute('SELECT * FROM vacancies ORDER BY created_at DESC').fetchall()
    return render_template('admin.html', users=users, vacancies=vacancies)

@app.route('/admin/change_role/<int:user_id>', methods=['POST'])
@admin_required
def change_role(user_id):
    new_role = request.form.get('role')
    if new_role not in ('applicant', 'employer', 'admin'):
        flash('Некорректная роль.', 'danger')
        return redirect(url_for('admin_panel'))
    db = get_db()
    db.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, user_id))
    db.commit()
    flash('Роль изменена.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    flash('Пользователь удалён.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_vacancy/<int:vacancy_id>', methods=['POST'])
@admin_required
def delete_vacancy(vacancy_id):
    db = get_db()
    db.execute('DELETE FROM vacancies WHERE id = ?', (vacancy_id,))
    db.commit()
    flash('Вакансия удалена.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)