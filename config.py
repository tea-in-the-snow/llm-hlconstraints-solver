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

