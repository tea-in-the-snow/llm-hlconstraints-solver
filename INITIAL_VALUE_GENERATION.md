# Initial Value Generation Service

这个服务用于为方法参数生成合法的 Java 初始化代码，无需约束条件。它可以被 `SignsToWrappers.java` 通过 RESTful API 调用来生成初始测试输入。

## 架构

### 组件

1. **initial_value_agent.py**: 核心 agent，负责生成初始化代码
2. **app.py** (`/initialize` 端点): HTTP RESTful API 端点
3. **InitialValueGenerator.java**: Java 客户端类，用于从 Java 代码通过 HTTP 调用服务

### 与 initializer_agent.py 的区别

- **initializer_agent.py**: 需要约束条件（constraints）和 heap_solver 输出，用于符号执行，通过 `/solve` 端点调用
- **initial_value_agent.py**: 不需要约束条件，仅基于参数类型生成合法的初始化代码，通过 `/initialize` 端点调用

## 使用方法

### 1. 启动服务

```bash
cd llm-hlconstraints-solver
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 2. 作为 HTTP RESTful API

调用 API：
```bash
curl -X POST http://localhost:8000/initialize \
  -H "Content-Type: application/json" \
  -d '{
    "parameter_types": [
      {"name": "p0", "type": "java.lang.Appendable"},
      {"name": "p1", "type": "int"}
    ]
  }'
```

响应：
```json
{
  "initialization_code": "java.lang.Appendable p0 = new java.lang.StringBuilder();\nint p1 = 0;",
  "variable_assignments": {"p0": "p0", "p1": "p1"},
  "type_plans": {...}
}
```

### 3. 从 Java 代码调用

在 `SignsToWrappers.java` 中：

```java
// 设置 useLLMForInitialization = true 来启用 LLM 生成
boolean useLLMForInitialization = true;

// 代码会通过 RESTful API 调用 LLM 服务生成初始化代码
// 服务 URL 可通过 LLM_INITIALIZER_URL 环境变量配置（默认: http://127.0.0.1:8000/initialize）
```

注意：
- 如果 `InitialValueGenerator` 类不可用或 LLM 服务失败，会自动回退到默认的 `getObjectDefaultValue()` 方法
- 使用反射来避免编译时依赖，使 LLM 功能真正可选
- Java 客户端使用 `HttpURLConnection` 进行 HTTP 调用，无需额外的依赖库

## 特性

### 接口类型处理

服务会自动为接口类型选择默认实现类：
- `Appendable` → `StringBuilder`
- `List` → `ArrayList`
- `Set` → `HashSet`
- `Map` → `HashMap`
- 等等（与 `initializer_agent.py` 保持一致）

### 具体类处理

- 如果类有无参构造函数，使用 `new ClassName()`
- 否则返回 `null`

### 最小化 null 值

服务会尽量生成非 null 的初始化代码，避免 NullPointerException。

## 配置

### 服务端配置

确保 `.env` 文件中配置了 `OPENAI_API_KEY`：

```
OPENAI_API_KEY=sk-...
```

其他配置在 `config.py` 中（如 `CLASS_PATH` 用于类型解析）。

### 客户端配置

Java 客户端可以通过环境变量配置：

- `LLM_INITIALIZER_URL`: 服务 URL（默认: `http://127.0.0.1:8000/initialize`）
- `LLM_INITIALIZER_TIMEOUT`: 请求超时时间（秒，默认: 60）

## 示例

输入：
```json
[
  {"name": "p0", "type": "java.lang.Appendable"},
  {"name": "p1", "type": "java.util.List"},
  {"name": "p2", "type": "int"}
]
```

输出代码：
```java
java.lang.Appendable p0 = new java.lang.StringBuilder();
java.util.List p1 = new java.util.ArrayList<>();
int p2 = 0;
```

