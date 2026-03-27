import os
from dotenv import load_dotenv

load_dotenv()

# LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# Embedding
EMBEDDING_MODEL = "BAAI/bge-m3"

# Chunking
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

# Retrieval
TOP_K = 5

# ChromaDB
CHROMA_PATH = "./chroma_db"
CHROMA_COLLECTION = "sme_policies"

# Data
DATA_RAW_HTML = "./data/html"
DATA_RAW_PDF = "./data/pdf"
