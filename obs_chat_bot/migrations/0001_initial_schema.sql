CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT NOT NULL,
    url_hash TEXT NOT NULL UNIQUE,
    title TEXT,
    cleaned_text TEXT,
    text_hash TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_articles_status ON articles (status);
CREATE INDEX idx_articles_text_hash ON articles (text_hash);

CREATE TABLE incoming_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER,
    channel TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    message_text TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE SET NULL,
    UNIQUE (channel, chat_id, message_id)
);

CREATE INDEX idx_incoming_messages_article_id
    ON incoming_messages (article_id);

CREATE TABLE analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    llm_model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    result_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
);

CREATE INDEX idx_analysis_results_article_id
    ON analysis_results (article_id);

CREATE TABLE processing_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER,
    incoming_message_id INTEGER,
    stage TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE SET NULL,
    FOREIGN KEY (incoming_message_id)
        REFERENCES incoming_messages (id) ON DELETE SET NULL
);

CREATE INDEX idx_processing_errors_article_id
    ON processing_errors (article_id);
CREATE INDEX idx_processing_errors_incoming_message_id
    ON processing_errors (incoming_message_id);
