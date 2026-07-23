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

CREATE TABLE identity_rebind_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    target_app_user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (target_app_user_id) REFERENCES app_users (id) ON DELETE CASCADE,
    UNIQUE (channel, external_user_id)
);

CREATE INDEX idx_identity_rebind_confirmations_expires_at
    ON identity_rebind_confirmations (expires_at);

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

CREATE TABLE github_accounts (
    app_user_id INTEGER PRIMARY KEY,
    github_user_id INTEGER NOT NULL,
    login TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_user_id) REFERENCES app_users (id) ON DELETE CASCADE,
    CHECK (github_user_id > 0),
    CHECK (length(trim(login)) > 0)
);

CREATE INDEX idx_github_accounts_github_user_id
    ON github_accounts (github_user_id);

CREATE TABLE github_installations (
    app_user_id INTEGER NOT NULL,
    installation_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (app_user_id, installation_id),
    FOREIGN KEY (app_user_id) REFERENCES github_accounts (app_user_id)
        ON DELETE CASCADE,
    CHECK (installation_id > 0)
);

CREATE INDEX idx_github_installations_installation_id
    ON github_installations (installation_id);

CREATE TABLE github_connection_attempts (
    app_user_id INTEGER PRIMARY KEY,
    owner TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (app_user_id) REFERENCES app_users (id) ON DELETE CASCADE,
    CHECK (length(trim(owner)) > 0)
);

CREATE INDEX idx_github_connection_attempts_expires_at
    ON github_connection_attempts (expires_at);

CREATE TABLE obsidian_vaults (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_user_id INTEGER NOT NULL UNIQUE,
    installation_id INTEGER NOT NULL,
    repository_id INTEGER NOT NULL,
    owner TEXT NOT NULL,
    repository TEXT NOT NULL,
    branch TEXT NOT NULL,
    root_path TEXT NOT NULL DEFAULT '',
    head_commit_sha TEXT,
    tree_sha TEXT,
    head_etag TEXT,
    last_checked_at TEXT,
    last_synced_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_user_id, installation_id)
        REFERENCES github_installations (app_user_id, installation_id)
        ON DELETE CASCADE,
    UNIQUE (app_user_id, id),
    CHECK (repository_id > 0)
);

CREATE INDEX idx_obsidian_vaults_installation_id
    ON obsidian_vaults (installation_id);
CREATE INDEX idx_obsidian_vaults_repository_id
    ON obsidian_vaults (repository_id);

CREATE TABLE obsidian_vault_confirmations (
    app_user_id INTEGER NOT NULL PRIMARY KEY,
    action TEXT NOT NULL,
    installation_id INTEGER,
    repository_id INTEGER,
    owner TEXT,
    repository TEXT,
    branch TEXT,
    root_path TEXT,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_user_id) REFERENCES app_users (id) ON DELETE CASCADE,
    FOREIGN KEY (app_user_id, installation_id)
        REFERENCES github_installations (app_user_id, installation_id)
        ON DELETE CASCADE,
    CHECK (
        (
            action = 'replace'
            AND installation_id IS NOT NULL
            AND repository_id IS NOT NULL
            AND owner IS NOT NULL
            AND repository IS NOT NULL
            AND branch IS NOT NULL
            AND root_path IS NOT NULL
        )
        OR (
            action = 'disconnect'
            AND installation_id IS NULL
            AND repository_id IS NULL
            AND owner IS NULL
            AND repository IS NULL
            AND branch IS NULL
            AND root_path IS NULL
        )
    )
);

CREATE INDEX idx_obsidian_vault_confirmations_expires_at
    ON obsidian_vault_confirmations (expires_at);

CREATE TABLE obsidian_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_user_id INTEGER NOT NULL,
    vault_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    blob_sha TEXT NOT NULL,
    title TEXT,
    markdown TEXT NOT NULL,
    frontmatter TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (app_user_id, vault_id)
        REFERENCES obsidian_vaults (app_user_id, id) ON DELETE CASCADE,
    UNIQUE (vault_id, path),
    UNIQUE (app_user_id, id)
);

CREATE INDEX idx_obsidian_notes_app_user_vault
    ON obsidian_notes (app_user_id, vault_id);
CREATE INDEX idx_obsidian_notes_vault_blob_sha
    ON obsidian_notes (vault_id, blob_sha);

CREATE TABLE obsidian_note_tags (
    app_user_id INTEGER NOT NULL,
    note_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (note_id, tag),
    FOREIGN KEY (app_user_id, note_id)
        REFERENCES obsidian_notes (app_user_id, id) ON DELETE CASCADE
);

CREATE INDEX idx_obsidian_note_tags_app_user_tag
    ON obsidian_note_tags (app_user_id, tag);

CREATE TABLE obsidian_note_wikilinks (
    app_user_id INTEGER NOT NULL,
    note_id INTEGER NOT NULL,
    target TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (note_id, target),
    FOREIGN KEY (app_user_id, note_id)
        REFERENCES obsidian_notes (app_user_id, id) ON DELETE CASCADE
);

CREATE INDEX idx_obsidian_note_wikilinks_app_user_target
    ON obsidian_note_wikilinks (app_user_id, target);

CREATE TABLE obsidian_vault_sync_leases (
    app_user_id INTEGER NOT NULL,
    vault_id INTEGER NOT NULL PRIMARY KEY,
    owner TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (app_user_id, vault_id)
        REFERENCES obsidian_vaults (app_user_id, id) ON DELETE CASCADE
);

CREATE INDEX idx_obsidian_vault_sync_leases_expires_at
    ON obsidian_vault_sync_leases (expires_at);
