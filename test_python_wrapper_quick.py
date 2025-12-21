"""
Quick Python wrapper test with timeout.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'javaUtils'))

from type_parse_wrapper import TypeParseServiceWrapper


def quick_test():
    """Quick test with single class"""
    jfreechart_classpath = "/home/shaoran/src/java-libs/jfreechart/target/jfreechart-1.5.4.jar"
    
    if not os.path.exists(jfreechart_classpath):
        print(f"ERROR: jfreechart JAR not found at {jfreechart_classpath}")
        return False
    
    print("Initializing TypeParseServiceWrapper with jfreechart...")
    service = TypeParseServiceWrapper(classpath=jfreechart_classpath)
    
    # Test single class - XYPlot (simpler than JFreeChart)
    print("\nParsing org.jfree.chart.plot.XYPlot...")
    xyplot_info = service.parse_type_info("org.jfree.chart.plot.XYPlot")
    
    if xyplot_info:
        print("✓ Successfully parsed XYPlot\n")
        print(xyplot_info.get_summary())
        
        print("\n" + "=" * 80)
        print("Constructor Signatures:")
        print("=" * 80)
        for ctor in xyplot_info.get_constructor_signatures():
            print(f"  {ctor}")
        
        print("\n" + "=" * 80)
        print("Inheritance Information:")
        print("=" * 80)
        print(f"Superclass: {xyplot_info.super_class_name}")
        print(f"Interfaces: {', '.join(xyplot_info.interfaces) if xyplot_info.interfaces else 'None'}")
        
        return True
    else:
        print("✗ Failed to parse XYPlot")
        return False


if __name__ == "__main__":
    success = quick_test()
    sys.exit(0 if success else 1)
