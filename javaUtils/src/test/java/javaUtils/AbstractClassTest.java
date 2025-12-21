package javaUtils;

import java.util.*;

public class AbstractClassTest {
    public static void main(String[] args) {
        // Test that ValueAxis (abstract) includes concrete subclass constructors
        TypeInfoJson valueAxisInfo = TypeParseService.parseTypeInfo("org.jfree.chart.axis.ValueAxis");
        
        System.out.println("ValueAxis Type Info:");
        System.out.println("  Class Type: " + valueAxisInfo.getClassType());
        System.out.println("  Is Abstract: " + valueAxisInfo.isAbstract());
        
        Map<String, Map<String, LinkedHashMap<String, String>>> concreteSubclasses = 
            valueAxisInfo.getConcreteSubclassConstructors();
        
        if (concreteSubclasses != null && !concreteSubclasses.isEmpty()) {
            System.out.println("  Concrete Subclass Implementations:");
            for (String className : concreteSubclasses.keySet()) {
                System.out.println("    - " + className);
                Map<String, LinkedHashMap<String, String>> ctors = concreteSubclasses.get(className);
                for (String ctorSig : ctors.keySet()) {
                    System.out.println("      Constructor: " + ctorSig);
                }
            }
        } else {
            System.out.println("  ERROR: No concrete subclass constructors found!");
        }
    }
}
