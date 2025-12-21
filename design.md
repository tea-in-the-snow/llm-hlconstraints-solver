# LLM 求解器设计

## LLM 求解器的总体功能

### 功能

求解器通过基于 RESTful 风格的 HTTP 接口与外部组件进行通信。其输入为一组高层次约束及相关上下文信息，输出为这些高层次约束的可满足性判断及相应的求解结果。总体而言，高层次约束用于刻画以被测方法输入参数为根的完整输入空间，尤其是涉及堆结构的状态描述。

例如，对于方法 `test(Node head)`，高层次约束集合不仅应当涵盖参数 `head` 本身的属性（如取值范围、空性）及其可能的动态类型，还应系统性地描述以 `head` 为起点所可达的整个链表结构，包括节点之间的连接关系、结构形态以及相关的不变式。

### 输入（FastAPI /solve 端点）

```
class SolveRequest:

 	constraints: List[str]          							约束列表

  	type_hierarchy: Dict[str, str]								类型层次
  	
  	variable_static_type: Dict[str, str]						约束集合中涉及到的变量的静态类型

  	heap_state: Optional[Dict[str, Any]]   						堆状态

  	source_context: Optional[Dict[str, Any]]		 			源代码上下文

  	max_tokens: Optional[int] = 512     						最大 token 数

  	temperature: Optional[float] = 0.0    						温度参数
```

### 输出

```
{
    "result": "SAT" | "UNSAT" | "UNKNOWN",  # 求解结果
    "valuation": [                          # SAT 时的估值列表
        {
            "variable": "head(ref)",
            "type": "LNode;",
            "newObject": true,
            "trueRef": true,
            "reference": 1
        }
    ]
}
```

## 关于增量求解

在符号执行过程中，路径探索通常呈树状结构。相邻的路径往往共享大部分前缀约束，如果每条路径都从头开始构建和求解，会造成巨大的计算浪费。增量求解旨在利用这些共享信息。在 JDart 中，利用 z3 等 SMT 求解器的增量求解功能支持来增量求解。

但是对于 LLM 来说，即便“把旧约束 + 新约束”一起喂给 LLM，也无法证明它是在“增量”而不是“重新猜”。

所以，使用增量求解一方面不能确定是否会有正确率上的提升，另一方面在 token 花费上也未必会降低。因为如果把每条路径的路径条件都进行求解，求解次数也大约就是路径的数量。但是如果实现来类似增量求解的功能，那么并不是每条路径求解一次，而是在中间过程中也要求解。也就是说，原先相当于只在约束树的叶子节点进行一次求解，现在在中间节点也要进行求解。其实相比于原先的方法可以减少上下文的长度，但总成本未必降低。

因此，暂时不考虑让 LLM 实现类似增量求解的功能。

## LLM 求解器的 muti-agent 架构设计

### type_solver

专注于类型相关的（显式和隐式）约束的求解。

职责：分析约束集合中每个变量的类型相关约束，结合变量的静态类型和源码上下文，生成每个变量的类型信息的解。

输入：

```python
constraints: List[str]
variable_static_type: Dict[str, str]
type_hierarchy: Dict[str, str]
```

输出：

```python
{
    "result": "SAT" | "UNSAT" | "UNKNOWN",
    "valuation": [
        {
            "variable": "head(ref)",
            "type": "LNode;",
        }
    ]
}
```

### type_solver_verifier

检验 type_solver 求解结果的合理性（不使用 LLM）

职责：

1. 检验 JSON 格式是否符合要求
2. 检验变量名合法性（必须来自约束）

输入：

```python
constraints: List[str]
heap_solver_output
```

输出：

```python
{
  "is_well_formed": false,
  "errors": [
    {
      "error_type": "INVALID_VARIABLE",
      "location": "valuation[0].variable",
      "message": "variable not in constraints"
    }
  ]
}
```

### heap_solver

专注于heap相关的约束的求解。

职责：基于 type_solver 的求解结果（不能推翻 type_solver 的结果，如有冲突返回 UNSAT），分析约束集合中每个变量的 heap 相关约束（包括 null 约束，引用的指向关系），生成每个变量的引用的指向类型。

输入：

```python
constraints: List[str]
source_context: Dict[str, Any]
heap_state: Dict[str, Any]
type_solver_output: 
```

输出：

```python
{
    "result": "SAT" | "UNSAT" | "UNKNOWN",  # 求解结果
    "valuation": [                          # SAT 时的估值列表
        {
            "variable": "head(ref)",
            "type": "LNode;",
            "newObject": true,
            "trueRef": true,
            "reference": 1
        }
    ]
}
```

### heap_solver_verifier

检验 heap_solver 求解结果的合理性（不使用 LLM）

职责：

1. 检验 JSON 格式是否符合要求
2. 检验变量名合法性（必须来自约束）
3. 检验是否符合 type_solver 的求解结果

输入：

```python
constraints: List[str]
heap_solver_output
```

输出：

```python
{
  "is_well_formed": false,
  "errors": [
    {
      "error_type": "INVALID_VARIABLE",
      "location": "valuation[0].variable",
      "message": "variable not in constraints"
    }
  ]
}
```

### refiner

在 type_solver_verifier 或者 heap_solver_verifier 检测结果不合理的情况下，根据 verifier 的输出进行修改和改进（使用 LLM）

输入：错误的结果以及 verifier 的输出

输出：改进后的正确结果

修改后继续返回 verifier 进行验证，如果还是不正确，再重试一次，还是不正确，则直接返回 UNKNOW

### initializer

基于 heap_solver 的求解结果，通过 javaUtils 查询相关类型以及类型的复杂类型field的构造函数信息，利用大模型生成构造所有符号化对象的 java 代码，要求包含完整的 import 等内容。

### code_executor_agent

执行 initializer 生成的代码，将通过执行构造函数链生成的对象转化成 JSON 对象

### code_executor_refiner

如果生成的代码在编译或执行时报错，尝试让大模型根据报错信息解决报错然后重新回到 code_executor_agent 进行执行

## logger

记录每个 agent 的输入输出，其中，涉及到 LLM 的 agent 记录与 LLM 的对话记录