# agent_registry/config.py
PERSISTENCE_FILE = "./data/agentcard.json"
MAX_REGISTER_NUM = 40
MAX_REQUEST_BODY_SIZE = 1024 * 1024  # 1MB default limit
MAX_URL_LENGTH = 1024  # 1KB default limit
# 最大文件大小限制：100MB
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024