# Java Type Parse Service

这个工具提供了根据类型签名获取Java类的详细信息的功能，包括：
- 所有构造函数签名
- 类的继承关系（父类、子类）
- 接口或抽象类的所有实现类
- 字段信息
- 静态工厂方法（Builder模式）

## 文件结构

```
javaUtils/
├── TypeParseService.java      # 主服务类，负责解析类型信息
├── TypeInfoJson.java           # 数据模型类，存储类型信息
├── type_parse_wrapper.py      # Python包装器，供Python代码调用
└── README.md                   # 本文档
```

## Java类说明

### TypeParseService.java

主要的类型解析服务类，提供以下静态方法：

#### `parseTypeInfo(String typeSignature)`
根据类型签名解析单个类型的完整信息。

**参数：**
- `typeSignature`: 完全限定的类名，如 "java.util.ArrayList"

**返回：**
- `TypeInfoJson`: 包含所有类型信息的对象

**示例：**
```java
TypeInfoJson info = TypeParseService.parseTypeInfo("java.util.ArrayList");
System.out.println(info.toJson());
```

#### `parseMultipleTypes(List<String> typeSignatures)`
批量解析多个类型的信息。

**参数：**
- `typeSignatures`: 类型签名列表

**返回：**
- `Map<String, TypeInfoJson>`: 类型签名到类型信息的映射

#### `getAllParsedTypes()`
获取所有已解析的类型信息。

**返回：**
- `Map<String, TypeInfoJson>`: 所有已解析类型的映射

#### `clearCache()`
清除所有缓存的类型信息。

### TypeInfoJson.java

数据模型类，包含以下信息：

**字段：**
- `typeName`: 类型名称
- `classType`: 类型分类（"class", "abstract class", "interface", "array", "primitive"）
- `superClassName`: 父类名称
- `subClassName`: 子类名称列表
- `interfaces`: 实现的接口列表
- `subInterfaceName`: 子接口列表（针对接口）
- `implementedClassName`: 实现类列表（针对接口）
- `fields`: 字段映射（字段名 -> 类型）
- `constructors`: 构造函数映射（签名 -> 参数映射）
- `builders`: 静态工厂方法映射（签名 -> 参数映射）
- `methods`: 方法列表（针对接口）
- `innerClassName`: 数组的元素类型
- `dimension`: 数组维度

**常用方法：**
- `toJson()`: 转换为格式化的JSON字符串
- `toCompactJson()`: 转换为紧凑的JSON字符串
- `fromJson(String json)`: 从JSON字符串创建对象
- `getSummary()`: 获取类型信息摘要
- `isInterface()`: 是否为接口
- `isAbstract()`: 是否为抽象类
- `isConcreteClass()`: 是否为具体类
- `getConstructorSignatures()`: 获取所有构造函数签名
- `getBuilderSignatures()`: 获取所有工厂方法签名
- `getAllRelatedTypes()`: 获取所有相关类型

## Python包装器使用说明

### TypeParseServiceWrapper类

Python包装器类，提供以下方法：

#### `parse_type_info(type_signature: str) -> Optional[TypeInfo]`
解析单个类型的信息。

**示例：**
```python
from javaUtils.type_parse_wrapper import TypeParseServiceWrapper

service = TypeParseServiceWrapper()
type_info = service.parse_type_info("java.util.ArrayList")

if type_info:
    print(type_info.get_summary())
    print("Constructors:", type_info.get_constructor_signatures())
```

#### `parse_multiple_types(type_signatures: List[str]) -> Dict[str, TypeInfo]`
批量解析多个类型。

**示例：**
```python
types = ["java.util.ArrayList", "java.util.HashMap"]
result = service.parse_multiple_types(types)

for type_sig, info in result.items():
    print(f"{type_sig}: {info.class_type}")
```

#### `get_constructors(type_signature: str) -> List[str]`
获取类的所有构造函数签名。

**示例：**
```python
constructors = service.get_constructors("java.util.ArrayList")
for ctor in constructors:
    print(ctor)
```

#### `get_inheritance_hierarchy(type_signature: str) -> Dict`
获取完整的继承层次结构。

**示例：**
```python
hierarchy = service.get_inheritance_hierarchy("java.util.AbstractList")
print("Superclass:", hierarchy.get('superclass'))
print("Subclasses:", hierarchy.get('subclasses'))
print("Interfaces:", hierarchy.get('interfaces'))
```

#### `get_all_implementations(type_signature: str) -> List[str]`
获取接口或抽象类的所有实现类。

**示例：**
```python
# 对于接口
implementations = service.get_all_implementations("java.util.List")
print("List implementations:", implementations)

# 对于抽象类
implementations = service.get_all_implementations("java.util.AbstractList")
print("AbstractList subclasses:", implementations)
```

### TypeInfo类

Python中的类型信息表示，包含以下属性和方法：

**属性：**
- `type_name`: 类型名称
- `class_type`: 类型分类
- `super_class_name`: 父类名称
- `sub_class_names`: 子类列表
- `interfaces`: 接口列表
- `implemented_class_names`: 实现类列表
- `fields`: 字段字典
- `constructors`: 构造函数字典
- `builders`: 工厂方法字典

**方法：**
- `is_interface()`: 是否为接口
- `is_abstract()`: 是否为抽象类
- `is_concrete_class()`: 是否为具体类
- `get_constructor_signatures()`: 获取构造函数签名列表
- `get_builder_signatures()`: 获取工厂方法签名列表
- `get_all_related_types()`: 获取所有相关类型
- `get_summary()`: 获取摘要信息

## Agent集成示例

### 在Type Solver Agent中使用

```python
from javaUtils.type_parse_wrapper import TypeParseServiceWrapper

class TypeSolverAgent:
    def __init__(self):
        self.type_service = TypeParseServiceWrapper()
    
    def solve_type_constraint(self, type_signature: str):
        """解决类型约束"""
        # 获取类型信息
        type_info = self.type_service.parse_type_info(type_signature)
        
        if not type_info:
            return None
        
        # 如果是接口或抽象类，获取所有实现类
        if type_info.is_interface() or type_info.is_abstract():
            implementations = type_info.implemented_class_names if type_info.is_interface() else type_info.sub_class_names
            print(f"Type {type_signature} has implementations: {implementations}")
            return implementations
        
        # 如果是具体类，获取构造函数
        if type_info.is_concrete_class():
            constructors = type_info.get_constructor_signatures()
            print(f"Type {type_signature} has constructors: {constructors}")
            return constructors
        
        return None
```

### 在Heap Solver Agent中使用

```python
from javaUtils.type_parse_wrapper import TypeParseServiceWrapper

class HeapSolverAgent:
    def __init__(self):
        self.type_service = TypeParseServiceWrapper()
    
    def create_object_instance(self, type_signature: str):
        """创建对象实例代码"""
        type_info = self.type_service.parse_type_info(type_signature)
        
        if not type_info:
            return None
        
        # 优先使用无参构造函数
        constructors = type_info.constructors
        if constructors:
            for ctor_sig, params in constructors.items():
                if not params:  # 无参构造函数
                    return f"new {type_info.type_name}()"
            
            # 如果没有无参构造，返回第一个构造函数的模板
            first_ctor = list(constructors.keys())[0]
            return f"// Use constructor: {first_ctor}"
        
        # 尝试使用工厂方法
        builders = type_info.builders
        if builders:
            first_builder = list(builders.keys())[0]
            return f"// Use builder: {first_builder}"
        
        return None
```

## 配置说明

在 `config.py` 中添加了以下配置：

```python
# Java utilities configuration
JAVA_UTILS_PATH = "/home/shaoran/repos/new-jdart/llm-hlconstraints-solver/javaUtils"
TYPE_PARSE_SERVICE_CLASS = "javaUtils.TypeParseService"
TYPE_INFO_JSON_CLASS = "javaUtils.TypeInfoJson"
```

这些配置指定了：
- `JAVA_UTILS_PATH`: Java工具类的路径
- `TYPE_PARSE_SERVICE_CLASS`: 类型解析服务的完全限定类名
- `TYPE_INFO_JSON_CLASS`: 类型信息数据模型的完全限定类名

## 编译和运行

### 使用 Maven 构建

```bash
cd llm-hlconstraints-solver/javaUtils
mvn -q clean package
```

生成产物：`target/javautils-0.1.0-SNAPSHOT.jar`

依赖管理：通过 `pom.xml` 引入 Soot（`ca.mcgill.sable:soot:4.1.0`）。本模块不再依赖 Gson，`TypeInfoJson` 已实现手工 JSON 序列化（`toJson()`）。

### 从Python调用

```python
from javaUtils.type_parse_wrapper import TypeParseServiceWrapper

# 初始化服务
service = TypeParseServiceWrapper()

# 使用服务
type_info = service.parse_type_info("your.package.ClassName")
```

## 注意事项

1. **Soot初始化**：使用前需要正确初始化Soot，包括设置classpath和加载必要的类。

2. **类路径配置**：确保 `config.py` 中的 `CLASS_PATH` 和 `SOURCE_PATH` 配置正确。

3. **依赖库**：需要以下Java库：
    - Soot framework (用于字节码分析)

4. **性能考虑**：解析大量类型时会消耗时间，建议使用 `parseMultipleTypes` 批量处理，或使用缓存机制。

5. **错误处理**：对于找不到的类或phantom类，服务会返回简化的类型信息或抛出异常。

## 扩展功能

可以根据需要扩展以下功能：

1. **方法签名解析**：添加对普通方法的详细解析
2. **注解信息**：解析类和方法的注解
3. **泛型支持**：更好地处理泛型类型
4. **依赖分析**：分析类之间的依赖关系
5. **缓存优化**：实现持久化缓存以提高性能

## 示例输出

### ArrayList的类型信息

```json
{
  "typeName": "java.util.ArrayList",
  "classType": "class",
  "superClassName": "java.util.AbstractList",
  "subClassName": [],
  "interfaces": ["java.util.List", "java.util.RandomAccess", "java.lang.Cloneable", "java.io.Serializable"],
  "fields": {
    "elementData": "java.lang.Object[]",
    "size": "int"
  },
  "constructors": {
    "ArrayList()": {},
    "ArrayList(int initialCapacity)": {
      "initialCapacity": "int"
    },
    "ArrayList(Collection c)": {
      "c": "java.util.Collection"
    }
  },
  "builders": {}
}
```

## 常见问题

**Q: 如何处理phantom类？**
A: Phantom类是Soot无法完全加载的类。服务会为这些类返回简化的信息，标记为 "phantom" 类型。

**Q: 如何获取私有构造函数？**
A: 当前实现只返回public和protected的构造函数。如需私有构造函数，可以修改 `parseClassOrAbstractClassInfo` 方法的过滤条件。

**Q: 支持Java 8+的特性吗？**
A: 支持。只要Soot能够正确解析目标Java版本的字节码。

**Q: 如何集成到现有的agent中？**
A: 在agent的 `__init__` 方法中创建 `TypeParseServiceWrapper` 实例，然后在需要类型信息时调用相应方法。
