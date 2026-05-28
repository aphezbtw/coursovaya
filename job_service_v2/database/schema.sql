CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT DEFAULT '',
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    role TEXT DEFAULT 'applicant',
    company TEXT DEFAULT '',
    skills TEXT DEFAULT '',
    avatar_file TEXT DEFAULT '',
    resume_file TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    salary_from INTEGER,
    salary_to INTEGER,
    company TEXT,
    employer_id INTEGER,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employer_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    vacancy_id INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (vacancy_id) REFERENCES vacancies (id),
    UNIQUE(user_id, vacancy_id)
);

-- Начальные вакансии
INSERT OR IGNORE INTO vacancies (id, title, description, salary_from, salary_to, company, employer_id, is_active) VALUES
(1, 'Программист Python', 'Разработка и сопровождение информационной системы службы занятости.', 120000, 150000, 'ГК «ИнфоСофт»', 0, 1),
(2, 'Системный аналитик', 'Анализ бизнес-процессов службы занятости.', 100000, 130000, 'Центр занятости населения', 0, 1),
(3, 'Инженер техподдержки', 'Сопровождение пользователей ИС.', 70000, 90000, 'Служба поддержки ИС', 0, 1),
(4, 'Администратор БД', 'Оптимизация и обслуживание БД информационной системы.', 130000, 160000, 'Департамент труда', 0, 1),
(5, 'Веб-дизайнер', 'Разработка интерфейсов для портала службы занятости.', 90000, 110000, 'Digital-агентство «Вектор»', 0, 1),
(6, 'Менеджер проектов', 'Управление проектами по автоматизации процессов занятости.', 150000, 180000, 'Министерство труда', 0, 1);