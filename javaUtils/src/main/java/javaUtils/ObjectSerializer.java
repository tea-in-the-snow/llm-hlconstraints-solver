package javaUtils;

import java.lang.reflect.Array;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.*;

/**
 * ObjectSerializer: Reflection-based JSON serialization for Java objects.
 * 
 * Produces JSON representation of objects including their fields, types, and references.
 * Handles primitives, strings, arrays, collections, and nested objects.
 */
public class ObjectSerializer {

    private static final int MAX_DEPTH = 10;
    private static final int MAX_COLLECTION_SIZE = 100;

    /**
     * Serialize an object to JSON string.
     * 
     * @param obj The object to serialize
     * @param varName The variable name for this object
     * @return JSON string representation
     */
    public static String toJson(Object obj, String varName) {
        Set<Integer> visited = new HashSet<>();
        StringBuilder sb = new StringBuilder();
        serializeObject(obj, varName, sb, visited, 0);
        return sb.toString();
    }

    private static void serializeObject(Object obj, String varName, StringBuilder sb, Set<Integer> visited, int depth) {
        if (depth > MAX_DEPTH) {
            sb.append("{\"error\":\"max_depth_exceeded\"}");
            return;
        }

        if (obj == null) {
            sb.append("{\"variable\":\"").append(escape(varName)).append("\",\"value\":null}");
            return;
        }

        Class<?> clazz = obj.getClass();
        int objId = System.identityHashCode(obj);

        // Check for circular references
        if (visited.contains(objId)) {
            sb.append("{\"variable\":\"").append(escape(varName)).append("\",");
            sb.append("\"class\":\"").append(escape(clazz.getName())).append("\",");
            sb.append("\"reference\":\"@").append(objId).append("\"}");
            return;
        }
        visited.add(objId);

        sb.append("{");
        sb.append("\"variable\":\"").append(escape(varName)).append("\",");
        sb.append("\"class\":\"").append(escape(clazz.getName())).append("\",");
        sb.append("\"reference\":\"@").append(objId).append("\",");

        // Handle primitives and primitive wrappers
        if (isPrimitiveOrWrapper(clazz)) {
            sb.append("\"value\":").append(toPrimitiveJson(obj));
            sb.append("}");
            return;
        }

        // Handle Strings
        if (obj instanceof String) {
            sb.append("\"value\":\"").append(escape((String) obj)).append("\"");
            sb.append("}");
            return;
        }

        // Handle arrays
        if (clazz.isArray()) {
            sb.append("\"array\":true,");
            sb.append("\"length\":").append(Array.getLength(obj)).append(",");
            sb.append("\"elements\":[");
            int len = Math.min(Array.getLength(obj), MAX_COLLECTION_SIZE);
            for (int i = 0; i < len; i++) {
                if (i > 0) sb.append(",");
                Object element = Array.get(obj, i);
                serializeObject(element, varName + "[" + i + "]", sb, visited, depth + 1);
            }
            sb.append("]}");
            return;
        }

        // Handle collections
        if (obj instanceof Collection) {
            Collection<?> coll = (Collection<?>) obj;
            sb.append("\"collection\":true,");
            sb.append("\"size\":").append(coll.size()).append(",");
            sb.append("\"elements\":[");
            int count = 0;
            for (Object element : coll) {
                if (count >= MAX_COLLECTION_SIZE) break;
                if (count > 0) sb.append(",");
                serializeObject(element, varName + "[" + count + "]", sb, visited, depth + 1);
                count++;
            }
            sb.append("]}");
            return;
        }

        // Handle maps
        if (obj instanceof Map) {
            Map<?, ?> map = (Map<?, ?>) obj;
            sb.append("\"map\":true,");
            sb.append("\"size\":").append(map.size()).append(",");
            sb.append("\"entries\":[");
            int count = 0;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (count >= MAX_COLLECTION_SIZE) break;
                if (count > 0) sb.append(",");
                sb.append("{\"key\":");
                serializeObject(entry.getKey(), varName + ".key" + count, sb, visited, depth + 1);
                sb.append(",\"value\":");
                serializeObject(entry.getValue(), varName + ".value" + count, sb, visited, depth + 1);
                sb.append("}");
                count++;
            }
            sb.append("]}");
            return;
        }

        // Handle regular objects - serialize fields
        sb.append("\"fields\":{");
        Field[] fields = getAllFields(clazz);
        boolean first = true;
        for (Field field : fields) {
            // Skip static fields
            if (Modifier.isStatic(field.getModifiers())) {
                continue;
            }

            field.setAccessible(true);
            try {
                Object value = field.get(obj);
                if (!first) sb.append(",");
                first = false;

                sb.append("\"").append(escape(field.getName())).append("\":");
                serializeObject(value, varName + "." + field.getName(), sb, visited, depth + 1);
            } catch (IllegalAccessException e) {
                // Skip fields we can't access
                if (!first) sb.append(",");
                first = false;
                sb.append("\"").append(escape(field.getName())).append("\":");
                sb.append("{\"error\":\"access_denied\"}");
            }
        }
        sb.append("}}");
    }

    private static Field[] getAllFields(Class<?> clazz) {
        List<Field> fields = new ArrayList<>();
        while (clazz != null && clazz != Object.class) {
            fields.addAll(Arrays.asList(clazz.getDeclaredFields()));
            clazz = clazz.getSuperclass();
        }
        return fields.toArray(new Field[0]);
    }

    private static boolean isPrimitiveOrWrapper(Class<?> clazz) {
        return clazz.isPrimitive()
                || clazz == Boolean.class
                || clazz == Byte.class
                || clazz == Character.class
                || clazz == Short.class
                || clazz == Integer.class
                || clazz == Long.class
                || clazz == Float.class
                || clazz == Double.class;
    }

    private static String toPrimitiveJson(Object obj) {
        if (obj instanceof Character) {
            return "\"" + escape(obj.toString()) + "\"";
        }
        return obj.toString();
    }

    private static String escape(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }
}
