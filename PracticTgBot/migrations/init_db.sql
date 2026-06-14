CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('client', 'executor', 'admin')),
    full_name TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS requests (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    executor_id INTEGER REFERENCES users(id),
    description TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'new' CHECK (status IN ('new', 'in_work', 'completed', 'extended')),
    created_at TIMESTAMP DEFAULT NOW(),
    deadline DATE
);

CREATE TABLE IF NOT EXISTS request_media (
    id SERIAL PRIMARY KEY,
    request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    media_type VARCHAR(10) CHECK (media_type IN ('photo', 'video'))
);

CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE,
    executor_id INTEGER REFERENCES users(id),
    text_report TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS extensions (
    id SERIAL PRIMARY KEY,
    request_id INTEGER REFERENCES requests(id) ON DELETE CASCADE,
    requested_days INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'waiting' CHECK (status IN ('waiting', 'approved', 'rejected')),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индексы для производительности
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_requests_status ON requests(status);
CREATE INDEX idx_requests_client_id ON requests(client_id);
CREATE INDEX idx_requests_executor_id ON requests(executor_id);