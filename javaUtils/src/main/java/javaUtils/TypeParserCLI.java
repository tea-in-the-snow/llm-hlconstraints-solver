package javaUtils;

import soot.*;
import java.util.*;

/**
 * Command-line interface for TypeParseService
 * Usage: java -cp javautils-0.1.0-SNAPSHOT.jar javaUtils.TypeParserCLI <classname> [classpath]
 */
public class TypeParserCLI {
    
    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("Usage: java javaUtils.TypeParserCLI <classname> [classpath]");
            System.exit(1);
        }
        
        String typeSignature = args[0];
        String classpath = args.length > 1 ? args[1] : "";
        
        try {
            initSoot(classpath);
            TypeInfoJson result = TypeParseService.parseTypeInfo(typeSignature);
            
            if (result != null) {
                System.out.println(result.toJson());
            } else {
                System.err.println("Failed to parse type: " + typeSignature);
                System.exit(1);
            }
        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            e.printStackTrace(System.err);
            System.exit(1);
        }
    }
    
    private static void initSoot(String classpath) {
        soot.G.reset();
        soot.options.Options.v().set_prepend_classpath(true);
        soot.options.Options.v().set_allow_phantom_refs(true);
        
        if (classpath != null && !classpath.isEmpty()) {
            soot.options.Options.v().set_soot_classpath(classpath);
            String[] paths = classpath.split(":");
            soot.options.Options.v().set_process_dir(Arrays.asList(paths));
        }
        
        soot.options.Options.v().set_whole_program(true);
        soot.Scene.v().loadNecessaryClasses();
    }
}
