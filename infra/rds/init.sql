-- Run once from the EC2 instance with the RDS master account.
-- The collector gets write access; the future MCP service gets SELECT only.
CREATE TABLE IF NOT EXISTS reviews (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_site VARCHAR(32) NOT NULL,
    source_review_id VARCHAR(128) NULL,
    review_date DATE NOT NULL,
    rating DECIMAL(2,1) NOT NULL,
    content TEXT NOT NULL,
    tokens TEXT NOT NULL,
    text_len INT UNSIGNED NOT NULL,
    token_count INT UNSIGNED NOT NULL,
    emoji_count INT UNSIGNED NOT NULL,
    year SMALLINT UNSIGNED NOT NULL,
    month TINYINT UNSIGNED NOT NULL,
    weekday TINYINT UNSIGNED NOT NULL,
    content_hash CHAR(64) NOT NULL,
    collected_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_reviews_source_hash (source_site, content_hash),
    KEY idx_reviews_site_date (source_site, review_date),
    KEY idx_reviews_collected_at (collected_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
