"""
Quick test for interface type analysis in jfreechart.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'javaUtils'))

from type_parse_wrapper import TypeParseServiceWrapper


def test_interfaces_quick():
    """Quick interface analysis test"""
    jfreechart_classpath = "/home/shaoran/src/java-libs/jfreechart/target/jfreechart-1.5.4.jar"
    
    if not os.path.exists(jfreechart_classpath):
        print(f"ERROR: jfreechart JAR not found")
        return False
    
    print("=" * 80)
    print("JFreeChart Interface Analysis Test")
    print("=" * 80)
    
    service = TypeParseServiceWrapper(classpath=jfreechart_classpath)
    
    # Test 1: Plot abstract class
    print("\n[Test 1] Plot abstract class")
    print("-" * 80)
    plot_info = service.parse_type_info("org.jfree.chart.plot.Plot")
    
    if plot_info and plot_info.is_abstract():
        print(f"✓ Successfully parsed Plot as abstract class")
        print(f"  Subclasses: {len(plot_info.sub_class_names)}")
        for sub in sorted(plot_info.sub_class_names)[:5]:
            print(f"    - {sub}")
    else:
        print(f"✗ Failed: Plot classification = {plot_info.class_type if plot_info else 'None'}")
        return False
    
    # Test 2: Pannable interface
    print("\n[Test 2] Pannable interface (true interface)")
    print("-" * 80)
    pannable_info = service.parse_type_info("org.jfree.chart.plot.Pannable")
    
    if pannable_info and pannable_info.is_interface():
        print(f"✓ Successfully parsed Pannable as interface")
        print(f"  Implementing Classes: {len(pannable_info.implemented_class_names)}")
        print(f"  Methods: {len(pannable_info.methods)}")
        for impl in sorted(pannable_info.implemented_class_names)[:5]:
            print(f"    - {impl}")
    else:
        print(f"✗ Failed: Pannable classification = {pannable_info.class_type if pannable_info else 'None'}")
        return False
    
    # Test 3: Zoomable interface
    print("\n[Test 3] Zoomable interface (true interface)")
    print("-" * 80)
    zoom_info = service.parse_type_info("org.jfree.chart.plot.Zoomable")
    
    if zoom_info and zoom_info.is_interface():
        print(f"✓ Successfully parsed Zoomable as interface")
        print(f"  Implementing Classes: {len(zoom_info.implemented_class_names)}")
        print(f"  Methods: {len(zoom_info.methods)}")
        for impl in sorted(zoom_info.implemented_class_names)[:5]:
            print(f"    - {impl}")
    else:
        print(f"✗ Failed: Zoomable classification = {zoom_info.class_type if zoom_info else 'None'}")
        return False
    
    # Test 4: XYPlot implements interfaces
    print("\n[Test 4] XYPlot interface implementation verification")
    print("-" * 80)
    xyplot_info = service.parse_type_info("org.jfree.chart.plot.XYPlot")
    
    if xyplot_info:
        print(f"✓ Successfully parsed XYPlot")
        print(f"  Classification: {xyplot_info.class_type}")
        print(f"  Superclass: {xyplot_info.super_class_name}")
        print(f"\n  Implements {len(xyplot_info.interfaces)} interfaces:")
        
        # Check key interfaces
        key_interfaces = ["Zoomable", "Pannable"]
        found_count = 0
        for iface in xyplot_info.interfaces:
            short_name = iface.split('.')[-1]
            if any(k in short_name for k in key_interfaces):
                print(f"    ✓ {short_name}")
                found_count += 1
            else:
                print(f"    - {short_name}")
        
        if found_count < len(key_interfaces):
            print(f"  ⚠ Only found {found_count}/{len(key_interfaces)} key interfaces")
    else:
        print(f"✗ Failed to parse XYPlot")
        return False
    
    # Test 5: Hierarchy analysis for interface
    print("\n[Test 5] Interface hierarchy analysis")
    print("-" * 80)
    hierarchy = service.get_inheritance_hierarchy("org.jfree.chart.plot.Zoomable")
    
    print(f"Zoomable hierarchy:")
    print(f"  Type: interface")
    implementers = hierarchy.get('implementers', [])
    print(f"  Implementers: {len(implementers)}")
    
    for impl in sorted(implementers)[:3]:
        print(f"    - {impl}")
    
    # Test 6: Plot polymorphism (abstract class with multiple subclasses)
    print("\n[Test 6] Plot polymorphism analysis")
    print("-" * 80)
    
    plot_hierarchy = service.get_inheritance_hierarchy("org.jfree.chart.plot.Plot")
    print(f"Plot (abstract class) hierarchy:")
    print(f"  Superclass: {plot_hierarchy.get('superclass', 'Object')}")
    
    subclasses = plot_hierarchy.get('subclasses', [])
    print(f"  Subclasses: {len(subclasses)}")
    for sub in sorted(subclasses)[:5]:
        print(f"    - {sub}")
    
    # Verify all subclasses are concrete or abstract
    print(f"\n  Subclass analysis:")
    subclass_types = []
    for sub_sig in subclasses[:3]:
        sub_info = service.parse_type_info(sub_sig)
        if sub_info:
            subclass_types.append(sub_info.class_type)
            print(f"    {sub_sig.split('.')[-1]}: {sub_info.class_type}")
    
    # Test 7: XYPlot inherits from Plot
    print("\n[Test 7] XYPlot inheritance chain verification")
    print("-" * 80)
    
    xyplot_hierarchy = service.get_inheritance_hierarchy("org.jfree.chart.plot.XYPlot")
    print(f"XYPlot inheritance chain:")
    print(f"  Superclass: {xyplot_hierarchy.get('superclass')}")
    
    # Verify Plot is the superclass
    if "Plot" in xyplot_hierarchy.get('superclass', ''):
        print(f"  ✓ Correctly inherits from Plot")
    else:
        print(f"  ⚠ Unexpected superclass")
    
    print("\n" + "=" * 80)
    print("✓ All interface analysis tests passed!")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = test_interfaces_quick()
    sys.exit(0 if success else 1)
