package javaUtils;

import soot.*;
import soot.util.Chain;
import java.util.*;
import java.util.stream.Collectors;
import java.util.concurrent.LinkedBlockingQueue;

/**
 * Service for parsing type hierarchy and constructor information based on type signature.
 */
public class TypeParseService {

    private final static HashMap<String, TypeInfoJson> handledTypes = new HashMap<>();
    private final static Queue<SootClass> handleQueue = new LinkedBlockingQueue<>();

    public static TypeInfoJson parseTypeInfo(String typeSignature) {
        handledTypes.clear();
        handleQueue.clear();
        SootClass sootClass = Scene.v().getSootClass(typeSignature);
        if (sootClass == null) {
            throw new RuntimeException("Cannot find type: " + typeSignature);
        }
        handleQueue.add(sootClass);
        while (!handleQueue.isEmpty()) {
            parseClassInfo(handleQueue.poll());
        }
        return handledTypes.get(typeSignature);
    }

    public static Map<String, TypeInfoJson> parseMultipleTypes(List<String> typeSignatures) {
        handledTypes.clear();
        handleQueue.clear();
        for (String typeSignature : typeSignatures) {
            try {
                SootClass sootClass = Scene.v().getSootClass(typeSignature);
                if (sootClass != null) handleQueue.add(sootClass);
            } catch (Exception e) {
                System.err.println("Error loading type: " + typeSignature + " - " + e.getMessage());
            }
        }
        while (!handleQueue.isEmpty()) parseClassInfo(handleQueue.poll());
        Map<String, TypeInfoJson> result = new HashMap<>();
        for (String typeSignature : typeSignatures) {
            if (handledTypes.containsKey(typeSignature)) result.put(typeSignature, handledTypes.get(typeSignature));
        }
        return result;
    }

    public static Map<String, TypeInfoJson> getAllParsedTypes() { return new HashMap<>(handledTypes); }

    private static SootClass parseType(Type type) {
        if (type instanceof RefType) {
            return ((RefType) type).getSootClass();
        } else if (type instanceof ArrayType) {
            ArrayType arrayType = (ArrayType) type;
            Type baseType = arrayType.baseType;
            if (baseType instanceof PrimType) {
                handledTypes.put(arrayType.toString(), new TypeInfoJson()
                        .setClassType("array")
                        .setInnerClassName(baseType.toQuotedString())
                        .setDimension(arrayType.numDimensions));
            } else {
                handledTypes.put(arrayType.toString(), new TypeInfoJson()
                        .setClassType("array")
                        .setInnerClassName(((RefType) baseType).getClassName())
                        .setDimension(arrayType.numDimensions));
            }
            return parseType(baseType);
        } else if (type instanceof PrimType) {
            handledTypes.put(type.toQuotedString(), new TypeInfoJson()
                    .setClassType("primitive")
                    .setTypeName(type.toQuotedString()));
            return null;
        }
        return null;
    }

    private static void parseClassInfo(SootClass sootClass) {
        if (handledTypes.containsKey(sootClass.getName())) return;
        if (sootClass.isPhantom()) {
            handledTypes.put(sootClass.getName(), new TypeInfoJson()
                    .setClassType("phantom")
                    .setTypeName(sootClass.getName()));
            return;
        }
        if (sootClass.isInterface()) parseInterfaceInfo(sootClass);
        else parseClassOrAbstractClassInfo(sootClass);
    }

    private static void parseInterfaceInfo(SootClass sootClass) {
        List<SootClass> subInterfaces = new ArrayList<>();
        try { if (Scene.v().getActiveHierarchy() != null) subInterfaces = Scene.v().getActiveHierarchy().getDirectSubinterfacesOf(sootClass); } catch (Exception e) { System.err.println("Error getting sub-interfaces: " + e.getMessage()); }
        handleQueue.addAll(subInterfaces);
        List<String> subInterfacesName = subInterfaces.stream().map(SootClass::getName).collect(Collectors.toList());

        List<SootClass> implementers = new ArrayList<>();
        try { if (Scene.v().getActiveHierarchy() != null) implementers = Scene.v().getActiveHierarchy().getDirectImplementersOf(sootClass); } catch (Exception e) { System.err.println("Error getting implementers: " + e.getMessage()); }
        handleQueue.addAll(implementers);
        List<String> implementersName = implementers.stream().map(SootClass::getName).collect(Collectors.toList());

        HashMap<String, String> fields = new HashMap<>();
        for (SootField field : sootClass.getFields()) {
            if (field.isPublic() || field.isProtected()) {
                fields.put(field.getName(), field.getType().toString());
                SootClass sc = parseType(field.getType());
                if (sc != null) {
                    handleQueue.add(sc);
                    // If field type is an interface or abstract class, fetch its implementers/subclasses
                    handleImplementersOrSubclasses(sc);
                }
            }
        }

        List<String> methods = new ArrayList<>();
        for (SootMethod method : sootClass.getMethods()) {
            if (method.isPublic() && !method.isConstructor()) methods.add(getMethodSignature(method));
        }

        handledTypes.put(sootClass.getName(), new TypeInfoJson()
                .setClassType("interface")
                .setTypeName(sootClass.getName())
                .setSubInterfaceName(subInterfacesName)
                .setImplementedClassName(implementersName)
                .setFields(fields)
                .setMethods(methods));
    }

    private static void parseClassOrAbstractClassInfo(SootClass sootClass) {
        String classType = sootClass.isAbstract() ? "abstract class" : "class";
        String superClassName = null;
        if (sootClass.hasSuperclass()) { superClassName = sootClass.getSuperclass().getName(); handleQueue.add(sootClass.getSuperclass()); }

        List<SootClass> subClasses = new ArrayList<>();
        try {
            if (Scene.v().getActiveHierarchy() != null) {
                subClasses = Scene.v().getActiveHierarchy().getDirectSubclassesOf(sootClass);
                subClasses = subClasses.stream().filter(SootClass::isPublic).collect(Collectors.toList());
            }
        } catch (Exception e) { System.err.println("Error getting subclasses: " + e.getMessage()); }
        handleQueue.addAll(subClasses);
        List<String> subClassesName = subClasses.stream().map(SootClass::getName).collect(Collectors.toList());

        Chain<SootClass> interfaces = sootClass.getInterfaces();
        List<String> interfacesName = new ArrayList<>();
        for (SootClass sc : interfaces) {
            handleQueue.add(sc);
            interfacesName.add(sc.getName());
        }

        HashMap<String, String> fields = new HashMap<>();
        for (SootField field : sootClass.getFields()) {
            if (field.isPublic() || field.isProtected()) {
                fields.put(field.getName(), field.getType().toString());
                SootClass sc = parseType(field.getType());
                if (sc != null) {
                    handleQueue.add(sc);
                    // If field type is an interface or abstract class, fetch its implementers/subclasses
                    handleImplementersOrSubclasses(sc);
                }
            }
        }

        List<SootMethod> constructorMethods = sootClass.getMethods().stream()
                .filter(m -> m.isConstructor() && (m.isPublic() || m.isProtected()))
                .collect(Collectors.toList());
        Map<String, LinkedHashMap<String, String>> constructors = new HashMap<>();
        for (SootMethod constructor : constructorMethods) {
            String signature = getConstructorSignature(constructor);
            LinkedHashMap<String, String> params = getMethodParameters(constructor);
            constructors.put(signature, params);
            for (Type paramType : constructor.getParameterTypes()) {
                SootClass sc = parseType(paramType);
                if (sc != null) {
                    handleQueue.add(sc);
                    // If parameter type is an interface or abstract class, fetch its implementers/subclasses
                    handleImplementersOrSubclasses(sc);
                }
            }
        }

        List<SootMethod> builderMethods = sootClass.getMethods().stream()
                .filter(m -> m.isStatic() && m.isPublic() && m.getReturnType().equals(sootClass.getType()))
                .collect(Collectors.toList());
        Map<String, LinkedHashMap<String, String>> builders = new HashMap<>();
        for (SootMethod builder : builderMethods) {
            String signature = getMethodSignature(builder);
            LinkedHashMap<String, String> params = getMethodParameters(builder);
            builders.put(signature, params);
            for (Type paramType : builder.getParameterTypes()) {
                SootClass sc = parseType(paramType);
                if (sc != null) {
                    handleQueue.add(sc);
                    // If parameter type is an interface or abstract class, fetch its implementers/subclasses
                    handleImplementersOrSubclasses(sc);
                }
            }
        }

        // If this is an abstract class, collect constructors of concrete subclasses
        Map<String, Map<String, LinkedHashMap<String, String>>> concreteSubclassConstructors = new HashMap<>();
        if (sootClass.isAbstract()) {
            for (SootClass subClass : subClasses) {
                if (!subClass.isAbstract() && !subClass.isInterface() && subClass.isPublic()) {
                    // Get constructors of concrete subclass
                    List<SootMethod> subCtors = subClass.getMethods().stream()
                            .filter(m -> m.isConstructor() && (m.isPublic() || m.isProtected()))
                            .collect(Collectors.toList());
                    if (!subCtors.isEmpty()) {
                        Map<String, LinkedHashMap<String, String>> subClassConstructors = new HashMap<>();
                        for (SootMethod subCtor : subCtors) {
                            String signature = getConstructorSignature(subCtor);
                            LinkedHashMap<String, String> params = getMethodParameters(subCtor);
                            subClassConstructors.put(signature, params);
                        }
                        concreteSubclassConstructors.put(subClass.getName(), subClassConstructors);
                    }
                }
            }
        }

        handledTypes.put(sootClass.getName(), new TypeInfoJson()
                .setClassType(classType)
                .setTypeName(sootClass.getName())
                .setSuperClassName(superClassName)
                .setSubClassName(subClassesName)
                .setInterfaces(interfacesName)
                .setFields(fields)
                .setConstructors(constructors)
                .setBuilders(builders)
                .setConcreteSubclassConstructors(concreteSubclassConstructors));
    }

    private static String getConstructorSignature(SootMethod constructor) {
        StringBuilder sb = new StringBuilder();
        sb.append(constructor.getDeclaringClass().getShortName()).append('(');
        List<Type> paramTypes = constructor.getParameterTypes();
        for (int i = 0; i < paramTypes.size(); i++) { if (i > 0) sb.append(','); sb.append(getSimpleTypeName(paramTypes.get(i))).append(" param").append(i); }
        sb.append(')');
        return sb.toString();
    }

    private static String getMethodSignature(SootMethod method) {
        StringBuilder sb = new StringBuilder();
        sb.append(getSimpleTypeName(method.getReturnType())).append(' ').append(method.getName()).append('(');
        List<Type> paramTypes = method.getParameterTypes();
        for (int i = 0; i < paramTypes.size(); i++) { if (i > 0) sb.append(','); sb.append(getSimpleTypeName(paramTypes.get(i))).append(" param").append(i); }
        sb.append(')');
        return sb.toString();
    }

    private static LinkedHashMap<String, String> getMethodParameters(SootMethod method) {
        LinkedHashMap<String, String> params = new LinkedHashMap<>();
        List<Type> paramTypes = method.getParameterTypes();
        for (int i = 0; i < paramTypes.size(); i++) params.put("param" + i, paramTypes.get(i).toString());
        return params;
    }

    private static String getSimpleTypeName(Type type) {
        String typeName = type.toString();
        int idx = typeName.lastIndexOf('.');
        return idx >= 0 ? typeName.substring(idx + 1) : typeName;
    }

    /**
     * When a parameter type is an interface or abstract class,
     * add its implementers (for interfaces) or subclasses (for abstract classes) to the queue.
     */
    private static void handleImplementersOrSubclasses(SootClass sootClass) {
        if (sootClass.isInterface()) {
            try {
                if (Scene.v().getActiveHierarchy() != null) {
                    List<SootClass> implementers = Scene.v().getActiveHierarchy().getDirectImplementersOf(sootClass);
                    for (SootClass impl : implementers) {
                        if (!handledTypes.containsKey(impl.getName())) {
                            handleQueue.add(impl);
                        }
                    }
                }
            } catch (Exception e) {
                System.err.println("Error getting implementers for " + sootClass.getName() + ": " + e.getMessage());
            }
        } else if (sootClass.isAbstract()) {
            try {
                if (Scene.v().getActiveHierarchy() != null) {
                    List<SootClass> subClasses = Scene.v().getActiveHierarchy().getDirectSubclassesOf(sootClass);
                    for (SootClass subClass : subClasses) {
                        if (!handledTypes.containsKey(subClass.getName())) {
                            handleQueue.add(subClass);
                        }
                    }
                }
            } catch (Exception e) {
                System.err.println("Error getting subclasses for " + sootClass.getName() + ": " + e.getMessage());
            }
        }
    }

    public static void clearCache() { handledTypes.clear(); handleQueue.clear(); }
}
