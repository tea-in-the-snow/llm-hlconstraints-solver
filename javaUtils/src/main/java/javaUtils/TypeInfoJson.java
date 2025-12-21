package javaUtils;

import java.util.*;

/**
 * JSON data model for storing type hierarchy and constructor information without external JSON libraries.
 */
public class TypeInfoJson {
    
    private String typeName;
    private String classType; // "class", "abstract class", "interface", "array", "primitive", "phantom"
    
    // For classes and abstract classes
    private String superClassName;
    private List<String> subClassName;
    private List<String> interfaces;
    
    // For interfaces
    private List<String> subInterfaceName;
    private List<String> implementedClassName;
    
    // Common fields
    private HashMap<String, String> fields;
    
    // Constructors: signature -> parameter map
    private Map<String, LinkedHashMap<String, String>> constructors;
    
    // Builder/factory methods: signature -> parameter map
    private Map<String, LinkedHashMap<String, String>> builders;
    
    // Methods (for interfaces)
    private List<String> methods;
    
    // For arrays
    private String innerClassName;
    private Integer dimension;
    
    // For abstract classes: constructors of concrete subclasses (for LLM to choose from)
    private Map<String, Map<String, LinkedHashMap<String, String>>> concreteSubclassConstructors;

    public TypeInfoJson() {
        this.subClassName = new ArrayList<>();
        this.interfaces = new ArrayList<>();
        this.subInterfaceName = new ArrayList<>();
        this.implementedClassName = new ArrayList<>();
        this.fields = new HashMap<>();
        this.constructors = new HashMap<>();
        this.builders = new HashMap<>();
        this.methods = new ArrayList<>();
        this.concreteSubclassConstructors = new HashMap<>();
    }

    public String getTypeName() { return typeName; }
    public TypeInfoJson setTypeName(String typeName) { this.typeName = typeName; return this; }
    public String getClassType() { return classType; }
    public TypeInfoJson setClassType(String classType) { this.classType = classType; return this; }
    public String getSuperClassName() { return superClassName; }
    public TypeInfoJson setSuperClassName(String superClassName) { this.superClassName = superClassName; return this; }
    public List<String> getSubClassName() { return subClassName; }
    public TypeInfoJson setSubClassName(List<String> subClassName) { this.subClassName = subClassName; return this; }
    public List<String> getInterfaces() { return interfaces; }
    public TypeInfoJson setInterfaces(List<String> interfaces) { this.interfaces = interfaces; return this; }
    public List<String> getSubInterfaceName() { return subInterfaceName; }
    public TypeInfoJson setSubInterfaceName(List<String> subInterfaceName) { this.subInterfaceName = subInterfaceName; return this; }
    public List<String> getImplementedClassName() { return implementedClassName; }
    public TypeInfoJson setImplementedClassName(List<String> implementedClassName) { this.implementedClassName = implementedClassName; return this; }
    public HashMap<String, String> getFields() { return fields; }
    public TypeInfoJson setFields(HashMap<String, String> fields) { this.fields = fields; return this; }
    public Map<String, LinkedHashMap<String, String>> getConstructors() { return constructors; }
    public TypeInfoJson setConstructors(Map<String, LinkedHashMap<String, String>> constructors) { this.constructors = constructors; return this; }
    public Map<String, LinkedHashMap<String, String>> getBuilders() { return builders; }
    public TypeInfoJson setBuilders(Map<String, LinkedHashMap<String, String>> builders) { this.builders = builders; return this; }
    public List<String> getMethods() { return methods; }
    public TypeInfoJson setMethods(List<String> methods) { this.methods = (methods == null) ? new ArrayList<>() : new ArrayList<>(methods); return this; }
    public String getInnerClassName() { return innerClassName; }
    public TypeInfoJson setInnerClassName(String innerClassName) { this.innerClassName = innerClassName; return this; }
    public Integer getDimension() { return dimension; }
    public TypeInfoJson setDimension(Integer dimension) { this.dimension = dimension; return this; }
    public Map<String, Map<String, LinkedHashMap<String, String>>> getConcreteSubclassConstructors() { return concreteSubclassConstructors; }
    public TypeInfoJson setConcreteSubclassConstructors(Map<String, Map<String, LinkedHashMap<String, String>>> concreteSubclassConstructors) {
        this.concreteSubclassConstructors = concreteSubclassConstructors;
        return this;
    }

    // Utility for JSON escaping
    private static String jescape(String s) {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder();
        b.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                case '\b': b.append("\\b"); break;
                case '\f': b.append("\\f"); break;
                default:
                    if (c < 0x20) {
                        b.append(String.format("\\u%04x", (int)c));
                    } else {
                        b.append(c);
                    }
            }
        }
        b.append('"');
        return b.toString();
    }

    private static String joinList(List<String> list) {
        if (list == null || list.isEmpty()) return "[]";
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < list.size(); i++) {
            if (i > 0) sb.append(',');
            sb.append(jescape(list.get(i)));
        }
        sb.append(']');
        return sb.toString();
    }

    private static String joinMap(Map<String, String> map) {
        if (map == null || map.isEmpty()) return "{}";
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, String> e : map.entrySet()) {
            if (!first) sb.append(',');
            first = false;
            sb.append(jescape(e.getKey())).append(':').append(jescape(e.getValue()));
        }
        sb.append('}');
        return sb.toString();
    }

    private static String joinNested(Map<String, LinkedHashMap<String, String>> map) {
        if (map == null || map.isEmpty()) return "{}";
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, LinkedHashMap<String, String>> e : map.entrySet()) {
            if (!first) sb.append(',');
            first = false;
            sb.append(jescape(e.getKey())).append(':').append(joinMap(e.getValue()));
        }
        sb.append('}');
        return sb.toString();
    }

    private static String joinDoubleNested(Map<String, Map<String, LinkedHashMap<String, String>>> map) {
        if (map == null || map.isEmpty()) return "{}";
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Map<String, LinkedHashMap<String, String>>> e : map.entrySet()) {
            if (!first) sb.append(',');
            first = false;
            sb.append(jescape(e.getKey())).append(':').append(joinNested(e.getValue()));
        }
        sb.append('}');
        return sb.toString();
    }

    /**
     * Manual JSON serialization without external libraries.
     */
    public String toJson() {
        StringBuilder sb = new StringBuilder();
        sb.append('{');
        sb.append("\"typeName\":").append(typeName == null ? "null" : jescape(typeName)).append(',');
        sb.append("\"classType\":").append(classType == null ? "null" : jescape(classType)).append(',');
        sb.append("\"superClassName\":").append(superClassName == null ? "null" : jescape(superClassName)).append(',');
        sb.append("\"subClassName\":").append(joinList(subClassName)).append(',');
        sb.append("\"interfaces\":").append(joinList(interfaces)).append(',');
        sb.append("\"subInterfaceName\":").append(joinList(subInterfaceName)).append(',');
        sb.append("\"implementedClassName\":").append(joinList(implementedClassName)).append(',');
        sb.append("\"fields\":").append(joinMap(fields)).append(',');
        sb.append("\"constructors\":").append(joinNested(constructors)).append(',');
        sb.append("\"builders\":").append(joinNested(builders)).append(',');
        sb.append("\"methods\":").append(joinList(methods)).append(',');
        sb.append("\"concreteSubclassConstructors\":").append(joinDoubleNested(concreteSubclassConstructors)).append(',');
        sb.append("\"innerClassName\":").append(innerClassName == null ? "null" : jescape(innerClassName)).append(',');
        sb.append("\"dimension\":").append(dimension == null ? "null" : dimension);
        sb.append('}');
        return sb.toString();
    }

    public String getSummary() {
        StringBuilder sb = new StringBuilder();
        sb.append("Type: ").append(typeName != null ? typeName : "Unknown").append('\n');
        sb.append("Classification: ").append(classType != null ? classType : "Unknown").append('\n');
        if (superClassName != null) sb.append("Superclass: ").append(superClassName).append('\n');
        if (subClassName != null && !subClassName.isEmpty()) sb.append("Subclasses: ").append(String.join(", ", subClassName)).append('\n');
        if (interfaces != null && !interfaces.isEmpty()) sb.append("Implements: ").append(String.join(", ", interfaces)).append('\n');
        if (implementedClassName != null && !implementedClassName.isEmpty()) sb.append("Implemented by: ").append(String.join(", ", implementedClassName)).append('\n');
        if (constructors != null && !constructors.isEmpty()) sb.append("Constructors: ").append(constructors.size()).append('\n');
        if (builders != null && !builders.isEmpty()) sb.append("Builder methods: ").append(builders.size()).append('\n');
        if (fields != null && !fields.isEmpty()) sb.append("Fields: ").append(fields.size()).append('\n');
        return sb.toString();
    }

    public boolean isInterface() { return "interface".equals(classType); }
    public boolean isAbstract() { return "abstract class".equals(classType); }
    public boolean isConcreteClass() { return "class".equals(classType); }
    public boolean isArray() { return "array".equals(classType); }
    public boolean isPrimitive() { return "primitive".equals(classType); }

    public List<String> getConstructorSignatures() { return constructors == null ? new ArrayList<>() : new ArrayList<>(constructors.keySet()); }
    public List<String> getBuilderSignatures() { return builders == null ? new ArrayList<>() : new ArrayList<>(builders.keySet()); }

    public Set<String> getAllRelatedTypes() {
        Set<String> relatedTypes = new HashSet<>();
        if (superClassName != null) relatedTypes.add(superClassName);
        if (subClassName != null) relatedTypes.addAll(subClassName);
        if (interfaces != null) relatedTypes.addAll(interfaces);
        if (subInterfaceName != null) relatedTypes.addAll(subInterfaceName);
        if (implementedClassName != null) relatedTypes.addAll(implementedClassName);
        return relatedTypes;
    }
}
