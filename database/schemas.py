#schemas
from enum import Enum


class TableName(Enum):
    USER_REGISTRATION = "user_registration"
    USER_WHITE_LIST = "user_white_list"


TABLE_SCHEMAS = {
    TableName.USER_REGISTRATION: """
        CREATE TABLE IF NOT EXISTS user_registration (
            telegram_id BIGINT PRIMARY KEY,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_name VARCHAR(25) NOT NULL UNIQUE
        )
    """,
    TableName.USER_WHITE_LIST: """
        CREATE TABLE IF NOT EXISTS user_white_list (
            id SERIAL PRIMARY KEY,
            user_name VARCHAR(25) NOT NULL UNIQUE
        )
    """
}

INDEXES = {
    TableName.USER_REGISTRATION: [
        "CREATE INDEX IF NOT EXISTS idx_user_registered_at ON user_registration(registered_at)",
        "CREATE INDEX IF NOT EXISTS idx_user_name ON user_registration(user_name)"
    ],
    TableName.USER_WHITE_LIST: [
        "CREATE INDEX IF NOT EXISTS idx_user_name ON user_white_list(user_name)"
    ]
}