CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT DEFAULT '',
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    role TEXT DEFAULT 'applicant'
);

CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    salary TEXT,
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

-- Предзаполненные вакансии
INSERT OR IGNORE INTO vacancies (id, title, description, salary, company, employer_id, is_active) VALUES
(1, 'Программист Python', 'Разработка и сопровождение информационной системы службы занятости.', '120 000 – 150 000 руб.', 'ГК «ИнфоСофт»', 0, 1),
(2, 'Системный аналитик', 'Анализ бизнес-процессов службы занятости.', '100 000 – 130 000 руб.', 'Центр занятости населения', 0, 1),
(3, 'Инженер техподдержки', 'Сопровождение пользователей ИС.', '70 000 – 90 000 руб.', 'Служба поддержки ИС', 0, 1),
(4, 'Администратор БД', 'Оптимизация и обслуживание БД информационной системы.', '130 000 – 160 000 руб.', 'Департамент труда', 0, 1),
(5, 'Веб-дизайнер', 'Разработка интерфейсов для портала службы занятости.', '90 000 – 110 000 руб.', 'Digital-агентство «Вектор»', 0, 1);