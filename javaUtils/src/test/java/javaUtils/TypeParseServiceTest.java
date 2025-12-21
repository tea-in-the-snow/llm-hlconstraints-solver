package javaUtils;

import org.junit.Test;
import static org.junit.Assert.*;
import java.util.*;

/**
 * Test TypeParseService by parsing commons-lang3 StringUtils class
 */
public class TypeParseServiceTest {

    @Test
    public void testParseStringUtilsConstructors() {
        // Initialize Soot with commons-lang3 in classpath
        initSoot();
        
        // Parse StringUtils class
        String typeSignature = "org.apache.commons.lang3.StringUtils";
        TypeInfoJson info = TypeParseService.parseTypeInfo(typeSignature);
        
        // Assertions
        assertNotNull("StringUtils info should not be null", info);
        assertEquals("StringUtils should be a class", "class", info.getClassType());
        assertEquals("StringUtils should be named correctly", typeSignature, info.getTypeName());
        
        // Check constructors
        List<String> constructorSigs = info.getConstructorSignatures();
        assertNotNull("Constructor signatures should not be null", constructorSigs);
        
        System.out.println("StringUtils Type Info:");
        System.out.println("  Class Type: " + info.getClassType());
        System.out.println("  Constructor Count: " + constructorSigs.size());
        System.out.println("  Constructors:");
        for (String sig : constructorSigs) {
            System.out.println("    - " + sig);
        }
        System.out.println();
    }

    @Test
    public void testParseArrayUtilsConstructors() {
        initSoot();
        
        String typeSignature = "org.apache.commons.lang3.ArrayUtils";
        TypeInfoJson info = TypeParseService.parseTypeInfo(typeSignature);
        
        assertNotNull("ArrayUtils info should not be null", info);
        assertEquals("ArrayUtils should be a class", "class", info.getClassType());
        
        List<String> constructorSigs = info.getConstructorSignatures();
        assertNotNull("Constructor signatures should not be null", constructorSigs);
        
        System.out.println("ArrayUtils Type Info:");
        System.out.println("  Class Type: " + info.getClassType());
        System.out.println("  Constructor Count: " + constructorSigs.size());
        System.out.println("  Constructors:");
        for (String sig : constructorSigs) {
            System.out.println("    - " + sig);
        }
        System.out.println();
    }

    @Test
    public void testParseMultipleTypes() {
        initSoot();
        
        List<String> typeSignatures = Arrays.asList(
            "org.apache.commons.lang3.StringUtils",
            "org.apache.commons.lang3.ArrayUtils",
            "org.apache.commons.lang3.NumberUtils"
        );
        
        Map<String, TypeInfoJson> results = TypeParseService.parseMultipleTypes(typeSignatures);
        
        assertNotNull("Results should not be null", results);
        assertTrue("Should have parsed at least one type", results.size() > 0);
        
        System.out.println("Parsed Multiple Types:");
        for (Map.Entry<String, TypeInfoJson> entry : results.entrySet()) {
            String typeName = entry.getKey();
            TypeInfoJson info = entry.getValue();
            System.out.println("  " + typeName + ": " + info.getConstructorSignatures().size() + " constructors");
        }
        System.out.println();
    }

    @Test
    public void testGetConstructorDetails() {
        initSoot();
        
        String typeSignature = "org.apache.commons.lang3.StringUtils";
        TypeInfoJson info = TypeParseService.parseTypeInfo(typeSignature);
        
        assertNotNull("Info should not be null", info);
        
        // Get constructors with their parameters
        Map<String, LinkedHashMap<String, String>> constructors = info.getConstructors();
        assertNotNull("Constructors map should not be null", constructors);
        
        System.out.println("StringUtils Constructor Details:");
        for (Map.Entry<String, LinkedHashMap<String, String>> ctor : constructors.entrySet()) {
            System.out.println("  Signature: " + ctor.getKey());
            LinkedHashMap<String, String> params = ctor.getValue();
            if (params.isEmpty()) {
                System.out.println("    (no parameters)");
            } else {
                for (Map.Entry<String, String> param : params.entrySet()) {
                    System.out.println("    - " + param.getKey() + ": " + param.getValue());
                }
            }
        }
        System.out.println();
    }

    @Test
    public void testJsonSerialization() {
        initSoot();
        
        String typeSignature = "org.apache.commons.lang3.StringUtils";
        TypeInfoJson info = TypeParseService.parseTypeInfo(typeSignature);
        
        assertNotNull("Info should not be null", info);
        
        // Test JSON serialization
        String json = info.toJson();
        assertNotNull("JSON should not be null", json);
        assertTrue("JSON should be non-empty", json.length() > 0);
        assertTrue("JSON should contain type name", json.contains(typeSignature));
        
        System.out.println("StringUtils JSON Output:");
        System.out.println(json);
        System.out.println();
    }

    private void initSoot() {
        // Initialize Soot with commons-lang3 library
        soot.G.reset();
        soot.options.Options.v().set_prepend_classpath(true);
        soot.options.Options.v().set_allow_phantom_refs(true);
        
        // Set classpath to include commons-lang3
        String commonsLangPath = "/home/shaoran/src/java-libs/commons-lang/target/commons-lang3-3.13.0.jar";
        soot.options.Options.v().set_soot_classpath(commonsLangPath);
        soot.options.Options.v().set_process_dir(Arrays.asList(commonsLangPath.split(",")));
        soot.options.Options.v().set_whole_program(true);
        
        soot.Scene.v().loadNecessaryClasses();
    }
}
