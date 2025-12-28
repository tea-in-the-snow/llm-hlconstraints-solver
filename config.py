"""
Configuration settings for the LLM service.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# OpenAI API configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY environment variable. Please set it in .env file.")

# LLM_MODEL = "claude-opus-4-5-20251101-thinking-c"  # Default model name
# LLM_MODEL = "claude-sonnet-4-5-20250929"  # Default model name
LLM_MODEL = "deepseek-chat"  # Default model name

# BASE_URL = "https://globalai.vip/v1"  # Optional: Set to a custom base URL (e.g., "https://api.openai.com/v1" or proxy URL)
# BASE_URL = "https://api.chatanywhere.tech/v1"  # Optional: Set to a custom base URL (e.g., "https://api.openai.com/v1" or proxy URL)
BASE_URL = "https://api.deepseek.com/v1"  # Optional: Set to a custom base URL (e.g., "https://api.openai.com/v1" or proxy URL)

CLASS_PATH = "/home/shaoran/repos/new-jdart/jdart-llm/lib/gson-2.2.4.jar,/home/shaoran/repos/new-jdart/jdartTest/build,/home/shaoran/src/java-libs/commons-lang/target/commons-lang3-3.13.0.jar,/home/shaoran/repos/new-jdart/jdartTest/build,/home/shaoran/src/java-libs/jfreechart/target/jfreechart-1.5.4.jar,/home/shaoran/src/java-libs/guava/target/guava-32.1.2-jre.jar"
SOURCE_PATH = "/home/shaoran/repos/new-jdart/jdartTest/src,/home/shaoran/src/java-libs/commons-lang/src,/home/shaoran/repos/new-jdart/jdartTest/build,/home/shaoran/src/java-libs/jfreechart/target/jfreechart-1.5.4.jar,/home/shaoran/src/java-libs/guava/guava/src"

# Java utilities configuration
JAVA_UTILS_PATH = "/home/shaoran/repos/new-jdart/llm-hlconstraints-solver/javaUtils"
TYPE_PARSE_SERVICE_CLASS = "javaUtils.TypeParseService"
TYPE_INFO_JSON_CLASS = "javaUtils.TypeInfoJson"

# Concurrency configuration
# Maximum number of concurrent requests (0 = unlimited, recommended: CPU count * 2)
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "0"))
# Thread pool size for asyncio.to_thread (0 = use default, recommended: CPU count * 4)
THREAD_POOL_SIZE = int(os.getenv("THREAD_POOL_SIZE", "0"))

# API Rate Limiting configuration
# Maximum requests per minute for LLM API (0 = unlimited, recommended: 60-120)
# Note: Different API providers have different limits:
# - OpenAI: ~60-3500 requests/min depending on tier
# - DeepSeek: ~60 requests/min for free tier
API_REQUESTS_PER_MINUTE = int(os.getenv("API_REQUESTS_PER_MINUTE", "60"))
# Maximum requests per second (0 = no limit, recommended: 2-5)
API_REQUESTS_PER_SECOND = int(os.getenv("API_REQUESTS_PER_SECOND", "0"))
# Maximum retries for 429 (rate limit) errors
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "3"))
# Enable API rate limiting (set to "false" to disable)
API_RATE_LIMITING_ENABLED = os.getenv("API_RATE_LIMITING_ENABLED", "true").lower() == "true"

