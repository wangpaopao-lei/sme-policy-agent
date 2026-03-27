"""
一次性数据摄入脚本
用法：在项目根目录执行
    python scripts/ingest.py
"""
import sys
import os

# 确保从项目根目录导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.pipeline import run

if __name__ == "__main__":
    run()
