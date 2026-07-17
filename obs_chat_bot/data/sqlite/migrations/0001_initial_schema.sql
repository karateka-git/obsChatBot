CREATE TABLE app_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE external_identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_user_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    external_chat_id TEXT NOT NULL,
    username TEXT,
    display_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_user_id) REFERENCES app_users (id) ON DELETE CASCADE,
    UNIQUE (channel, external_user_id)
);

CREATE INDEX idx_external_identities_app_user_id
    ON external_identities (app_user_id);

CREATE TABLE identity_link_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_user_id) REFERENCES app_users (id) ON DELETE CASCADE
);

CREATE INDEX idx_identity_link_tokens_app_user_id
    ON identity_link_tokens (app_user_id);
CREATE INDEX idx_identity_link_tokens_expires_at
    ON identity_link_tokens (expires_at);

INSERT INTO app_users (id, display_name)
VALUES (1, 'Legacy user');

CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_user_id INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    title TEXT,
    cleaned_text TEXT,
    text_hash TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_user_id) REFERENCES app_users (id) ON DELETE CASCADE,
    UNIQUE (app_user_id, normalized_url)
);

CREATE INDEX idx_articles_app_user_status
    ON articles (app_user_id, status);
CREATE INDEX idx_articles_app_user_text_hash
    ON articles (app_user_id, text_hash);

CREATE TABLE incoming_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_user_id INTEGER NOT NULL,
    article_id INTEGER,
    channel TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    message_text TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_user_id) REFERENCES app_users (id) ON DELETE CASCADE,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE SET NULL,
    UNIQUE (channel, chat_id, message_id)
);

CREATE INDEX idx_incoming_messages_app_user_id
    ON incoming_messages (app_user_id);
CREATE INDEX idx_incoming_messages_article_id
    ON incoming_messages (article_id);

CREATE TABLE analysis_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_user_id INTEGER NOT NULL,
    article_id INTEGER NOT NULL,
    llm_model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    result_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_user_id) REFERENCES app_users (id) ON DELETE CASCADE,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
);

CREATE INDEX idx_analysis_results_app_user_article_id
    ON analysis_results (app_user_id, article_id);
CREATE INDEX idx_analysis_results_article_id
    ON analysis_results (article_id);

CREATE TABLE processing_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_user_id INTEGER,
    article_id INTEGER,
    incoming_message_id INTEGER,
    stage TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_user_id) REFERENCES app_users (id) ON DELETE SET NULL,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE SET NULL,
    FOREIGN KEY (incoming_message_id)
        REFERENCES incoming_messages (id) ON DELETE SET NULL
);

CREATE INDEX idx_processing_errors_app_user_id
    ON processing_errors (app_user_id);
CREATE INDEX idx_processing_errors_article_id
    ON processing_errors (article_id);
CREATE INDEX idx_processing_errors_incoming_message_id
    ON processing_errors (incoming_message_id);
